"""
Extractor de indicadores del Banco Mundial (API v2, sin llave).

La respuesta SIEMPRE es una lista de dos elementos:
    [ {"page":1,"pages":1,"per_page":1000,"total":36,"lastupdated":"..."},
      [ {"indicator":{"id":"FP.CPI.TOTL.ZG","value":"Inflation, ..."},
         "country":{"id":"CO","value":"Colombia"},
         "countryiso3code":"COL", "date":"2023", "value":11.74,
         "unit":"", "obs_status":"", "decimal":1}, ... ] ]

Trampa clásica: si el código del indicador está mal, la API responde
HTTP 200 (¡no un error!) con un solo elemento que trae un "message".
Por eso validamos la forma de la respuesta y no solo el código HTTP.
"""
import logging
from typing import Iterator, List, Optional

import requests

from ingesta import comun, config

log = logging.getLogger("ingesta.banco_mundial")

FUENTE = "banco_mundial"


class RespuestaInvalida(Exception):
    pass


def extraer_indicador(sesion: requests.Session, paises: List[str],
                      indicador: str, anio_desde: int,
                      anio_hasta: int) -> Iterator[dict]:
    url = f"{config.BANCO_MUNDIAL_URL}/country/{';'.join(paises)}/indicator/{indicador}"
    pagina = 1
    while True:
        params = {
            "format": "json",
            "date": f"{anio_desde}:{anio_hasta}",
            "per_page": config.BM_TAMANO_PAGINA,
            "page": pagina,
        }
        resp = sesion.get(url, params=params, timeout=config.HTTP_TIMEOUT)
        resp.raise_for_status()
        datos = resp.json()

        if not isinstance(datos, list) or len(datos) < 2 or datos[1] is None:
            mensaje = datos[0].get("message") if isinstance(datos, list) and datos else datos
            raise RespuestaInvalida(f"{indicador}: respuesta inesperada -> {mensaje}")

        meta, filas = datos
        yield from filas

        if pagina >= int(meta.get("pages", 1)):
            break
        pagina += 1


def ejecutar(anio_desde: int = config.BM_ANIO_DESDE,
             anio_hasta: Optional[int] = None,
             indicadores: Optional[dict] = None,
             paises: Optional[List[str]] = None,
             sesion: Optional[requests.Session] = None):
    """Extrae cada indicador y lo guarda en su propia carpeta (dataset)."""
    from datetime import date
    anio_hasta = anio_hasta or date.today().year
    indicadores = indicadores or config.INDICADORES_BM
    paises = paises or config.PAISES
    sesion = sesion or comun.crear_sesion()
    fecha_ingesta = comun.ahora_utc()

    archivos, fallidos = [], []
    for codigo, nombre in indicadores.items():
        try:
            registros = [
                comun.construir_sobre(
                    FUENTE, nombre,
                    id_registro=f"{codigo}|{fila.get('countryiso3code')}|{fila.get('date')}",
                    payload=fila, fecha_ingesta=fecha_ingesta,
                )
                for fila in extraer_indicador(sesion, paises, codigo, anio_desde, anio_hasta)
            ]
        except (requests.RequestException, RespuestaInvalida) as e:
            # Un indicador caído no debe tumbar a los demás.
            log.error("Falló %s (%s): %s", codigo, nombre, e)
            fallidos.append(codigo)
            continue

        archivos.append(comun.guardar_jsonl(
            registros, FUENTE, nombre, fecha_ingesta,
            url=f"{config.BANCO_MUNDIAL_URL}/country/{';'.join(paises)}/indicator/{codigo}",
            parametros={"indicador": codigo, "paises": paises,
                        "anio_desde": anio_desde, "anio_hasta": anio_hasta},
        ))

    if fallidos:
        # Que la ejecución termine en error para que Airflow lo marque (Paso 6).
        raise RuntimeError(f"Indicadores con error: {fallidos}")
    return archivos
