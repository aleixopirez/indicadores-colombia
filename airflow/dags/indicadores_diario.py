"""
### Indicadores económicos de Colombia · actualización diaria (Paso 8)

Recorre el pipeline completo, igual que `actualizar.ps1`, pero programado:

1. **Ingesta** desde las fuentes (las tres en paralelo).
2. **Kafka**: publica los archivos nuevos de la zona raw.
3. **HDFS**: el consumidor los escribe en el data lake.
4. **PySpark**: cura los datos (elimina repetidos y valida).
5. **PostgreSQL**: carga la zona de servicio (Power BI la lee de aquí).
6. **HTML**: genera el dashboard con Plotly.
7. **GitHub Pages**: lo publica.

Kafka y HDFS se encienden solo mientras se usan, para no pasar los 8 GB de RAM.
Las tareas que los apagan corren **siempre**, aunque algo falle antes.
"""
from datetime import timedelta

import pendulum
from airflow.sdk import dag, task
from airflow.sdk.exceptions import AirflowSkipException

DIAS_ATRAS = 45                  # ventana de la ingesta diaria (los repetidos se eliminan en Spark)
ANIOS_BANCO_MUNDIAL = 5          # el Banco Mundial corrige cifras de años recientes

ZONA = "America/Bogota"
SPARK = "spark-tareas"           # contenedor de Spark que queda encendido (en reposo)
SPARK_SUBMIT = ["/opt/spark/bin/spark-submit", "--master", "local[2]", "--driver-memory", "1g"]


def _fecha(logical_date):
    """Fecha de la ejecución. En ejecuciones manuales Airflow 3 puede no
    tener logical_date: entonces se usa la fecha de hoy."""
    fecha = pendulum.instance(logical_date) if logical_date else pendulum.now(ZONA)
    return fecha.in_timezone(ZONA)


@dag(
    dag_id="indicadores_diario",
    description="Ingesta → Kafka → HDFS → PySpark → PostgreSQL → dashboard HTML → GitHub Pages",
    schedule="0 7 * * *",                                   # todos los días a las 7:00 a. m.
    start_date=pendulum.datetime(2026, 11, 1, tz=ZONA),
    catchup=False,                  # si el PC estuvo apagado, no repite los días perdidos
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=5)},
    tags=["indicadores", "curso"],
    doc_md=__doc__,
)
def indicadores_diario():

    # ------------------------------------------------------------- 1. Ingesta
    @task
    def ingesta_trm(logical_date=None):
        from ingesta import trm
        desde = _fecha(logical_date).subtract(days=DIAS_ATRAS).to_date_string()
        archivo = trm.ejecutar(desde=desde)
        return str(archivo) if archivo else None

    @task
    def ingesta_banrep(logical_date=None):
        from ingesta import banrep
        desde = _fecha(logical_date).subtract(days=DIAS_ATRAS).to_date_string()
        return [str(a) for a in (banrep.ejecutar(desde=desde) or [])]

    @task(retries=1, retry_delay=timedelta(minutes=10))
    def ingesta_banco_mundial(logical_date=None):
        """Datos anuales: si la API del Banco Mundial está caída, se sigue
        con lo que ya hay en el data lake (no detiene el resto)."""
        from ingesta import banco_mundial
        try:
            archivos = banco_mundial.ejecutar(anio_desde=_fecha(logical_date).year - ANIOS_BANCO_MUNDIAL)
            return [str(a) for a in archivos]
        except RuntimeError as e:
            raise AirflowSkipException(f"Banco Mundial sin actualizar: {e}")

    # ---------------------------------------------------- 2-3. Kafka y HDFS
    @task(trigger_rule="none_failed")      # sigue aunque el Banco Mundial se haya saltado
    def encender_kafka_hdfs():
        from orquestacion import contenedores
        contenedores.encender(["kafka", "namenode", "datanode"])

    @task
    def kafka_producir():
        from streaming import productor, topicos
        topicos.crear_topicos()           # no hace nada si ya existen
        enviados = productor.ejecutar()   # {archivo: mensajes}
        return {"archivos": len(enviados), "mensajes": sum(enviados.values())}

    @task
    def hdfs_consumir():
        from datalake import consumidor_hdfs
        return consumidor_hdfs.ejecutar()

    @task(trigger_rule="all_done")         # se apaga aunque algo haya fallado
    def apagar_kafka():
        from orquestacion import contenedores
        contenedores.apagar(["kafka"])

    # ------------------------------------------------------------ 4. PySpark
    @task
    def spark_curar():
        from orquestacion import contenedores
        contenedores.encender(["namenode", "datanode"])
        contenedores.ejecutar(SPARK, SPARK_SUBMIT + [
            "--conf", "spark.hadoop.dfs.replication=1",
            "procesamiento/curar.py"], directorio="/proyecto")

    # --------------------------------------------------------- 5. PostgreSQL
    @task
    def spark_servir():
        from orquestacion import contenedores
        contenedores.ejecutar(SPARK, SPARK_SUBMIT + [
            "--packages", "org.postgresql:postgresql:42.7.4",
            "--conf", "spark.jars.ivy=/tmp/.ivy2",
            "procesamiento/servir.py"], directorio="/proyecto")

    @task(trigger_rule="all_done")
    def apagar_hdfs():
        from orquestacion import contenedores
        contenedores.apagar(["namenode", "datanode"])

    # -------------------------------------------------------------- 6. HTML
    @task
    def generar_dashboard():
        from visualizacion.generar import generar
        return [str(r) for r in generar("postgres")]

    # ------------------------------------------------------- 7. GitHub Pages
    @task(retries=3)
    def publicar_github(logical_date=None):
        import os
        from pathlib import Path
        from orquestacion import github
        from visualizacion import config
        token = os.getenv("GITHUB_TOKEN")
        if not token:
            raise AirflowSkipException("Sin GITHUB_TOKEN en .env: el dashboard se generó pero no se publicó.")
        return github.publicar_archivo(
            Path(config.SALIDA) / "dashboard.html",
            repo=os.getenv("GITHUB_REPO", "aleixopirez/indicadores-colombia"),
            ruta_repo="docs/index.html", token=token,
            mensaje=f"Actualiza dashboard ({_fecha(logical_date).to_date_string()}) [Airflow]")

    # ------------------------------------------------------------ el flujo
    encendido = encender_kafka_hdfs()
    [ingesta_trm(), ingesta_banrep(), ingesta_banco_mundial()] >> encendido
    consumido = encendido >> kafka_producir() >> hdfs_consumir()
    consumido >> apagar_kafka()
    servido = consumido >> spark_curar() >> spark_servir()
    servido >> apagar_hdfs()
    servido >> generar_dashboard() >> publicar_github()


indicadores_diario()
