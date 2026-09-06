import os
import subprocess
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).parents[2]


def test_production_compose_only_publishes_tls_gateway():
    manifest = yaml.safe_load((PROJECT_ROOT / "compose.production.yml").read_text())
    services = manifest["services"]

    assert set(services) == {"gateway", "api", "airflow-scheduler"}
    assert services["gateway"]["ports"] == ["80:80", "443:443"]
    assert "ports" not in services["api"]
    assert "ports" not in services["airflow-scheduler"]
    assert not ({"postgres", "redis", "opensearch", "langfuse-web"} & set(services))


def test_production_workloads_are_non_root_and_hardened():
    manifest = yaml.safe_load((PROJECT_ROOT / "compose.production.yml").read_text())

    for name, expected_user in (("api", "10001:10001"), ("airflow-scheduler", "50000:50000")):
        service = manifest["services"][name]
        assert service["user"] == expected_user
        assert service["read_only"] is True
        assert service["cap_drop"] == ["ALL"]
        assert "no-new-privileges:true" in service["security_opt"]
        assert service["deploy"]["resources"]["limits"]["memory"]
        assert service["stop_grace_period"]


def test_production_workloads_enable_role_aware_validation_and_disable_schema_mutation():
    manifest = yaml.safe_load((PROJECT_ROOT / "compose.production.yml").read_text())

    api_environment = manifest["services"]["api"]["environment"]
    scheduler_environment = manifest["services"]["airflow-scheduler"]["environment"]

    assert api_environment["ENVIRONMENT"] == "production"
    assert api_environment["SERVICE_ROLE"] == "api"
    assert api_environment["OPENSEARCH_SCHEMA_MANAGEMENT_ENABLED"] == "false"
    assert scheduler_environment["ENVIRONMENT"] == "production"
    assert scheduler_environment["SERVICE_ROLE"] == "ingestion"
    assert scheduler_environment["OPENSEARCH_SCHEMA_MANAGEMENT_ENABLED"] == "false"


def test_production_secrets_are_file_mounted_not_literal_environment_values():
    manifest = yaml.safe_load((PROJECT_ROOT / "compose.production.yml").read_text())
    api = manifest["services"]["api"]
    environment = api["environment"]

    for variable in (
        "API_KEYS",
        "POSTGRES_DATABASE_URL",
        "OPENAI_API_KEY",
        "JINA_API_KEY",
        "OPENSEARCH__PASSWORD",
        "REDIS__PASSWORD",
        "LANGFUSE_SECRET_KEY",
    ):
        assert variable not in environment
        assert environment[f"{variable}_FILE"].startswith("/run/secrets/")


def test_images_declare_non_root_runtime_users_and_safe_entrypoints():
    api_dockerfile = (PROJECT_ROOT / "Dockerfile").read_text()
    airflow_dockerfile = (PROJECT_ROOT / "airflow/Dockerfile.production").read_text()
    airflow_entrypoint = (PROJECT_ROOT / "airflow/production-entrypoint.sh").read_text()

    assert "USER 10001:10001" in api_dockerfile
    assert 'ENTRYPOINT ["/usr/local/bin/rag-entrypoint"]' in api_dockerfile
    assert "USER 50000:50000" in airflow_dockerfile
    assert 'ENTRYPOINT ["/usr/local/bin/airflow-production-entrypoint"]' in airflow_dockerfile
    assert "airflow users create" not in airflow_entrypoint
    assert "admin/admin" not in airflow_entrypoint


def test_api_entrypoint_loads_secret_file_and_rejects_ambiguous_sources(tmp_path):
    script = PROJECT_ROOT / "deploy/docker-entrypoint.sh"
    secret_file = tmp_path / "api_keys"
    secret_file.write_text('["safe-test-key"]')
    environment = os.environ.copy()
    environment.pop("API_KEYS", None)
    environment["API_KEYS_FILE"] = str(secret_file)

    loaded = subprocess.run(
        [
            "sh",
            str(script),
            "python",
            "-c",
            'import os; assert os.environ["API_KEYS"] == \'["safe-test-key"]\'',
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert loaded.returncode == 0

    environment["API_KEYS"] = '["conflicting-key"]'
    rejected = subprocess.run(
        ["sh", str(script), "python", "-c", "pass"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert rejected.returncode != 0
    assert "Both API_KEYS and API_KEYS_FILE are set" in rejected.stderr
