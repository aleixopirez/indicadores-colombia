# Paso 6 — PostgreSQL + Power BI: la zona de servicio

```
HDFS curated (Parquet) ──► (6) SPARK servir.py ──JDBC──► PostgreSQL  servicio.*  ──► Power BI
HDFS referencia/gobiernos ─┘                                (localhost:5432)
```

## Objetivo

Dejar los datos **listos para mostrar**: con nombres en español, el gobierno
de cada dato ya asignado y la fuente a citar, en una base que Power BI lee en
milisegundos.

## Tablas (esquema `servicio`, base `indicadores`)

| tabla | filas | para qué |
|---|---:|---|
| `indicadores` | 75.200 | gráficas de series: una fila por dato, con `presidente`/`periodo` (solo Colombia) |
| `resumen_gobierno` | 11 | una fila por gobierno: inflación, desempleo, PIB, TRM inicial/final, tasa de política |
| `gobiernos` | 11 | periodos presidenciales |
| `catalogo_indicadores` | 18 | nombre, unidad, frecuencia y **fuente a citar** de cada indicador |

## Ejecución

```powershell
# 1. Apagar Hive (libera memoria) y encender HDFS + PostgreSQL
docker compose --profile hive down
docker compose --profile hdfs --profile postgres up -d
docker compose ps                     # namenode y postgres (healthy)

# 2. Cargar PostgreSQL desde HDFS con Spark
#    (la primera vez descarga el driver JDBC de PostgreSQL desde Maven)
docker compose run --rm spark-servir

# 3. Verificar desde PostgreSQL
docker compose exec postgres psql -U pipeline -d indicadores -c "SELECT presidente, periodo, inflacion_promedio, trm_variacion_pct FROM servicio.resumen_gobierno ORDER BY inicio;"
```

## Conectar Power BI Desktop

1. **Inicio → Obtener datos → Más… → Base de datos PostgreSQL → Conectar.**
2. Servidor: `localhost:5432` · Base de datos: `indicadores` ·
   Modo: **Importar** → Aceptar.
3. Credenciales: pestaña **Base de datos** · usuario `lector` · contraseña
   `lector` → Conectar.
4. Si aparece un aviso de que la conexión no está cifrada, **Aceptar**
   (PostgreSQL local de curso, sin certificado SSL).
5. Marcar las 4 tablas `servicio.*` → **Cargar**.
6. En **Vista de modelo**, crear la relación
   `indicadores[periodo]` (*) → `gobiernos[periodo]` (1).
7. Para actualizar después de una nueva carga: **Inicio → Actualizar**.

Ideas de visuales:
- Líneas: `indicadores` filtrado a *Inflación anual*, eje `anio`, leyenda `pais_nombre`.
- Barras: `resumen_gobierno`, eje `periodo`, valor `inflacion_promedio`.
- Tarjeta: última TRM (`indicadores`, *TRM*, fuente `banrep`, fecha máxima).
- Siempre un cuadro de texto con `fuente_cita` y la regla de asignación.

## Estructura

```
procesamiento/servir.py      # construye las 4 tablas y las carga por JDBC
procesamiento/catalogo.py    # + nombres en español, países, fuentes a citar
postgres/01_esquema.sql      # esquema servicio + usuario lector (solo la 1.ª vez)
tests/test_servir.py         # 5 pruebas con Spark real (se omiten en Windows)
```

## Decisiones de diseño (para discutir en clase)

1. **Capas con propósitos distintos.** HDFS/Spark/Hive: procesar mucho en
   lote. PostgreSQL: responder rápido lo poco que pide un dashboard. Copiar
   el resultado final a una base de servicio es el patrón habitual.
2. **Spark escribe por JDBC.** El mismo motor que limpió los datos los
   carga; `--packages` trae el driver de PostgreSQL desde Maven.
3. **`overwrite` + `truncate`.** Vacía y recarga cada tabla sin borrarla: se
   conservan permisos y vistas creadas encima.
4. **Tablas desnormalizadas.** `indicadores` ya trae nombre del indicador,
   país en español, gobierno y fuente: Power BI no tiene que hacer joins.
5. **La regla de asignación vive en un solo lugar por motor**: `servir.py`
   (Spark) y la vista de Hive dan cifras idénticas; las pruebas lo vigilan.
6. **Usuario de solo lectura** (`lector`) para el dashboard: quien solo
   consulta no debe poder borrar.
7. **Catálogo con la fuente a citar.** Cada cifra publicada en redes debe
   llevar su fuente; la tabla la trae lista.
8. **Credenciales en el `docker-compose.yml`** solo porque es un entorno de
   curso. En producción: archivo `.env` fuera del control de versiones.

## Preguntas de control

- ¿Qué pasa si conectas Power BI con `lector` e intentas `DELETE FROM servicio.gobiernos`?
- Ejecuta `spark-servir` dos veces. ¿Cambia el número de filas? ¿Por qué?
- ¿Por qué `resumen_gobierno` no tiene inflación para 2026-2030?
- ¿Qué ventaja tiene que el país venga ya traducido en la tabla y no en Power BI?

## Siguiente paso

**Paso 7 — Airflow:** encadenar los pasos 1 a 6 en un DAG que corra solo
cada día, y dejar listo el insumo para generar los reels.
