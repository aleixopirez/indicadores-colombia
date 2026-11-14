// Funciones de dibujo con Plotly.js (dashboard y reels).
// Requiere _formato.js cargado antes.

// Une objetos de configuración en profundidad (los arreglos se reemplazan)
function unir(base, extra) {
  const r = Object.assign({}, base);
  for (const [k, v] of Object.entries(extra || {})) {
    r[k] = v && typeof v === "object" && !Array.isArray(v) && base[k] && typeof base[k] === "object"
      ? unir(base[k], v) : v;
  }
  return r;
}

// Diseño oscuro común. separators ",." = coma decimal y punto de miles (es-CO)
function disenoBase(escala = 1, extra = {}) {
  const t = (n) => Math.round(n * escala);
  return unir({
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    font: { family: FUENTE, color: C.secundario, size: t(13) },
    separators: ",.",
    margin: { l: t(8), r: t(16), t: t(16), b: t(8), pad: t(4) },
    showlegend: false,
    hovermode: "x unified",
    hoverlabel: { bgcolor: C.tarjeta, bordercolor: C.borde, font: { color: C.texto, family: FUENTE, size: t(13) } },
    xaxis: { automargin: true, showgrid: false, zeroline: false, showline: true, linecolor: C.borde,
             ticks: "", tickfont: { color: C.secundario, size: t(13) } },
    yaxis: { automargin: true, gridcolor: C.borde, griddash: "dash", zeroline: false, showline: false,
             ticks: "", tickfont: { color: C.tenue, size: t(12) } },
  }, extra);
}

const CONFIG_DASH = { displaylogo: false, responsive: true, locale: "es",
  modeBarButtonsToRemove: ["select2d", "lasso2d", "autoScale2d"] };
const CONFIG_REEL = { staticPlot: true, locale: "es" };

const xy = (serie) => ({ x: serie.map((p) => p[0]), y: serie.map((p) => p[1]) });

function hexA(color, alfa) {
  return color + Math.round(alfa * 255).toString(16).padStart(2, "0");
}

// Franjas de gobiernos: rectángulos neutros alternos + nombre vertical arriba
function franjasGobierno(desde, escala = 1, conEtiqueta = true) {
  const minimo = desde || "0000";
  const shapes = [], annotations = [];
  D.gobiernos.filter((g) => g.fin > minimo).forEach((g, i) => {
    const x0 = g.inicio < minimo ? minimo : g.inicio;
    const x1 = g.fin > D.fecha_corte ? D.fecha_corte : g.fin;
    if (i % 2) shapes.push({ type: "rect", xref: "x", yref: "paper", x0, x1, y0: 0, y1: 1,
      fillcolor: "rgba(148,163,184,0.07)", line: { width: 0 }, layer: "below" });
    if (conEtiqueta) {
      const medio = new Date((Date.parse(x0) + Date.parse(x1)) / 2).toISOString().slice(0, 10);
      annotations.push({ x: medio, xref: "x", yref: "paper", y: 0.99, yanchor: "top",
        text: g.corto, textangle: -90, showarrow: false,
        font: { color: C.tenue, size: Math.round(11 * escala), family: FUENTE } });
    }
  });
  return { shapes, annotations };
}

// ------------------------------------------------------------- reels
// animar: "linea" (se dibuja de izquierda a derecha) o "barras" (crecen desde 0)
function graficaReel(id, trazas, diseno, animar) {
  const el = document.getElementById(id);
  fuentesListas.then(() => setTimeout(() => {
    if (animar === "linea") {
      const completa = trazas.map((t) => ({ x: t.x.slice(), y: t.y.slice() }));
      const inicio = trazas.map((t) => Object.assign({}, t, { x: t.x.slice(0, 1), y: t.y.slice(0, 1) }));
      Plotly.newPlot(el, inicio, diseno, CONFIG_REEL).then(() => {
        const ms = 2600, t0 = performance.now();
        const paso = (ahora) => {
          const p = Math.min(1, (ahora - t0) / ms);
          const suave = 1 - Math.pow(1 - p, 3);
          Plotly.restyle(el, {
            x: completa.map((c) => c.x.slice(0, Math.max(1, Math.round(c.x.length * suave)))),
            y: completa.map((c) => c.y.slice(0, Math.max(1, Math.round(c.y.length * suave)))),
          });
          if (p < 1) requestAnimationFrame(paso);
        };
        requestAnimationFrame(paso);
      });
    } else if (animar === "barras") {
      // Crecen desde 0 cuadro a cuadro (Plotly.animate deja rastros con esquinas redondeadas)
      const finales = trazas.map((t) => ({ x: t.x.slice(), texttemplate: t.texttemplate }));
      const ceros = trazas.map((t) => Object.assign({}, t, { x: t.x.map(() => 0), text: null, texttemplate: "" }));
      Plotly.newPlot(el, ceros, diseno, CONFIG_REEL).then(() => {
        const ms = 1800, t0 = performance.now();
        const paso = (ahora) => {
          const p = Math.min(1, (ahora - t0) / ms);
          const suave = 1 - Math.pow(1 - p, 3);
          Plotly.restyle(el, { x: finales.map((f) => f.x.map((v) => v * suave)) });
          if (p < 1) requestAnimationFrame(paso);
          else Plotly.restyle(el, { texttemplate: finales.map((f) => f.texttemplate) });
        };
        requestAnimationFrame(paso);
      });
    } else {
      Plotly.newPlot(el, trazas, diseno, CONFIG_REEL);
    }
  }, 700));
}
