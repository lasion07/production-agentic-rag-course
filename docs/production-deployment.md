# Production deployment boundary

`compose.yml` is a development-only learning stack. Production uses `compose.production.yml`, which
contains only a TLS gateway, the serving API, and an optional scheduler profile. PostgreSQL, Redis,
OpenSearch and Langfuse must be managed services or independently operated private services.

## Security boundary

- Caddy is the only service publishing host ports (`80/443`) and obtains the public TLS certificate.
- The API is reachable only on the internal Compose network through `expose`, not a host `ports` mapping.
- Stateful dependencies must use private DNS/VPC addresses, authentication, TLS and verified certificates.
- The production stack does not deploy OpenSearch Dashboards, Airflow Webserver, database consoles or
  observability stores. If an operator UI is added, put it behind a separate authenticated administrative
  ingress with SSO/MFA; never reuse the public RAG hostname.
- API and Airflow scheduler run as fixed non-root users, with read-only root filesystems, dropped Linux
  capabilities, `no-new-privileges`, PID/resource limits and bounded termination grace periods.
- Secrets are mounted as files under `/run/secrets`; entrypoints export only an explicit allowlist at runtime.
- Both workloads set `ENVIRONMENT=production` with an explicit `SERVICE_ROLE`, so shared dependency
  controls apply to ingestion without requiring API-only credentials.
- `OPENSEARCH_SCHEMA_MANAGEMENT_ENABLED=false` prevents API startup and scheduled ingestion from creating
  indices or pipelines. Provision and migrate search schemas in an explicit release job.

## External dependency requirements

- PostgreSQL: authenticated URL with `sslmode=verify-full` and a trusted CA path.
- Redis: password/ACL, TLS enabled and certificate requirement set to `required`.
- OpenSearch: HTTPS, verified CA and a least-privilege service account limited to the RAG indices/pipelines.
- OpenAI and Jina: HTTPS endpoints and restricted/rotatable project keys.
- Langfuse: HTTPS and project-scoped credentials. Raw content additionally requires the explicit
  `ALLOW_PRODUCTION_CONTENT_CAPTURE=true` policy decision.
- Airflow: the included production profile runs only the scheduler. Its metadata database must use verified
  TLS. Deploy any web UI separately behind TLS plus SSO/MFA.

## Secret preparation

Create the files listed in `deploy/secrets/README.md` from a secret manager or a protected local directory.
Never commit them. `api_keys` must be a JSON array; database URLs should percent-encode special password
characters. CA files must contain the issuing PEM chain rather than a server certificate copied ad hoc.

## Validate and deploy

1. Copy `deploy/production.env.example` to a protected location and replace every example value.
2. Point `PRODUCTION_SECRETS_DIR` at the populated secret directory.
3. Use immutable image references, preferably a digest, for `RAG_API_IMAGE` and `RAG_AIRFLOW_IMAGE`.
4. Validate configuration:

   `docker compose --env-file /secure/production.env -f compose.production.yml config --quiet`

5. Start serving:

   `docker compose --env-file /secure/production.env -f compose.production.yml up -d gateway api`

6. Run Airflow database migrations as a one-off release job, then start the optional scheduler profile:

   `docker compose --profile ingestion --env-file /secure/production.env -f compose.production.yml up -d airflow-scheduler`

7. Verify HTTPS `/api/v1/live`, then call protected `/api/v1/health` with a production API key.

## Rotation and rollback

- Rotate provider/service credentials by replacing mounted secret files and recreating only the affected
  containers. Keep two API keys during a client-key overlap window.
- Roll back by restoring the previous immutable image reference and recreating API/scheduler. Caddy data is
  persistent so certificate state survives application rollback.
- This manifest deliberately performs no database or OpenSearch schema mutation. Release migrations and
  index cutover are handled by PR-P0-04.
