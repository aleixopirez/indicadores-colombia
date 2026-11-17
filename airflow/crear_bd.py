"""Crea la base de datos 'airflow' dentro del PostgreSQL del proyecto, si no
existe. Airflow guarda ahí su estado (ejecuciones, tareas, registros).
Se ejecuta cada vez que arranca el contenedor de Airflow; si ya existe, no hace nada."""
import os
import time

import pg8000.native

for intento in range(30):
    try:
        con = pg8000.native.Connection(
            user=os.getenv("POSTGRES_USER", "pipeline"),
            password=os.getenv("POSTGRES_PASSWORD", "pipeline"),
            host=os.getenv("POSTGRES_HOST", "postgres"), database="indicadores")
        break
    except Exception as e:          # PostgreSQL todavía arrancando
        print(f"Esperando a PostgreSQL ({e})")
        time.sleep(2)
else:
    raise SystemExit("No se pudo conectar a PostgreSQL")

if con.run("SELECT 1 FROM pg_database WHERE datname = 'airflow'"):
    print("La base de datos 'airflow' ya existe.")
else:
    con.run("CREATE DATABASE airflow")
    print("Base de datos 'airflow' creada.")
con.close()
