"""
Pruebas del Paso 3 sin HDFS ni Kafka reales.
"""
import json
from types import SimpleNamespace

import pytest

from datalake import config, consumidor_hdfs
from datalake.webhdfs import ErrorHDFS, WebHDFS


# =============================================================== WebHDFS
class Resp:
    def __init__(self, status=200, datos=None, contenido=b""):
        self.status_code, self._datos, self.content = status, datos, contenido
        self.text = json.dumps(datos) if datos is not None else ""

    def json(self):
        if self._datos is None:
            raise ValueError("sin json")
        return self._datos


class SesionHDFS:
    """Simula NameNode + DataNode guardando archivos en un diccionario."""

    def __init__(self, modo_seguro_veces=0):
        self.archivos, self.llamadas = {}, []
        self.modo_seguro_veces = modo_seguro_veces

    def put(self, url, params=None, data=None, headers=None, timeout=None):
        self.llamadas.append(("PUT", url, dict(params or {})))
        if url.startswith("http://localhost:9864/"):            # DataNode
            self.archivos[url.split("/webhdfs/v1", 1)[1].split("?")[0]] = data
            return Resp(201)
        op = params["op"]
        if self.modo_seguro_veces:
            self.modo_seguro_veces -= 1
            return Resp(403, {"RemoteException": {
                "exception": "SafeModeException", "message": "Name node is in safe mode."}})
        if op == "MKDIRS":
            return Resp(200, {"boolean": True})
        if op == "CREATE":
            ruta = url.split("/webhdfs/v1", 1)[1]
            # El NameNode responde con el nombre INTERNO del DataNode.
            return Resp(200, {"Location": f"http://datanode:9864/webhdfs/v1{ruta}"
                                          f"?op=CREATE&namenoderpcaddress=namenode:8020"})
        raise AssertionError(op)

    def get(self, url, params=None, timeout=None):
        self.llamadas.append(("GET", url, dict(params or {})))
        if url.startswith("http://localhost:9864/"):
            return Resp(200, contenido=self.archivos[url.split("/webhdfs/v1", 1)[1].split("?")[0]])
        ruta = url.split("/webhdfs/v1", 1)[1]
        if params["op"] == "OPEN":
            return Resp(200, {"Location": f"http://datanode:9864/webhdfs/v1{ruta}?op=OPEN"})
        if params["op"] == "GETFILESTATUS":
            return Resp(200, {}) if ruta in self.archivos else Resp(404, {"RemoteException": {
                "exception": "FileNotFoundException", "message": "no existe"}})
        raise AssertionError(params["op"])


@pytest.fixture(autouse=True)
def sin_esperas(monkeypatch):
    monkeypatch.setattr(config, "ESPERA_MODO_SEGURO_S", 0)


def test_escribir_en_dos_pasos_y_traducir_datanode():
    sesion = SesionHDFS()
    hdfs = WebHDFS("http://localhost:9870", "root", "localhost:9864", sesion)
    hdfs.escribir("/datalake/raw/a.jsonl", b"hola\n")

    (_, url1, p1), (_, url2, _) = sesion.llamadas
    assert url1 == "http://localhost:9870/webhdfs/v1/datalake/raw/a.jsonl"
    assert p1["op"] == "CREATE" and p1["noredirect"] == "true" and p1["overwrite"] == "true"
    assert url2.startswith("http://localhost:9864/webhdfs/v1/datalake/raw/a.jsonl")
    assert "namenoderpcaddress=namenode:8020" in url2          # la query se conserva
    assert hdfs.leer("/datalake/raw/a.jsonl") == b"hola\n"
    assert hdfs.existe("/datalake/raw/a.jsonl") and not hdfs.existe("/otro")


def test_reintenta_mientras_esta_en_modo_seguro():
    sesion = SesionHDFS(modo_seguro_veces=2)
    WebHDFS("http://localhost:9870", "root", "localhost:9864", sesion).mkdirs("/datalake")
    assert len(sesion.llamadas) == 3


def test_otros_errores_no_se_reintentan():
    class SesionError(SesionHDFS):
        def put(self, url, **kw):
            self.llamadas.append(url)
            return Resp(403, {"RemoteException": {"exception": "AccessControlException",
                                                  "message": "Permission denied"}})
    sesion = SesionError()
    with pytest.raises(ErrorHDFS, match="AccessControlException"):
        WebHDFS("http://x:9870", "root", "", sesion).mkdirs("/datalake")
    assert len(sesion.llamadas) == 1


def test_ruta_relativa_es_un_error():
    with pytest.raises(ValueError):
        WebHDFS("http://x", "root", "", SesionHDFS()).mkdirs("datalake")


# =============================================================== consumidor
def msg(topico, particion, offset, fuente, dataset, id_registro, fecha="2026-11-06T15:00:00Z"):
    return SimpleNamespace(offset=offset, value={
        "fuente": fuente, "dataset": dataset, "id_registro": id_registro,
        "fecha_ingesta": fecha, "payload": {"o": offset}})


from kafka.structs import TopicPartition as TP   # la misma que entrega Kafka


class ConsumidorFalso:
    """polls_sin_asignar simula el rebalance inicial: Kafka aún no asignó
    particiones y poll() devuelve vacío aunque haya mensajes."""

    def __init__(self, lotes, polls_sin_asignar=0):
        self.lotes, self.commits = list(lotes), 0
        self.polls_sin_asignar = polls_sin_asignar

    def assignment(self):
        return set() if self.polls_sin_asignar >= 0 else {TP("raw.banrep", 0)}

    def poll(self, timeout_ms=None, max_records=None):
        if self.polls_sin_asignar >= 0:
            self.polls_sin_asignar -= 1
            return {}
        return self.lotes.pop(0) if self.lotes else {}

    def commit(self):
        self.commits += 1


