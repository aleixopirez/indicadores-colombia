"""
Paso 6 — Trabajo de Spark: zona curada (HDFS) -> zona de servicio (PostgreSQL).

    docker compose run --rm spark-servir

Construye 4 tablas pensadas para Power BI y para los reels:

  servicio.indicadores          una fila por dato (75 mil), con nombres en
                                español y el gobierno al que corresponde
  servicio.gobiernos            los periodos presidenciales
  servicio.resumen_gobierno     una fila por gobierno: promedios anuales, TRM
                                al inicio y al final, tasa de política
  servicio.catalogo_indicadores nombre, unidad, frecuencia y fuente a citar

¿Por qué copiar a PostgreSQL si ya está en Hive? Porque cada herramienta
sirve para algo distinto: Hive/Spark procesan volúmenes grandes en lote;
PostgreSQL responde en milisegundos las consultas pequeñas y repetidas de un
dashboard, y Power BI se conecta a él sin instalar nada.
"""
import argparse
import os
import sys
import time

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql import types as T

from procesamiento import catalogo
from procesamiento.transformaciones import crear_sesion

HDFS = "hdfs://namenode:8020"

ESQUEMA_GOBIERNOS = T.StructType([
    T.StructField("presidente", T.StringType()),
    T.StructField("periodo", T.StringType()),
    T.StructField("inicio", T.DateType()),
    T.StructField("fin", T.DateType()),
])


def _mapa(diccionario: dict):
    """dict de Python -> columna MAP de Spark, para traducir códigos."""
    return F.create_map(*[F.lit(x) for par in diccionario.items() for x in par])


def fecha_referencia(df: DataFrame):
    """REGLA DE ASIGNACIÓN (la misma de Hive, Paso 5):
    diaria -> su fecha; anual -> 1 de julio del año (gobierno que gobernó la
    mayor parte del año)."""
    return F.when(F.col("frecuencia") == "anual",
                  F.make_date(F.col("anio"), F.lit(7), F.lit(1))
                  ).otherwise(F.col("fecha"))


def tabla_indicadores(curado: DataFrame, gobiernos: DataFrame) -> DataFrame:
    paises, nombres, fuentes = (_mapa(catalogo.PAISES_ES),
                                _mapa(catalogo.NOMBRES_INDICADORES),
                                _mapa(catalogo.FUENTES_PUBLICAS))
    base = (curado
            .withColumn("fecha_ref", fecha_referencia(curado))
            .withColumn("nombre_indicador",
                        F.coalesce(nombres[F.col("indicador")], F.col("indicador")))
            .withColumn("pais_nombre",
                        F.coalesce(paises[F.col("pais")], F.col("pais_nombre")))
            .withColumn("fuente_cita", F.coalesce(fuentes[F.col("fuente")], F.col("fuente"))))

    # Solo los datos de Colombia tienen gobierno. Join por RANGO de fechas
    # (no por igualdad); broadcast porque gobiernos tiene 11 filas.
    g = F.broadcast(gobiernos.select("presidente", "periodo", "inicio", "fin"))
    con_gobierno = base.join(
        g,
        (base["pais"] == "COL") & (base["fecha_ref"] >= g["inicio"]) & (base["fecha_ref"] < g["fin"]),
        "left")

    return con_gobierno.select(
        "indicador", "nombre_indicador", "pais", "pais_nombre", "fecha", "anio",
        "frecuencia", "valor", "unidad", "presidente", "periodo",
        "fuente", "fuente_cita")


