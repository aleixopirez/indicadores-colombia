"""
Pruebas del Paso 4 con Spark real (modo local) y datos pequeños.

Requieren PySpark y Java. En Windows sin Java se OMITEN automáticamente;
corren dentro del contenedor de Spark o en cualquier equipo con Java:
    docker compose run --rm spark bash -c "pip install -q pytest && python3 -m pytest -q tests/test_procesamiento.py"
"""
import json

import pytest

pyspark = pytest.importorskip("pyspark")

from pyspark.sql import functions as F  # noqa: E402

from procesamiento import transformaciones as tr  # noqa: E402


@pytest.fixture(scope="module")
def spark():
    s = tr.crear_sesion("pruebas", master="local[1]")
    s.sparkContext.setLogLevel("ERROR")
    yield s
    s.stop()


def sobre(fuente, dataset, id_registro, payload, fecha_ingesta="2026-11-06T15:00:00Z"):
    return json.dumps({"fuente": fuente, "dataset": dataset, "id_registro": id_registro,
                       "fecha_ingesta": fecha_ingesta, "payload": payload})


def lineas(spark, *textos):
    return spark.createDataFrame([(t,) for t in textos], ["value"])


def banrep(id_, fecha, valor, subject="IRIBRM00", unidad="NR", dataset="ibr", ingesta=None):
    payload = {"TIME_PERIOD": fecha, "OBS_VALUE": valor, "atributos_obs": {},
               "serie": {"REFERENCE_AREA": "CO", "SUBJECT": subject, "UNIT_MEASURE": unidad,
                         "FREQ": "D"},
               "atributos_serie": {}}
    return sobre("banrep", dataset, id_, payload, ingesta or "2026-11-06T15:00:00Z")


# ------------------------------------------------------------------ pruebas
def test_linea_invalida_se_descarta(spark):
    df = tr.leer_sobres(lineas(spark, "{no es json", banrep("a", "20260101", "1")))
    assert df.count() == 1


def test_deduplicar_conserva_la_ingesta_mas_reciente(spark):
    df = tr.deduplicar(tr.leer_sobres(lineas(
        spark,
        banrep("x", "20260101", "9.0", ingesta="2026-11-06T14:00:00Z"),
        banrep("x", "20260101", "9.5", ingesta="2026-11-06T15:00:00Z"),
        banrep("y", "20260102", "8.0"),
    )))
    assert df.count() == 2
    payload = json.loads(df.where("id_registro = 'x'").first()["payload"])
    assert payload["OBS_VALUE"] == "9.5"


def test_trm_gov_expande_el_rango_de_vigencia(spark):
    """La TRM del viernes rige viernes, sábado, domingo y lunes festivo."""
    payload = {"valor": "4000.5", "unidad": "COP",
               "vigenciadesde": "2026-11-13T00:00:00.000",
               "vigenciahasta": "2026-11-16T00:00:00.000"}
    etapas = tr.curar(lineas(spark, sobre("datos_gov_co", "trm", "trm|2026-11-13", payload)))
    filas = etapas["curado"].orderBy("fecha").collect()
    assert [str(f["fecha"]) for f in filas] == [
        "2026-11-13", "2026-11-14", "2026-11-15", "2026-11-16"]
    assert all(f["valor"] == 4000.5 and f["indicador"] == "trm" for f in filas)


def test_banrep_separa_series_por_catalogo(spark):
    etapas = tr.curar(lineas(
        spark,
        banrep("1", "20080102", "9.498", "IRIBRM00", "NR"),
        banrep("2", "20080102", "9.900", "IRIBRM00", "ER"),
        banrep("3", "20080102", "9.600", "IRIBRM03", "NR"),
    ))
    indicadores = {r["indicador"]: r["valor"] for r in etapas["curado"].collect()}
    assert indicadores == {"ibr_overnight_nominal": 9.498,
                           "ibr_overnight_efectiva": 9.9,
                           "ibr_3m_nominal": 9.6}
    fila = etapas["curado"].first()
    assert str(fila["fecha"]) == "2008-01-02" and fila["anio"] == 2008


def test_serie_fuera_del_catalogo_no_se_pierde(spark):
    etapas = tr.curar(lineas(spark, banrep("1", "20260101", "5", "NUEVA", "XX")))
    assert etapas["curado"].first()["indicador"] == "ibr_NUEVA_XX"
    assert etapas["curado"].first()["unidad"] == "sin catálogo"


def test_valores_y_fechas_invalidos_se_cuentan_y_descartan(spark):
    """Con ANSI activo, un cast directo detendría el trabajo completo."""
    etapas = tr.curar(lineas(
        spark,
        banrep("ok", "20260101", "5.0"),
        banrep("sin_valor", "20260102", "n/d"),
        banrep("sin_fecha", "2026-99-99", "5.0"),
    ))
    assert [r["id_registro"] for r in etapas["curado"].collect()] == ["ok"]
    rep = tr.reporte_calidad(etapas).first()
    assert (rep["leidos"], rep["sin_valor"], rep["sin_fecha"], rep["filas_curadas"]) == (3, 1, 1, 1)


def test_banco_mundial_fecha_al_cierre_del_anio_y_nulos(spark):
    def bm(id_, pais, anio, valor):
        return sobre("banco_mundial", "inflacion_anual_pct", id_, {
            "indicator": {"id": "FP.CPI.TOTL.ZG"}, "country": {"value": "Colombia"},
            "countryiso3code": pais, "date": anio, "value": valor})

    etapas = tr.curar(lineas(spark, bm("a", "COL", "2023", 11.74), bm("b", "COL", "2024", None)))
    filas = etapas["curado"].collect()
    assert len(filas) == 1                                    # el año sin dato se descarta
    f = filas[0]
    assert (str(f["fecha"]), f["anio"], f["pais"], f["pais_nombre"], f["unidad"]) == (
        "2023-12-31", 2023, "COL", "Colombia", "% anual")


def test_conciliacion_trm_detecta_diferencias(spark):
    def gov(fecha, valor):
        return sobre("datos_gov_co", "trm", f"trm|{fecha}", {
            "valor": valor, "unidad": "COP",
            "vigenciadesde": f"{fecha}T00:00:00.000", "vigenciahasta": f"{fecha}T00:00:00.000"})

    etapas = tr.curar(lineas(
        spark,
        gov("2026-11-05", "3230.00"), gov("2026-11-06", "3228.26"),
        banrep("b1", "20261105", "3230.00", "CCSP", "COP", "trm_banrep"),
        banrep("b2", "20261106", "3299.99", "CCSP", "COP", "trm_banrep"),
    ))
    r = tr.conciliar_trm(etapas["curado"]).first()
    assert (r["dias_comparados"], r["dias_distintos"]) == (2, 1)
    assert r["diferencia_maxima"] == pytest.approx(71.73)


def test_esquema_curado_es_el_mismo_para_todas_las_fuentes(spark):
    etapas = tr.curar(lineas(spark, banrep("1", "20260101", "5")))
    assert etapas["curado"].columns == tr.COLUMNAS_CURADAS
    tipos = dict(etapas["curado"].dtypes)
    assert (tipos["fecha"], tipos["valor"], tipos["anio"]) == ("date", "double", "int")
