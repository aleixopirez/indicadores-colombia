"""
Extractor del Banco de la República (servicio web SDMX 2.1).

URL:  {BANREP_URL}/data/{AGENCIA},{FLOW_ID},{VERSION}/all/ALL/?startPeriod=...&endPeriod=...
      p. ej. .../data/ESTAT,DF_TRM_DAILY_HIST,1.0/all/ALL/?startPeriod=2023

Conceptos que se practican aquí:
  - SDMX: el estándar de intercambio de estadísticas de bancos centrales,
    Eurostat, OCDE, FMI... Aprenderlo sirve para muchas fuentes.
  - Respuestas en XML (no JSON): se recorren con xml.etree de la librería estándar.
  - Guardar el XML original además del JSONL: la capa raw debe permitir
    reconstruir exactamente lo que respondió la fuente.
  - "Sin datos" no es un error: SDMX responde 404 cuando el rango está vacío.

El parser soporta los dos formatos XML de SDMX 2.1:
  * Genérico:   <Series><SeriesKey><Value id="..." value="..."/></SeriesKey>
                  <Obs><ObsDimension value="2026-11-04"/><ObsValue value="4012.35"/></Obs>
  * Específico: <Series FREQ="D" ...><Obs TIME_PERIOD="2026-11-04" OBS_VALUE="4012.35"/>
"""
import logging
import xml.etree.ElementTree as ET
from typing import Dict, Iterator, List, Optional

import requests

from ingesta import comun, config

log = logging.getLogger("ingesta.banrep")

FUENTE = "banrep"


def _local(tag: str) -> str:
    """'{http://...namespace...}Series' -> 'Series'. Así ignoramos los namespaces."""
    return tag.rsplit("}", 1)[-1]


def _hijos(elem, nombre: str):
    return [h for h in elem if _local(h.tag) == nombre]


def _valores(elem) -> Dict[str, str]:
    """<SeriesKey>/<Attributes> genéricos: <Value id="X" value="Y"/> -> {X: Y}"""
    return {v.get("id"): v.get("value") for v in elem if _local(v.tag) == "Value"}


def parsear_sdmx(xml_bytes: bytes) -> Iterator[dict]:
    """Convierte la respuesta SDMX en filas planas SIN transformar valores
    (todo queda como texto, tal cual vino)."""
    raiz = ET.fromstring(xml_bytes)
    for serie in raiz.iter():
        if _local(serie.tag) != "Series":
            continue

        clave_bloque = _hijos(serie, "SeriesKey")
        if clave_bloque:                                   # formato genérico
            clave = _valores(clave_bloque[0])
            attrs = _hijos(serie, "Attributes")
            atributos_serie = _valores(attrs[0]) if attrs else {}
        else:                                              # formato específico
            clave, atributos_serie = dict(serie.attrib), {}

        for obs in _hijos(serie, "Obs"):
            dim, val = _hijos(obs, "ObsDimension"), _hijos(obs, "ObsValue")
            if dim or val:                                 # genérico
                attrs = _hijos(obs, "Attributes")
                fila = {
                    "TIME_PERIOD": dim[0].get("value") if dim else None,
                    "OBS_VALUE": val[0].get("value") if val else None,
                    "atributos_obs": _valores(attrs[0]) if attrs else {},
                }
            else:                                          # específico
                a = dict(obs.attrib)
                fila = {
                    "TIME_PERIOD": a.pop("TIME_PERIOD", None),
                    "OBS_VALUE": a.pop("OBS_VALUE", None),
                    "atributos_obs": a,
                }
            fila["serie"] = clave
            fila["atributos_serie"] = atributos_serie
            yield fila


def url_datos(flow_id: str) -> str:
    return (f"{config.BANREP_URL}/data/"
            f"{config.BANREP_AGENCIA},{flow_id},{config.BANREP_VERSION}/all/ALL/")


def descargar_flujo(sesion: requests.Session, flow_id: str,
                    desde: Optional[str] = None,
                    hasta: Optional[str] = None) -> Optional[bytes]:
    """Devuelve el XML crudo, o None si el servicio dice que no hay datos."""
    params = {"dimensionAtObservation": "TIME_PERIOD", "detail": "full"}
    if desde:
        params["startPeriod"] = desde
    if hasta:
        params["endPeriod"] = hasta

    resp = sesion.get(url_datos(flow_id), params=params, timeout=config.BANREP_TIMEOUT)
    if resp.status_code == 404:
        log.warning("%s: sin datos para el rango pedido (404 NoResultsFound).", flow_id)
        return None
    resp.raise_for_status()
    return resp.content


def listar_flujos(sesion: Optional[requests.Session] = None) -> List[dict]:
    """Consulta el catálogo de flujos (dataflows) que publica el servicio.
    Úsenlo para descubrir los FLOW_ID antes de agregarlos a config.py."""
    sesion = sesion or comun.crear_sesion()
    url = f"{config.BANREP_URL}/dataflow/{config.BANREP_AGENCIA}/all/latest"
    resp = sesion.get(url, timeout=config.BANREP_TIMEOUT)
    resp.raise_for_status()

    flujos = []
    for df in ET.fromstring(resp.content).iter():
        if _local(df.tag) != "Dataflow" or not df.get("id"):
            continue
        nombres = {n.get("{http://www.w3.org/XML/1998/namespace}lang", ""): (n.text or "").strip()
                   for n in df if _local(n.tag) == "Name"}
        nombre = nombres.get("es") or nombres.get("en") or next(iter(nombres.values()), "")
        flujos.append({"id": df.get("id"), "nombre": nombre})
    return sorted(flujos, key=lambda f: f["id"])


def ejecutar(desde: Optional[str] = None, hasta: Optional[str] = None,
             flujos: Optional[dict] = None,
             sesion: Optional[requests.Session] = None):
    """Descarga cada flujo, guarda el XML original y el JSONL con sobres."""
    flujos = flujos or config.FLUJOS_BANREP
    sesion = sesion or comun.crear_sesion()
    fecha_ingesta = comun.ahora_utc()

    archivos, fallidos = [], []
    for flow_id, nombre in flujos.items():
        try:
            xml = descargar_flujo(sesion, flow_id, desde, hasta)
            if xml is None:
                continue
            comun.guardar_original(xml, FUENTE, nombre, fecha_ingesta, "xml")
            registros = []
            for fila in parsear_sdmx(xml):
                clave = ".".join(v or "" for v in fila["serie"].values())
                registros.append(comun.construir_sobre(
                    FUENTE, nombre,
                    id_registro=f"{flow_id}|{clave}|{fila['TIME_PERIOD']}",
                    payload=fila, fecha_ingesta=fecha_ingesta,
                ))
        except (requests.RequestException, ET.ParseError) as e:
            log.error("Falló %s (%s): %s", flow_id, nombre, e)
            fallidos.append(flow_id)
            continue

        if not registros:
            log.warning("%s: el XML no traía observaciones.", flow_id)
            continue
        archivos.append(comun.guardar_jsonl(
            registros, FUENTE, nombre, fecha_ingesta,
            url=url_datos(flow_id),
            parametros={"flow_id": flow_id, "desde": desde, "hasta": hasta},
        ))

    if fallidos:
        raise RuntimeError(f"Flujos con error: {fallidos}")
    return archivos
