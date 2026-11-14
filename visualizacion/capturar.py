"""
Convierte los reels HTML en PNG (imagen fija) y MP4 (video animado) con
Playwright. El MP4 se codifica en H.264, el formato que aceptan TikTok,
Instagram y Facebook.
"""
import shutil
import subprocess
from pathlib import Path

from . import config


def _ffmpeg() -> str:
    """ffmpeg del sistema o, si no hay, el que trae imageio-ffmpeg."""
    ruta = shutil.which("ffmpeg")
    if ruta:
        return ruta
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def _a_mp4(webm: Path, mp4: Path, recorte_inicial_s: float) -> None:
    subprocess.run([
        _ffmpeg(), "-y", "-loglevel", "error",
        "-ss", f"{recorte_inicial_s:.2f}", "-i", str(webm),
        "-t", f"{config.DURACION_REEL_MS / 1000:.2f}",
        "-vf", f"scale={config.REEL['ancho']}:{config.REEL['alto']},fps=30",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", str(mp4),
    ], check=True)


def capturar(salida: Path | None = None, video: bool = True, solo: list[str] | None = None) -> list[Path]:
    from playwright.sync_api import sync_playwright

    salida = Path(salida or config.SALIDA)
    carpeta = salida / "reels"
    paginas = sorted(carpeta.glob("*.html"))
    if solo:
        paginas = [p for p in paginas if any(s in p.stem for s in solo)]
    if not paginas:
        raise SystemExit(f"No hay reels en {carpeta}. Ejecute primero: python -m visualizacion generar")

    tam = {"width": config.REEL["ancho"], "height": config.REEL["alto"]}
    hechos = []
    with sync_playwright() as pw:
        # "chromium" = el navegador que descarga `playwright install`; si no, Edge/Chrome del sistema
        canal = None if config.NAVEGADOR == "chromium" else config.NAVEGADOR
        navegador = pw.chromium.launch(channel=canal)
        for pagina in paginas:
            # 1) PNG: se espera a que termine la animación
            ctx = navegador.new_context(viewport=tam, device_scale_factor=1)
            p = ctx.new_page()
            p.goto(pagina.resolve().as_uri())
            p.wait_for_function("window.__listo === true", timeout=20000)
            p.wait_for_timeout(300)
            png = pagina.with_suffix(".png")
            p.screenshot(path=str(png))
            ctx.close()
            hechos.append(png)
            print(f"  PNG  {png}")

            # 2) Video: Playwright graba webm; ffmpeg lo pasa a MP4 H.264
            if video:
                tmp = carpeta / "_video_tmp"
                ctx = navegador.new_context(viewport=tam, device_scale_factor=1,
                                            record_video_dir=str(tmp), record_video_size=tam)
                p = ctx.new_page()
                p.goto("about:blank")
                p.wait_for_timeout(400)             # tramo en blanco que luego se recorta
                p.goto(pagina.resolve().as_uri())
                p.wait_for_timeout(config.DURACION_REEL_MS + 300)
                webm = Path(p.video.path())
                ctx.close()
                mp4 = pagina.with_suffix(".mp4")
                _a_mp4(webm, mp4, recorte_inicial_s=0.55)
                shutil.rmtree(tmp, ignore_errors=True)
                hechos.append(mp4)
                print(f"  MP4  {mp4}")
        navegador.close()
    return hechos
