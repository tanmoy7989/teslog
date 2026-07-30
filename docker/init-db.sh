#!/bin/bash
set -euo pipefail

# Creates the Teslog database and user on first Postgres startup.
# Credentials come from env vars passed by docker-compose (TESLOG_* must be set in .env).

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${TESLOG_DB_USER:-teslog}') THEN
            CREATE USER ${TESLOG_DB_USER:-teslog} WITH PASSWORD '${TESLOG_DB_PASS}';
        END IF;
    END
    \$\$;

    SELECT 'CREATE DATABASE ${TESLOG_DB_NAME:-teslog} OWNER ${TESLOG_DB_USER:-teslog}'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${TESLOG_DB_NAME:-teslog}')\gexec

    GRANT ALL PRIVILEGES ON DATABASE ${TESLOG_DB_NAME:-teslog} TO ${TESLOG_DB_USER:-teslog};
EOSQL
