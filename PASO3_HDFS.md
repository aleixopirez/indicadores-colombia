# Paso 3 — HDFS: el data lake

```
Kafka raw.* ──► (3) CONSUMIDOR ──► HDFS /datalake/raw/<fuente>/<dataset>/fecha_ingesta=.../part-*.jsonl
                   ▲ este paso                         (luego lo leen PySpark y Hive)
```

## Objetivo

Guardar de forma **permanente y distribuida** todo lo que pasa por Kafka.
Kafka retiene 7 días; HDFS guarda la historia completa con la que PySpark
(Paso 4) y Hive (Paso 5) van a trabajar.

## Requisitos

- Paso 2 funcionando (tópicos `raw.*` con mensajes).
- RAM: Kafka + HDFS usan ~2,2 GB. Cierra Power BI y pestañas que no uses.
- La primera vez se descarga `apache/hadoop:3.4.1` (~1,1 GB).

## Ejecución

```powershell
# 1. Encender Kafka + HDFS
docker compose --profile kafka --profile hdfs up -d
docker compose ps        # esperar namenode (healthy); tarda ~1 minuto

# 2. Ver HDFS en el navegador: http://localhost:9870
#    Datanodes -> debe aparecer 1 nodo "In service"

# 3. Pasar todo de Kafka a HDFS
python -m datalake consumir

# 4. Revisar
python -m datalake resumen
python -m datalake ls /datalake/raw/banrep/ibr
python -m datalake cat <ruta de un part-*.jsonl> --lineas 2

# 5. Apagar
docker compose --profile kafka --profile hdfs down
```

En la interfaz web: *Utilities → Browse the file system → /datalake/raw*.

## Estructura

```
hadoop.env                 # configuración de HDFS (replicación, bloques, WebHDFS)
docker-compose.yml         # perfiles kafka + hdfs (namenode, datanode)
datalake/
  config.py                # URL de WebHDFS, raíz del lake, grupo de Kafka
  webhdfs.py               # cliente REST de HDFS (sin Java en Windows)
  consumidor_hdfs.py       # Kafka -> HDFS con commit manual
  __main__.py              # consumir, ls, resumen, cat
tests/test_datalake.py     # 11 pruebas sin HDFS ni Kafka reales
```

## Decisiones de diseño (para discutir en clase)

1. **NameNode y DataNode.** El NameNode guarda *dónde* está cada bloque
   (metadatos); los DataNodes guardan los bytes. Por eso escribir es en dos
   pasos: primero se le pregunta al NameNode, luego se envían los datos al
   DataNode que indicó.
2. **WebHDFS en vez de cliente nativo.** Desde Windows evita instalar Java,
   Hadoop y winutils. Spark y Hive (pasos 4 y 5) sí usarán el protocolo
   nativo por el puerto 8020.
3. **Traducción `datanode` → `localhost`.** El NameNode indica el DataNode con
   su nombre dentro de Docker, que Windows no resuelve. El cliente pide la
   dirección sin redirección (`noredirect=true`) y la traduce.
4. **Replicación 1, bloques de 32 MB.** Un solo DataNode. En un clúster real
   serían 3 réplicas y 128 MB.
5. **Misma estructura que `data/raw` local:** `fuente/dataset/fecha_ingesta=`.
   Las particiones `clave=valor` las reconocen Spark y Hive sin configuración.
6. **Un archivo por lote, no por mensaje.** Cada archivo, por pequeño que sea,
   ocupa memoria en el NameNode: millones de archivos pequeños son el
   problema clásico de HDFS.
7. **Commit manual, después de escribir.** Si HDFS falla, Kafka no avanza y
   el lote se vuelve a entregar (*at-least-once*).
8. **Escritura idempotente.** El nombre del archivo lleva el offset inicial
   del lote. Si el mismo lote se procesa dos veces, se sobrescribe el mismo
   archivo en vez de duplicar datos.
9. **Modo lote por defecto.** `consumir` termina cuando los tópicos quedan
   vacíos: es lo que necesita Airflow para encadenar la siguiente tarea.
   `--continuo` lo deja escuchando como un servicio.
10. **Esperar el rebalance antes de concluir "no hay datos".** Al unirse un
    consumidor a un grupo nuevo, Kafka tarda unos segundos en asignarle
    particiones y mientras tanto `poll()` devuelve vacío. La primera versión
    de este consumidor terminó con "0 mensajes" por confundir las dos cosas;
    ahora solo cuenta respuestas vacías cuando ya tiene particiones asignadas.

## Preguntas de control

- ¿Cuántos registros tiene HDFS para `banrep/ibr`? ¿Coincide con Kafka?
  ¿Por qué hay duplicados y en qué paso se eliminan?
- Ejecuta `python -m datalake consumir` dos veces. ¿Qué hace la segunda?
  ¿Dónde guarda Kafka esa información?
- En la interfaz web, abre un archivo y mira *Block information*:
  ¿en cuántos bloques está y en qué DataNode?
- Apaga el DataNode (`docker stop datanode`) e intenta leer un archivo.
  ¿Qué pasaría con replicación 3 y tres DataNodes?

## Siguiente paso

**Paso 4 — PySpark:** leer `/datalake/raw`, limpiar (fechas, tipos,
duplicados por `id_registro`) y escribir la zona *curada* en formato Parquet.
