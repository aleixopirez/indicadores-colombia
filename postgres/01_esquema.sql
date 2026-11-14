-- Se ejecuta UNA sola vez, cuando PostgreSQL arranca con el volumen vacío.
-- Las tablas las crea Spark (procesamiento/servir.py) en este esquema.

CREATE SCHEMA IF NOT EXISTS servicio;
COMMENT ON SCHEMA servicio IS
  'Zona de servicio: tablas listas para Power BI y los reels. Las recarga Spark (Paso 6); no editar a mano.';

-- Usuario de solo lectura para el dashboard: Power BI no necesita escribir.
CREATE ROLE lector LOGIN PASSWORD 'lector';
GRANT USAGE ON SCHEMA servicio TO lector;
ALTER DEFAULT PRIVILEGES FOR ROLE pipeline IN SCHEMA servicio GRANT SELECT ON TABLES TO lector;
