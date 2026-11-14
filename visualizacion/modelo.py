"""
Prepara las cifras y series que dibujan el dashboard y los reels.

Todo se calcula aquí, en Python, y llega a las páginas como JSON ya listo:
las plantillas HTML solo dibujan, no calculan. Así las cifras se pueden
probar (tests/test_visualizacion.py) sin abrir un navegador.
"""
import datetime as dt
from collections import defaultdict

from visualizacion import config

PAISES_ORDEN = ["COL", "BRA", "MEX", "CHL", "PER", "ARG", "USA", "WLD"]


def _fecha(texto: str) -> dt.date:
    return dt.date.fromisoformat(texto[:10])


def nombre_corto(presidente: str) -> str:
    """'César Gaviria Trujillo' -> 'Gaviria'; 'Juan Manuel Santos Calderón' ->
    'Santos'; 'Abelardo de la Espriella' -> 'De la Espriella'."""
    if " de la " in presidente:
        return "De la " + presidente.split(" de la ", 1)[1]
    partes = presidente.split()
    return partes[2] if len(partes) >= 4 else partes[1]


def periodo_corto(periodo: str) -> str:
    """'1990-1994' -> '90–94'"""
    a, b = periodo.split("-")
    return f"{a[2:]}–{b[2:]}"


def serie(indicadores, indicador, pais="COL", fuente=None, desde=None):
    """[(fecha, valor), ...] ordenada, de un indicador/país/fuente."""
    filas = [
        (_fecha(f["fecha"]), f["valor"]) for f in indicadores
        if f["indicador"] == indicador and f["pais"] == pais
        and (fuente is None or f["fuente"] == fuente)
        and f["valor"] is not None
    ]
    filas.sort()
    if desde:
        filas = [x for x in filas if x[0] >= desde]
    return filas


def ultimo_en_o_antes(serie_ordenada, fecha):
    previos = [x for x in serie_ordenada if x[0] <= fecha]
    return previos[-1] if previos else None


def puntos_de_cambio(serie_ordenada):
    """Para series escalonadas (tasa de política): solo los días en que el valor
    cambia, más el último. 10 mil puntos -> ~100, la gráfica es idéntica."""
    salida = []
    for i, (f, v) in enumerate(serie_ordenada):
        if not salida or v != salida[-1][1] or i == len(serie_ordenada) - 1:
            salida.append((f, v))
    return salida


def mensual(serie_ordenada):
    """Último dato de cada mes (para gráficas de varias décadas en el celular)."""
    por_mes = {}
    for f, v in serie_ordenada:
        por_mes[(f.year, f.month)] = (f, v)
    return [por_mes[k] for k in sorted(por_mes)]


def _js(serie_ordenada, decimales=2):
    return [[f.isoformat(), round(v, decimales)] for f, v in serie_ordenada]


