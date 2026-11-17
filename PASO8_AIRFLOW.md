# Paso 8 · Orquestación con Apache Airflow

Airflow ejecuta **todos los días a las 7:00 a. m.** el mismo recorrido que `actualizar.ps1`, pero sin que nadie lo lance a mano. Cada paso queda registrado, con reintentos y una vista gráfica que muestra qué corrió, cuánto tardó y dónde falló.

```
            ┌─ ingesta_trm ───────────┐
            ├─ ingesta_banrep ────────┼─► encender_kafka_hdfs ─► kafka_producir ─► hdfs_consumir ─┬─► apagar_kafka
            └─ ingesta_banco_mundial ─┘                                                          │
                                                                                                 └─► spark_curar ─► spark_servir ─┬─► apagar_hdfs
                                                                                                                                  └─► generar_dashboard ─► publicar_github
```

## Cómo está montado

| Pieza | Qué es |
|---|---|
| `airflow` | Un solo contenedor con Airflow 3.3.2 en modo *standalone*: interfaz web, scheduler, dag-processor y triggerer. Su base de datos es `airflow`, dentro del mismo PostgreSQL del proyecto. |
| `spark-tareas` | Un contenedor de Spark en reposo. Airflow ejecuta ahí `curar.py` y `servir.py`. Mientras no corre ningún trabajo casi no consume memoria. |
| Socket de Docker | Airflow tiene acceso a Docker para **encender Kafka y HDFS solo mientras se usan** y apagarlos al terminar, así el equipo de 8 GB no se queda sin memoria. |
| `airflow/dags/indicadores_diario.py` | El DAG, es decir, la definición del flujo. |
| `orquestacion/` | Las funciones que usa el DAG para manejar contenedores y publicar en GitHub. Se prueban sin Airflow (`tests/test_orquestacion.py`). |

Las tareas de Python (ingesta, Kafka, HDFS, dashboard) usan **el mismo código del proyecto**, montado dentro del contenedor en `/opt/proyecto`. Si edita algo en VS Code, Airflow usa la versión nueva en la siguiente ejecución.

## 1. Preparar el equipo (una sola vez)

**Memoria para Docker.** Airflow suma cerca de 1,2 GB. Abra (o cree) el archivo `C:\Users\aleix\.wslconfig` y deje:

```ini
[wsl2]
memory=5GB
```

Guárdelo y reinicie WSL:

```powershell
wsl --shutdown
```

Luego abra Docker Desktop de nuevo.

**Token de GitHub** (para publicar el dashboard):

1. En github.com: foto → **Settings** → **Developer settings** → **Personal access tokens** → **Fine-grained tokens** → **Generate new token**.
2. Póngale un nombre (por ejemplo `airflow-indicadores`) y una vigencia (por ejemplo 1 año).
3. En *Repository access* elija **Only select repositories** → `indicadores-colombia`.
4. En *Permissions* → *Repository permissions* → **Contents: Read and write**.
5. **Generate token** y cópielo: GitHub solo lo muestra una vez.
6. En la carpeta del proyecto:
   ```powershell
   copy env.ejemplo .env
   code .env
   ```
   Pegue el token después de `GITHUB_TOKEN=` y guarde.

`.env` está en `.gitignore`: **nunca** se sube a GitHub. Sin token, Airflow genera el dashboard pero no lo publica; la tarea `publicar_github` queda en rosado (*skipped*).

## 2. Encender Airflow

```powershell
cd C:\Users\aleix\Documents\pipeline-indicadores
docker compose --profile todo create
docker compose --profile airflow up -d --build
```

- `create` deja **creados pero apagados** los contenedores de Kafka y HDFS, para que Airflow los encienda cuando los necesite.
- `--build` construye la imagen de Airflow solo la primera vez, lo que tarda unos 5 minutos. Las siguientes veces arranca en segundos.

Espere 1 o 2 minutos y abra **http://localhost:8082**. No pide usuario: está configurado para uso local.

## 3. Primera ejecución

1. En la lista de **Dags** aparece `indicadores_diario`. Actívelo con el interruptor de la izquierda.
2. Haga clic en el nombre y luego en **Trigger** (▶) para correrlo ya, sin esperar a las 7:00.
3. Abra la pestaña **Graph** para ver el flujo en vivo:
   - verde: terminó bien
   - amarillo / verde claro: en cola o corriendo
   - rojo: falló
   - rosado: se saltó (por ejemplo, el Banco Mundial caído)
   - naranja: falló porque falló una tarea anterior
