# Instrucciones para Copilot en Power BI

**Requisito:** Copilot solo funciona si el área de trabajo está en una capacidad
de Fabric de pago (F2 o superior) o Power BI Premium (P1 o superior). Con Pro o
la versión gratuita no aparece o no responde.

**Antes de usar Copilot** (Copilot no hace bien estas tareas; son 2 minutos):
1. Vista → Temas → Examinar temas → `powerbi/tema_indicadores.json`.
2. Renombrar las tablas: `indicadores`, `resumen_gobierno`, `gobiernos`, `catalogo`.
3. Crear la página y ponerle tamaño **1080 × 1920** (Formato → Configuración
   del lienzo → Personalizado). Copilot construye sobre la página activa.

**Cómo usarlas:** Inicio → **Copilot** → pegar una instrucción por vez →
revisar lo que propone → Conservar. Si el resultado en español es pobre,
repetir la instrucción en inglés (Copilot suele entender mejor el inglés).

---

## 1. Medidas DAX

En la **Vista de consulta DAX** (ícono de tabla con DAX a la izquierda) →
Copilot:

```
Crea en la tabla indicadores las medidas que están en el archivo medidas.dax:
Valor (promedio de valor), TRM actual y TRM hace un año (filtrando indicador = "trm"
y fuente = "banrep", usando la fecha máxima), Variación TRM 12 meses,
Tasa BanRep actual (indicador = "tasa_politica_monetaria", dividida entre 100),
Inflación Colombia e Inflación mundo (indicador = "inflacion_anual_pct", último
año con dato para pais = "COL", divididas entre 100), Brecha inflación vs mundo (pp),
Desempleo Colombia, Fecha de actualización ("Datos al " + fecha máxima en español)
y Fuentes (concatenar los valores distintos de fuente_cita separados por " · ").
```

Más confiable: pegar tú mismo cada medida de `powerbi/medidas.dax`
(clic derecho en `indicadores` → Nueva medida). Copilot sirve para revisar o
explicar una medida: *"Explica qué hace la medida TRM hace un año"*.

---

## 2. Página «Colombia hoy»

```
Crea una página de portada vertical para redes sociales titulada "COLOMBIA EN CIFRAS".
Arriba, una tarjeta con la medida Fecha de actualización.
Debajo, cuatro tarjetas grandes en dos filas: TRM actual, Variación TRM 12 meses,
Tasa BanRep actual e Inflación Colombia, cada una con una etiqueta corta en español.
Debajo, un gráfico de líneas de la medida Valor por fecha, filtrado a indicador = "trm",
fuente = "banrep" y los últimos 12 meses, titulado "El dólar en los últimos 12 meses".
Al pie, una tarjeta pequeña con la medida Fuentes.
Usa los colores del tema; no agregues leyendas ni segmentadores.
```

## 3. Página «Inflación por gobierno»

```
Crea una página vertical titulada "INFLACIÓN PROMEDIO POR GOBIERNO" con subtítulo
"Colombia, % anual". Agrega un gráfico de barras horizontales con resumen_gobierno[Gobierno]
en el eje y resumen_gobierno[inflacion_promedio] como valor, filtrado a
anios_con_datos mayor o igual a 3, ordenado cronológicamente por inicio, con
etiquetas de datos visibles y todas las barras del mismo color.
Debajo, una tarjeta con la medida Nota metodológica y al pie una tarjeta con la medida Fuentes.
No uses colores distintos por gobierno.
```

## 4. Página «El dólar en 40 años»

```
Crea una página vertical titulada "EL DÓLAR EN COLOMBIA, 1986-2026".
Arriba, una tarjeta grande con la medida TRM actual.
Debajo, un gráfico de líneas grande de la medida Valor por indicadores[fecha], con
indicadores[periodo] como leyenda, filtrado a indicador = "trm", fuente = "banrep" y
fecha desde el 7 de agosto de 1986. Al pie, una tarjeta con la medida Fuentes.
```

## 5. Página «Colombia frente a la región»

```
Crea una página vertical titulada "INFLACIÓN: COLOMBIA VS. LA REGIÓN".
Agrega un gráfico de barras horizontales con indicadores[pais_nombre] y la medida Valor,
filtrado a indicador = "inflacion_anual_pct" y al último año disponible, ordenado de
mayor a menor, con etiquetas de datos. Debajo, una tarjeta con la medida
Brecha inflación vs mundo (pp) con la etiqueta "puntos sobre el promedio mundial".
Debajo, un gráfico de líneas de Valor por anio con pais_nombre como leyenda, solo
Colombia y Mundo, desde 2015. Al pie, la medida Fuentes.
```

Ajuste manual después: Formato del gráfico de barras → Barras → Colores →
Mostrar todo → **Colombia en ámbar (#F5B700)** y el resto en gris (#475569).

## 6. Página «Tasa del Banco de la República»

```
Crea una página vertical titulada "TASA DE INTERÉS DEL BANCO DE LA REPÚBLICA".
Arriba, una tarjeta grande con la medida Tasa BanRep actual. Debajo, un gráfico de
líneas de la medida Valor por fecha con periodo como leyenda, filtrado a
indicador = "tasa_politica_monetaria". Agrega un cuadro de texto que diga:
"La fija la Junta Directiva del Banco de la República, independiente del Gobierno."
Al pie, la medida Fuentes.
```

## 7. Página «Explorador» (16:9, para clase)

```
Crea una página de análisis con segmentadores de nombre_indicador, pais_nombre y periodo,
un gráfico de líneas de la medida Valor por fecha con pais_nombre como leyenda, y una
tabla con todas las columnas de resumen_gobierno.
```

---

## Ajustes finales (Copilot no los hace bien)

Después de que Copilot cree cada página, revisa con la guía `PASO6B_DASHBOARD.md`:
- **Posiciones:** todo dentro de la zona segura (x 60–940, y 160–1480).
- **Tamaños:** cifras de las tarjetas de 40 pt o más; etiquetas de 14 pt o más.
- **Agregación:** que las gráficas usen la medida `Valor` (promedio) y no
  "Suma de valor". Si aparece "Suma de valor", cámbiala.
- **Textos:** que ningún título califique a un gobierno ("mejor", "peor").
