"""
Consumidor de prueba: muestra en la terminal los mensajes de un tópico.

Sirve para comprobar que el productor funcionó. El consumidor "de verdad"
(el que escribe en HDFS) llega en el Paso 3.
"""
import json
import logging
from collections import Counter
from typing import Optional

from streaming import config

log = logging.getLogger("streaming.consumidor")


def crear_consumidor(topico: str, grupo: Optional[str], desde_inicio: bool):
    from kafka import KafkaConsumer
    return KafkaConsumer(
        topico,
        bootstrap_servers=config.KAFKA_BOOTSTRAP,
        group_id=grupo,                      # None = no guarda posición (offsets)
        auto_offset_reset="earliest" if desde_inicio else "latest",
        enable_auto_commit=grupo is not None,
        consumer_timeout_ms=5000,            # termina tras 5 s sin mensajes
        key_deserializer=lambda k: k.decode("utf-8") if k else None,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
    )


def ejecutar(topico: str, maximo: int = 5, desde_inicio: bool = True,
             grupo: Optional[str] = None, consumidor=None) -> Counter:
    """Imprime los primeros `maximo` mensajes y cuenta todos por dataset."""
    propio = consumidor is None
    consumidor = consumidor or crear_consumidor(topico, grupo, desde_inicio)
    por_dataset = Counter()
    try:
        for i, msg in enumerate(consumidor):
            por_dataset[msg.value.get("dataset", "?")] += 1
            if i < maximo:
                print(f"[partición {msg.partition} | offset {msg.offset}] "
                      f"key={msg.key}")
                print(f"    payload={json.dumps(msg.value['payload'], ensure_ascii=False)[:160]}")
    finally:
        if propio:
            consumidor.close()

    total = sum(por_dataset.values())
    print(f"\nTotal leído de {topico}: {total} mensajes")
    for dataset, n in sorted(por_dataset.items()):
        print(f"  {dataset:<28} {n:>8}")
    return por_dataset
