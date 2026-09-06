# Production secret files

Create these files locally or materialize them from your secret manager. This directory is git-ignored
except for this README. Use one value per file and permissions `0600`.

- `api_keys`: JSON list such as `["generated-key-1","generated-key-2"]`
- `postgres_database_url`: authenticated URL containing `sslmode=verify-full` and
  `sslrootcert=/run/secrets/postgres_ca`
- `postgres_ca`: PEM CA certificate
- `openai_api_key`
- `jina_api_key`
- `opensearch_password`
- `opensearch_ca`: PEM CA certificate
- `redis_password`
- `redis_ca`: PEM CA certificate
- `langfuse_public_key`
- `langfuse_secret_key`
- `airflow_database_url`: authenticated Airflow metadata DB URL with verified TLS

Do not create production secrets by copying the development credentials from `compose.yml`.