def construir(tablas: dict) -> dict:
    ind = tablas["indicadores"]
    gobiernos = sorted(tablas["gobiernos"], key=lambda g: g["inicio"])
    resumen = sorted(tablas["resumen_gobierno"], key=lambda g: g["inicio"])
    catalogo = tablas["catalogo_indicadores"]

    fecha_corte = max(_fecha(f["fecha"]) for f in ind)

    # ---------------------------------------------------------------- TRM
    trm = serie(ind, "trm", fuente="banrep")
    trm_hoy = trm[-1]
    trm_hace_un_anio = ultimo_en_o_antes(trm, trm_hoy[0].replace(year=trm_hoy[0].year - 1))
    variacion_trm = trm_hoy[1] / trm_hace_un_anio[1] - 1 if trm_hace_un_anio else None

    # ----------------------------------------------------- tasa de política
    tasa = serie(ind, "tasa_politica_monetaria", fuente="banrep")
    tasa_hoy = tasa[-1]
    tasa_hace_un_anio = ultimo_en_o_antes(tasa, tasa_hoy[0].replace(year=tasa_hoy[0].year - 1))

    # ------------------------------------------------- anuales (Banco Mundial)
    anuales = defaultdict(lambda: defaultdict(dict))      # indicador -> pais -> anio -> valor
    nombres_pais = {}
    for f in ind:
        if f["frecuencia"] == "anual" and f["valor"] is not None:
            anuales[f["indicador"]][f["pais"]][int(f["anio"])] = f["valor"]
            nombres_pais[f["pais"]] = f["pais_nombre"]

    def ultimo_anual(indicador, pais):
        datos = anuales[indicador][pais]
        if not datos:
            return None, None
        anio = max(datos)
        return anio, datos[anio]

    anio_inf, inflacion_col = ultimo_anual("inflacion_anual_pct", "COL")
    inflacion_mundo = anuales["inflacion_anual_pct"]["WLD"].get(anio_inf)
    anio_des, desempleo_col = ultimo_anual("desempleo_pct", "COL")

    # Ranking regional del último año con dato para Colombia
    region = sorted(
        [{"pais": p, "nombre": nombres_pais[p], "valor": round(v, 2)}
         for p, datos in anuales["inflacion_anual_pct"].items()
         for a, v in datos.items() if a == anio_inf],
        key=lambda x: x["valor"], reverse=True)

    # Explorador: todos los indicadores anuales, todos los países
    nombres_ind = {c["indicador"]: c["nombre_indicador"] for c in catalogo}
    unidades = {c["indicador"]: c["unidad"] for c in catalogo}
    explorador = {
        indicador: {
            "nombre": nombres_ind.get(indicador, indicador),
            "unidad": unidades.get(indicador, ""),
            "series": {p: sorted(([a, round(v, 3)] for a, v in paises[p].items()))
                       for p in PAISES_ORDEN if p in paises},
        }
        for indicador, paises in sorted(anuales.items())
    }

    # ----------------------------------------------------------- gobiernos
    gob = [{
        "presidente": g["presidente"], "corto": nombre_corto(g["presidente"]),
        "periodo": g["periodo"], "periodo_corto": periodo_corto(g["periodo"]),
        "inicio": g["inicio"][:10], "fin": g["fin"][:10],
    } for g in gobiernos]

    resumen_js = []
    for r in resumen:
        resumen_js.append({
            "presidente": r["presidente"], "corto": nombre_corto(r["presidente"]),
            "periodo": r["periodo"], "periodo_corto": periodo_corto(r["periodo"]),
            "en_curso": bool(r["en_curso"]), "anios": r["anios_con_datos"] or 0,
            "inflacion": r["inflacion_promedio"], "desempleo": r["desempleo_promedio"],
            "pib": r["crecimiento_pib_promedio"],
            "trm_inicial": r["trm_inicial"], "trm_final": r["trm_final"],
            "trm_variacion": r["trm_variacion_pct"],
            "tasa": r["tasa_politica_promedio"],
        })

    # Solo gobiernos con al menos 3 años de datos anuales (comparación justa)
    inflacion_gobierno = [r for r in resumen_js if r["inflacion"] is not None and r["anios"] >= 3]

    fuentes = {c["indicador"]: c["fuente_cita"] for c in catalogo}
    inicio_comparacion = dt.date(1986, 8, 7)

    return {
        "fecha_corte": fecha_corte.isoformat(),
        "colores": config.COLORES,
        "nota": config.NOTA_METODOLOGICA,
        "kpi": {
            "trm": round(trm_hoy[1], 2), "trm_fecha": trm_hoy[0].isoformat(),
            "trm_hace_un_anio": round(trm_hace_un_anio[1], 2) if trm_hace_un_anio else None,
            "trm_variacion": round(variacion_trm * 100, 1) if variacion_trm is not None else None,
            "tasa": tasa_hoy[1], "tasa_fecha": tasa_hoy[0].isoformat(),
            "tasa_hace_un_anio": tasa_hace_un_anio[1] if tasa_hace_un_anio else None,
            "inflacion": round(inflacion_col, 2), "inflacion_anio": anio_inf,
            "inflacion_mundo": round(inflacion_mundo, 2) if inflacion_mundo is not None else None,
            "desempleo": round(desempleo_col, 2), "desempleo_anio": anio_des,
        },
        "trm_diaria": _js([x for x in trm if x[0] >= inicio_comparacion]),
        "trm_mensual": _js(mensual([x for x in trm if x[0] >= inicio_comparacion])),
        "trm_12m": _js([x for x in trm if x[0] > trm_hoy[0].replace(year=trm_hoy[0].year - 1)]),
        "tasa_politica": _js(puntos_de_cambio(tasa)),
        "gobiernos": gob,
        "resumen": resumen_js,
        "inflacion_gobierno": inflacion_gobierno,
        "region": region,
        "inflacion_col_mundo": {
            "COL": sorted([a, round(v, 2)] for a, v in anuales["inflacion_anual_pct"]["COL"].items()),
            "WLD": sorted([a, round(v, 2)] for a, v in anuales["inflacion_anual_pct"]["WLD"].items()),
        },
        "explorador": explorador,
        "paises": {p: nombres_pais.get(p, p) for p in PAISES_ORDEN if p in nombres_pais},
        "fuentes": fuentes,
    }
