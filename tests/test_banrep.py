"""
Pruebas sin red del extractor del Banco de la República (SDMX 2.1).
Los XML de ejemplo siguen la estructura del estándar SDMX 2.1.
"""
import json

import pytest

from ingesta import banrep, config
from ingesta.__main__ import main


class RespuestaXML:
    def __init__(self, contenido: bytes, status=200):
        self.content, self.status_code = contenido, status

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


XML_GENERICO = b"""<?xml version="1.0" encoding="UTF-8"?>
<message:GenericData
  xmlns:message="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
  xmlns:generic="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/data/generic">
  <message:Header><message:ID>IREF1</message:ID></message:Header>
  <message:DataSet>
    <generic:Series>
      <generic:SeriesKey>
        <generic:Value id="FREQ" value="D"/>
        <generic:Value id="TRM_TYPE" value="TRM"/>
      </generic:SeriesKey>
      <generic:Attributes><generic:Value id="UNIT_MEASURE" value="COP"/></generic:Attributes>
      <generic:Obs>
        <generic:ObsDimension value="2026-11-03"/>
        <generic:ObsValue value="4010.12"/>
      </generic:Obs>
      <generic:Obs>
        <generic:ObsDimension value="2026-11-04"/>
        <generic:ObsValue value="4012.35"/>
        <generic:Attributes><generic:Value id="OBS_STATUS" value="A"/></generic:Attributes>
      </generic:Obs>
    </generic:Series>
  </message:DataSet>
</message:GenericData>"""

XML_ESPECIFICO = b"""<?xml version="1.0" encoding="UTF-8"?>
<message:StructureSpecificData
  xmlns:message="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message">
  <message:DataSet>
    <Series FREQ="D" IBR_TERM="ON">
      <Obs TIME_PERIOD="2026-11-04" OBS_VALUE="9.25" OBS_STATUS="A"/>
    </Series>
  </message:DataSet>
</message:StructureSpecificData>"""

XML_FLUJOS = b"""<?xml version="1.0" encoding="UTF-8"?>
<message:Structure
  xmlns:message="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
  xmlns:structure="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure"
  xmlns:common="http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common">
  <message:Structures><structure:Dataflows>
    <structure:Dataflow id="DF_TRM_DAILY_HIST" agencyID="ESTAT" version="1.0">
      <common:Name xml:lang="en">Exchange rate</common:Name>
      <common:Name xml:lang="es">Tasa Representativa del Mercado</common:Name>
    </structure:Dataflow>
    <structure:Dataflow id="DF_IBR_DAILY_HIST" agencyID="ESTAT" version="1.0">
      <common:Name xml:lang="es">IBR</common:Name>
    </structure:Dataflow>
  </structure:Dataflows></message:Structures>
</message:Structure>"""


def test_parser_formato_generico():
    filas = list(banrep.parsear_sdmx(XML_GENERICO))
    assert len(filas) == 2
    assert filas[1]["TIME_PERIOD"] == "2026-11-04"
    assert filas[1]["OBS_VALUE"] == "4012.35"           # texto, sin convertir
    assert filas[1]["serie"] == {"FREQ": "D", "TRM_TYPE": "TRM"}
    assert filas[1]["atributos_serie"] == {"UNIT_MEASURE": "COP"}
    assert filas[1]["atributos_obs"] == {"OBS_STATUS": "A"}


def test_parser_formato_especifico():
    (fila,) = banrep.parsear_sdmx(XML_ESPECIFICO)
    assert fila["TIME_PERIOD"] == "2026-11-04"
    assert fila["OBS_VALUE"] == "9.25"
    assert fila["serie"] == {"FREQ": "D", "IBR_TERM": "ON"}
    assert fila["atributos_obs"] == {"OBS_STATUS": "A"}


def test_ejecutar_guarda_xml_original_y_jsonl():
    def manejador(url, p):
        assert "/data/ESTAT,DF_TRM_DAILY_HIST,1.0/all/ALL/" in url
        assert p["startPeriod"] == "2026" and p["dimensionAtObservation"] == "TIME_PERIOD"
        return RespuestaXML(XML_GENERICO)

    (archivo,) = banrep.ejecutar(desde="2026", flujos={"DF_TRM_DAILY_HIST": "trm_banrep"},
                                 sesion=SesionFalsa(manejador))
    registros = [json.loads(l) for l in archivo.read_text(encoding="utf-8").splitlines()]
    assert len(registros) == 2
    assert registros[0]["id_registro"] == "DF_TRM_DAILY_HIST|D.TRM|2026-11-03"
    assert registros[0]["fuente"] == "banrep"
    originales = list(archivo.parent.glob("*_original.xml"))
    assert originales and originales[0].read_bytes() == XML_GENERICO


def test_404_es_sin_datos_no_error(raw_temporal):
    sesion = SesionFalsa(lambda u, p: RespuestaXML(b"NoResultsFound", status=404))
    assert banrep.ejecutar(flujos={"DF_IBR_DAILY_HIST": "ibr"}, sesion=sesion) == []
    assert not raw_temporal.exists()


def test_error_de_servidor_marca_fallo_pero_sigue_con_otros():
    def manejador(url, p):
        if "DF_MALO" in url:
            return RespuestaXML(b"", status=500)
        return RespuestaXML(XML_ESPECIFICO)

    with pytest.raises(RuntimeError, match="DF_MALO"):
        banrep.ejecutar(flujos={"DF_MALO": "malo", "DF_IBR_DAILY_HIST": "ibr"},
                        sesion=SesionFalsa(manejador))
    assert list(config.RAW_DIR.glob("banrep/ibr/*/*.jsonl"))


def test_listar_flujos_prefiere_nombre_en_espanol():
    flujos = banrep.listar_flujos(SesionFalsa(lambda u, p: RespuestaXML(XML_FLUJOS)))
    assert flujos == [
        {"id": "DF_IBR_DAILY_HIST", "nombre": "IBR"},
        {"id": "DF_TRM_DAILY_HIST", "nombre": "Tasa Representativa del Mercado"},
    ]


def test_cli_todo_devuelve_1_si_una_fuente_falla(monkeypatch):
    llamadas = []
    monkeypatch.setattr("ingesta.trm.ejecutar", lambda **k: llamadas.append("trm"))
    monkeypatch.setattr("ingesta.banco_mundial.ejecutar", lambda **k: llamadas.append("bm"))

    def falla(**k):
        raise RuntimeError("caído")
    monkeypatch.setattr("ingesta.banrep.ejecutar", falla)

    assert main(["todo"]) == 1
    assert llamadas == ["trm", "bm"]       # las otras fuentes sí corrieron
