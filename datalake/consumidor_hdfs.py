"""
Consumidor Kafka -> HDFS: lleva los mensajes de los tópicos raw.* al data lake.

  Kafka raw.<fuente>  ──poll (lote)──►  agrupar por fuente/dataset/fecha_ingesta
                                              │
                                              ▼
  HDFS /datalake/raw/<fuente>/<dataset>/fecha_ingesta=YYYY-MM-DD/
          part-<tópico>-p<partición>-o<offset inicial>.jsonl
                                              │
                         solo después de escribir ▼
                                   commit de offsets en Kafka

Conceptos que se practican aquí:
  - Grupo de consumidores: Kafka recuerda hasta dónde leyó "hdfs-raw-writer".
    Si el proceso se detiene, al volver sigue donde iba.
  - Commit MANUAL después de escribir (at-least-once): si el programa falla
    entre escribir y hacer commit, el lote se vuelve a leer...
  - ...pero el nombre del archivo depende del offset inicial, así que re-escribir
    el mismo lote SOBRESCRIBE el mismo archivo en vez de duplicar datos.
    Escritura idempotente.
  - Archivos por lote, no un archivo por mensaje: HDFS sufre con millones de
    archivos pequeños (cada uno ocupa memoria en el NameNode).
"""
import json
import logging
import time
from collections import defaultdict
from typing import Dict, Optional, Tuple

from datalake import config
from datalake.webhdfs import WebHDFS

log = logging.getLogger("datalake.consumidor")


def crear_consumidor():
    from kafka import KafkaConsumer
    return KafkaConsumer(
        *config.TOPICOS,
        bootstrap_servers=config.KAFKA_BOOTSTRAP,
        group_id=config.GRUPO_CONSUMIDOR,
        client_id="hdfs-raw-writer",
        enable_auto_commit=False,          # commit solo cuando HDFS confirmó
        auto_offset_reset="earliest",      # primera vez: desde el inicio
        max_poll_records=config.MAX_REGISTROS_POR_LOTE,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    )


def ruta_destino(topico: str, particion: int, offset_inicial: int,
                 fuente: str, dataset: str, fecha_ingesta: str) -> str:
    dia = fecha_ingesta[:10]
    return (f"{config.RAIZ_RAW}/{fuente}/{dataset}/fecha_ingesta={dia}/"
            f"part-{topico}-p{particion}-o{offset_inicial:012d}.jsonl")


def agrupar_lote(lote: dict) -> Dict[str, list]:
    """{TopicPartition: [mensajes]} -> {ruta_hdfs: [sobres]} conservando el orden."""
    grupos: Dict[Tuple, list] = defaultdict(list)
    primer_offset: Dict[Tuple, int] = {}
    for tp, mensajes in lote.items():
        for m in mensajes:
            sobre = m.value
            clave = (tp.topic, tp.partition, sobre["fuente"], sobre["dataset"],
                     sobre["fecha_ingesta"][:10])
            primer_offset.setdefault(clave, m.offset)
            grupos[clave].append(sobre)

    archivos = {}
    for clave, sobres in grupos.items():
        topico, particion, fuente, dataset, dia = clave
        ruta = ruta_destino(topico, particion, primer_offset[clave], fuente, dataset, dia)
        archivos[ruta] = sobres
    return archivos


def escribir_lote(hdfs: WebHDFS, archivos: Dict[str, list]) -> int:
    total = 0
    for ruta, sobres in archivos.items():
        contenido = "".join(json.dumps(s, ensure_ascii=False) + "\n" for s in sobres)
        hdfs.mkdirs(ruta.rsplit("/", 1)[0])
        hdfs.escribir(ruta, contenido.encode("utf-8"), sobrescribir=True)
        log.debug("%s: %d registros", ruta, len(sobres))
        total += len(sobres)
    return total


def ejecutar(continuo: bool = False, consumidor=None,
             hdfs: Optional[WebHDFS] = None) -> dict:
    """Consume hasta vaciar los tópicos (modo lote, el que usará Airflow)
    o indefinidamente (continuo=True)."""
    propio = consumidor is None
    consumidor = consumidor or crear_consumidor()
    hdfs = hdfs or WebHDFS()
    hdfs.mkdirs(config.RAIZ_RAW)

    resumen = {"mensajes": 0, "archivos": 0, "lotes": 0}
    vacios = 0
    inicio = time.monotonic()
    asignado = False
    try:
        while True:
            lote = consumidor.poll(timeout_ms=config.ESPERA_POLL_MS,
                                   max_records=config.MAX_REGISTROS_POR_LOTE)

            # Al unirse a un grupo, Kafka tarda unos segundos en asignar las
            # particiones (rebalance). Mientras tanto, poll() devuelve vacío:
            # eso NO significa que los tópicos estén vacíos.
            if not asignado:
                particiones = consumidor.assignment()
                if particiones:
                    asignado = True
                    log.info("Grupo '%s': %d particiones asignadas",
                             config.GRUPO_CONSUMIDOR, len(particiones))
                elif time.monotonic() - inicio > config.ESPERA_ASIGNACION_S:
                    raise RuntimeError(
                        f"Kafka no asignó particiones en {config.ESPERA_ASIGNACION_S}s. "
                        f"¿Existen los tópicos? python -m streaming crear-topicos")
                else:
                    continue

            if not lote:
                vacios += 1
                if not continuo and vacios >= config.POLLS_VACIOS_PARA_TERMINAR:
                    break
                continue
            vacios = 0

            archivos = agrupar_lote(lote)
            n = escribir_lote(hdfs, archivos)   # si falla, NO hay commit
            consumidor.commit()

            resumen["mensajes"] += n
            resumen["archivos"] += len(archivos)
            resumen["lotes"] += 1
            log.info("Lote %d: %d mensajes -> %d archivos en HDFS",
                     resumen["lotes"], n, len(archivos))
    finally:
        if propio:
            consumidor.close()

    log.info("Total: %d mensajes en %d archivos (%d lotes)",
             resumen["mensajes"], resumen["archivos"], resumen["lotes"])
    return resumen
