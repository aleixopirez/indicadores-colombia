"""
Publica el dashboard en GitHub Pages sin usar git: sube docs/index.html al
repositorio con la API de GitHub ("create or update file contents").

Así Airflow no toca la copia del repositorio que hay en Windows. Antes de
hacer cambios propios en el proyecto, traiga lo que publicó Airflow con
`git pull`.

Requiere un token de GitHub (fine-grained) con permiso "Contents: Read and
write" solo sobre el repositorio, guardado en el archivo .env (fuera de git).
"""
import base64
import logging
from pathlib import Path
from typing import Optional

import requests

log = logging.getLogger(__name__)
API = "https://api.github.com"


def publicar_archivo(local: Path, repo: str, ruta_repo: str, token: str,
                     mensaje: str, rama: str = "main",
                     sesion: Optional[requests.Session] = None) -> Optional[str]:
    """Crea o actualiza `ruta_repo` en `repo` con el contenido de `local`.
    Devuelve el sha del commit, o None si el archivo no cambió."""
    sesion = sesion or requests.Session()
    cabeceras = {"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"}
    url = f"{API}/repos/{repo}/contents/{ruta_repo}"
    contenido = Path(local).read_bytes()

    actual = sesion.get(url, headers=cabeceras, params={"ref": rama}, timeout=60)
    sha = None
    if actual.status_code == 200:
        sha = actual.json()["sha"]
        if _sha_blob(contenido) == sha:
            log.info("%s no cambió: no hay nada que publicar.", ruta_repo)
            return None
    elif actual.status_code != 404:
        _fallar(actual)

    cuerpo = {"message": mensaje, "branch": rama,
              "content": base64.b64encode(contenido).decode("ascii")}
    if sha:
        cuerpo["sha"] = sha
    resp = sesion.put(url, headers=cabeceras, json=cuerpo, timeout=120)
    if resp.status_code not in (200, 201):
        _fallar(resp)
    commit = resp.json()["commit"]["sha"]
    log.info("Publicado %s en %s (commit %s)", ruta_repo, repo, commit[:7])
    return commit


def _sha_blob(contenido: bytes) -> str:
    """El mismo hash que calcula git para un archivo (blob)."""
    import hashlib
    return hashlib.sha1(b"blob %d\0" % len(contenido) + contenido).hexdigest()


def _fallar(resp) -> None:
    detalle = resp.text[:300]
    if resp.status_code in (401, 403):
        detalle = ("token sin permiso o vencido (revise GITHUB_TOKEN en .env: "
                   "necesita 'Contents: Read and write' sobre el repositorio). " + detalle)
    raise RuntimeError(f"GitHub respondió {resp.status_code}: {detalle}")
