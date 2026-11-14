# Paso 4 — PySpark: de la zona raw a la zona curada

```
HDFS /datalake/raw (JSONL, 3 formatos, duplicados)
        │  (4) SPARK: leer → deduplicar → normalizar → unificar → validar
        ▼
HDFS /datalake/curated/indicadores/indicador=<nombre>/*.parquet   (un esquema para todo)
```

## Objetivo

Convertir datos crudos, heterogéneos y con duplicados en **una sola tabla
limpia** de indicadores, con el mismo esquema para todas las fuentes:

| columna | tipo | ejemplo |
|---|---|---|
| indicador | string | `inflacion_anual_pct`, `trm`, `ibr_3m_nominal` |
| pais / pais_nombre | string | `COL` / `Colombia` |
| fecha / anio | date / int | `2023-12-31` / `2023` |
| frecuencia | string | `diaria`, `anual` |
| valor | double | `11.74` |
| unidad | string | `% anual`, `COP por USD` |
| fuente, dataset, id_registro, fecha_ingesta | | trazabilidad hasta la zona raw |

## Ejecución

```powershell
# 1. Solo HDFS (Kafka no hace falta y así sobra memoria para Spark)
docker compose stop kafka
docker compose --profile hdfs up -d
docker compose ps                     # namenode (healthy)

# 2. Correr el trabajo de Spark (la primera vez descarga ~740 MB)
docker compose run --rm spark

# 3. Revisar la zona curada
python -m datalake ls /datalake/curated/indicadores
```

Para ver la interfaz de Spark (`http://localhost:4040`) mientras corre:
`docker compose run --rm --service-ports spark`.

Pruebas de Spark (dentro del contenedor, que sí tiene Java):
```powershell
docker compose run --rm spark bash -c "pip install -q pytest && python3 -m pytest -q tests/test_procesamiento.py"
```

## Estructura

```
procesamiento/
  catalogo.py          # traducción fuente -> indicador, unidad (la "tabla de verdad")
  transformaciones.py  # funciones DataFrame -> DataFrame (probables por separado)
  curar.py             # el trabajo: lee, transforma, escribe, reporta
tests/test_procesamiento.py   # 9 pruebas con Spark real y datos pequeños
```

## Resultado de referencia (6 nov. 2026, 112.539 registros raw, 31 s)

| fuente/dataset | leídos | duplicados | descartados | filas curadas |
|---|---:|---:|---:|---:|
| banrep/ibr | 56.384 | 28.192 | 0 | 28.192 (8 series) |
| banrep/trm_banrep | 35.239 | 13.459 | 0 | 21.780 (desde 1967) |
| banrep/tasa_politica_monetaria | 10.493 | 0 | 0 | 10.493 |
| datos_gov_co/trm | 8.407 | 25 | 0 | 12.759 (rango expandido a días) |
| banco_mundial/inflacion_anual_pct | 288 | 0 | 30 sin valor | 258 |
| banco_mundial/desempleo_pct | 288 | 0 | 8 sin valor | 280 |

**Conciliación TRM:** 12.759 días comparados entre datos.gov.co y el Banco de
la República (1991–2026): **0 diferencias**.

**Tamaño:** 48 MB en la zona raw → **1,2 MB** en la zona curada (17 carpetas,
un Parquet por indicador). ~40 veces menos: sin duplicados, sin el texto
repetido de cada sobre JSON, y Parquet comprime columna por columna.

## Decisiones de diseño (para discutir en clase)

1. **Payload como texto, esquema por fuente.** Cada fuente tiene una
   estructura distinta; se lee el sobre con el payload como string y cada
   normalizador lo interpreta con su propio esquema (`from_json`).
2. **Deduplicar con `Window` + `row_number`.** Por `id_registro`, se conserva
   la ingesta más reciente. Es el patrón estándar para "última versión".
3. **Expandir rangos (`sequence` + `explode`).** Un registro de TRM de
   datos.gov.co vale para varios días (fin de semana, festivos). Se convierte
   a una fila por día para que todas las series diarias tengan el mismo grano.
4. **Catálogo + broadcast join.** El IBR trae 8 series en un mismo flujo
   (4 plazos × nominal/efectiva). Una tabla pequeña las traduce; `broadcast`
   la copia a cada nodo en vez de redistribuir los datos grandes.
5. **Nada se pierde en silencio.** Una serie que no esté en el catálogo
   queda con nombre genérico y unidad "sin catálogo"; fechas o valores
   inválidos se cuentan en el reporte antes de descartarse.
6. **ANSI en Spark 4.** Viene activado: `cast` de un texto inválido detiene
   todo el trabajo. Se usan `try_cast` y `try_to_timestamp`.
7. **Anual al 31 de diciembre.** El valor de un año se fecha al cierre del
   período, para cruzarlo bien con series diarias y con gobiernos.
8. **Parquet particionado por indicador.** Formato columnar y comprimido;
   Hive y Spark leen solo la carpeta del indicador que necesitan.
   `repartition("indicador")` deja un archivo por indicador (no cientos).
9. **`spark.sql.shuffle.partitions = 8`.** El valor por defecto (200) crea
   200 tareas casi vacías con pocos datos.
10. **Reescritura completa (`overwrite`).** La zona curada siempre es el
    resultado de procesar toda la zona raw: simple, repetible e idempotente.
11. **Dos fuentes para el mismo dato = control de calidad.** La conciliación
    de la TRM da confianza antes de publicar cifras en redes.

## Preguntas de control

- ¿Por qué `datos_gov_co/trm` tiene **más** filas curadas que registros únicos?
- ¿Qué pasaría con el promedio del IBR si no se separaran sus 8 series?
- Agrega a `catalogo.py` una serie que no exista y vuelve a correr: ¿dónde aparece?
- Cambia `try_cast` por `cast` y mete un valor `"n/d"` en una prueba: ¿qué pasa?
- ¿Cuántos archivos Parquet hay en `/datalake/curated/indicadores`? ¿Por qué ese número?

## Siguiente paso

**Paso 5 — Hive:** crear una tabla externa sobre la zona curada para
consultarla con SQL (por ejemplo, inflación promedio por gobierno).
