"""
Transformaciones de la zona raw a la zona curada.

Cada función recibe y devuelve un DataFrame, sin leer ni escribir archivos:
así se pueden probar con datos pequeños (tests/test_procesamiento.py).

Flujo:
    texto JSONL ─► leer_sobres ─► deduplicar ─┬─► normalizar_trm_gov ────────┐
                                              ├─► normalizar_banco_mundial ──┼─► unión ─► zona curada
                                              └─► normalizar_banrep ─────────┘

Esquema de la zona curada (igual para todas las fuentes):
    indicador, pais, pais_nombre, fecha, anio, frecuencia, valor, unidad,
    fuente, dataset, id_registro, fecha_ingesta

Nota sobre Spark 4: el modo ANSI viene activado. Convertir "abc" a número o
"2026-13-45" a fecha detiene TODO el trabajo con un error. Por eso se usan
try_cast y try_to_timestamp: devuelven null y el reporte de calidad lo cuenta.
"""
from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F
from pyspark.sql import types as T

from procesamiento import catalogo

COLUMNAS_CURADAS = ["indicador", "pais", "pais_nombre", "fecha", "anio",
                    "frecuencia", "valor", "unidad", "fuente", "dataset",
                    "id_registro", "fecha_ingesta"]

# El payload se lee como TEXTO: cada fuente tiene una estructura distinta y
# se interpreta después, con el esquema propio de cada una.
ESQUEMA_SOBRE = T.StructType([
    T.StructField("fuente", T.StringType()),
    T.StructField("dataset", T.StringType()),
    T.StructField("id_registro", T.StringType()),
    T.StructField("fecha_ingesta", T.StringType()),
    T.StructField("payload", T.StringType()),
])

ESQUEMA_TRM_GOV = T.StructType([
    T.StructField("valor", T.StringType()),
    T.StructField("unidad", T.StringType()),
    T.StructField("vigenciadesde", T.StringType()),
    T.StructField("vigenciahasta", T.StringType()),
])

ESQUEMA_BANCO_MUNDIAL = T.StructType([
    T.StructField("countryiso3code", T.StringType()),
    T.StructField("country", T.StructType([T.StructField("value", T.StringType())])),
    T.StructField("date", T.StringType()),
    T.StructField("value", T.DoubleType()),
])

ESQUEMA_BANREP = T.StructType([
    T.StructField("TIME_PERIOD", T.StringType()),
    T.StructField("OBS_VALUE", T.StringType()),
    T.StructField("serie", T.MapType(T.StringType(), T.StringType())),
])


# ----------------------------------------------------------------- lectura
def leer_sobres(lineas: DataFrame) -> DataFrame:
    """DataFrame de texto (columna `value`, una línea JSONL por fila) ->
    columnas del sobre. Las líneas que no son JSON válido quedan con
    fuente = null y se descartan."""
    return (lineas
            .select(F.from_json("value", ESQUEMA_SOBRE).alias("s"))
            .select("s.*")
            .where(F.col("fuente").isNotNull())
            .withColumn("fecha_ingesta",
                        F.to_timestamp("fecha_ingesta", "yyyy-MM-dd'T'HH:mm:ssX")))


def deduplicar(sobres: DataFrame) -> DataFrame:
    """Un registro por id_registro: el de la ingesta más reciente.

    Los duplicados vienen de ejecutar la extracción más de una vez (en
    nuestro caso el IBR y la TRM del Banco). Window + row_number es el
    patrón estándar: numera las versiones de cada id de la más nueva a la
    más vieja y se queda con la número 1."""
    ventana = Window.partitionBy("id_registro").orderBy(F.col("fecha_ingesta").desc())
    return (sobres
            .withColumn("_version", F.row_number().over(ventana))
            .where("_version = 1")
            .drop("_version"))