def tabla_resumen_gobierno(indicadores: DataFrame, gobiernos: DataFrame) -> DataFrame:
    """Una fila por gobierno. Mismas cifras que las consultas 1-3 de Hive."""
    col = indicadores.where(F.col("periodo").isNotNull())

    anuales = (col.where(F.col("frecuencia") == "anual")
               .groupBy("periodo").agg(
                   F.round(F.avg(F.when(F.col("indicador") == "inflacion_anual_pct", F.col("valor"))), 2)
                   .alias("inflacion_promedio"),
                   F.round(F.avg(F.when(F.col("indicador") == "desempleo_pct", F.col("valor"))), 2)
                   .alias("desempleo_promedio"),
                   F.round(F.avg(F.when(F.col("indicador") == "crecimiento_pib_pct", F.col("valor"))), 2)
                   .alias("crecimiento_pib_promedio"),
                   F.countDistinct("anio").alias("anios_con_datos")))

    # TRM del Banco de la República: primer y último dato de cada periodo.
    trm = col.where((F.col("indicador") == "trm") & (F.col("fuente") == "banrep"))
    extremos = trm.groupBy("periodo").agg(
        F.min_by("valor", "fecha").alias("trm_inicial"),
        F.max_by("valor", "fecha").alias("trm_final"),
        F.min("fecha").alias("trm_desde"),
        F.max("fecha").alias("trm_hasta"))
    extremos = extremos.withColumn(
        "trm_variacion_pct",
        F.round(100 * (F.col("trm_final") / F.col("trm_inicial") - 1), 1))

    tasa = (col.where(F.col("indicador") == "tasa_politica_monetaria")
            .groupBy("periodo").agg(
                F.round(F.avg("valor"), 2).alias("tasa_politica_promedio"),
                F.min("valor").alias("tasa_politica_minima"),
                F.max("valor").alias("tasa_politica_maxima")))

    return (gobiernos
            .join(anuales, "periodo", "left")
            .join(extremos, "periodo", "left")
            .join(tasa, "periodo", "left")
            .withColumn("en_curso", F.col("fin") > F.current_date())
            .select("presidente", "periodo", "inicio", "fin", "en_curso",
                    "inflacion_promedio", "desempleo_promedio",
                    "crecimiento_pib_promedio", "anios_con_datos",
                    "trm_inicial", "trm_final", "trm_variacion_pct",
                    "trm_desde", "trm_hasta",
                    "tasa_politica_promedio", "tasa_politica_minima",
                    "tasa_politica_maxima")
            .orderBy("inicio"))


def tabla_catalogo(indicadores: DataFrame) -> DataFrame:
    return (indicadores.groupBy("indicador", "nombre_indicador", "unidad", "frecuencia",
                                "fuente", "fuente_cita")
            .agg(F.min("fecha").alias("desde"), F.max("fecha").alias("hasta"),
                 F.count("*").alias("registros"),
                 F.countDistinct("pais").alias("paises"))
            .orderBy("indicador", "fuente"))


def construir_tablas(curado: DataFrame, gobiernos: DataFrame) -> dict:
    indicadores = tabla_indicadores(curado, gobiernos).cache()
    return {
        "indicadores": indicadores,
        "gobiernos": gobiernos,
        "resumen_gobierno": tabla_resumen_gobierno(indicadores, gobiernos),
        "catalogo_indicadores": tabla_catalogo(indicadores),
    }


def escribir_postgres(tablas: dict, url: str, usuario: str, clave: str, esquema: str):
    """overwrite + truncate: vacía y recarga la tabla sin borrarla, así no se
    rompen las vistas ni los permisos que alguien haya creado sobre ella."""
    for nombre, df in tablas.items():
        inicio = time.time()
        (df.write.mode("overwrite")
         .option("truncate", "true")
         .option("batchsize", 5000)
         .jdbc(url, f"{esquema}.{nombre}",
               properties={"user": usuario, "password": clave,
                           "driver": "org.postgresql.Driver"}))
        print(f"  {esquema}.{nombre:<22} {df.count():>7} filas  ({time.time() - inicio:.1f} s)")


def main(argv=None):
    p = argparse.ArgumentParser(description="Paso 6: curado -> PostgreSQL")
    p.add_argument("--curado", default=f"{HDFS}/datalake/curated/indicadores")
    p.add_argument("--gobiernos", default=f"{HDFS}/datalake/referencia/gobiernos")
    p.add_argument("--jdbc", default=os.getenv("POSTGRES_JDBC",
                                               "jdbc:postgresql://postgres:5432/indicadores"))
    p.add_argument("--usuario", default=os.getenv("POSTGRES_USER", "pipeline"))
    p.add_argument("--clave", default=os.getenv("POSTGRES_PASSWORD", "pipeline"))
    p.add_argument("--esquema", default="servicio")
    p.add_argument("--master", default=None)
    args = p.parse_args(argv)

    inicio = time.time()
    spark: SparkSession = crear_sesion("servir-indicadores", master=args.master)
    spark.sparkContext.setLogLevel("ERROR")

    curado = spark.read.parquet(args.curado)
    gobiernos = spark.read.csv(args.gobiernos, header=True, schema=ESQUEMA_GOBIERNOS,
                               encoding="UTF-8")
    tablas = construir_tablas(curado, gobiernos)

    print(f"\nCargando en {args.jdbc} (esquema {args.esquema}):")
    escribir_postgres(tablas, args.jdbc, args.usuario, args.clave, args.esquema)

    print("\n=== servicio.resumen_gobierno ===")
    tablas["resumen_gobierno"].select(
        "presidente", "periodo", "inflacion_promedio", "desempleo_promedio",
        "trm_variacion_pct", "tasa_politica_promedio", "en_curso").show(20, truncate=False)

    print(f"Terminado en {time.time() - inicio:.0f} s")
    spark.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
