"""Pruebas de la capa de visualización (Paso 7). No necesitan Docker ni navegador."""
import json

import pytest

pytest.importorskip("jinja2")

from visualizacion import datos, generar, modelo


def _fila(indicador, pais, fecha, valor, frecuencia="diaria", fuente="banrep"):
    return {"indicador": indicador, "nombre_indicador": indicador, "pais": pais,
            "pais_nombre": {"COL": "Colombia", "WLD": "Mundo", "BRA": "Brasil"}[pais],
            "fecha": fecha, "anio": int(fecha[:4]), "frecuencia": frecuencia, "valor": valor,
            "unidad": "", "presidente": None, "periodo": None, "fuente": fuente, "fuente_cita": "x"}


@pytest.fixture
def tablas():
    ind = [
        _fila("trm", "COL", "2024-06-01", 4000.0), _fila("trm", "COL", "2025-06-01", 4200.0),
        _fila("trm", "COL", "2025-06-02", 4100.0),
        _fila("tasa_politica_monetaria", "COL", "2024-06-01", 11.0),
        _fila("tasa_politica_monetaria", "COL", "2025-06-02", 9.25),
    ]
    for pais, base in (("COL", 5.0), ("WLD", 3.0), ("BRA", 4.0)):
        for anio in (2022, 2023, 2024):
            ind.append(_fila("inflacion_anual_pct", pais, f"{anio}-12-31", base + anio - 2022,
                             "anual", "banco_mundial"))
    ind.append(_fila("desempleo_pct", "COL", "2024-12-31", 9.0, "anual", "banco_mundial"))
    gob = [{"presidente": "Gustavo Petro Urrego", "periodo": "2022-2026",
            "inicio": "2022-08-07", "fin": "2026-08-07"}]
    res = [{"presidente": "Gustavo Petro Urrego", "periodo": "2022-2026", "inicio": "2022-08-07",
            "fin": "2026-08-07", "en_curso": False, "inflacion_promedio": 6.0,
            "desempleo_promedio": 9.0, "crecimiento_pib_promedio": 1.5, "anios_con_datos": 3,
            "trm_inicial": 4300.0, "trm_final": 4100.0, "trm_variacion_pct": -4.7,
            "tasa_politica_promedio": 10.0}]
    cat = [{"indicador": i, "nombre_indicador": i, "unidad": "%", "fuente_cita": "Banco Mundial"}
           for i in ("inflacion_anual_pct", "desempleo_pct")]
    return {"indicadores": ind, "gobiernos": gob, "resumen_gobierno": res, "catalogo_indicadores": cat}


@pytest.mark.parametrize("nombre, corto", [
    ("César Gaviria Trujillo", "Gaviria"), ("Juan Manuel Santos Calderón", "Santos"),
    ("Abelardo de la Espriella", "De la Espriella"), ("Gustavo Petro Urrego", "Petro"),
])
def test_nombre_corto(nombre, corto):
    assert modelo.nombre_corto(nombre) == corto


def test_periodo_corto():
    assert modelo.periodo_corto("1990-1994") == "90–94"


def test_construir_kpis(tablas):
    d = modelo.construir(tablas)
    k = d["kpi"]
    assert d["fecha_corte"] == "2025-06-02"
    assert k["trm"] == 4100.0 and k["trm_hace_un_anio"] == 4000.0 and k["trm_variacion"] == 2.5
    assert k["tasa"] == 9.25 and k["tasa_hace_un_anio"] == 11.0
    assert k["inflacion_anio"] == 2024 and k["inflacion"] == 7.0 and k["inflacion_mundo"] == 5.0
    assert [r["pais"] for r in d["region"]] == ["COL", "BRA", "WLD"]      # de mayor a menor
    assert d["inflacion_gobierno"][0]["corto"] == "Petro"


def test_generar_paginas_autocontenidas(tablas, tmp_path):
    carpeta = tmp_path / "json"
    datos.guardar_json(tablas, carpeta)
    escritos = generar.generar(str(carpeta), tmp_path / "salida", motor="echarts")
    assert len(escritos) == 1 + len(generar.REELS)
    for ruta in escritos:
        html = ruta.read_text(encoding="utf-8")
        assert "<script src=" not in html and "https://" not in html.split("<script>")[0]
        assert "@font-face" in html and "const D = " in html
    # ningún '</script>' accidental dentro de los datos incrustados
    dash = (tmp_path / "salida" / "dashboard.html").read_text(encoding="utf-8")
    bloque = dash.split("const D = ", 1)[1].split(";</script>", 1)[0]
    assert "</" not in bloque
    assert json.loads(bloque.replace("<\\/", "</"))["kpi"]["trm"] == 4100.0


def test_seguro_en_script():
    assert generar._seguro_en_script('a</script>b') == 'a<\\/script>b'


def test_generar_con_plotly(tablas, tmp_path):
    carpeta = tmp_path / "json"
    datos.guardar_json(tablas, carpeta)
    escritos = generar.generar(str(carpeta), tmp_path / "plotly", motor="plotly")
    assert len(escritos) == 1 + len(generar.REELS)
    dash = (tmp_path / "plotly" / "dashboard.html").read_text(encoding="utf-8")
    assert "Plotly.register(module.exports)" in dash and "Plotly.newPlot" in dash
    assert "echarts.init" not in dash and "(Plotly.js)" in dash
    reel = (tmp_path / "plotly" / "reels" / "03_dolar_historia.html").read_text(encoding="utf-8")
    assert "El dólar a través de" in reel and "franjasGobierno" in reel


def test_motor_desconocido(tablas, tmp_path):
    with pytest.raises(ValueError):
        generar.generar("x", tmp_path, motor="d3")
