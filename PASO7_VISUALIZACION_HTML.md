# Paso 7 · Capa de visualización en HTML (dashboard + reels)

Este paso lee la **zona de servicio** de PostgreSQL (`servicio.*`, cargada en el Paso 6) y produce:

| Salida | Para qué |
|---|---|
| `salida/dashboard.html` | Dashboard interactivo (16:9): KPIs, TRM desde 1986 con zoom y franjas de gobierno, comparación por gobierno con selector, Colombia vs. mundo, región, tasa del BanRep, explorador de indicadores y tabla resumen. |
| `salida/reels/*.html` | 5 reels verticales 1080×1920 animados. |
| `salida/reels/*.png` | Imagen fija de cada reel (carrusel, historia, miniatura). |
| `salida/reels/*.mp4` | Video H.264 de 9 s de cada reel, listo para TikTok, Instagram Reels y Facebook. |
| `salida/datos_visualizacion.json` | Las cifras exactas que salieron en esa corrida (trazabilidad). |

Todo es **autocontenido**: la librería de gráficas, la fuente Inter y los datos van dentro de cada HTML. Se abre con doble clic, sin internet y sin servidor.

## Dos librerías de gráficas para elegir

El mismo diseño, los mismos datos y los mismos textos se pueden dibujar con dos librerías de código abierto:

| | Apache ECharts 6.1 | Plotly.js 4.3 |
|---|---|---|
| Licencia | Apache 2.0 | MIT |
| Comando | `generar --motor echarts` | `generar` (**por defecto**) |
| Salida | `salida/echarts/` | `salida/` |
| Peso del HTML | ≈ 1,6 MB | ≈ 1,7 MB |
| Animación de los reels | Nativa (líneas y barras) | Hecha cuadro a cuadro en `_comun_plotly.js` |
| Interacción del dashboard | Zoom con barra deslizante | Zoom, desplazamiento, barra de rango, clic y doble clic en la leyenda |
| Relación con Python | Solo JavaScript | La misma librería que usa `plotly` en Python y Streamlit |

Las plantillas de Plotly (`plantillas/plotly/`) **heredan** de las de ECharts y solo reemplazan el bloque de gráficas: los títulos, textos, KPIs y la tabla se escriben una sola vez.

## Arquitectura

```
PostgreSQL servicio.*  ──►  datos.py      (pg8000, usuario lector de solo lectura)
                             │
                             ▼
                           modelo.py     (KPIs, series, gobiernos, región: un solo dict "D")
                             │
                             ▼
                           generar.py    (Jinja2: plantillas + ECharts + Inter + D → HTML)
                             │
                             ▼
                           capturar.py   (Playwright + Edge → PNG; webm → MP4 con ffmpeg)
```

Archivos:

```
visualizacion/
  config.py         colores, tamaño del reel, zona segura, navegador, conexión
  datos.py          lee Postgres o una carpeta de JSON
  modelo.py         arma los datos que usan las plantillas
  generar.py        escribe los HTML
  capturar.py       PNG y MP4
  __main__.py       línea de comandos
  plantillas/
    _estilos.html   tipografía y colores compartidos
    _formato.js     formato es-CO y contador animado (ambas librerías)
    _comun_echarts.js / _comun_plotly.js   ejes, franjas de gobierno, animación
    _reel_base.html lienzo 1080×1920 con zona segura
    dashboard.html
    reels/01_portada.html … 05_tasa_banrep.html
    plotly/         dashboard.html y reels/ con Plotly (heredan de los anteriores)
  vendor/           echarts.min.js 6.1.0 (Apache 2.0), plotly-basic.min.js 4.3.0 (MIT) e Inter (OFL)
```

## 1. Instalar dependencias (Windows, en la terminal de VS Code)

```powershell
cd C:\Users\aleix\Documents\pipeline-indicadores
.\.venv\Scripts\Activate.ps1
uv pip install jinja2 pg8000 playwright imageio-ffmpeg
```

No hace falta `playwright install`: la captura usa **Microsoft Edge**, que ya viene con Windows. ffmpeg tampoco se instala aparte, lo trae `imageio-ffmpeg`.