4. Haga clic en una tarea → **Logs** para ver su salida, por ejemplo el reporte de calidad de PySpark en `spark_curar`.

La ejecución completa tarda unos 10 minutos. Al final, el dashboard en GitHub Pages queda actualizado.

**Importante:** Airflow publica directamente en GitHub, sin pasar por su copia local. Antes de hacer cambios propios en el proyecto, traiga lo que publicó:

```powershell
git pull
```

## 4. Uso diario

- Corre solo **a las 7:00 a. m.**, si el PC está encendido, Docker Desktop abierto y el contenedor `airflow` arriba. Este último se enciende solo con Docker gracias a `restart: unless-stopped`.
- Para que Docker arranque al iniciar Windows: Docker Desktop → *Settings* → *General* → **Start Docker Desktop when you sign in**.
- Si el PC estuvo apagado a esa hora, ese día se pierde y **no** se recupera después (`catchup=False`). Puede lanzarlo a mano con **Trigger**.

**Apagar** (los datos y el historial de Airflow se conservan):

```powershell
docker compose --profile airflow stop
```

**Volver a encender:**

```powershell
docker compose --profile airflow up -d
```

Con Airflow, **use `stop` en lugar de `down`**. `down` borra los contenedores de Kafka y HDFS y Airflow ya no los encuentra. Si lo usó, vuelva a crearlos con `docker compose --profile todo create`.

## 5. Conceptos de Airflow que muestra este DAG (para la clase)

| Concepto | Dónde se ve |
|---|---|
| **DAG** y **tareas** con TaskFlow (`@dag`, `@task`) | Todo el archivo `indicadores_diario.py` |
| **Programación** con cron | `schedule="0 7 * * *"`, zona `America/Bogota` |
| **Paralelismo** | Las tres ingestas corren a la vez |
| **Reintentos** | `retries=2` cada 5 minutos por defecto; 1 (a los 10 min) para el Banco Mundial y 3 para `publicar_github` |
| **Saltar sin fallar** | `ingesta_banco_mundial` lanza `AirflowSkipException` si la API está caída |
| **Reglas de disparo** (*trigger rules*) | `encender_kafka_hdfs` usa `none_failed` (acepta que el Banco Mundial se salte); `apagar_kafka` y `apagar_hdfs` usan `all_done` (corren **aunque algo falle**, para liberar memoria) |
| **XCom** | Cada tarea devuelve un resumen (archivos, mensajes) visible en la pestaña *XCom* |
| **catchup** | `False`: no repite los días en que el PC estuvo apagado |
| **Fecha lógica** | La ingesta trae desde `fecha de ejecución − 45 días` |

## 6. Problemas comunes

| Síntoma | Causa / solución |
|---|---|
| `No existe el contenedor 'kafka'` | Se usó `down`. Ejecute `docker compose --profile todo create`. |
| `Permission denied` con `docker.sock` en el log | En `docker-compose.yml`, servicio `airflow`, cambie `user: "50000:0"` por `user: root` y ejecute `docker compose --profile airflow up -d`. |
| La página http://localhost:8082 no abre | Airflow tarda 1-2 min en arrancar: `docker compose logs -f airflow`. |
| `GitHub respondió 401` o `403` | Token vencido o sin permiso *Contents: Read and write*. Genere otro, cámbielo en `.env` y reinicie con `docker compose --profile airflow up -d`. |
| `spark_curar` falla por memoria (`exit code 137`) | Suba `memory` en `.wslconfig` (paso 1) y cierre programas pesados. |
| Docker: "WSL is unresponsive" | `wsl --shutdown` y abra Docker Desktop de nuevo. |
| Al hacer `git pull` aparece un conflicto en `docs/index.html` | Quédese con la versión de GitHub: `git checkout --theirs docs/index.html`, `git add docs/index.html` y `git commit`. |

## 7. ¿Y `actualizar.ps1`?

Sigue funcionando igual, para correr el pipeline a mano sin Airflow. **No** los use al mismo tiempo, porque los dos encienden y apagan los mismos contenedores. Los reels (PNG/MP4) siguen siendo manuales (`python -m visualizacion capturar`), porque necesitan el navegador de Windows.
