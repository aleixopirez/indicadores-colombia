"""
Paso 4 — Trabajo de Spark: zona raw -> zona curada (Parquet).

Dentro de Docker (lo normal):
    docker compose run --rm spark spark-submit procesamiento/curar.py

Con rutas propias (por ejemplo, para probar con data/raw local):
    spark-submit procesamiento/curar.py --origen data/raw --destino /tmp/curado

El destino se SOBRESCRIBE completo en cada ejecución: la zona curada siempre
es el resultado de procesar toda la zona raw. Simple y repetible.
"""
import argparse
import sys
import time

from procesamiento import transformaciones as tr

HDFS = "hdfs://namenode:8020"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Paso 4: raw -> curado")
    parser.add_argument("--origen", default=f"{HDFS}/datalake/raw")
    parser.add_argument("--destino", default=f"{HDFS}/datalake/curated/indicadores")
    parser.add_argument("--master", default=None,
                        help="p. ej. local[2]; por defecto lo define spark-submit")
    args = parser.parse_args(argv)

    inicio = time.time()
    spark = tr.crear_sesion(master=args.master)
    # ERROR y no WARN: con rutas con comodines (*), Spark imprime un aviso
    # largo e inofensivo ("FileNotFoundException ... _spark_metadata").
    spark.sparkContext.setLogLevel("ERROR")

    # Solo los .jsonl (se ignoran manifiestos, .kafka_ok y XML originales).
    patron = f"{args.origen}/*/*/fecha_ingesta=*/*.jsonl"
    print(f"\nLeyendo {patron}")
    lineas = spark.read.text(patron)

    etapas = tr.curar(lineas)
    curado = etapas["curado"].cache()   # se usa 3 veces: escribir, reportar, conciliar

    # Un archivo por indicador (repartition) y una carpeta por indicador
    # (partitionBy): Hive y Spark podrán leer solo el indicador que necesiten.
    (curado.repartition("indicador")
     .write.mode("overwrite")
     .partitionBy("indicador")
     .parquet(args.destino))
    print(f"Zona curada escrita en {args.destino}\n")

    print("=== Reporte de calidad ===")
    tr.reporte_calidad(etapas).show(50, truncate=False)

    print("=== Indicadores en la zona curada ===")
    (curado.groupBy("indicador", "fuente", "frecuencia", "unidad")
     .count().orderBy("indicador", "fuente").show(50, truncate=False))

    print("=== Conciliación TRM: datos.gov.co vs Banco de la República ===")
    tr.conciliar_trm(curado).show(truncate=False)

    print("=== Colombia: inflación y desempleo, últimos 5 años ===")
    (curado.where("pais = 'COL' AND indicador IN ('inflacion_anual_pct', 'desempleo_pct')")
     .groupBy("anio").pivot("indicador").agg({"valor": "first"})
     .orderBy("anio", ascending=False).show(5))

    print(f"Terminado en {time.time() - inicio:.0f} s")
    spark.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
