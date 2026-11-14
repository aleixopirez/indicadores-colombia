"""
Creación de tópicos con KafkaAdminClient.

Se crean de forma explícita (el broker tiene auto.create.topics.enable=false)
para que particiones, replicación y retención sean decisiones de diseño, no
valores por defecto.
"""
import logging

from kafka import KafkaAdminClient
from kafka.admin import NewTopic
from kafka.errors import TopicAlreadyExistsError

from streaming import config

log = logging.getLogger("streaming.topicos")


def crear_topicos(admin=None) -> dict:
    """Crea los tópicos que falten. Devuelve {topico: 'creado' | 'ya existía'}."""
    propio = admin is None
    admin = admin or KafkaAdminClient(bootstrap_servers=config.KAFKA_BOOTSTRAP,
                                      client_id="pipeline-admin")
    try:
        existentes = set(admin.list_topics())
        resultado = {}
        nuevos = []
        for topico in config.TOPICOS.values():
            if topico in existentes:
                resultado[topico] = "ya existía"
            else:
                nuevos.append(NewTopic(name=topico,
                                       num_partitions=config.PARTICIONES,
                                       replication_factor=config.REPLICACION,
                                       topic_configs=config.CONFIG_TOPICO))
        if nuevos:
            try:
                admin.create_topics(nuevos)
            except TopicAlreadyExistsError:
                pass  # otro proceso los creó entre list_topics y create_topics
            for t in nuevos:
                resultado[t.name] = "creado"
        for topico, estado in resultado.items():
            log.info("%-22s %s", topico, estado)
        return resultado
    finally:
        if propio:
            admin.close()
