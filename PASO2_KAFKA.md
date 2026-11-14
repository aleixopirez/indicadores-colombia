# Paso 2 — Kafka: de la zona raw a un flujo de mensajes

```
data/raw/*.jsonl ──► (2) PRODUCTOR ──► Kafka [raw.datos_gov_co | raw.banco_mundial | raw.banrep] ──► (3) consumidor → HDFS
                       ▲ este paso
```

## Objetivo

Desacoplar la **extracción** del **almacenamiento**. Los extractores del Paso 1
no saben que existe HDFS; solo dejan archivos. El productor los convierte en
mensajes, y cualquier sistema (HDFS, una alerta, un dashboard en vivo) puede
leerlos sin tocar el código de la ingesta.

## Requisitos

- Docker Desktop corriendo (*Engine running*).
- Paso 1 ejecutado: debe haber archivos en `data/raw/`.
- `uv pip install -r requirements.txt` (agrega `kafka-python`).

## Ejecución

```powershell
# 1. Encender Kafka (solo Kafka, ~700 MB de RAM)
docker compose --profile kafka up -d
docker compose ps                      # esperar a que diga "healthy"

# 2. Crear los tópicos
python -m streaming crear-topicos

# 3. Publicar todo lo pendiente de data/raw
python -m streaming producir

# 4. Ver qué llegó
python -m streaming consumir raw.banrep --max 3
python -m streaming consumir raw.banco_mundial --max 3

# 5. Apagar al terminar (los mensajes se conservan en el volumen kafka-data)
docker compose --profile kafka down
```

Interfaz web opcional (usa ~500 MB más): `docker compose --profile kafka-ui up -d`
y abrir <http://localhost:8080>.

## Estructura

```
docker-compose.yml     # Kafka 4.1 (KRaft) + Kafka UI, por perfiles
streaming/
  config.py            # bootstrap, tópicos, particiones, retención
  topicos.py           # crea los tópicos con KafkaAdminClient
  productor.py         # .jsonl -> mensajes (key = id_registro)
  consumidor.py        # consumidor de prueba para la terminal
  __main__.py          # línea de comandos
tests/test_streaming.py  # 7 pruebas sin Kafka real
```

## Decisiones de diseño (para discutir en clase)

1. **KRaft, sin Zookeeper.** Desde Kafka 4.0 Zookeeper ya no existe: un solo
   contenedor es broker y controller. Menos memoria, menos piezas.
2. **Un tópico por fuente, no por indicador.** `raw.banco_mundial` lleva los 7
   indicadores; el dataset viaja en un *header* y dentro del sobre. Agregar un
   indicador no obliga a crear tópicos.
3. **key = `id_registro`.** Mensajes con la misma key van a la misma partición
   y conservan su orden. Si un dato se re-extrae, sus versiones quedan juntas.
4. **3 particiones.** Permite hasta 3 consumidores en paralelo dentro de un
   mismo grupo. Con 1 partición, el paralelismo sería imposible.
5. **Replicación 1.** Solo hay un broker. En producción serían 3 brokers y
   replicación 3: si uno cae, no se pierden datos.
6. **Retención de 7 días.** Kafka no es el almacenamiento definitivo; es el
   amortiguador. El histórico permanente vive en HDFS (Paso 3).
7. **`acks="all"` + `flush()`.** El productor espera la confirmación del
   broker antes de dar un archivo por enviado.
8. **Checkpoint `.kafka_ok`.** Volver a ejecutar el productor no duplica
   mensajes. `--reenviar` existe para cuando sí se quiere repetir.
9. **Tópicos explícitos** (`auto.create.topics.enable=false`). Un error de
   tipeo en el nombre del tópico falla en vez de crear uno nuevo en silencio.
10. **Dos listeners.** `localhost:9092` para Python en Windows y
    `kafka:19092` para otros contenedores. Es el error más común al montar
    Kafka en Docker.

## Preguntas de control

- ¿Cuántos mensajes tiene cada tópico? ¿Coincide con las líneas de los `.jsonl`?
- Ejecuta `consumir` dos veces con `--grupo clase`. ¿Por qué la segunda vez
  no muestra nada? ¿Y sin `--grupo`?
- Apaga Kafka, ejecuta `producir`, y revisa: ¿se creó el `.kafka_ok`? ¿Por qué no?
- Ejecuta la ingesta del Paso 1 otra vez y luego `producir`. ¿Qué se envía?

## Siguiente paso

**Paso 3 — HDFS:** un consumidor que lea los tópicos `raw.*` y escriba los
mensajes en HDFS, particionados por fuente, dataset y fecha de ingesta.
