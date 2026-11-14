"""
Cliente mínimo de WebHDFS: la API REST de HDFS.

¿Por qué WebHDFS y no una librería nativa? Porque funciona con `requests`
desde Windows sin instalar Java, Hadoop ni winutils. Y porque deja ver cómo
funciona HDFS por dentro:

  ESCRIBIR un archivo son DOS pasos:
    1) PUT al NameNode  /webhdfs/v1/<ruta>?op=CREATE
       El NameNode no recibe datos: decide en qué DataNode van los bloques
       y responde con esa dirección.
    2) PUT de los bytes a ese DataNode.

  Con noredirect=true el NameNode devuelve la dirección en un JSON en vez de
  una redirección HTTP 307, y así podemos traducir "datanode:9864" (nombre
  interno de Docker) a "localhost:9864" (puerto publicado en Windows).

Documentación: https://hadoop.apache.org/docs/stable/hadoop-project-dist/hadoop-hdfs/WebHDFS.html
"""
import logging
import time
from typing import List, Optional
from urllib.parse import urlsplit, urlunsplit

import requests

from datalake import config

log = logging.getLogger("datalake.webhdfs")


class ErrorHDFS(Exception):
    def __init__(self, excepcion: str, mensaje: str, status: int):
        super().__init__(f"{excepcion}: {mensaje} (HTTP {status})")
        self.excepcion, self.status = excepcion, status


class WebHDFS:
    def __init__(self, url: str = None, usuario: str = None,
                 datanode_publico: Optional[str] = None, sesion=None):
        self.url = (url or config.WEBHDFS_URL).rstrip("/")
        self.usuario = usuario or config.HDFS_USUARIO
        self.datanode_publico = (config.DATANODE_PUBLICO if datanode_publico is None
                                 else datanode_publico)
        self.sesion = sesion or requests.Session()

    # ------------------------------------------------------------ utilidades
    def _url(self, ruta: str) -> str:
        if not ruta.startswith("/"):
            raise ValueError(f"La ruta HDFS debe ser absoluta: {ruta}")
        return f"{self.url}/webhdfs/v1{ruta}"

    def _params(self, op: str, **extra) -> dict:
        return {"op": op, "user.name": self.usuario, **extra}

    @staticmethod
    def _revisar(resp) -> None:
        if resp.status_code < 400:
            return
        try:
            remota = resp.json()["RemoteException"]
            raise ErrorHDFS(remota.get("exception", "?"), remota.get("message", ""),
                            resp.status_code)
        except (ValueError, KeyError):
            raise ErrorHDFS("HTTPError", resp.text[:200], resp.status_code)

    def _traducir_datanode(self, ubicacion: str) -> str:
        """http://datanode:9864/webhdfs/... -> http://localhost:9864/webhdfs/..."""
        if not self.datanode_publico:
            return ubicacion
        partes = urlsplit(ubicacion)
        return urlunsplit(partes._replace(netloc=self.datanode_publico))

    def _con_reintento_modo_seguro(self, funcion):
        """Recién encendido, el NameNode está en modo seguro (no acepta
        escrituras) mientras los DataNodes reportan sus bloques."""
        for intento in range(config.REINTENTOS_MODO_SEGURO):
            try:
                return funcion()
            except ErrorHDFS as e:
                if e.excepcion not in ("SafeModeException", "RetriableException"):
                    raise
                log.warning("HDFS en modo seguro, reintento %d en %ds...",
                            intento + 1, config.ESPERA_MODO_SEGURO_S)
                time.sleep(config.ESPERA_MODO_SEGURO_S)
        return funcion()

    # ------------------------------------------------------------ operaciones
    def mkdirs(self, ruta: str) -> bool:
        def hacer():
            r = self.sesion.put(self._url(ruta), params=self._params("MKDIRS"),
                                timeout=config.HDFS_TIMEOUT)
            self._revisar(r)
            return r.json().get("boolean", False)
        return self._con_reintento_modo_seguro(hacer)

    def escribir(self, ruta: str, contenido: bytes, sobrescribir: bool = True) -> None:
        def hacer():
            # Paso 1: preguntar al NameNode en qué DataNode escribir.
            r = self.sesion.put(
                self._url(ruta),
                params=self._params("CREATE", overwrite=str(sobrescribir).lower(),
                                    noredirect="true"),
                timeout=config.HDFS_TIMEOUT)
            self._revisar(r)
            ubicacion = self._traducir_datanode(r.json()["Location"])
            # Paso 2: enviar los bytes al DataNode.
            r = self.sesion.put(ubicacion, data=contenido,
                                headers={"Content-Type": "application/octet-stream"},
                                timeout=config.HDFS_TIMEOUT)
            self._revisar(r)
        self._con_reintento_modo_seguro(hacer)

    def subir_archivo(self, local, ruta: str) -> int:
        """Copia un archivo del equipo a HDFS (como `hdfs dfs -put -f`)."""
        from pathlib import Path
        contenido = Path(local).read_bytes()
        self.mkdirs(ruta.rsplit("/", 1)[0] or "/")
        self.escribir(ruta, contenido, sobrescribir=True)
        return len(contenido)

    def leer(self, ruta: str) -> bytes:
        r = self.sesion.get(self._url(ruta),
                            params=self._params("OPEN", noredirect="true"),
                            timeout=config.HDFS_TIMEOUT)
        self._revisar(r)
        r = self.sesion.get(self._traducir_datanode(r.json()["Location"]),
                            timeout=config.HDFS_TIMEOUT)
        self._revisar(r)
        return r.content

    def listar(self, ruta: str) -> List[dict]:
        r = self.sesion.get(self._url(ruta), params=self._params("LISTSTATUS"),
                            timeout=config.HDFS_TIMEOUT)
        self._revisar(r)
        return r.json()["FileStatuses"]["FileStatus"]

    def resumen(self, ruta: str) -> dict:
        """Archivos, carpetas y bytes bajo una ruta (como `hdfs dfs -count`)."""
        r = self.sesion.get(self._url(ruta), params=self._params("GETCONTENTSUMMARY"),
                            timeout=config.HDFS_TIMEOUT)
        self._revisar(r)
        return r.json()["ContentSummary"]

    def existe(self, ruta: str) -> bool:
        r = self.sesion.get(self._url(ruta), params=self._params("GETFILESTATUS"),
                            timeout=config.HDFS_TIMEOUT)
        if r.status_code == 404:
            return False
        self._revisar(r)
        return True
