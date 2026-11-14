# Indicadores económicos de Colombia y el mundo

Proyecto de pipeline de datos que nos muestra, en la capa de consumo, indicadores económicos de Colombia y el mundo con herramientas open source.

**Dashboard en línea:** https://aleixopirez.github.io/indicadores-colombia/

```
APIs de datos abiertos ─► Ingesta (Python) ─► Apache Kafka ─► HDFS ─► PySpark ─► Hive
                                                                        │
                                                                        ▼
                                Power BI ◄── PostgreSQL (zona de servicio) ──► HTML (Plotly): dashboard + reels
```

## Fuentes de datos

- **Banco de la República** (SDMX): TRM diaria, tasa de política monetaria, IBR.
- **datos.gov.co** (Socrata): TRM.
- **Banco Mundial** (API v2): inflación, desempleo, PIB, exportaciones y otros, para Colombia, la región y el mundo.

## Pasos del pipeline

| Paso | Qué hace | Guía |
|---|---|---|
| 1 | Ingesta desde las fuentes a la zona raw (JSONL) | [PASO1_INGESTA.md](PASO1_INGESTA.md) |
| 2 | Streaming con Apache Kafka | [PASO2_KAFKA.md](PASO2_KAFKA.md) |
| 3 | Data lake en HDFS | [PASO3_HDFS.md](PASO3_HDFS.md) |
| 4 | Limpieza y curado con PySpark | [PASO4_PYSPARK.md](PASO4_PYSPARK.md) |
| 5 | Tablas y consultas en Hive | [PASO5_HIVE.md](PASO5_HIVE.md) |
| 6 | Zona de servicio en PostgreSQL y Power BI | [PASO6_POSTGRES_POWERBI.md](PASO6_POSTGRES_POWERBI.md) · [PASO6B_DASHBOARD.md](PASO6B_DASHBOARD.md) |
| 7 | Dashboard HTML y reels para redes sociales | [PASO7_VISUALIZACION_HTML.md](PASO7_VISUALIZACION_HTML.md) |

## Estructura

```
ingesta/          Paso 1: extractores (TRM, Banco Mundial, Banco de la República)
streaming/        Paso 2: productor y consumidor de Kafka
datalake/         Paso 3: escritura en HDFS (WebHDFS)
procesamiento/    Pasos 4 y 6: transformaciones PySpark y tablas de servicio
hive/             Paso 5: tablas externas y consultas
postgres/         Paso 6: esquema de la zona de servicio
powerbi/          Tema, medidas DAX y guía del dashboard ejecutivo
visualizacion/    Paso 7: dashboard HTML y reels (Plotly / ECharts)
referencia/       Períodos presidenciales de Colombia (1986–2030)
docs/             Página publicada en GitHub Pages
tests/            Pruebas (pytest)
docker-compose.yml  Kafka, HDFS, Hive, Spark y PostgreSQL con perfiles
```

## Inicio rápido (Windows, VS Code)

```powershell
uv venv; .\.venv\Scripts\Activate.ps1
uv pip install -r requirements.txt
docker compose --profile postgres up -d
python -m visualizacion generar
python -m visualizacion publicar     # copia el dashboard a docs/index.html
```

## Nota metodológica

Cada año se asigna al gobierno en el cargo el 1 de julio. Los indicadores dependen también del contexto económico mundial, no solo del gobierno. La tasa de política monetaria la fija la Junta Directiva del Banco de la República, independiente del Gobierno.

## Herramientas

Python · Apache Kafka · Apache Hadoop (HDFS) · Apache Spark (PySpark) · Apache Hive · PostgreSQL · Docker · Plotly.js · Apache ECharts · Power BI
