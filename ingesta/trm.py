"""
Extractor de la TRM diaria desde datos.gov.co (API Socrata / SODA).

Cada registro de la API se ve así:
    {"valor": "3792.98", "unidad": "COP",
     "vigenciadesde": "2020-08-05T00:00:00.000",
     "vigenciahasta": "2020-08-05T00:00:00.000"}

Conceptos que se practican aquí:
  - Paginación con $limit / $offset
  - Filtros en el servidor con $where (SoQL), para hacer cargas incrementales
  - Orden estable ($order) para que la paginación no repita ni pierda filas
"""
import logging
from typing import Iterator, Optional

import requests

from ingesta import comun, config

log = logging.getLogger("ingesta.trm")

FUENTE = "datos_gov_co"
DATASET = "trm"


def construir_where(desde: Optional[str], hasta: Optional[str]) -> Optional[str]:
    condiciones = []
    if desde:
        condiciones.append(f"vigenciadesde >= '{desde}T00:00:00'")
    if hasta:
        condiciones.append(f"vigenciadesde <= '{hasta}T23:59:59'")
    return " AND ".join(condiciones) or None


def extraer_trm(sesion: requests.Session, desde: Optional[str] = None,
                hasta: Optional[str] = None) -> Iterator[dict]:
    """Recorre todas las páginas y entrega los registros uno a uno.

    desde / hasta: fechas 'YYYY-MM-DD' (opcionales). Sin ellas trae toda la
    historia (desde 1991, ~12.000 filas).
    """
    params = {
        "$order": "vigenciadesde ASC",
        "$limit": config.TRM_TAMANO_PAGINA,
        "$offset": 0,
    }
    where = construir_where(desde, hasta)
    if where:
        params["$where"] = where

    headers = {}
    if config.SOCRATA_APP_TOKEN:
        headers["X-App-Token"] = config.SOCRATA_APP_TOKEN

    while True:
        resp = sesion.get(config.TRM_URL, params=params, headers=headers,
                          timeout=config.HTTP_TIMEOUT)
        resp.raise_for_status()
        pagina = resp.json()
        log.debug("offset=%s -> %d filas", params["$offset"], len(pagina))

        yield from pagina

        # Si la página llegó incompleta, era la última.
        if len(pagina) < config.TRM_TAMANO_PAGINA:
            break
        params["$offset"] += config.TRM_TAMANO_PAGINA


def ejecutar(desde: Optional[str] = None, hasta: Optional[str] = None,
             sesion: Optional[requests.Session] = None):
    sesion = sesion or comun.crear_sesion()
    fecha_ingesta = comun.ahora_utc()

    registros = []
    for fila in extraer_trm(sesion, desde, hasta):
        dia = fila.get("vigenciadesde", "")[:10]
        registros.append(comun.construir_sobre(
            FUENTE, DATASET, id_registro=f"trm|{dia}",
            payload=fila, fecha_ingesta=fecha_ingesta,
        ))

    if not registros:
        log.warning("TRM: la API no devolvió registros para el rango pedido.")
        return None

    return comun.guardar_jsonl(
        registros, FUENTE, DATASET, fecha_ingesta,
        url=config.TRM_URL, parametros={"desde": desde, "hasta": hasta},
    )
