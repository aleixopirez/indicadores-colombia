"""
Genera las páginas HTML autocontenidas (sin internet) a partir de las tablas
de servicio: el dashboard interactivo y los reels verticales 1080×1920.
"""
import base64
import json
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import config, datos, modelo

REELS = [
    "01_portada", "02_inflacion_gobiernos", "03_dolar_historia", "04_region", "05_tasa_banrep",
]


def _seguro_en_script(texto: str) -> str:
    """Evita que un '</script>' dentro del JS o del JSON cierre la etiqueta.
    También escribe el carácter U+FFFD como escape: Plotly lo trae literal y
    algunos servidores lo rechazan por parecer UTF-8 dañado."""
    return texto.replace("</", "<\\/").replace("\ufffd", "\\ufffd")


def _fuentes() -> dict:
    carpeta = config.BASE / "vendor" / "fuentes"
    return {peso: base64.b64encode((carpeta / f"inter-latin-{peso}-normal.woff2").read_bytes()).decode()
            for peso in (400, 600, 800)}


# Dos "motores" de gráficas con las mismas plantillas HTML:
#   echarts -> plantillas/            (Apache ECharts, licencia Apache 2.0)
#   plotly  -> plantillas/plotly/     (Plotly.js, licencia MIT; hereda de las de ECharts
#                                      y solo reemplaza el código de las gráficas)
MOTORES = {
    "echarts": {"nombre": "Apache ECharts", "prefijo": "", "comun": "_comun_echarts.js"},
    "plotly": {"nombre": "Plotly.js", "prefijo": "plotly/", "comun": "_comun_plotly.js"},
}


def _leer(ruta: Path) -> str:
    return ruta.read_text(encoding="utf-8")


def _libreria(motor: str) -> str:
    vendor = config.BASE / "vendor"
    if motor == "echarts":
        return _leer(vendor / "echarts.min.js")
    # Plotly + textos en español. El archivo de idioma es un módulo CommonJS:
    # se envuelve para registrarlo sin tocar la variable global "module".
    return (_leer(vendor / "plotly-basic.min.js")
            + "\n;(function(){var module={exports:{}};\n"
            + _leer(vendor / "plotly-locale-es.js")
            + "\nPlotly.register(module.exports);})();")


def contexto(d: dict, motor: str = "plotly") -> dict:
    """Variables comunes a todas las plantillas."""
    from markupsafe import Markup
    m = MOTORES[motor]
    return {
        "datos": Markup(_seguro_en_script(json.dumps(d, ensure_ascii=False, separators=(",", ":")))),
        "libreria": Markup(_seguro_en_script(_libreria(motor))),
        "nombre_libreria": m["nombre"],
        "formato": Markup(_seguro_en_script(_leer(config.PLANTILLAS / "_formato.js"))),
        "comun": Markup(_seguro_en_script(_leer(config.PLANTILLAS / m["comun"]))),
        "fuentes": _fuentes(),
        "c": d["colores"],
        "reel": config.REEL,
        "duracion_ms": config.DURACION_REEL_MS,
        "nota": d["nota"],
        "autor": config.AUTOR,
        "anio_corte": d["fecha_corte"][:4],
        "n_gobiernos": len(d["gobiernos"]),
        "primero": d["inflacion_gobierno"][0]["periodo"][:4] if d["inflacion_gobierno"] else "",
        "ultimo": d["inflacion_gobierno"][-1]["periodo"][-4:] if d["inflacion_gobierno"] else "",
        "anio_inflacion": d["kpi"]["inflacion_anio"],
        "anio_tasa": d["tasa_politica"][0][0][:4] if d["tasa_politica"] else "",
    }


def generar(origen: str = "postgres", salida: Path | None = None, motor: str | None = None) -> list[Path]:
    motor = motor or config.MOTOR
    if motor not in MOTORES:
        raise ValueError(f"motor desconocido: {motor} (use {', '.join(MOTORES)})")
    # El motor por defecto escribe en salida/; el otro, en salida/<motor>/
    salida = Path(salida or (config.SALIDA if motor == config.MOTOR else config.SALIDA / motor))
    (salida / "reels").mkdir(parents=True, exist_ok=True)

    tablas = datos.cargar(origen)
    d = modelo.construir(tablas)
    ctx = contexto(d, motor)
    prefijo = MOTORES[motor]["prefijo"]

    env = Environment(loader=FileSystemLoader(config.PLANTILLAS),
                      autoescape=select_autoescape(["html"]))
    escritos = []

    destino = salida / "dashboard.html"
    destino.write_text(env.get_template(f"{prefijo}dashboard.html").render(**ctx), encoding="utf-8")
    escritos.append(destino)

    for nombre in REELS:
        destino = salida / "reels" / f"{nombre}.html"
        destino.write_text(env.get_template(f"{prefijo}reels/{nombre}.html").render(**ctx), encoding="utf-8")
        escritos.append(destino)

    # Copia de los datos usados (trazabilidad: qué cifras salieron en cada reel)
    (salida / "datos_visualizacion.json").write_text(
        json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return escritos
