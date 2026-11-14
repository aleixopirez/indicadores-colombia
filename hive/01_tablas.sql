-- =============================================================================
-- Paso 5 — Hive: tablas sobre el data lake
--
-- Ejecutar (después de encender Hive):
--   docker compose exec hiveserver2 beeline -u jdbc:hive2://localhost:10000/ -f /proyecto/hive/01_tablas.sql
--
-- Este script se puede ejecutar todas las veces que se quiera: borra y crea
-- las DEFINICIONES de las tablas. Los datos están en HDFS y no se tocan.
-- =============================================================================

CREATE DATABASE IF NOT EXISTS indicadores_db;
USE indicadores_db;

-- -----------------------------------------------------------------------------
-- 1. Indicadores: tabla EXTERNA sobre la zona curada que escribió Spark.
--    EXTERNAL = Hive solo guarda la descripción (esquema y ubicación).
--    Un DROP TABLE borra la descripción, NUNCA los archivos de HDFS.
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS indicadores;

CREATE EXTERNAL TABLE indicadores (
    pais          STRING,
    pais_nombre   STRING,
    fecha         DATE,
    anio          INT,
    frecuencia    STRING,
    valor         DOUBLE,
    unidad        STRING,
    fuente        STRING,
    dataset       STRING,
    id_registro   STRING,
    fecha_ingesta TIMESTAMP
)
PARTITIONED BY (indicador STRING)      -- cada carpeta indicador=... es una partición
STORED AS PARQUET
LOCATION 'hdfs://namenode:8020/datalake/curated/indicadores';

-- Hive no descubre solo las carpetas que Spark creó: hay que registrarlas.
-- Volver a ejecutarlo cada vez que aparezca un indicador nuevo.
MSCK REPAIR TABLE indicadores;

-- -----------------------------------------------------------------------------
-- 2. Gobiernos: tabla de referencia (referencia/gobiernos.csv subido a HDFS).
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS gobiernos;

CREATE EXTERNAL TABLE gobiernos (
    presidente STRING,
    periodo    STRING,
    inicio     DATE,          -- incluido
    fin        DATE           -- excluido: el 7 de agosto es del gobierno que entra
)
ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
STORED AS TEXTFILE
LOCATION 'hdfs://namenode:8020/datalake/referencia/gobiernos'
TBLPROPERTIES ('skip.header.line.count' = '1');

-- -----------------------------------------------------------------------------
-- 3. Vista: cada indicador de Colombia con el gobierno al que corresponde.
--
--    REGLA DE ASIGNACIÓN (decisión de análisis, debe citarse al publicar):
--      * Series diarias: por su fecha exacta.
--      * Series anuales: el año se asigna al gobierno en el cargo el 1 de
--        julio, es decir, al que gobernó la mayor parte de ese año.
--        Ej.: 2022 -> Duque (ene-ago); 2023 -> primer año completo de Petro.
--
--    No hay una columna común para unir (equi-join): la condición es un
--    rango de fechas. Por eso se usa un producto cruzado filtrado, que Hive
--    bloquea por defecto como medida de seguridad.
-- -----------------------------------------------------------------------------
SET hive.strict.checks.cartesian.product=false;

CREATE OR REPLACE VIEW indicadores_gobierno AS
SELECT
    g.presidente,
    g.periodo,
    g.inicio,
    g.fin,
    i.indicador,
    i.fecha,
    i.anio,
    i.frecuencia,
    i.valor,
    i.unidad,
    i.fuente
FROM indicadores i
CROSS JOIN gobiernos g
WHERE i.pais = 'COL'
  AND (CASE WHEN i.frecuencia = 'anual'
            THEN to_date(concat(cast(i.anio AS STRING), '-07-01'))
            ELSE i.fecha END) >= g.inicio
  AND (CASE WHEN i.frecuencia = 'anual'
            THEN to_date(concat(cast(i.anio AS STRING), '-07-01'))
            ELSE i.fecha END) <  g.fin;

-- Verificación rápida
SHOW PARTITIONS indicadores;
SELECT COUNT(*) AS filas_indicadores FROM indicadores;
SELECT * FROM gobiernos;
