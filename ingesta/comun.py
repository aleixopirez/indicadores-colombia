"""
Utilidades compartidas por todos los extractores:
  - sesión HTTP con reintentos
  - "sobre" (envelope) estándar para cada registro
  - escritura en la zona raw como JSON Lines + manifiesto de la ejecución
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ingesta import config

log = logging.getLogger("ingesta")


def crear_sesion() -> requests.Session:
    """Sesión HTTP que reintenta automáticamente con espera exponencial
    (1s, 2s, 4s, ...) cuando la API responde 429 o 5xx, o falla la red."""
    reintentos = Retry(
        total=config.HTTP_REINTENTOS,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True,
    )
    sesion = requests.Session()
    sesion.mount("https://", HTTPAdapter(max_retries=reintentos))
    sesion.headers.update({"User-Agent": config.USER_AGENT})
    return sesion


def ahora_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def construir_sobre(fuente: str, dataset: str, id_registro: str,
                    payload: dict, fecha_ingesta: str) -> dict:
    """Envuelve el registro original SIN modificarlo.

    - id_registro: llave natural del dato. En el Paso 2 será la *key* del
      mensaje en Kafka; así un mismo dato re-extraído se reconoce como el mismo.
    - payload: el JSON exacto que devolvió la API (capa raw = sin limpiar).
    """
    return {
        "fuente": fuente,
        "dataset": dataset,
        "id_registro": id_registro,
        "fecha_ingesta": fecha_ingesta,
        "payload": payload,
    }


def ruta_particion(fuente: str, dataset: str, fecha_ingesta: str) -> Path:
    """data/raw/<fuente>/<dataset>/fecha_ingesta=YYYY-MM-DD/
    El formato clave=valor es el que Hive y Spark reconocen como partición."""
    dia = fecha_ingesta[:10]
    return config.RAW_DIR / fuente / dataset / f"fecha_ingesta={dia}"


def guardar_original(contenido: bytes, fuente: str, dataset: str,
                     fecha_ingesta: str, extension: str) -> Path:
    """Guarda la respuesta tal cual llegó (XML, CSV...), byte por byte.
    Útil cuando la fuente no es JSON: si el parser tenía un error, se puede
    re-procesar sin volver a llamar a la API."""
    carpeta = ruta_particion(fuente, dataset, fecha_ingesta)
    carpeta.mkdir(parents=True, exist_ok=True)
    marca = fecha_ingesta.replace(":", "").replace("-", "")
    archivo = carpeta / f"{dataset}_{marca}_original.{extension}"
    archivo.write_bytes(contenido)
    return archivo


def guardar_jsonl(registros: list, fuente: str, dataset: str,
                  fecha_ingesta: str, url: str, parametros: dict) -> Path:
    """Escribe un archivo .jsonl (un registro por línea) y su manifiesto."""
    carpeta = ruta_particion(fuente, dataset, fecha_ingesta)
    carpeta.mkdir(parents=True, exist_ok=True)

    marca = fecha_ingesta.replace(":", "").replace("-", "")
    archivo = carpeta / f"{dataset}_{marca}.jsonl"

    with archivo.open("w", encoding="utf-8") as f:
        for r in registros:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    manifiesto = {
        "fuente": fuente,
        "dataset": dataset,
        "fecha_ingesta": fecha_ingesta,
        "url": url,
        "parametros": parametros,
        "registros": len(registros),
        "archivo": archivo.name,
    }
    (carpeta / f"_manifiesto_{marca}.json").write_text(
        json.dumps(manifiesto, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    log.info("%s/%s: %d registros -> %s", fuente, dataset, len(registros), archivo)
    return archivo
