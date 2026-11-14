-- =============================================================================
-- Paso 5 — Consultas de análisis (insumo para el dashboard y los reels)
--
--   docker compose exec hiveserver2 beeline -u jdbc:hive2://localhost:10000/indicadores_db -f /proyecto/hive/02_consultas.sql
--
-- Las cifras describen lo que ocurrió en cada periodo. Un indicador depende
-- de muchos factores (economía mundial, precios del petróleo, pandemia...),
-- no solo del gobierno: al publicar, mostrar el dato y su contexto, no un
-- veredicto.
-- =============================================================================
USE indicadores_db;
SET hive.strict.checks.cartesian.product=false;

-- -----------------------------------------------------------------------------
-- Consulta 1. Indicadores anuales promedio por gobierno (Colombia)
-- anios_con_datos permite ver si un periodo está incompleto.
-- -----------------------------------------------------------------------------
SELECT
    presidente,
    periodo,
    ROUND(AVG(CASE WHEN indicador = 'inflacion_anual_pct' THEN valor END), 2) AS inflacion_promedio,
    ROUND(AVG(CASE WHEN indicador = 'desempleo_pct'       THEN valor END), 2) AS desempleo_promedio,
    ROUND(AVG(CASE WHEN indicador = 'crecimiento_pib_pct' THEN valor END), 2) AS crecimiento_pib_promedio,
    COUNT(DISTINCT anio) AS anios_con_datos
FROM indicadores_gobierno
WHERE frecuencia = 'anual'
GROUP BY presidente, periodo, inicio
ORDER BY inicio;

-- -----------------------------------------------------------------------------
-- Consulta 2. TRM al inicio y al final de cada gobierno (fuente: Banco de la
-- República, la serie más larga). Funciones de ventana: ROW_NUMBER numera los
-- días de cada periodo del primero al último y del último al primero.
-- -----------------------------------------------------------------------------
WITH trm AS (
    SELECT presidente, periodo, inicio, fin, fecha, valor,
           ROW_NUMBER() OVER (PARTITION BY periodo ORDER BY fecha ASC)  AS desde_inicio,
           ROW_NUMBER() OVER (PARTITION BY periodo ORDER BY fecha DESC) AS desde_final
    FROM indicadores_gobierno
    WHERE indicador = 'trm' AND fuente = 'banrep'
)
SELECT
    presidente,
    periodo,
    MAX(CASE WHEN desde_inicio = 1 THEN fecha END) AS primer_dia,
    MAX(CASE WHEN desde_inicio = 1 THEN valor END) AS trm_inicial,
    MAX(CASE WHEN desde_final  = 1 THEN fecha END) AS ultimo_dia,
    MAX(CASE WHEN desde_final  = 1 THEN valor END) AS trm_final,
    ROUND(100 * (MAX(CASE WHEN desde_final = 1 THEN valor END)
               / MAX(CASE WHEN desde_inicio = 1 THEN valor END) - 1), 1) AS variacion_pct,
    MAX(fin) > current_date() AS en_curso
FROM trm
GROUP BY presidente, periodo, inicio
ORDER BY inicio;

-- -----------------------------------------------------------------------------
-- Consulta 3. Tasa de política monetaria del Banco de la República por
-- gobierno: promedio, mínimo y máximo. (Serie disponible desde 1998.)
-- -----------------------------------------------------------------------------
SELECT
    presidente,
    periodo,
    ROUND(AVG(valor), 2) AS tasa_promedio,
    MIN(valor)           AS tasa_minima,
    MAX(valor)           AS tasa_maxima,
    COUNT(*)             AS dias_con_dato
FROM indicadores_gobierno
WHERE indicador = 'tasa_politica_monetaria'
GROUP BY presidente, periodo, inicio
ORDER BY inicio;

-- -----------------------------------------------------------------------------
-- Consulta 4. Comparación regional: inflación del último año con dato para
-- Colombia, frente a los demás países y el promedio mundial (WLD).
-- -----------------------------------------------------------------------------
SELECT
    pais_nombre,
    anio,
    ROUND(valor, 2) AS inflacion_pct
FROM indicadores
WHERE indicador = 'inflacion_anual_pct'
  AND anio = (SELECT MAX(anio) FROM indicadores
              WHERE indicador = 'inflacion_anual_pct' AND pais = 'COL')
ORDER BY inflacion_pct DESC;
