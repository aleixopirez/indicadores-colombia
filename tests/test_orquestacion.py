"""Pruebas del Paso 8 (orquestación). No necesitan Docker, Airflow ni internet."""
import base64
import hashlib

import pytest

from orquestacion import contenedores, github


# ------------------------------------------------------------ Docker falso
class ContenedorFalso:
    def __init__(self, nombre, estados):
        self.name, self.id = nombre, f"id-{nombre}"
        self._estados = list(estados)      # se consumen en cada reload()
        self.actual = self._estados[0]
        self.encendido = self.apagado = 0
        self.attrs = {}

    def reload(self):
        """Cada consulta de estado avanza al siguiente de la lista."""
        self.actual = self._estados[0]
        if len(self._estados) > 1:
            self._estados.pop(0)
        salud = self.actual if self.actual in ("healthy", "unhealthy", "starting") else None
        self.attrs = {"State": {"Status": "running" if salud else self.actual,
                                **({"Health": {"Status": salud}} if salud else {})}}

    def start(self):
        self.encendido += 1

    def stop(self, timeout=10):
        self.apagado += 1


class ApiFalsa:
    def __init__(self, salida, codigo):
        self.salida, self.codigo, self.comandos = salida, codigo, []

    def exec_create(self, cid, cmd, workdir=None):
        self.comandos.append((cid, cmd, workdir))
        return {"Id": "e1"}

    def exec_start(self, eid, stream=True):
        return iter(self.salida)

    def exec_inspect(self, eid):
        return {"ExitCode": self.codigo}


class ClienteFalso:
    def __init__(self, contenedores_, api=None):
        self.mapa = {c.name: c for c in contenedores_}
        self.api = api

    @staticmethod
    def obtener(cli, nombre):
        if nombre not in cli.mapa:
            raise contenedores.ErrorContenedor(f"No existe el contenedor '{nombre}'")
        return cli.mapa[nombre]


def test_encender_espera_hasta_healthy():
    nn = ContenedorFalso("namenode", ["exited", "starting", "starting", "healthy"])
    dn = ContenedorFalso("datanode", ["exited", "running"])
    cli = ClienteFalso([nn, dn])
    contenedores.encender(["namenode", "datanode"], cli=cli, intervalo=0, obtener=cli.obtener)
    assert nn.encendido == 1 and dn.encendido == 1


def test_encender_no_reinicia_lo_que_ya_esta_encendido():
    k = ContenedorFalso("kafka", ["healthy"])
    cli = ClienteFalso([k])
    contenedores.encender(["kafka"], cli=cli, intervalo=0, obtener=cli.obtener)
    assert k.encendido == 0


def test_encender_falla_si_queda_unhealthy():
    k = ContenedorFalso("kafka", ["exited", "starting", "unhealthy"])
    cli = ClienteFalso([k])
    with pytest.raises(contenedores.ErrorContenedor, match="unhealthy"):
        contenedores.encender(["kafka"], cli=cli, intervalo=0, obtener=cli.obtener)


def test_encender_falla_por_tiempo():
    k = ContenedorFalso("kafka", ["exited"] + ["starting"] * 50)
    cli = ClienteFalso([k])
    with pytest.raises(contenedores.ErrorContenedor, match="a tiempo"):
        contenedores.encender(["kafka"], cli=cli, intervalo=0, espera_maxima=0, obtener=cli.obtener)


def test_contenedor_inexistente_explica_como_crearlo():
    cli = ClienteFalso([])
    with pytest.raises(contenedores.ErrorContenedor, match="No existe"):
        contenedores.encender(["kafka"], cli=cli, obtener=cli.obtener)


def test_apagar_solo_lo_encendido_e_ignora_faltantes():
    k = ContenedorFalso("kafka", ["healthy"])
    dn = ContenedorFalso("datanode", ["exited"])
    cli = ClienteFalso([k, dn])
    contenedores.apagar(["kafka", "datanode", "no-existe"], cli=cli, obtener=cli.obtener)
    assert k.apagado == 1 and dn.apagado == 0


def test_ejecutar_devuelve_lineas_y_respeta_el_codigo():
    sp = ContenedorFalso("spark-tareas", ["running"])
    api = ApiFalsa([b"linea 1\nlin", b"ea 2\n", b"fin"], 0)
    cli = ClienteFalso([sp], api)
    lineas = contenedores.ejecutar("spark-tareas", ["spark-submit", "x.py"], cli=cli,
                                   obtener=cli.obtener, directorio="/proyecto")
    assert lineas == ["linea 1", "linea 2", "fin"]
    assert api.comandos == [("id-spark-tareas", ["spark-submit", "x.py"], "/proyecto")]

    api.codigo = 1
    with pytest.raises(contenedores.ErrorContenedor, match="código 1"):
        contenedores.ejecutar("spark-tareas", ["spark-submit"], cli=cli, obtener=cli.obtener)


# ------------------------------------------------------------ GitHub falso
class Resp:
    def __init__(self, status, datos=None, texto=""):
        self.status_code, self._datos, self.text = status, datos or {}, texto

    def json(self):
        return self._datos


class SesionGitHub:
    def __init__(self, get, put=None):
        self.get_resp, self.put_resp, self.puts = get, put, []

    def get(self, url, headers=None, params=None, timeout=None):
        assert headers["Authorization"] == "Bearer tok"
        return self.get_resp

    def put(self, url, headers=None, json=None, timeout=None):
        self.puts.append((url, json))
        return self.put_resp


def sha_git(b):
    return hashlib.sha1(b"blob %d\0" % len(b) + b).hexdigest()


def test_publicar_actualiza_con_sha(tmp_path):
    f = tmp_path / "dashboard.html"
    f.write_bytes(b"<html>nuevo</html>")
    s = SesionGitHub(Resp(200, {"sha": sha_git(b"viejo")}), Resp(200, {"commit": {"sha": "c0ffee1"}}))
    assert github.publicar_archivo(f, "u/r", "docs/index.html", "tok", "msg", sesion=s) == "c0ffee1"
    url, cuerpo = s.puts[0]
    assert url.endswith("/repos/u/r/contents/docs/index.html")
    assert cuerpo["sha"] == sha_git(b"viejo") and cuerpo["branch"] == "main"
    assert base64.b64decode(cuerpo["content"]) == b"<html>nuevo</html>"


def test_publicar_no_hace_commit_si_no_cambio(tmp_path):
    f = tmp_path / "d.html"
    f.write_bytes(b"igual")
    s = SesionGitHub(Resp(200, {"sha": sha_git(b"igual")}))
    assert github.publicar_archivo(f, "u/r", "docs/index.html", "tok", "msg", sesion=s) is None
    assert s.puts == []


def test_publicar_archivo_nuevo_sin_sha(tmp_path):
    f = tmp_path / "d.html"
    f.write_bytes(b"x")
    s = SesionGitHub(Resp(404), Resp(201, {"commit": {"sha": "abc"}}))
    github.publicar_archivo(f, "u/r", "docs/index.html", "tok", "msg", sesion=s)
    assert "sha" not in s.puts[0][1]


def test_publicar_token_invalido_da_mensaje_claro(tmp_path):
    f = tmp_path / "d.html"
    f.write_bytes(b"x")
    s = SesionGitHub(Resp(401, texto="Bad credentials"))
    with pytest.raises(RuntimeError, match="GITHUB_TOKEN"):
        github.publicar_archivo(f, "u/r", "docs/index.html", "tok", "msg", sesion=s)