class HDFSFalso:
    def __init__(self, falla=False):
        self.archivos, self.carpetas, self.falla = {}, set(), falla

    def mkdirs(self, ruta):
        self.carpetas.add(ruta)

    def escribir(self, ruta, contenido, sobrescribir=True):
        if self.falla:
            raise ErrorHDFS("IOException", "disco lleno", 500)
        self.archivos[ruta] = contenido


def test_agrupa_por_dataset_y_nombra_por_offset_inicial():
    tp = TP("raw.banrep", 1)
    lote = {tp: [msg("raw.banrep", 1, 40, "banrep", "ibr", "a"),
                 msg("raw.banrep", 1, 41, "banrep", "trm_banrep", "b"),
                 msg("raw.banrep", 1, 42, "banrep", "ibr", "c")]}
    archivos = consumidor_hdfs.agrupar_lote(lote)

    base = "/datalake/raw/banrep"
    assert set(archivos) == {
        f"{base}/ibr/fecha_ingesta=2026-11-06/part-raw.banrep-p1-o000000000040.jsonl",
        f"{base}/trm_banrep/fecha_ingesta=2026-11-06/part-raw.banrep-p1-o000000000041.jsonl",
    }
    ibr = next(v for k, v in archivos.items() if "/ibr/" in k)
    assert [s["id_registro"] for s in ibr] == ["a", "c"]        # orden conservado


def test_consume_escribe_y_hace_commit_despues():
    lotes = [
        {TP("raw.banrep", 0): [msg("raw.banrep", 0, 0, "banrep", "ibr", "x"),
                               msg("raw.banrep", 0, 1, "banrep", "ibr", "y")]},
        {TP("raw.banco_mundial", 2): [msg("raw.banco_mundial", 2, 7, "banco_mundial",
                                          "desempleo_pct", "z")]},
    ]
    consumidor, hdfs = ConsumidorFalso(lotes), HDFSFalso()
    resumen = consumidor_hdfs.ejecutar(consumidor=consumidor, hdfs=hdfs)

    assert resumen == {"mensajes": 3, "archivos": 2, "lotes": 2}
    assert consumidor.commits == 2
    ruta_ibr = next(r for r in hdfs.archivos if "/ibr/" in r)
    lineas = hdfs.archivos[ruta_ibr].decode().splitlines()
    assert [json.loads(l)["id_registro"] for l in lineas] == ["x", "y"]
    assert "/datalake/raw/banrep/ibr/fecha_ingesta=2026-11-06" in hdfs.carpetas


def test_si_hdfs_falla_no_hay_commit():
    lotes = [{TP("raw.banrep", 0): [msg("raw.banrep", 0, 0, "banrep", "ibr", "x")]}]
    consumidor = ConsumidorFalso(lotes)
    with pytest.raises(ErrorHDFS):
        consumidor_hdfs.ejecutar(consumidor=consumidor, hdfs=HDFSFalso(falla=True))
    assert consumidor.commits == 0          # Kafka volverá a entregar el lote


def test_reprocesar_el_mismo_lote_no_duplica_archivos():
    """Simula: se escribió en HDFS, el programa murió antes del commit, y al
    reiniciar Kafka entrega el mismo lote otra vez."""
    lote = {TP("raw.banrep", 0): [msg("raw.banrep", 0, 100, "banrep", "ibr", "x")]}
    hdfs = HDFSFalso()
    consumidor_hdfs.ejecutar(consumidor=ConsumidorFalso([lote]), hdfs=hdfs)
    consumidor_hdfs.ejecutar(consumidor=ConsumidorFalso([lote]), hdfs=hdfs)
    assert len(hdfs.archivos) == 1


def test_modo_lote_termina_con_topicos_vacios():
    consumidor = ConsumidorFalso([])
    assert consumidor_hdfs.ejecutar(consumidor=consumidor, hdfs=HDFSFalso()) == {
        "mensajes": 0, "archivos": 0, "lotes": 0}


def test_espera_la_asignacion_de_particiones_antes_de_terminar():
    """El error real del primer intento: 0 mensajes porque el consumidor
    terminó mientras Kafka todavía asignaba particiones al grupo nuevo."""
    lote = {TP("raw.banrep", 0): [msg("raw.banrep", 0, 0, "banrep", "ibr", "x")]}
    consumidor = ConsumidorFalso([lote], polls_sin_asignar=5)
    resumen = consumidor_hdfs.ejecutar(consumidor=consumidor, hdfs=HDFSFalso())
    assert resumen["mensajes"] == 1


def test_error_claro_si_nunca_se_asignan_particiones(monkeypatch):
    monkeypatch.setattr(config, "ESPERA_ASIGNACION_S", 0)
    consumidor = ConsumidorFalso([], polls_sin_asignar=10**6)
    with pytest.raises(RuntimeError, match="no asignó particiones"):
        consumidor_hdfs.ejecutar(consumidor=consumidor, hdfs=HDFSFalso())


def test_subir_archivo_local_a_hdfs(tmp_path):
    local = tmp_path / "gobiernos.csv"
    local.write_text("presidente,periodo\nA,2020-2024\n", encoding="utf-8")
    sesion = SesionHDFS()
    hdfs = WebHDFS("http://localhost:9870", "root", "localhost:9864", sesion)
    n = hdfs.subir_archivo(local, "/datalake/referencia/gobiernos/gobiernos.csv")
    assert n == local.stat().st_size
    assert hdfs.leer("/datalake/referencia/gobiernos/gobiernos.csv") == local.read_bytes()
    ops = [p.get("op") for _, _, p in sesion.llamadas]
    assert ops[:2] == ["MKDIRS", "CREATE"]
