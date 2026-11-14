"""
Productor: lee los .jsonl de la zona raw y publica cada sobre en Kafka.

  data/raw/<fuente>/<dataset>/fecha_ingesta=.../*.jsonl
        │  una línea = un sobre = un mensaje
        ▼
  tópico raw.<fuente>
        key     = id_registro          (mismo dato -> misma partición, en orden)
        value   = el sobre JSON completo
        headers = dataset, fecha_ingesta

Conceptos que se practican aquí:
  - key de un mensaje y particionamiento
  - acks="all": el broker confirma antes de dar el mensaje por enviado
  - envío asíncrono + flush (lotes) vs. enviar y esperar uno por uno
  - checkpoint: un archivo .kafka_ok marca qué ya se envió, para que volver a
    ejecutar el productor no duplique mensajes (salvo que se pida --reenviar)
"""
import json
import logging
from pathlib import Path
from typing import Iterator, List, Optional

from streaming import config

log = logging.getLogger("streaming.productor")


def crear_productor():
    from kafka import KafkaProducer
    return KafkaProducer(
        bootstrap_servers=config.KAFKA_BOOTSTRAP,
        client_id="pipeline-productor",
        key_serializer=lambda k: k.encode("utf-8"),
        value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
        acks="all",                 # esperar confirmación del broker
        retries=5,
        linger_ms=50,               # agrupa mensajes en lotes de hasta 50 ms
        batch_size=64 * 1024,
        compression_type="gzip",    # gzip no necesita librerías extra en Windows
    )


def archivos_pendientes(fuente: Optional[str] = None,
                        reenviar: bool = False) -> List[Path]:
    """Lista los .jsonl de la zona raw que aún no se han enviado."""
    base = config.RAW_DIR
    fuentes = [fuente] if fuente else list(config.TOPICOS)
    archivos = []
    for f in fuentes:
        for archivo in sorted((base / f).glob("*/fecha_ingesta=*/*.jsonl")):
            marca = archivo.with_name(archivo.name + config.SUFIJO_ENVIADO)
            if reenviar or not marca.exists():
                archivos.append(archivo)
    return archivos


def leer_sobres(archivo: Path) -> Iterator[dict]:
    with archivo.open(encoding="utf-8") as f:
        for n, linea in enumerate(f, 1):
            linea = linea.strip()
            if not linea:
                continue
            try:
                yield json.loads(linea)
            except json.JSONDecodeError as e:
                # Una línea dañada no debe detener el envío del resto.
                log.warning("%s línea %d inválida, se omite: %s", archivo.name, n, e)


def enviar_archivo(productor, archivo: Path) -> int:
    """Publica todas las líneas de un archivo. Devuelve cuántas se enviaron."""
    errores = []

    def al_fallar(exc):
        errores.append(exc)

    enviados = 0
    for sobre in leer_sobres(archivo):
        topico = config.TOPICOS[sobre["fuente"]]
        productor.send(
            topico,
            key=sobre["id_registro"],
            value=sobre,
            headers=[("dataset", sobre["dataset"].encode()),
                     ("fecha_ingesta", sobre["fecha_ingesta"].encode())],
        ).add_errback(al_fallar)
        enviados += 1

    productor.flush()   # bloquea hasta que el broker confirme todo el lote
    if errores:
        raise RuntimeError(f"{archivo.name}: {len(errores)} mensajes fallaron "
                           f"(primero: {errores[0]})")

    # Solo se marca como enviado si TODO el archivo llegó.
    archivo.with_name(archivo.name + config.SUFIJO_ENVIADO).write_text(
        str(enviados), encoding="utf-8")
    return enviados


def ejecutar(fuente: Optional[str] = None, reenviar: bool = False,
             productor=None) -> dict:
    archivos = archivos_pendientes(fuente, reenviar)
    if not archivos:
        log.info("No hay archivos pendientes por enviar.")
        return {}

    propio = productor is None
    productor = productor or crear_productor()
    resumen = {}
    try:
        for archivo in archivos:
            n = enviar_archivo(productor, archivo)
            destino = archivo.relative_to(config.RAW_DIR).parts
            log.info("%s/%s: %d mensajes -> %s", destino[0], destino[1], n,
                     config.TOPICOS[destino[0]])
            resumen[str(archivo)] = n
    finally:
        if propio:
            productor.close()
    return resumen
