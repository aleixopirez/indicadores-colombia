"""
Punto de entrada por consola.

    python -m ingesta trm                          # toda la historia
    python -m ingesta trm --desde 2026-10-01       # incremental
    python -m ingesta banco_mundial --desde 1990 --hasta 2025
    python -m ingesta banrep --listar              # catálogo de flujos SDMX
    python -m ingesta banrep --desde 2020
    python -m ingesta todo
    python -m ingesta -v todo                      # -v va ANTES de la fuente
"""
import argparse
import logging
import sys

from ingesta import banco_mundial, banrep, trm


def main(argv=None):
    parser = argparse.ArgumentParser(prog="ingesta", description="Paso 1: extracción a zona raw")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="fuente", required=True)

    p_trm = sub.add_parser("trm", help="TRM diaria (datos.gov.co)")
    p_trm.add_argument("--desde", help="YYYY-MM-DD")
    p_trm.add_argument("--hasta", help="YYYY-MM-DD")

    p_bm = sub.add_parser("banco_mundial", help="Indicadores del Banco Mundial")
    p_bm.add_argument("--desde", type=int, default=None, help="año inicial")
    p_bm.add_argument("--hasta", type=int, default=None, help="año final")

    p_br = sub.add_parser("banrep", help="Banco de la República (SDMX)")
    p_br.add_argument("--desde", help="YYYY, YYYY-MM o YYYY-MM-DD")
    p_br.add_argument("--hasta", help="YYYY, YYYY-MM o YYYY-MM-DD")
    p_br.add_argument("--listar", action="store_true",
                      help="muestra los flujos disponibles y termina")

    sub.add_parser("todo", help="Todas las fuentes con valores por defecto")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

    if args.fuente == "banrep" and args.listar:
        for f in banrep.listar_flujos():
            print(f"{f['id']:<32} {f['nombre']}")
        return 0

    errores = []

    def correr(nombre, funcion, **kwargs):
        # Una fuente caída no impide intentar las demás en "todo".
        try:
            funcion(**kwargs)
        except Exception as e:  # noqa: BLE001
            logging.getLogger("ingesta").error("%s terminó con error: %s", nombre, e)
            errores.append(nombre)

    desde = getattr(args, "desde", None)
    hasta = getattr(args, "hasta", None)

    if args.fuente in ("trm", "todo"):
        correr("trm", trm.ejecutar, desde=desde, hasta=hasta)
    if args.fuente in ("banco_mundial", "todo"):
        kwargs = {k: v for k, v in (("anio_desde", desde), ("anio_hasta", hasta)) if v}
        correr("banco_mundial", banco_mundial.ejecutar, **kwargs)
    if args.fuente in ("banrep", "todo"):
        correr("banrep", banrep.ejecutar, desde=desde, hasta=hasta)

    # Código de salida != 0 para que Airflow marque la tarea como fallida.
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
