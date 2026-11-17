"""
Pruebas sin red: una sesión falsa devuelve respuestas con la misma forma
que las APIs reales. Ejecutar con:  python -m pytest -q
"""
import json

import pytest
import requests

from ingesta import banco_mundial, config, trm


class RespuestaFalsa:
    def __init__(self, datos, status=200):
        self._datos, self.status_code = datos, status

    def json(self):
        return self._datos

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(f"HTTP {self.status_code}")


class SesionFalsa:
    def __init__(self, manejador):
        self.manejador, self.llamadas = manejador, []

    def get(self, url, params=None, headers=None, timeout=None):
        self.llamadas.append((url, dict(params or {})))
        return self.manejador(url, params or {})


@pytest.fixture(autouse=True)
def raw_temporal(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RAW_DIR", tmp_path / "raw")
    return tmp_path / "raw"


def leer_jsonl(ruta):
    return [json.loads(l) for l in ruta.read_text(encoding="utf-8").splitlines()]


# ---------------------------------------------------------------- TRM
def fila_trm(i):
    return {"valor": f"{4000 + i}.00", "unidad": "COP",
            "vigenciadesde": f"2026-01-{(i % 28) + 1:02d}T00:00:00.000",
            "vigenciahasta": f"2026-01-{(i % 28) + 1:02d}T00:00:00.000"}


def test_trm_pagina_hasta_pagina_incompleta(monkeypatch):
    monkeypatch.setattr(config, "TRM_TAMANO_PAGINA", 3)
    filas = [fila_trm(i) for i in range(7)]  # 3 + 3 + 1

    def manejador(url, p):
        return RespuestaFalsa(filas[p["$offset"]:p["$offset"] + p["$limit"]])

    sesion = SesionFalsa(manejador)
    archivo = trm.ejecutar(desde="2026-01-01", sesion=sesion)

    assert len(sesion.llamadas) == 3
    assert [p["$offset"] for _, p in sesion.llamadas] == [0, 3, 6]
    assert sesion.llamadas[0][1]["$where"] == "vigenciadesde >= '2026-01-01T00:00:00'"

    registros = leer_jsonl(archivo)
    assert len(registros) == 7
    assert registros[0]["payload"] == filas[0]            # payload intacto
    assert registros[0]["id_registro"] == "trm|2026-01-01"
    assert archivo.parent.name.startswith("fecha_ingesta=")
    assert archivo.parent.parent.name == "trm"


def test_trm_sin_datos_no_crea_archivo(raw_temporal):
    assert trm.ejecutar(sesion=SesionFalsa(lambda u, p: RespuestaFalsa([]))) is None
    assert not raw_temporal.exists()


# ---------------------------------------------------------- Banco Mundial
def fila_bm(cod, pais, anio, valor):
    return {"indicator": {"id": cod, "value": "x"},
            "country": {"id": pais[:2], "value": pais},
            "countryiso3code": pais, "date": str(anio), "value": valor,
            "unit": "", "obs_status": "", "decimal": 1}


def test_banco_mundial_pagina_y_guarda_por_indicador(monkeypatch):
    monkeypatch.setattr(config, "BM_TAMANO_PAGINA", 2)
    cod = "FP.CPI.TOTL.ZG"
    filas = [fila_bm(cod, "COL", a, 5.0) for a in (2023, 2022, 2021)]

    def manejador(url, p):
        assert url.endswith(f"/country/COL;WLD/indicator/{cod}")
        pag = p["page"]
        meta = {"page": pag, "pages": 2, "per_page": 2, "total": 3}
        return RespuestaFalsa([meta, filas[(pag - 1) * 2: pag * 2]])

    archivos = banco_mundial.ejecutar(
        anio_desde=2021, anio_hasta=2023, paises=["COL", "WLD"],
        indicadores={cod: "inflacion_anual_pct"}, sesion=SesionFalsa(manejador))

    registros = leer_jsonl(archivos[0])
    assert len(registros) == 3
    assert registros[0]["id_registro"] == f"{cod}|COL|2023"
    assert archivos[0].parent.parent.name == "inflacion_anual_pct"
    manifiesto = next(archivos[0].parent.glob("_manifiesto_*.json"))
    assert json.loads(manifiesto.read_text())["registros"] == 3


def test_banco_mundial_codigo_invalido_responde_200_con_mensaje():
    """La API devuelve 200 + mensaje cuando el indicador no existe."""
    malo = [{"message": [{"id": "120", "key": "Invalid value",
                          "value": "The provided parameter value is not valid"}]}]
    bueno = lambda c: [{"page": 1, "pages": 1}, [fila_bm(c, "COL", 2023, 1.0)]]

    def manejador(url, p):
        return RespuestaFalsa(malo if "NO.EXISTE" in url else bueno("SL.UEM.TOTL.ZS"))

    with pytest.raises(RuntimeError, match="NO.EXISTE"):
        banco_mundial.ejecutar(
            paises=["COL"], anio_desde=2023, anio_hasta=2023,
            indicadores={"NO.EXISTE": "malo", "SL.UEM.TOTL.ZS": "desempleo_pct"},
            sesion=SesionFalsa(manejador), pausa_reintento=0)
    # el indicador bueno sí se guardó aunque el otro fallara
    assert list(config.RAW_DIR.glob("banco_mundial/desempleo_pct/*/*.jsonl"))


def test_banco_mundial_reintenta_los_que_fallaron():
    """Una caída momentánea (503) se recupera en el segundo intento."""
    cod = "FP.CPI.TOTL.ZG"
    llamadas = {"n": 0}

    def manejador(url, p):
        llamadas["n"] += 1
        if llamadas["n"] == 1:
            raise requests.ConnectionError("503 momentáneo")
        return RespuestaFalsa([{"page": 1, "pages": 1}, [fila_bm(cod, "COL", 2025, 5.1)]])

    archivos = banco_mundial.ejecutar(
        anio_desde=2025, anio_hasta=2025, paises=["COL"],
        indicadores={cod: "inflacion_anual_pct"}, sesion=SesionFalsa(manejador),
        pausa_reintento=0)
    assert len(archivos) == 1 and llamadas["n"] == 2