# ------------------------------------------------------------ normalización
def normalizar_trm_gov(sobres: DataFrame) -> DataFrame:
    """TRM de datos.gov.co. Un registro cubre un RANGO de fechas
    (vigenciadesde..vigenciahasta): la TRM del viernes rige sábado, domingo y
    lunes festivo. Se expande a una fila por día con sequence + explode, para
    que todas las series diarias tengan el mismo grano."""
    p = F.from_json("payload", ESQUEMA_TRM_GOV)
    desde = F.to_date(F.expr("try_to_timestamp(p.vigenciadesde, \"yyyy-MM-dd'T'HH:mm:ss.SSS\")"))
    hasta = F.to_date(F.expr("try_to_timestamp(p.vigenciahasta, \"yyyy-MM-dd'T'HH:mm:ss.SSS\")"))
    return (sobres
            .where(F.col("fuente") == "datos_gov_co")
            .withColumn("p", p)
            .withColumn("fecha", F.explode(F.sequence(desde, F.coalesce(hasta, desde))))
            .select(
                F.lit(catalogo.TRM_GOV["indicador"]).alias("indicador"),
                F.lit(catalogo.PAIS_COLOMBIA[0]).alias("pais"),
                F.lit(catalogo.PAIS_COLOMBIA[1]).alias("pais_nombre"),
                "fecha",
                F.lit("diaria").alias("frecuencia"),
                F.expr("try_cast(p.valor AS DOUBLE)").alias("valor"),
                F.lit(catalogo.TRM_GOV["unidad"]).alias("unidad"),
                "fuente", "dataset", "id_registro", "fecha_ingesta"))


def normalizar_banco_mundial(sobres: DataFrame) -> DataFrame:
    """Indicadores anuales. El valor de un año se fecha al 31 de diciembre
    (cierre del período): así se cruza bien con series diarias."""
    spark = sobres.sparkSession
    unidades = spark.createDataFrame(
        list(catalogo.BANCO_MUNDIAL.items()), ["dataset", "unidad"])
    p = F.from_json("payload", ESQUEMA_BANCO_MUNDIAL)
    anio = F.expr("try_cast(p.date AS INT)")
    return (sobres
            .where(F.col("fuente") == "banco_mundial")
            .withColumn("p", p)
            .join(F.broadcast(unidades), "dataset", "left")
            .select(
                F.col("dataset").alias("indicador"),
                F.col("p.countryiso3code").alias("pais"),
                F.col("p.country.value").alias("pais_nombre"),
                F.make_date(anio, F.lit(12), F.lit(31)).alias("fecha"),
                F.lit("anual").alias("frecuencia"),
                F.col("p.value").alias("valor"),
                F.coalesce("unidad", F.lit("sin catálogo")).alias("unidad"),
                "fuente", "dataset", "id_registro", "fecha_ingesta"))


def normalizar_banrep(sobres: DataFrame) -> DataFrame:
    """Series SDMX del Banco de la República. Cada dataset puede traer varias
    series (el IBR trae 8); el catálogo las separa por SUBJECT y UNIT_MEASURE.
    El cruce con el catálogo es un broadcast join: la tabla pequeña se copia a
    cada nodo en vez de redistribuir la grande."""
    spark = sobres.sparkSession
    cat = spark.createDataFrame(
        catalogo.BANREP, ["dataset", "subject", "unit_measure", "indicador_cat", "unidad_cat"])
    p = F.from_json("payload", ESQUEMA_BANREP)
    return (sobres
            .where(F.col("fuente") == "banrep")
            .withColumn("p", p)
            .withColumn("subject", F.col("p.serie")["SUBJECT"])
            .withColumn("unit_measure", F.col("p.serie")["UNIT_MEASURE"])
            .join(F.broadcast(cat), ["dataset", "subject", "unit_measure"], "left")
            .select(
                # Serie fuera del catálogo: nombre genérico, nunca se descarta.
                F.coalesce("indicador_cat",
                           F.concat_ws("_", "dataset", "subject", "unit_measure")
                           ).alias("indicador"),
                F.lit(catalogo.PAIS_COLOMBIA[0]).alias("pais"),
                F.lit(catalogo.PAIS_COLOMBIA[1]).alias("pais_nombre"),
                F.to_date(F.expr("try_to_timestamp(p.TIME_PERIOD, 'yyyyMMdd')")).alias("fecha"),
                F.lit("diaria").alias("frecuencia"),
                F.expr("try_cast(p.OBS_VALUE AS DOUBLE)").alias("valor"),
                F.coalesce("unidad_cat", F.lit("sin catálogo")).alias("unidad"),
                "fuente", "dataset", "id_registro", "fecha_ingesta"))


