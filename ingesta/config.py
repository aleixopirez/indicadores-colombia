"""
Configuración de las fuentes de datos (Paso 1: ingesta).

Todo lo que un estudiante podría querer cambiar (países, indicadores, rutas)
vive aquí, separado de la lógica de extracción.
"""
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
# Zona "raw" (aterrizaje): los datos tal cual llegan de la fuente.
# En el Paso 3 esta misma estructura de carpetas se replica en HDFS.
RAW_DIR = Path(os.getenv("RAW_DIR", "data/raw"))

# ---------------------------------------------------------------------------
# Fuente 1: TRM diaria — datos.gov.co (Superintendencia Financiera)
# API Socrata (SODA). Dataset 32sa-8pi3.
# ---------------------------------------------------------------------------
TRM_URL = "https://www.datos.gov.co/resource/32sa-8pi3.json"
# Token opcional: sin él la API funciona, pero con límites de peticiones más bajos.
# Se crea gratis en https://www.datos.gov.co/profile/edit/developer_settings
SOCRATA_APP_TOKEN = os.getenv("SOCRATA_APP_TOKEN")
TRM_TAMANO_PAGINA = 1000

# ---------------------------------------------------------------------------
# Fuente 2: Indicadores del Banco Mundial (API v2, sin autenticación)
# ---------------------------------------------------------------------------
BANCO_MUNDIAL_URL = "https://api.worldbank.org/v2"

# Colombia + países de referencia para comparar. WLD = promedio mundial.
PAISES = ["COL", "BRA", "MEX", "CHL", "PER", "ARG", "USA", "WLD"]

# código del indicador -> nombre corto (se usa en carpetas y en el dashboard)
INDICADORES_BM = {
    "FP.CPI.TOTL.ZG": "inflacion_anual_pct",
    "SL.UEM.TOTL.ZS": "desempleo_pct",
    "NY.GDP.MKTP.KD.ZG": "crecimiento_pib_pct",
    "NY.GDP.MKTP.CD": "pib_usd_corrientes",
    "NY.GDP.PCAP.CD": "pib_per_capita_usd",
    "NE.EXP.GNFS.CD": "exportaciones_usd",
    "NE.EXP.GNFS.ZS": "exportaciones_pct_pib",
}

# Rango por defecto: desde 1990 permite comparar varios gobiernos.
BM_ANIO_DESDE = 1990
BM_TAMANO_PAGINA = 1000

# ---------------------------------------------------------------------------
# Fuente 3: Banco de la República — servicio web SDMX (sin llave)
# Guía técnica: https://suameca.banrep.gov.co/archivos/webservices/documento_tecnico_ws_consumo_sdmx.pdf
# ---------------------------------------------------------------------------
BANREP_URL = "https://totoro.banrep.gov.co/nsi-jax-ws/rest"
BANREP_AGENCIA = "ESTAT"   # el Banco usa el identificador de agencia de Eurostat
BANREP_VERSION = "1.0"
BANREP_TIMEOUT = 120       # las series históricas diarias son XML pesados

# FLOW_ID -> nombre corto. Convención del Banco:
#   DF_<TEMA>_<PERIODICIDAD>_HIST   -> serie histórica completa
#   DF_<TEMA>_<PERIODICIDAD>_LATEST -> solo el dato más reciente
# Para ver TODOS los flujos disponibles (tasa de política monetaria, etc.):
#   python -m ingesta banrep --listar
# y agréguenlos aquí con el id exacto que aparezca en la lista.
FLUJOS_BANREP = {
    "DF_TRM_DAILY_HIST": "trm_banrep",                  # para conciliar con la TRM de datos.gov.co
    "DF_IBR_DAILY_HIST": "ibr",                         # Indicador Bancario de Referencia
    "DF_CBR_DAILY_HIST": "tasa_politica_monetaria",     # tasa de intervención del Banco
}
# Otros flujos disponibles en el catálogo (nov. 2026) que pueden agregar:
#   DF_CBR_MONTHLY_HIST     tasa de política monetaria, promedio mensual
#   DF_UVR_DAILY_HIST       UVR (unidad indexada a la inflación)
#   DF_DTF_DAILY_HIST       DTF
#   DF_COLCAP_MONTHLY_HIST  índice COLCAP de la Bolsa de Valores de Colombia
#   DF_MONAGG_MONTHLY_HIST  agregados monetarios
#   DF_TES_MONTHLY_HIST     TES (deuda pública)

# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
HTTP_TIMEOUT = 30          # segundos
HTTP_REINTENTOS = 4        # reintentos ante 429 / 5xx / caídas de red
USER_AGENT = "pipeline-indicadores-educativo/1.0"
