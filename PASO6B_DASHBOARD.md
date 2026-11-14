# Paso 6B — Dashboard en Power BI para reels (TikTok, Instagram, Facebook)

Archivos de apoyo:
- `powerbi/prompts_copilot.md` — instrucciones listas para pegar en Copilot (si tu cuenta lo tiene)
- `powerbi/tema_indicadores.json` — tema visual (colores, tipografía, tarjetas)
- `powerbi/medidas.dax` — medidas listas para copiar

## 0. Principios de diseño (por qué se ve "de especialista")

1. **Un mensaje por página.** Un reel dura segundos: cada página responde UNA
   pregunta ("¿cuánto cuesta el dólar hoy?"), con el título como respuesta.
2. **Un solo color de acento.** Ámbar = Colombia o el dato protagonista. Todo
   lo demás en tonos fríos y grises. El ojo va directo a lo importante.
3. **Sin rojo/verde para gobiernos.** Mismo color para todos: el dashboard
   informa, no califica. Eso es lo que da credibilidad en redes.
4. **Siempre fuente + fecha + regla.** Cada página lleva al pie la fuente
   (medida `Fuentes`), la fecha de corte y, si compara gobiernos, la nota
   metodológica. Sin eso, una cifra en redes no es confiable.
5. **Números grandes, texto mínimo.** En el celular se lee a 30 cm y con
   el pulgar encima: cifras de 40+ pt, etiquetas de 14+ pt, nada de leyendas
   diminutas.
6. **Zonas seguras.** TikTok e Instagram tapan arriba (pestañas), abajo
   (texto del video y música) y a la derecha (botones de "me gusta"):

```
   1080 px
 ┌──────────────────────────┐ 0
 │ zona tapada (pestañas)   │
 ├──────────────────────┬───┤ 160
 │                      │   │
 │   ZONA SEGURA        │ b │
 │   x: 60 → 940        │ o │
 │   y: 160 → 1480      │ t │  1920 px
 │                      │ o │
 │                      │ n │
 │                      │ e │
 ├──────────────────────┴─s─┤ 1480
 │ zona tapada (descripción,│
 │ música, comentarios)     │
 └──────────────────────────┘ 1920
```

Todo lo importante va dentro de la zona segura; el fondo puede llegar a los
bordes.

## 1. Preparación (una sola vez)

1. **Aplicar el tema:** Vista → Temas → (flecha) → **Examinar temas** →
   `powerbi/tema_indicadores.json`.
2. **Renombrar tablas** (panel Datos, clic derecho → Cambiar nombre):
   `servicio indicadores` → `indicadores`, `servicio resumen_gobierno` →
   `resumen_gobierno`, `servicio gobiernos` → `gobiernos`,
   `servicio catalogo_indicadores` → `catalogo`.
3. **Relación** (Vista de modelo): `indicadores[periodo]` (*) → `gobiernos[periodo]` (1).
4. **Medidas:** crear las de `powerbi/medidas.dax` (clic derecho en
   `indicadores` → Nueva medida) y la columna `Gobierno` en `resumen_gobierno`.
5. **Orden cronológico:** en `gobiernos`, columna `periodo` → Herramientas de
   columnas → Ordenar por columna → `inicio`. Igual con `Gobierno` en
   `resumen_gobierno`.
6. **Columna valor:** en `indicadores`, seleccionar `valor` → Resumen →
   **No resumir**. (En las gráficas usar la medida `Valor`.)

## 2. Tamaño de página 9:16

Para cada página de reel: panel Formato (página sin nada seleccionado) →
**Configuración del lienzo** → Tipo: **Personalizado** → **1080 × 1920**.
Vista → **Ajustar a la página** para trabajarla completa en pantalla.

## 3. Las páginas

Coordenadas en píxeles (x, y, ancho, alto). Se fijan en Formato → General →
Propiedades → Tamaño y posición.

### Página 1 — «Colombia hoy» (portada)

| visual | contenido | posición |
|---|---|---|
| Cuadro de texto | **COLOMBIA EN CIFRAS** (40 pt, blanco) | 60, 170, 880, 70 |
| Tarjeta | medida `Fecha de actualización` (16 pt, gris) | 60, 240, 880, 50 |
| Tarjeta | `TRM actual` · etiqueta "Dólar hoy (TRM)" | 60, 320, 430, 220 |
| Tarjeta | `Variación TRM 12 meses` · "vs hace un año" | 510, 320, 430, 220 |
| Tarjeta | `Tasa BanRep actual` · "Tasa del Banco de la República" | 60, 560, 430, 220 |
| Tarjeta | `Inflación Colombia` · título con `Título inflación` | 510, 560, 430, 220 |
| Gráfico de líneas | Eje `fecha`, valor `Valor`; filtros: indicador = trm, fuente = banrep, fecha = últimos 12 meses (filtro relativo) · Título "El dólar en los últimos 12 meses" | 60, 800, 880, 560 |
| Tarjeta | `Fuentes` (12 pt) | 60, 1380, 880, 80 |

