"""
Lectura de la zona de servicio.

Dos orígenes con el mismo resultado (dict tabla -> lista de filas):
  - "postgres": las tablas servicio.* que cargó Spark en el Paso 6 (lo normal)
  - una carpeta con <tabla>.json: para trabajar sin la base encendida, para
    pruebas, o para que un estudiante practique solo la visualización.

Se usa pg8000 (driver 100 % Python): instala en cualquier Windows sin
compilar nada.
"""
import datetime as dt
import decimal
import json
from pathlib import Path

from visualizacion import config


def _normalizar(valor):
    if isinstance(valor, decimal.Decimal):
        return float(valor)
    if isinstance(valor, (dt.date, dt.datetime)):
        return valor.isoformat()[:10]
    return valor


def cargar_postgres(parametros: dict = None) -> dict:
    import pg8000.native
    p = parametros or config.POSTGRES
    con = pg8000.native.Connection(**p)
    try:
        tablas = {}
        for tabla in config.TABLAS:
            filas = con.run(f"SELECT * FROM {config.ESQUEMA}.{tabla}")
            columnas = [c["name"] for c in con.columns]
            tablas[tabla] = [dict(zip(columnas, map(_normalizar, f))) for f in filas]
        return tablas
    finally:
        con.close()


def cargar_json(carpeta) -> dict:
    carpeta = Path(carpeta)
    return {t: json.loads((carpeta / f"{t}.json").read_text(encoding="utf-8"))
            for t in config.TABLAS}


def guardar_json(tablas: dict, carpeta) -> None:
    """Instantánea de la zona de servicio (útil para clase o respaldo)."""
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    for nombre, filas in tablas.items():
        (carpeta / f"{nombre}.json").write_text(
            json.dumps(filas, ensure_ascii=False, default=_normalizar), encoding="utf-8")


def cargar(origen: str = "postgres") -> dict:
    return cargar_postgres() if origen == "postgres" else cargar_json(origen)
