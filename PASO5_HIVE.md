# Paso 5 — Hive: SQL sobre el data lake

```
HDFS /datalake/curated/indicadores (Parquet) ─┐
HDFS /datalake/referencia/gobiernos (CSV)  ───┼─► (5) HIVE: tablas externas + vista ─► SQL
                                              │      indicadores_gobierno
```

## Objetivo

Consultar con **SQL** lo que Spark dejó en HDFS, sin mover ni copiar datos, y
cruzar los indicadores con los **periodos presidenciales** de Colombia.

## Requisitos

- Paso 4 ejecutado (zona curada en HDFS).
- RAM: HDFS + Hive ~2,7 GB. Kafka y Spark apagados.
- La primera vez se descarga `apache/hive:4.0.1` (~900 MB).

## Ejecución

```powershell
# 1. Subir la tabla de gobiernos a HDFS (desde Windows, por WebHDFS)
python -m datalake subir referencia/gobiernos.csv /datalake/referencia/gobiernos/gobiernos.csv

# 2. Encender Hive (el perfil hive enciende también HDFS)
docker compose stop kafka
docker compose --profile hive up -d
docker compose ps                 # hiveserver2 (healthy): tarda 1-2 minutos

# 3. Crear tablas y vista
docker compose exec hiveserver2 beeline -u jdbc:hive2://localhost:10000/ -f /proyecto/hive/01_tablas.sql

# 4. Consultas de análisis
docker compose exec hiveserver2 beeline -u jdbc:hive2://localhost:10000/indicadores_db -f /proyecto/hive/02_consultas.sql

# 5. Consola interactiva (salir con !quit)
docker compose exec hiveserver2 beeline -u jdbc:hive2://localhost:10000/indicadores_db

# 6. Reiniciar solo Hive (p. ej. tras cambiar su configuración)
docker compose --profile hive up -d --force-recreate hiveserver2

# 7. Apagar Hive y HDFS (los datos de HDFS se conservan)
docker compose --profile hive down
```

No usar `stop` ni `restart` con Hive: al reiniciar el mismo contenedor, la
imagen intenta crear otra vez el metastore y falla. Cada vez que Hive se
crea de nuevo, repetir el paso 3 (tarda segundos).

## Estructura

```
referencia/gobiernos.csv   # periodos presidenciales 1986-2030 (mantenido a mano)
referencia/LEEME.md        # fuente y reglas de la tabla
hive/01_tablas.sql         # base, tablas externas, MSCK REPAIR, vista
hive/02_consultas.sql      # 4 consultas de análisis
```

## Resultado de referencia (6 nov. 2026)

Consulta 1 — promedios anuales por gobierno (Colombia, Banco Mundial):

| presidente | periodo | inflación | desempleo | crec. PIB | años |
|---|---|---:|---:|---:|---:|
| César Gaviria Trujillo | 1990-1994 | 25,67 | 8,90 | 4,31 | 4 |
| Ernesto Samper Pizano | 1994-1998 | 19,71 | 11,92 | 2,81 | 4 |
| Andrés Pastrana Arango | 1998-2002 | 8,60 | 17,53 | 0,73 | 4 |
| Álvaro Uribe Vélez | 2002-2006 | 5,59 | 12,27 | 5,20 | 4 |
| Álvaro Uribe Vélez | 2006-2010 | 4,75 | 11,42 | 3,91 | 4 |
| Juan Manuel Santos Calderón | 2010-2014 | 2,88 | 9,57 | 5,12 | 4 |
| Juan Manuel Santos Calderón | 2014-2018 | 5,01 | 8,99 | 2,24 | 4 |
| Iván Duque Márquez | 2018-2022 | 4,93 | 12,68 | 3,53 | 4 |
| Gustavo Petro Urrego | 2022-2026 | 7,83 | 9,17 | 1,66 | 3 |

Consulta 2 — TRM: el gobierno 2026-2030 (Abelardo de la Espriella) aparece
con `en_curso = true` y datos desde el 7 ago. 2026.

## Decisiones de diseño (para discutir en clase)

1. **Tablas EXTERNAS.** Hive guarda solo la descripción; los datos siguen en
   HDFS. `DROP TABLE` no borra archivos. Spark escribe, Hive consulta.
2. **Metastore embebido (Derby) y desechable.** Liviano para 8 GB. Se pierde
   al apagar, pero el DDL lo recrea. En producción: metastore en PostgreSQL,
   compartido por Hive, Spark y otras herramientas.
3. **`MSCK REPAIR TABLE`.** Hive no se entera solo de las carpetas
   `indicador=...` que crea Spark; hay que registrarlas.
4. **Regla de asignación de años** (la decisión más delicada del proyecto):
   - Series diarias: por fecha exacta (`inicio` incluido, `fin` excluido).
   - Series anuales: al gobierno en el cargo el **1 de julio** (el que
     gobernó la mayor parte del año). 2022 → Duque; 2023 → Petro.
   Otra regla (p. ej. 31 de diciembre) cambia los promedios: **se debe citar
   al publicar**.
5. **Join por rango, no por igualdad.** No hay una columna común entre un
   indicador y un gobierno; la condición es `inicio <= fecha < fin`. Hive lo
   resuelve como producto cruzado filtrado y por seguridad lo bloquea por
   defecto (`hive.strict.checks.cartesian.product`).
6. **Funciones de ventana** (`ROW_NUMBER`) para el primer y último dato de
   cada periodo, sin subconsultas por gobierno.
7. **`anios_con_datos` y `en_curso`.** Un promedio de 1 año no se compara con
   uno de 4: la consulta dice cuántos datos hay detrás de cada cifra.
8. **Suplantación (proxy users).** Hive accede a HDFS "en nombre de" quien
   se conecta, y HDFS lo rechaza si no lo autoriza con
   `hadoop.proxyuser.<usuario>.hosts/groups` (en `hadoop.env`). Este paso
   falló dos veces con `User: root is not allowed to impersonate root`:
   desactivar `hive.server2.enable.doAs` no bastó, porque el metastore
   embebido también suplanta por su cuenta. La solución correcta está del
   lado de HDFS: autorizar al usuario de Hive. En un clúster real se limita
   a hosts y grupos concretos en vez de `*`.
   Un tercer error vino después, al ejecutar la primera consulta con Tez:
   Hive se identificaba como `root` (variable `HADOOP_USER_NAME`) pero el
   proceso corría como `hive`, y Tez exige que el dueño de su carpeta
   temporal sea quien envía la consulta. Regla general: **un mismo servicio
   debe tener una sola identidad**.
9. **Solo nombres y fechas en `gobiernos`.** El pipeline mide; no clasifica
   ni califica. Un indicador depende de muchos factores (economía mundial,
   petróleo, pandemia), no solo del gobierno.

## Preguntas de control

- Ejecuta `DROP TABLE indicadores;` y luego `python -m datalake ls /datalake/curated/indicadores`.
  ¿Siguen los archivos? ¿Por qué?
- Cambia la regla anual a `'-12-31'` en la vista. ¿Qué gobiernos cambian de promedio?
- ¿Por qué Barco (1986-1990) tiene 1 año de datos y De la Espriella ninguno en la consulta 1?
- ¿Qué pasaría si `fin` fuera incluido (`<=`) en vez de excluido (`<`)?

## Siguiente paso

**Paso 6 — PostgreSQL + Power BI:** llevar las tablas de resultados a
PostgreSQL (zona de servicio) y conectar el dashboard.
