"""
Pruebas del Paso 6 (construcción de las tablas de servicio) con Spark real.
La escritura en PostgreSQL no se prueba aquí: necesita la base encendida.
Se omiten en Windows sin Java, igual que tests/test_procesamiento.py.
"""
import datetime as dt

import pytest

pytest.importorskip("pyspark")

from procesamiento import servir  # noqa: E402
from procesamiento.transformaciones import COLUMNAS_CURADAS, crear_sesion  # noqa: E402

D = dt.date


@pytest.fixture(scope="module")
def spark():
    s = crear_sesion("pruebas-servir", master="local[1]")
    s.sparkContext.setLogLevel("ERROR")
    yield s
    s.stop()


@pytest.fixture
def gobiernos(spark):
    return spark.createDataFrame([
        ("Presidente A", "2018-2022", D(2018, 8, 7), D(2022, 8, 7)),
        ("Presidente B", "2022-2026", D(2022, 8, 7), D(2026, 8, 7)),
        ("Presidente C", "2026-2030", D(2026, 8, 7), D(2030, 8, 7)),
    ], schema=servir.ESQUEMA_GOBIERNOS)


def fila(indicador, pais, fecha, frecuencia, valor, fuente="banco_mundial", pais_nombre=None):
    return {"indicador": indicador, "pais": pais, "pais_nombre": pais_nombre or pais,
            "fecha": fecha, "anio": fecha.year, "frecuencia": frecuencia, "valor": valor,
            "unidad": "u", "fuente": fuente, "dataset": indicador, "id_registro": "x",
            "fecha_ingesta": dt.datetime(2026, 11, 6)}


def curado(spark, filas):
    return spark.createDataFrame(filas).select(*COLUMNAS_CURADAS)


def test_regla_anual_mayor_parte_del_anio(spark, gobiernos):
    """2022 -> A (gobernó ene-ago); 2023 -> B."""
    df = curado(spark, [
        fila("inflacion_anual_pct", "COL", D(2022, 12, 31), "anual", 10.0),
        fila("inflacion_anual_pct", "COL", D(2023, 12, 31), "anual", 11.0),
    ])
    t = servir.tabla_indicadores(df, gobiernos)
    asignado = {r["anio"]: r["presidente"] for r in t.collect()}
    assert asignado == {2022: "Presidente A", 2023: "Presidente B"}


def test_regla_diaria_por_fecha_exacta_fin_excluido(spark, gobiernos):
    df = curado(spark, [
        fila("trm", "COL", D(2022, 8, 6), "diaria", 4000.0, "banrep"),
        fila("trm", "COL", D(2022, 8, 7), "diaria", 4100.0, "banrep"),   # día de posesión
    ])
    asignado = {str(r["fecha"]): r["periodo"]
                for r in servir.tabla_indicadores(df, gobiernos).collect()}
    assert asignado == {"2022-08-06": "2018-2022", "2022-08-07": "2022-2026"}


def test_solo_colombia_tiene_gobierno_y_nombres_en_espanol(spark, gobiernos):
    df = curado(spark, [
        fila("inflacion_anual_pct", "BRA", D(2023, 12, 31), "anual", 4.6, pais_nombre="Brazil"),
        fila("inflacion_anual_pct", "WLD", D(2023, 12, 31), "anual", 5.0, pais_nombre="World"),
    ])
    filas = {r["pais"]: r for r in servir.tabla_indicadores(df, gobiernos).collect()}
    assert filas["BRA"]["pais_nombre"] == "Brasil" and filas["BRA"]["presidente"] is None
    assert filas["WLD"]["pais_nombre"] == "Mundo"
    assert filas["BRA"]["nombre_indicador"] == "Inflación anual"
    assert filas["BRA"]["fuente_cita"].startswith("Banco Mundial")


def test_resumen_por_gobierno(spark, gobiernos):
    df = curado(spark, [
        fila("inflacion_anual_pct", "COL", D(2023, 12, 31), "anual", 10.0),
        fila("inflacion_anual_pct", "COL", D(2024, 12, 31), "anual", 6.0),
        fila("desempleo_pct", "COL", D(2023, 12, 31), "anual", 9.0),
        fila("trm", "COL", D(2022, 8, 8), "diaria", 4000.0, "banrep"),
        fila("trm", "COL", D(2026, 8, 6), "diaria", 3000.0, "banrep"),
        fila("trm", "COL", D(2024, 1, 2), "diaria", 9999.0, "datos_gov_co"),   # otra fuente: se ignora
        fila("tasa_politica_monetaria", "COL", D(2023, 1, 2), "diaria", 12.0, "banrep"),
        fila("tasa_politica_monetaria", "COL", D(2024, 1, 2), "diaria", 10.0, "banrep"),
    ])
    tablas = servir.construir_tablas(df, gobiernos)
    r = {x["periodo"]: x for x in tablas["resumen_gobierno"].collect()}

    b = r["2022-2026"]
    assert (b["inflacion_promedio"], b["desempleo_promedio"], b["anios_con_datos"]) == (8.0, 9.0, 2)
    assert (b["trm_inicial"], b["trm_final"], b["trm_variacion_pct"]) == (4000.0, 3000.0, -25.0)
    assert (b["tasa_politica_promedio"], b["tasa_politica_minima"], b["tasa_politica_maxima"]) == (11.0, 10.0, 12.0)
    assert r["2018-2022"]["inflacion_promedio"] is None          # sin datos: NULL, no 0
    assert r["2026-2030"]["en_curso"] is True and r["2018-2022"]["en_curso"] is False


def test_catalogo_lista_cada_indicador_con_su_fuente(spark, gobiernos):
    df = curado(spark, [
        fila("trm", "COL", D(2024, 1, 2), "diaria", 4000.0, "banrep"),
        fila("trm", "COL", D(2024, 1, 2), "diaria", 4000.0, "datos_gov_co"),
    ])
    cat = servir.construir_tablas(df, gobiernos)["catalogo_indicadores"].collect()
    assert sorted((c["indicador"], c["fuente"]) for c in cat) == [
        ("trm", "banrep"), ("trm", "datos_gov_co")]
    assert all(c["nombre_indicador"] == "TRM (pesos por dólar)" for c in cat)
