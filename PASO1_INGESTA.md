# Pipeline de indicadores económicos — Paso 1: Ingesta desde la fuente

```
[APIs abiertas] ──► (1) EXTRACCIÓN ──► zona raw (JSONL) ──► (2) Kafka ──► (3) HDFS ──► (4) PySpark ──► (5) Hive ──► PostgreSQL ──► Power BI
                     ▲ este paso                                                    (6) Airflow orquesta todo
```

## Objetivo

Traer los datos **tal cual los entrega la fuente**, sin limpiarlos, a una zona
de aterrizaje ("raw"). Limpiar y transformar es trabajo de PySpark (Paso 4).
Si algo sale mal más adelante, siempre podemos volver a procesar desde raw sin
volver a llamar a las APIs.

## Fuentes

| Fuente | Qué trae | API | Frecuencia |
|---|---|---|---|
| datos.gov.co (Superfinanciera) | TRM diaria COP/USD desde 1991 | Socrata, dataset `32sa-8pi3` | diaria |
| Banco Mundial | Inflación, desempleo, crecimiento PIB, PIB USD, PIB per cápita, exportaciones (USD y % PIB) | `api.worldbank.org/v2` | anual |
| Banco de la República | TRM e IBR (y cualquier otro flujo SDMX que agreguen) | SDMX 2.1, `totoro.banrep.gov.co/nsi-jax-ws/rest` | diaria |

Países: Colombia + Brasil, México, Chile, Perú, Argentina, EE. UU. y promedio
mundial (`WLD`). Se cambian en `ingesta/config.py`.

## Estructura

```
ingesta/
  config.py          # países, indicadores, URLs, rutas  ← lo que se edita
  comun.py           # sesión HTTP con reintentos, "sobre", escritura JSONL
  trm.py             # extractor TRM (paginación $limit/$offset, filtro $where)
  banco_mundial.py   # extractor Banco Mundial (paginación por page/pages)
  banrep.py          # extractor Banco de la República (SDMX, respuesta XML)
  __main__.py        # línea de comandos
tests/                 # pruebas sin red (11)
```

## Cómo ejecutarlo

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m pytest -q                                   # 1) pruebas (sin internet)
python -m ingesta trm                                 # 2) TRM completa (~12.000 filas)
python -m ingesta trm --desde 2026-10-01              #    incremental
python -m ingesta banco_mundial --desde 1990          # 3) indicadores anuales
python -m ingesta banrep --listar                     # 4) catálogo de flujos del Banco
python -m ingesta banrep --desde 2015                 #    TRM + IBR desde 2015
python -m ingesta -v todo                             #    todo, con log detallado
```

Opcional: `export SOCRATA_APP_TOKEN=...` para límites más altos en datos.gov.co.

## Qué queda en disco

```
data/raw/
  datos_gov_co/trm/fecha_ingesta=2026-11-04/
      trm_20261104T151200Z.jsonl
      _manifiesto_20261104T151200Z.json
  banco_mundial/inflacion_anual_pct/fecha_ingesta=2026-11-04/...
  banco_mundial/desempleo_pct/fecha_ingesta=2026-11-04/...
  banrep/ibr/fecha_ingesta=2026-11-04/
      ibr_20261104T151200Z.jsonl
      ibr_20261104T151200Z_original.xml      ← respuesta SDMX byte por byte
      _manifiesto_20261104T151200Z.json
```

Cada línea del `.jsonl` es un **sobre** con el registro original adentro:

```json
{"fuente": "datos_gov_co", "dataset": "trm", "id_registro": "trm|2026-11-04",
 "fecha_ingesta": "2026-11-04T15:12:00Z",
 "payload": {"valor": "4012.35", "unidad": "COP",
             "vigenciadesde": "2026-11-04T00:00:00.000", "vigenciahasta": "2026-11-04T00:00:00.000"}}
```

## Decisiones de diseño (para discutir en clase)

1. **JSON Lines, no un JSON gigante.** Una línea = un registro = un mensaje de
   Kafka en el Paso 2. Spark y Hive leen JSONL de forma nativa.
2. **El sobre.** `id_registro` es la llave natural (`trm|fecha`,
   `indicador|país|año`). Será la *key* del mensaje en Kafka y permite
   deduplicar si el mismo dato se extrae dos veces.
3. **Particiones `fecha_ingesta=YYYY-MM-DD`.** Es el formato `clave=valor` que
   Hive y Spark reconocen. La misma estructura se copia a HDFS en el Paso 3.
4. **Manifiesto por ejecución.** URL, parámetros y número de registros: la
   trazabilidad mínima para auditar una carga.
5. **Reintentos con espera exponencial** ante 429/5xx. Las APIs públicas fallan.
6. **Validar la forma, no solo el HTTP.** El Banco Mundial responde **200** con
   un `message` cuando el código del indicador está mal (lo cubre una prueba).
7. **Un indicador caído no tumba a los demás**, pero la ejecución termina en
   error para que Airflow la marque como fallida (Paso 6).
8. **SDMX y XML (Banco de la República).** Es el estándar de bancos centrales,
   Eurostat, OCDE y FMI: aprenderlo sirve para muchas fuentes. Como la respuesta
   es XML, se guarda también el archivo original; si el parser tenía un error,
   se re-procesa sin volver a llamar al servicio.
9. **"Sin datos" no es error.** SDMX responde 404 cuando el rango está vacío;
   el extractor lo registra como advertencia y sigue.
10. **Descubrir antes de configurar.** `banrep --listar` consulta el catálogo
   del servicio; los FLOW_ID se copian de ahí, no se adivinan.
11. **Valores `null` se conservan.** El Banco Mundial devuelve `value: null` en
   años sin dato; decidir qué hacer con ellos es tarea de la limpieza.

## Verificación rápida

```bash
wc -l data/raw/datos_gov_co/trm/*/*.jsonl
head -n 2 data/raw/banco_mundial/inflacion_anual_pct/*/*.jsonl
cat data/raw/datos_gov_co/trm/*/_manifiesto_*.json
```

Conciliación entre fuentes: la TRM llega de datos.gov.co **y** del Banco de la
República. ¿Coinciden los valores para la misma fecha? ¿Cuál dejarían como
fuente oficial en el dashboard y por qué?

Preguntas de control: ¿cuántos registros trajo la TRM? ¿Coincide la última
fecha con la TRM publicada hoy? ¿Qué años tienen `value: null` para Colombia?

## Ejercicio para estudiantes

Con el dataset abierto de su proyecto final:
1. Agreguen su fuente en `config.py` y escriban `mi_fuente.py` siguiendo el
   patrón de `trm.py` (paginación + sobre + `guardar_jsonl`).
2. Definan la `id_registro` de su dato y justifiquen por qué es única.
3. Escriban una prueba con `SesionFalsa` que cubra la paginación.

## Cierre del Paso 1 — checklist

- [ ] `python -m pytest -q` → 11 pruebas en verde
- [ ] `python -m ingesta banrep --listar` muestra el catálogo; si quieren la
      tasa de política monetaria, agreguen su FLOW_ID a `FLUJOS_BANREP`
- [ ] `python -m ingesta todo` termina con código 0
- [ ] Cada carpeta en `data/raw/` tiene `.jsonl` + `_manifiesto_*.json`
- [ ] La TRM de ambas fuentes coincide para una fecha de control

## Siguiente paso

**Paso 2 — Kafka:** un productor que lea estos `.jsonl` y publique cada sobre
en un tópico por fuente (`raw.datos_gov_co.trm`, `raw.banco_mundial`), usando
`id_registro` como key.
