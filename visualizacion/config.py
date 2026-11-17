"""
Configuración de la capa de visualización (Paso 7).
"""
import os
from pathlib import Path

BASE = Path(__file__).parent
PLANTILLAS = BASE / "plantillas"
ECHARTS_JS = BASE / "vendor" / "echarts.min.js"
SALIDA = Path(os.getenv("SALIDA_VISUALIZACION", "salida"))

# PostgreSQL (zona de servicio del Paso 6). Desde Windows: localhost.
# Se usa el usuario de SOLO LECTURA: la visualización nunca escribe.
POSTGRES = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5432")),
    "database": os.getenv("POSTGRES_DB", "indicadores"),
    "user": os.getenv("POSTGRES_LECTOR", "lector"),
    "password": os.getenv("POSTGRES_LECTOR_CLAVE", "lector"),
}
ESQUEMA = "servicio"
TABLAS = ["indicadores", "gobiernos", "resumen_gobierno", "catalogo_indicadores"]

# Paleta (la misma del tema de Power BI)
COLORES = {
    "fondo": "#0B1220", "tarjeta": "#111B2E", "borde": "#1E2A44",
    "texto": "#F1F5F9", "secundario": "#94A3B8", "tenue": "#64748B",
    "acento": "#F5B700",           # Colombia / dato protagonista
    "serie": ["#38BDF8", "#A78BFA", "#34D399", "#F472B6", "#FB923C", "#E2E8F0", "#64748B"],
    "gris_barra": "#475569",
}

# Reels: lienzo vertical y zona segura (lo que no tapan TikTok/Instagram)
REEL = {"ancho": 1080, "alto": 1920,
        "seguro": {"izq": 60, "der": 940, "arriba": 160, "abajo": 1480}}
DURACION_REEL_MS = 9000          # duración del video de cada reel

# Navegador para capturar PNG/MP4 con Playwright.
#   Windows: "msedge" (ya viene instalado) · Linux: "chrome" o "chromium"
NAVEGADOR = os.getenv("NAVEGADOR_CAPTURA", "msedge" if os.name == "nt" else "chrome")

NOTA_METODOLOGICA = (
    "Cada año se asigna al gobierno que gobernó la mayor parte de ese año "
    "(en el cargo el 1 de julio). Los indicadores dependen también del contexto "
    "económico mundial, no solo del gobierno."
)

# Librería de gráficas por defecto ("plotly" o "echarts"). La elegida escribe en
# salida/; la otra, si se pide con --motor, en salida/<motor>/.
MOTOR = os.environ.get("MOTOR_VISUALIZACION", "plotly")

# Autor que aparece al final del dashboard ("Elaborado por ...")
AUTOR = os.environ.get("AUTOR_DASHBOARD", "Aleixo Eder Pineda, Electronic Engineer · Big Data Specialist")