### Página 2 — «La inflación, gobierno por gobierno»

| visual | contenido | posición |
|---|---|---|
| Cuadro de texto | **INFLACIÓN PROMEDIO POR GOBIERNO** + subtítulo "Colombia, % anual" | 60, 170, 880, 130 |
| Gráfico de barras **horizontales** | Eje `resumen_gobierno[Gobierno]`, valor `inflacion_promedio`; filtro: `anios_con_datos` ≥ 3 · Etiquetas de datos activadas · Orden: por `Gobierno` (cronológico) | 60, 320, 880, 900 |
| Tarjeta | `Nota metodológica` (12 pt) | 60, 1240, 880, 120 |
| Tarjeta | `Fuentes` | 60, 1380, 880, 80 |

Barras horizontales porque los nombres son largos y en vertical no caben.
Todas del mismo color (ámbar); el dato es el protagonista, no un gobierno.

### Página 3 — «El dólar en 40 años»

| visual | contenido | posición |
|---|---|---|
| Cuadro de texto | **EL DÓLAR EN COLOMBIA, 1986-2026** | 60, 170, 880, 90 |
| Tarjeta | `TRM actual` | 60, 270, 880, 160 |
| Gráfico de líneas | Eje `fecha`, valor `Valor`, **Leyenda `periodo`**; filtros: indicador = trm, fuente = banrep, fecha ≥ 7/8/1986 | 60, 450, 880, 900 |
| Tarjeta | `Fuentes` | 60, 1380, 880, 80 |

La leyenda por `periodo` pinta cada tramo de la línea de un color distinto:
se ve en qué gobierno ocurrió cada subida o bajada sin agregar texto.

### Página 4 — «Colombia frente a la región»

| visual | contenido | posición |
|---|---|---|
| Cuadro de texto | **INFLACIÓN: COLOMBIA VS. LA REGIÓN** + `Título inflación` | 60, 170, 880, 120 |
| Gráfico de barras horizontales | Eje `pais_nombre`, valor `Valor`; filtros: indicador = inflacion_anual_pct, anio = último · Orden descendente · **Colores: Colombia ámbar, el resto gris #475569** (Formato → Barras → Colores → Mostrar todo) | 60, 310, 880, 560 |
| Tarjeta | `Brecha inflación vs mundo (pp)` · "puntos sobre el promedio mundial" | 60, 890, 880, 160 |
| Gráfico de líneas | Eje `anio`, valor `Valor`, leyenda `pais_nombre`; filtros: indicador = inflacion_anual_pct, país = Colombia y Mundo, anio ≥ 2015 | 60, 1070, 880, 290 |
| Tarjeta | `Fuentes` | 60, 1380, 880, 80 |

### Página 5 — «La tasa del Banco de la República»

| visual | contenido | posición |
|---|---|---|
| Cuadro de texto | **TASA DE INTERÉS DEL BANCO DE LA REPÚBLICA** | 60, 170, 880, 90 |
| Tarjeta | `Tasa BanRep actual` | 60, 270, 880, 160 |
| Gráfico de líneas | Eje `fecha`, valor `Valor`, leyenda `periodo`; filtro indicador = tasa_politica_monetaria | 60, 450, 880, 780 |
| Cuadro de texto | "La fija la Junta Directiva del Banco de la República, independiente del Gobierno." (14 pt) | 60, 1250, 880, 110 |
| Tarjeta | `Fuentes` | 60, 1380, 880, 80 |

Esa nota evita el error más común en redes: atribuir la tasa de interés al
presidente.

### Página 6 — «Explorador» (para clase y análisis, no para reels)

Lienzo 16:9 (1920 × 1080). Segmentadores de `nombre_indicador`, `pais_nombre`
y `periodo`; gráfico de líneas `fecha` × `Valor` por `pais_nombre`; tabla
`resumen_gobierno` completa. Sirve para explorar antes de decidir qué reel
hacer.

## 4. Exportar para redes

- **Imagen por página:** Archivo → Exportar → **Exportar a PDF** (todas las
  páginas, 1080 × 1920) y convertir cada página a PNG; o capturar la página en
  modo "Ajustar a la página" a pantalla completa.
- **Video:** Power BI no exporta video. En el **Paso 8** un script de Python
  leerá PostgreSQL y generará los reels MP4 (gráficas animadas, 9:16) de
  forma automática; estas páginas sirven como diseño de referencia.

## 5. Lista de chequeo antes de publicar

- [ ] La fecha de corte es la de hoy (Inicio → Actualizar después de cargar).
- [ ] Cada página tiene fuente; las de gobiernos, la nota metodológica.
- [ ] Nada importante fuera de la zona segura (x 60–940, y 160–1480).
- [ ] Cifras redondeadas (TRM sin decimales en títulos, tasas con 1 decimal).
- [ ] El texto del post describe datos, no opiniones ("la inflación promedió
      X %", no "el mejor/peor gobierno").
