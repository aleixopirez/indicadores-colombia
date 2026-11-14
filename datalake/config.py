"""
Configuración del Paso 3 (HDFS).
"""
import os

from streaming import config as config_kafka

# WebHDFS del NameNode. Desde Windows: localhost:9870.
WEBHDFS_URL = os.getenv("WEBHDFS_URL", "http://localhost:9870")

# Al escribir, el NameNode responde "escribe en http://datanode:9864/...".
# Windows no conoce el nombre "datanode", así que reemplazamos esa dirección
# por la que está publicada en el equipo. Dentro de Docker se deja vacío.
DATANODE_PUBLICO = os.getenv("DATANODE_PUBLICO", "localhost:9864")

HDFS_USUARIO = os.getenv("HDFS_USUARIO", "root")
HDFS_TIMEOUT = 60

# Raíz de la zona raw dentro de HDFS. Misma estructura que data/raw local:
#   /datalake/raw/<fuente>/<dataset>/fecha_ingesta=YYYY-MM-DD/part-*.jsonl
RAIZ_RAW = "/datalake/raw"

# Kafka
KAFKA_BOOTSTRAP = config_kafka.KAFKA_BOOTSTRAP
TOPICOS = list(config_kafka.TOPICOS.values())
GRUPO_CONSUMIDOR = "hdfs-raw-writer"   # Kafka guarda hasta dónde leyó este grupo
MAX_REGISTROS_POR_LOTE = 5000
ESPERA_POLL_MS = 3000
POLLS_VACIOS_PARA_TERMINAR = 2         # en modo lote: termina al vaciar los tópicos
ESPERA_ASIGNACION_S = 60               # máximo para que Kafka asigne particiones

# Si el NameNode acaba de arrancar está en "modo seguro" (solo lectura).
REINTENTOS_MODO_SEGURO = 10
ESPERA_MODO_SEGURO_S = 6
