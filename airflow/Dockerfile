# Airflow 3.3.2 con lo que necesita el proyecto. Se construye una sola vez:
#   docker compose --profile airflow build
FROM apache/airflow:3.3.2-python3.12

COPY requisitos.txt /tmp/requisitos.txt
# Se fija la versión de Airflow para que pip no la cambie al instalar lo demás.
RUN pip install --no-cache-dir "apache-airflow==3.3.2" -r /tmp/requisitos.txt
