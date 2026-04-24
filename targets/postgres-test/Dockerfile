FROM pgvector/pgvector:pg16

# Seed aplicado automaticamente pelo docker-entrypoint.sh do Postgres na
# primeira inicialização (quando o PGDATA está vazio). Gera ~26 assets de IA
# quando o Radar Agent escaneia este banco.
COPY init/00-seed.sql /docker-entrypoint-initdb.d/00-seed.sql
