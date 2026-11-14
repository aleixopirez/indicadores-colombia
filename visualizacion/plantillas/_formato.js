// Funciones comunes a cualquier librería de gráficas (ECharts o Plotly).
// D (los datos) lo define la página antes de cargar este archivo.

const C = D.colores;
const LOCALE = "es-CO";
const FUENTE = "Inter, Segoe UI, sans-serif";

// Las gráficas se dibujan cuando la fuente Inter ya cargó; si no, la
// librería mide las etiquetas con otra fuente y las recorta.
const fuentesListas = document.fonts ? document.fonts.ready : Promise.resolve();

// ---------------------------------------------------------------- formato
const fmt = {
  num: (v, dec = 0) => v == null ? "—" :
    new Intl.NumberFormat(LOCALE, { minimumFractionDigits: dec, maximumFractionDigits: dec }).format(v),
  pesos: (v, dec = 0) => v == null ? "—" : "$" + fmt.num(v, dec),
  pct: (v, dec = 1) => v == null ? "—" : fmt.num(v, dec) + " %",
  signo: (v, dec = 1) => v == null ? "—" : (v > 0 ? "+" : v < 0 ? "−" : "") + fmt.num(Math.abs(v), dec),
  fecha: (iso) => new Date(iso + "T12:00:00").toLocaleDateString(LOCALE,
    { day: "numeric", month: "long", year: "numeric" }),
};

// Contador animado para las cifras grandes
function contar(el, valor, formato, ms = 1400, retraso = 0) {
  if (valor == null) { el.textContent = "—"; return; }
  setTimeout(() => {
    const inicio = performance.now();
    const paso = (ahora) => {
      const p = Math.min(1, (ahora - inicio) / ms);
      const suave = 1 - Math.pow(1 - p, 3);
      el.textContent = formato(valor * suave);
      if (p < 1) requestAnimationFrame(paso); else el.textContent = formato(valor);
    };
    requestAnimationFrame(paso);
  }, retraso);
}
