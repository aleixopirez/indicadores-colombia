"""
Configuración del Paso 2 (Kafka).
"""
import os

from ingesta import config as config_ingesta

# Desde Windows (VS Code) Kafka se ve en localhost:9092.
# Desde otro contenedor (Paso 3 en adelante) sería kafka:19092.
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")

RAW_DIR = config_ingesta.RAW_DIR

# Un tópico por FUENTE. El dataset (trm, ibr, desempleo_pct...) viaja en un
# header del mensaje y dentro del sobre, así no hay que crear un tópico cada
# vez que se agrega un indicador.
TOPICOS = {
    "datos_gov_co": "raw.datos_gov_co",
    "banco_mundial": "raw.banco_mundial",
    "banrep": "raw.banrep",
}

# Configuración de cada tópico.
PARTICIONES = 3          # permite hasta 3 consumidores en paralelo por grupo
REPLICACION = 1          # un solo broker en el equipo del curso
CONFIG_TOPICO = {
    # 7 días: suficiente para que el Paso 3 (HDFS) consuma, aunque se apague
    # el equipo un fin de semana. El histórico permanente vive en HDFS.
    "retention.ms": str(7 * 24 * 60 * 60 * 1000),
    "cleanup.policy": "delete",
}

# Archivo que marca qué .jsonl ya se enviaron (para no reenviar todo cada vez).
SUFIJO_ENVIADO = ".kafka_ok"