## 2. Encender PostgreSQL

```powershell
docker compose --profile postgres up -d
```

(Si la zona de servicio está vacía, corra antes el Paso 6: `docker compose --profile hdfs --profile spark run --rm spark-servir`.)

## 3. Generar el dashboard y los reels

```powershell
python -m visualizacion generar
start salida\dashboard.html
```

## 4. Capturar PNG y MP4

```powershell
python -m visualizacion capturar              # los 5 reels, PNG + MP4 (~20 s por reel)
python -m visualizacion capturar --sin-video  # solo PNG (rápido)
python -m visualizacion capturar --solo portada region
```

O todo de una vez: `python -m visualizacion todo`.

Con Plotly, agregue `--motor plotly` a cualquiera de los tres comandos (`generar`, `capturar`, `todo`); los archivos quedan en `salida\plotly\`.

## 5. Trabajar sin Docker (clase o pruebas)

```powershell
python -m visualizacion exportar datos_servicio         # con Postgres encendido, una vez
python -m visualizacion generar --origen datos_servicio  # luego, sin Docker
```

Así un estudiante puede practicar solo la visualización con los JSON.

## Los 5 reels

| # | Reel | Dato protagonista |
|---|---|---|
| 1 | Colombia en cifras | TRM, tasa BanRep, inflación y desempleo + dólar 12 meses |
| 2 | ¿Cuánto subieron los precios en cada gobierno? | Inflación promedio por período (≥ 3 años de datos) |
| 3 | El dólar a través de 11 gobiernos | TRM mensual 1986–hoy con franjas presidenciales |
| 4 | Colombia frente a la región | Inflación del último año con dato |
| 5 | La tasa del Banco de la República | Tasa de política desde 1998 |

## Decisiones de diseño (para explicar en clase)

- **Zona segura**: todo lo importante está entre x 60–940 y y 160–1480. Abajo y a la derecha van el texto del post y los botones de la app; por eso esa parte del lienzo queda "vacía" a propósito.
- **Colores neutros por gobierno**: todas las barras de gobiernos van en el mismo ámbar, y las franjas alternan dos grises. El color no califica a nadie, solo destaca el dato.
- **Nota metodológica visible**: cada año se asigna al gobierno en el cargo el 1 de julio, y los resultados dependen también del contexto mundial. En el reel de la tasa se aclara que la fija la Junta del BanRep, que es independiente.
- **Formato colombiano**: punto de miles y coma decimal (`$3.228`, `12,25 %`) con `Intl.NumberFormat("es-CO")`, y meses en español en los ejes.
- **Cifras tabulares** (`font-feature-settings: "tnum"`): los contadores no "bailan" mientras suben.
- **Reproducible**: cada corrida guarda `datos_visualizacion.json` con las cifras publicadas.

## Personalizar

- Colores, duración del video y zona segura: `visualizacion/config.py`.
- Textos de un reel: su archivo en `plantillas/reels/`.
- Reel nuevo: copie uno de `plantillas/reels/`, cambie bloques y agréguelo a `REELS` en `generar.py`.
- Otro navegador para capturar: variable `NAVEGADOR_CAPTURA=chrome`.

## Pruebas

```powershell
python -m pytest -q tests/test_visualizacion.py
```

## Problemas comunes

| Síntoma | Causa / solución |
|---|---|
| `connection refused` al generar | Postgres apagado: `docker compose --profile postgres up -d`. |
| `password authentication failed for user "lector"` | El rol se crea con `postgres/01_esquema.sql` (Paso 6). |
| `Executable doesn't exist ... msedge` | Edge no está en la ruta estándar: `$env:NAVEGADOR_CAPTURA="chrome"` (si tiene Chrome) o `python -m playwright install chromium` y `$env:NAVEGADOR_CAPTURA="chromium"`. |
| El MP4 no sube a la red | Ya sale en H.264 + yuv420p + faststart, 1080×1920 a 30 fps, que es lo que piden las tres redes. |