# ------------------------------------------------------------------ unión
def curar(lineas: DataFrame) -> dict:
    """Aplica todo el flujo. Devuelve un diccionario con los DataFrames
    intermedios para poder medir la calidad de cada etapa."""
    sobres = leer_sobres(lineas)
    unicos = deduplicar(sobres)
    normalizado = (normalizar_trm_gov(unicos)
                   .unionByName(normalizar_banco_mundial(unicos))
                   .unionByName(normalizar_banrep(unicos))
                   .withColumn("anio", F.year("fecha"))
                   .select(*COLUMNAS_CURADAS))
    valido = normalizado.where(F.col("fecha").isNotNull() & F.col("valor").isNotNull())
    return {"sobres": sobres, "unicos": unicos,
            "normalizado": normalizado, "curado": valido}


# ---------------------------------------------------------------- calidad
def reporte_calidad(etapas: dict) -> DataFrame:
    """Una fila por fuente/dataset: cuántos registros entraron, cuántos eran
    duplicados, cuántos se descartaron por fecha o valor vacío, y el rango
    de fechas resultante."""
    def contar(df, nombre):
        return df.groupBy("fuente", "dataset").agg(F.count("*").alias(nombre))

    normalizado = etapas["normalizado"]
    descartes = (normalizado.groupBy("fuente", "dataset").agg(
        F.sum(F.col("fecha").isNull().cast("int")).alias("sin_fecha"),
        F.sum(F.col("valor").isNull().cast("int")).alias("sin_valor")))
    curado = (etapas["curado"].groupBy("fuente", "dataset").agg(
        F.count("*").alias("filas_curadas"),
        F.countDistinct("indicador").alias("indicadores"),
        F.min("fecha").alias("desde"),
        F.max("fecha").alias("hasta")))

    return (contar(etapas["sobres"], "leidos")
            .join(contar(etapas["unicos"], "unicos"), ["fuente", "dataset"], "left")
            .withColumn("duplicados", F.col("leidos") - F.col("unicos"))
            .join(descartes, ["fuente", "dataset"], "left")
            .join(curado, ["fuente", "dataset"], "left")
            .select("fuente", "dataset", "leidos", "duplicados", "unicos",
                    "sin_fecha", "sin_valor", "filas_curadas", "indicadores",
                    "desde", "hasta")
            .orderBy("fuente", "dataset"))


def conciliar_trm(curado: DataFrame, tolerancia: float = 0.01) -> DataFrame:
    """Compara la TRM de datos.gov.co con la del Banco de la República día a
    día. Dos fuentes independientes para el mismo dato: si coinciden, hay
    confianza; si no, hay que investigar antes de publicar."""
    trm = curado.where(F.col("indicador") == "trm")
    gov = trm.where(F.col("fuente") == "datos_gov_co").select("fecha", F.col("valor").alias("gov"))
    br = trm.where(F.col("fuente") == "banrep").select("fecha", F.col("valor").alias("banrep"))
    return (gov.join(br, "fecha", "inner")
            .withColumn("diferencia", F.abs(F.col("gov") - F.col("banrep")))
            .agg(F.count("*").alias("dias_comparados"),
                 F.sum((F.col("diferencia") > tolerancia).cast("int")).alias("dias_distintos"),
                 F.max("diferencia").alias("diferencia_maxima"),
                 F.min("fecha").alias("desde"),
                 F.max("fecha").alias("hasta")))


def crear_sesion(nombre: str = "curar-indicadores", master: str = None) -> SparkSession:
    constructor = (SparkSession.builder.appName(nombre)
                   # Pocos datos: 200 particiones de shuffle (el valor por
                   # defecto) serían 200 tareas casi vacías.
                   .config("spark.sql.shuffle.partitions", "8")
                   .config("spark.sql.session.timeZone", "UTC"))
    if master:
        constructor = constructor.master(master)
    return constructor.getOrCreate()
