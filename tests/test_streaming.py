"""
Pruebas del Paso 2 sin Kafka real: un productor falso guarda lo que "envía".
"""
import json
from types import SimpleNamespace

import pytest

from streaming import config, consumidor, productor, topicos


# ------------------------------------------------------------------ dobles
class FuturoFalso:
    def __init__(self, falla=None):
        self.falla = falla

    def add_errback(self, fn):
        if self.falla:
            fn(self.falla)
        return self


class ProductorFalso:
    def __init__(self, falla_en=None):
        self.enviados, self.flushes, self.falla_en = [], 0, falla_en

    def send(self, topico, key=None, value=None, headers=None):
        self.enviados.append({"topico": topico, "key": key, "value": value,
                              "headers": dict(headers or [])})
        falla = Exception("broker caído") if key == self.falla_en else None
        return FuturoFalso(falla)

    def flush(self):
        self.flushes += 1


# ------------------------------------------------------------------ datos
@pytest.fixture
def raw(tmp_path, monkeypatch):
    base = tmp_path / "raw"
    monkeypatch.setattr(config, "RAW_DIR", base)
    return base


def escribir_jsonl(raw, fuente, dataset, ids, extra_lineas=()):
    carpeta = raw / fuente / dataset / "fecha_ingesta=2026-11-06"
    carpeta.mkdir(parents=True, exist_ok=True)
    archivo = carpeta / f"{dataset}_20261106T150000Z.jsonl"
    lineas = [json.dumps({"fuente": fuente, "dataset": dataset, "id_registro": i,
                          "fecha_ingesta": "2026-11-06T15:00:00Z",
                          "payload": {"v": n}}) for n, i in enumerate(ids)]
    archivo.write_text("\n".join(lineas + list(extra_lineas)) + "\n", encoding="utf-8")
    return archivo


# ------------------------------------------------------------------ productor
def test_publica_cada_linea_con_key_topico_y_headers(raw):
    escribir_jsonl(raw, "banrep", "ibr", ["DF_IBR|a|2026-11-05", "DF_IBR|a|2026-11-06"])
    escribir_jsonl(raw, "banco_mundial", "desempleo_pct", ["SL.UEM|COL|2025"])

    p = ProductorFalso()
    resumen = productor.ejecutar(productor=p)

    assert sum(resumen.values()) == 3
    topicos_usados = {m["topico"] for m in p.enviados}
    assert topicos_usados == {"raw.banrep", "raw.banco_mundial"}
    m = next(m for m in p.enviados if m["key"] == "DF_IBR|a|2026-11-06")
    assert m["value"]["payload"] == {"v": 1}                 # sobre completo
    assert m["headers"] == {"dataset": b"ibr", "fecha_ingesta": b"2026-11-06T15:00:00Z"}
    assert p.flushes == 2                                    # un flush por archivo


def test_checkpoint_evita_reenviar_y_reenviar_lo_ignora(raw):
    archivo = escribir_jsonl(raw, "datos_gov_co", "trm", ["trm|2026-11-06"])

    productor.ejecutar(productor=ProductorFalso())
    marca = archivo.with_name(archivo.name + ".kafka_ok")
    assert marca.read_text() == "1"

    segundo = ProductorFalso()
    assert productor.ejecutar(productor=segundo) == {}       # nada pendiente
    assert segundo.enviados == []

    tercero = ProductorFalso()
    productor.ejecutar(reenviar=True, productor=tercero)
    assert len(tercero.enviados) == 1


def test_filtra_por_fuente(raw):
    escribir_jsonl(raw, "banrep", "ibr", ["x"])
    escribir_jsonl(raw, "datos_gov_co", "trm", ["y"])
    p = ProductorFalso()
    productor.ejecutar(fuente="banrep", productor=p)
    assert [m["key"] for m in p.enviados] == ["x"]


def test_linea_danada_se_omite_sin_detener_el_envio(raw):
    escribir_jsonl(raw, "banrep", "ibr", ["a", "b"], extra_lineas=["{esto no es json", ""])
    p = ProductorFalso()
    productor.ejecutar(productor=p)
    assert [m["key"] for m in p.enviados] == ["a", "b"]


def test_si_falla_un_mensaje_no_se_marca_como_enviado(raw):
    archivo = escribir_jsonl(raw, "banrep", "ibr", ["ok", "malo"])
    with pytest.raises(RuntimeError, match="1 mensajes fallaron"):
        productor.ejecutar(productor=ProductorFalso(falla_en="malo"))
    assert not archivo.with_name(archivo.name + ".kafka_ok").exists()


# ------------------------------------------------------------------ tópicos
class AdminFalso:
    def __init__(self, existentes):
        self.existentes, self.creados = set(existentes), []

    def list_topics(self):
        return list(self.existentes)

    def create_topics(self, nuevos):
        self.creados.extend(nuevos)


def test_crear_topicos_solo_crea_los_que_faltan():
    admin = AdminFalso(existentes=["raw.banrep", "__consumer_offsets"])
    resultado = topicos.crear_topicos(admin)

    assert resultado["raw.banrep"] == "ya existía"
    assert resultado["raw.datos_gov_co"] == "creado"
    nombres = sorted(t.name for t in admin.creados)
    assert nombres == ["raw.banco_mundial", "raw.datos_gov_co"]
    t = admin.creados[0]
    assert t.num_partitions == 3 and t.replication_factor == 1
    assert t.topic_configs["retention.ms"] == str(7 * 24 * 3600 * 1000)


# ------------------------------------------------------------------ consumidor
def test_consumidor_cuenta_por_dataset(capsys):
    mensajes = [
        SimpleNamespace(partition=0, offset=i, key=f"k{i}",
                        value={"dataset": ds, "payload": {"v": i}})
        for i, ds in enumerate(["ibr", "ibr", "trm_banrep"])
    ]
    conteo = consumidor.ejecutar("raw.banrep", maximo=1, consumidor=iter(mensajes))
    salida = capsys.readouterr().out

    assert conteo == {"ibr": 2, "trm_banrep": 1}
    assert salida.count("key=") == 1                       # solo imprime `maximo`
    assert "Total leído de raw.banrep: 3 mensajes" in salida
