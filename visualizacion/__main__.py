"""
Capa de visualización HTML (Paso 7).

  python -m visualizacion generar                 # lee PostgreSQL (zona servicio)
  python -m visualizacion generar --origen DIR    # o JSON exportados (sin Docker)
  python -m visualizacion generar --motor echarts # versión con ECharts (en salida/echarts)
  python -m visualizacion exportar DIR            # guarda las tablas de Postgres en JSON
  python -m visualizacion capturar [--sin-video] [--solo portada]
  python -m visualizacion todo                    # generar + capturar
  python -m visualizacion publicar                # copia el dashboard a docs/index.html (GitHub Pages)
"""
import argparse
from pathlib import Path

from . import config


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m visualizacion", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--salida", type=Path, default=None,
                    help="carpeta de salida (por defecto: salida; con el motor no predeterminado, salida/<motor>)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generar", help="crear dashboard.html y los reels HTML")
    g.add_argument("--origen", default="postgres", help="'postgres' o una carpeta con los JSON")
    g.add_argument("--motor", choices=["plotly", "echarts"], default=None, help="librería de gráficas")

    e = sub.add_parser("exportar", help="guardar las tablas de servicio en JSON")
    e.add_argument("carpeta", type=Path)

    c = sub.add_parser("capturar", help="reels HTML → PNG y MP4")
    c.add_argument("--sin-video", action="store_true")
    c.add_argument("--motor", choices=["plotly", "echarts"], default=None)
    c.add_argument("--solo", nargs="*", help="parte del nombre del reel, p. ej. portada region")

    t = sub.add_parser("todo", help="generar + capturar")
    t.add_argument("--origen", default="postgres")
    t.add_argument("--sin-video", action="store_true")
    t.add_argument("--motor", choices=["plotly", "echarts"], default=None)

    pb = sub.add_parser("publicar", help="copiar salida/dashboard.html a docs/index.html (GitHub Pages)")
    pb.add_argument("--docs", type=Path, default=Path("docs"))

    a = ap.parse_args()
    motor = getattr(a, "motor", None) or config.MOTOR
    salida = a.salida or (config.SALIDA if motor == config.MOTOR else config.SALIDA / motor)
    if a.cmd in ("generar", "todo"):
        from .generar import generar
        for ruta in generar(a.origen, salida, motor):
            print(f"  HTML {ruta}")
    if a.cmd == "exportar":
        from . import datos
        datos.guardar_json(datos.cargar_postgres(), a.carpeta)
        print(f"Tablas guardadas en {a.carpeta}")
    if a.cmd == "publicar":
        import shutil
        origen = salida / "dashboard.html"
        if not origen.exists():
            raise SystemExit(f"No existe {origen}. Ejecute primero: python -m visualizacion generar")
        a.docs.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origen, a.docs / "index.html")
        (a.docs / ".nojekyll").touch()      # GitHub Pages sirve el HTML tal cual, sin Jekyll
        print(f"Copiado a {a.docs / 'index.html'}. Ahora: git add docs && git commit -m \"Actualiza dashboard\" && git push")
    if a.cmd in ("capturar", "todo"):
        from .capturar import capturar
        capturar(salida, video=not a.sin_video, solo=getattr(a, "solo", None))


if __name__ == "__main__":
    main()
