"""
Catálogo de indicadores: traduce lo que llega de cada fuente a un nombre,
una unidad y una frecuencia comunes.

Es la "tabla de verdad" del proyecto. Cuando se agregue un indicador en la
ingesta (Paso 1), se agrega aquí su traducción. Si llega algo que no está en
el catálogo, NO se descarta en silencio: queda con un nombre genérico y el
reporte de calidad lo señala.
"""

# --- Banco Mundial: el dataset ya es el nombre del indicador ---------------
BANCO_MUNDIAL = {
    # dataset                 unidad
    "inflacion_anual_pct":    "% anual",
    "desempleo_pct":          "% de la fuerza laboral",
    "crecimiento_pib_pct":    "% anual",
    "pib_usd_corrientes":     "USD corrientes",
    "pib_per_capita_usd":     "USD corrientes",
    "exportaciones_usd":      "USD corrientes",
    "exportaciones_pct_pib":  "% del PIB",
}

# --- Banco de la República: (dataset, SUBJECT, UNIT_MEASURE) -> indicador ---
# Códigos SDMX observados en los datos reales (nov. 2026):
#   IBR:  IRIBRM00 = overnight, IRIBRM01 = 1 mes, IRIBRM03 = 3 meses,
#         IRIBRM06 = 6 meses;  NR = tasa nominal, ER = tasa efectiva
#   TPM:  IRCBRM01, unidad PA (porcentaje anual)
#   TRM:  CCSP, unidad COP
# Verifíquenlos con el catálogo del Banco si agregan nuevos flujos.
_PLAZOS_IBR = {"IRIBRM00": "overnight", "IRIBRM01": "1m",
               "IRIBRM03": "3m", "IRIBRM06": "6m"}
_TIPOS_IBR = {"NR": "nominal", "ER": "efectiva"}

BANREP = [
    # (dataset, SUBJECT, UNIT_MEASURE, indicador, unidad)
    ("trm_banrep", "CCSP", "COP", "trm", "COP por USD"),
    ("tasa_politica_monetaria", "IRCBRM01", "PA", "tasa_politica_monetaria", "% anual"),
] + [
    ("ibr", subject, unidad, f"ibr_{plazo}_{tipo}", "% anual")
    for subject, plazo in _PLAZOS_IBR.items()
    for unidad, tipo in _TIPOS_IBR.items()
]

# --- datos.gov.co ------------------------------------------------------------
TRM_GOV = {"indicador": "trm", "unidad": "COP por USD"}

PAIS_COLOMBIA = ("COL", "Colombia")


# =============================================================================
# Paso 6 — Nombres para mostrar (dashboard y reels)
# =============================================================================
# El Banco Mundial entrega los nombres de países en inglés ("Brazil", "World").
PAISES_ES = {
    "COL": "Colombia", "BRA": "Brasil", "MEX": "México", "CHL": "Chile",
    "PER": "Perú", "ARG": "Argentina", "USA": "Estados Unidos", "WLD": "Mundo",
}

NOMBRES_INDICADORES = {
    "inflacion_anual_pct":     "Inflación anual",
    "desempleo_pct":           "Tasa de desempleo",
    "crecimiento_pib_pct":     "Crecimiento del PIB",
    "pib_usd_corrientes":      "PIB (USD corrientes)",
    "pib_per_capita_usd":      "PIB per cápita (USD)",
    "exportaciones_usd":       "Exportaciones (USD)",
    "exportaciones_pct_pib":   "Exportaciones (% del PIB)",
    "trm":                     "TRM (pesos por dólar)",
    "tasa_politica_monetaria": "Tasa de política monetaria",
}
_PLAZOS_TEXTO = {"overnight": "overnight", "1m": "1 mes", "3m": "3 meses", "6m": "6 meses"}
for _plazo, _texto in _PLAZOS_TEXTO.items():
    for _tipo in ("nominal", "efectiva"):
        NOMBRES_INDICADORES[f"ibr_{_plazo}_{_tipo}"] = f"IBR {_texto} ({_tipo})"

# Cómo citar cada fuente al publicar.
FUENTES_PUBLICAS = {
    "banco_mundial": "Banco Mundial, Indicadores del Desarrollo Mundial",
    "banrep":        "Banco de la República de Colombia",
    "datos_gov_co":  "Superintendencia Financiera de Colombia (datos.gov.co)",
}
