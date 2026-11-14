// Funciones de dibujo con Apache ECharts (dashboard y reels).
// Requiere _formato.js cargado antes.

// Meses y días en español para los ejes de tiempo de ECharts
echarts.registerLocale("ES", {
  time: {
    month: ["enero","febrero","marzo","abril","mayo","junio","julio","agosto","septiembre","octubre","noviembre","diciembre"],
    monthAbbr: ["ene","feb","mar","abr","may","jun","jul","ago","sep","oct","nov","dic"],
    dayOfWeek: ["domingo","lunes","martes","miércoles","jueves","viernes","sábado"],
    dayOfWeekAbbr: ["dom","lun","mar","mié","jue","vie","sáb"],
  },
  legend: { selector: { all: "Todos", inverse: "Invertir" } },
});

const iniciar = (el) => echarts.init(el, null, { locale: "ES" });

// --------------------------------------------- estilo base de las gráficas
function estiloBase(escala = 1) {
  const t = (n) => Math.round(n * escala);
  return {
    backgroundColor: "transparent",
    textStyle: { fontFamily: "Inter, Segoe UI, sans-serif", color: C.secundario, fontSize: t(13) },
    animationDuration: 2400,
    animationEasing: "cubicOut",
    tooltip: {
      trigger: "axis", backgroundColor: C.tarjeta, borderColor: C.borde,
      textStyle: { color: C.texto, fontSize: t(13) },
    },
    grid: { left: t(12), right: t(16), top: t(24), bottom: t(12),
            outerBoundsMode: "same", outerBoundsContain: "axisLabel" },
  };
}

// Une las opciones del eje con las extra, sin perder axisLabel (fusión de 1 nivel)
function fusionar(base, extra) {
  const r = Object.assign({}, base, extra);
  if (extra.axisLabel) r.axisLabel = Object.assign({}, base.axisLabel, extra.axisLabel);
  return r;
}

function ejeTiempo(escala = 1, extra = {}) {
  return fusionar({
    type: "time",
    axisLine: { lineStyle: { color: C.borde } },
    axisTick: { show: false },
    axisLabel: { color: C.secundario, fontSize: Math.round(13 * escala), hideOverlap: true, fontFamily: FUENTE },
    splitLine: { show: false },
  }, extra);
}

function ejeValor(escala = 1, formato = (v) => fmt.num(v), extra = {}) {
  return fusionar({
    type: "value", scale: true,
    axisLabel: { color: C.tenue, fontSize: Math.round(12 * escala), formatter: formato, fontFamily: FUENTE },
    splitLine: { lineStyle: { color: C.borde, type: "dashed" } },
  }, extra);
}

// ------------------------------------------------- franjas de gobiernos
// Una franja por gobierno, alternando dos tonos NEUTROS (no "colores
// políticos"): sirven para ubicar en el tiempo, no para calificar.
function franjasGobierno(desde, escala = 1, conEtiqueta = true) {
  const minimo = desde || "0000";
  return {
    silent: true,
    data: D.gobiernos
      .filter((g) => g.fin > minimo)
      .map((g, i) => [{
        xAxis: g.inicio < minimo ? minimo : g.inicio,
        itemStyle: { color: i % 2 ? "rgba(148,163,184,0.06)" : "rgba(148,163,184,0.0)" },
        label: {
          show: conEtiqueta, position: "insideTop", distance: Math.round(8 * escala),
          formatter: g.corto, color: C.tenue, fontSize: Math.round(11 * escala),
          rotate: 90, align: "right", verticalAlign: "middle",
        },
      }, { xAxis: g.fin }]),
  };
}

// Gradiente vertical para áreas bajo la línea
function gradiente(color, alfaArriba = 0.35) {
  return new echarts.graphic.LinearGradient(0, 0, 0, 1, [
    { offset: 0, color: color + Math.round(alfaArriba * 255).toString(16).padStart(2, "0") },
    { offset: 1, color: color + "00" },
  ]);
}


// Gráfica de un reel: arranca cuando ya entró el encabezado
function graficaReel(id, opcion) {
  fuentesListas.then(() => {
    const g = iniciar(document.getElementById(id));
    setTimeout(() => g.setOption(Object.assign(estiloBase(1.6), opcion)), 700);
  });
}
