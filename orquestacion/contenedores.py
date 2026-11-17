"""
Encender, apagar y ejecutar comandos en los contenedores del proyecto desde
Airflow, con el SDK de Docker (paquete `docker`).

Airflow corre dentro de un contenedor con acceso al socket de Docker
(/var/run/docker.sock), así que puede manejar a sus "vecinos" por nombre:
kafka, namenode, datanode, spark-tareas... Los contenedores deben existir
(se crean una vez con `docker compose --profile todo create`); aquí solo se
encienden y se apagan, para no tener todo prendido en un equipo de 8 GB.
"""
import logging
import time
from typing import Iterable, List, Optional, Sequence

log = logging.getLogger(__name__)

ESPERA_MAXIMA_S = 300      # el NameNode tarda 1-2 min en salir del modo seguro
INTERVALO_S = 5


class ErrorContenedor(RuntimeError):
    pass


def cliente():
    import docker   # importación tardía: las pruebas usan un cliente falso
    return docker.from_env()


def _obtener(cli, nombre: str):
    import docker.errors
    try:
        return cli.containers.get(nombre)
    except docker.errors.NotFound:
        raise ErrorContenedor(
            f"No existe el contenedor '{nombre}'. Créelo una vez desde Windows con:\n"
            "    docker compose --profile todo create")


def estado(contenedor) -> str:
    """'healthy' / 'unhealthy' / 'starting' si tiene healthcheck; si no, el
    estado del proceso ('running', 'exited', ...)."""
    contenedor.reload()
    st = contenedor.attrs.get("State", {})
    salud = st.get("Health", {}).get("Status")
    return salud or st.get("Status", "desconocido")


def listo(contenedor) -> bool:
    return estado(contenedor) in ("healthy", "running")


def encender(nombres: Iterable[str], cli=None, espera_maxima: float = ESPERA_MAXIMA_S,
             intervalo: float = INTERVALO_S, obtener=None) -> None:
    """Enciende los contenedores y espera a que estén sanos (healthy)."""
    cli = cli or cliente()
    obtener = obtener or _obtener
    contenedores = [obtener(cli, n) for n in nombres]
    for c in contenedores:
        if estado(c) not in ("healthy", "running", "starting"):
            log.info("Encendiendo %s", c.name)
            c.start()
    limite = time.monotonic() + espera_maxima
    pendientes = list(contenedores)
    while pendientes:
        pendientes = [c for c in pendientes if not listo(c)]
        if not pendientes:
            break
        for c in pendientes:
            if estado(c) in ("exited", "dead", "unhealthy"):
                raise ErrorContenedor(f"{c.name} quedó en estado '{estado(c)}'")
        if time.monotonic() > limite:
            raise ErrorContenedor("No quedaron listos a tiempo: "
                                  + ", ".join(f"{c.name}={estado(c)}" for c in pendientes))
        time.sleep(intervalo)
    log.info("Listos: %s", ", ".join(c.name for c in contenedores))


def apagar(nombres: Iterable[str], cli=None, obtener=None) -> None:
    """Apaga los contenedores (se conservan, con sus datos en volúmenes)."""
    cli = cli or cliente()
    obtener = obtener or _obtener
    for n in nombres:
        try:
            c = obtener(cli, n)
        except ErrorContenedor as e:
            log.warning("%s", e)
            continue
        if estado(c) not in ("exited", "created"):
            log.info("Apagando %s", n)
            c.stop(timeout=30)


def ejecutar(nombre: str, comando: Sequence[str], cli=None, obtener=None,
             directorio: Optional[str] = None) -> List[str]:
    """Ejecuta un comando dentro de un contenedor encendido (como `docker exec`)
    y copia su salida al registro de Airflow. Falla si el comando falla."""
    cli = cli or cliente()
    obtener = obtener or _obtener
    c = obtener(cli, nombre)
    if not listo(c):
        log.info("Encendiendo %s", nombre)
        c.start()
    log.info("%s$ %s", nombre, " ".join(comando))
    exec_id = cli.api.exec_create(c.id, list(comando), workdir=directorio)["Id"]
    lineas, resto = [], b""
    for trozo in cli.api.exec_start(exec_id, stream=True):
        resto += trozo
        *completas, resto = resto.split(b"\n")
        for linea in completas:
            texto = linea.decode("utf-8", "replace").rstrip()
            lineas.append(texto)
            log.info("%s", texto)
    if resto:
        lineas.append(resto.decode("utf-8", "replace"))
        log.info("%s", lineas[-1])
    codigo = cli.api.exec_inspect(exec_id)["ExitCode"]
    if codigo != 0:
        raise ErrorContenedor(f"'{' '.join(comando)}' terminó con código {codigo} en {nombre}")
    return lineas
