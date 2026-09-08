#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 <canary|promote|rollback> <production-env-file> <image@sha256:digest>" >&2
  exit 64
}

[[ $# -eq 3 ]] || usage

action=$1
env_file=$2
image_ref=$3
script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
project_root=$(cd "$script_dir/.." && pwd)
compose_file="$project_root/compose.production.yml"

[[ -f "$env_file" ]] || { echo "Production env file not found" >&2; exit 66; }
[[ "$image_ref" =~ ^[^[:space:]]+@sha256:[0-9a-f]{64}$ ]] || {
  echo "Image must be pinned by immutable sha256 digest" >&2
  exit 65
}

export RAG_API_IMAGE="$image_ref"

readiness_command='import json,urllib.request,pathlib
raw=pathlib.Path("/run/secrets/api_keys").read_text().strip()
try:
    parsed=json.loads(raw)
    key=parsed[0] if isinstance(parsed,list) else str(parsed)
except json.JSONDecodeError:
    key=raw.splitlines()[0]
request=urllib.request.Request("http://127.0.0.1:8000/api/v1/ready",headers={"X-API-Key":key})
response=urllib.request.urlopen(request,timeout=10)
assert response.status == 200, response.status
print("readiness=ok")'

compose() {
  docker compose --env-file "$env_file" -f "$compose_file" "$@"
}

verify_ready() {
  compose exec -T api python -c "$readiness_command"
}

current_image() {
  local container_id
  container_id=$(compose ps -q api)
  [[ -n "$container_id" ]] || return 1
  docker inspect --format '{{.Config.Image}}' "$container_id"
}

deploy_candidate() {
  compose pull api &&
    compose up -d --no-deps --wait --wait-timeout 180 api &&
    verify_ready
}

restore_previous() {
  local previous_ref=$1
  echo "Candidate failed health verification; restoring previous image" >&2
  export RAG_API_IMAGE="$previous_ref"
  compose pull api &&
    compose up -d --no-deps --wait --wait-timeout 180 api &&
    verify_ready
}

case "$action" in
  canary)
    canary_project="${COMPOSE_PROJECT_NAME:-production-agentic-rag}-canary"
    cleanup() {
      docker compose --project-name "$canary_project" --env-file "$env_file" -f "$compose_file" down --remove-orphans
    }
    trap cleanup EXIT INT TERM
    docker compose --project-name "$canary_project" --env-file "$env_file" -f "$compose_file" pull api
    docker compose --project-name "$canary_project" --env-file "$env_file" -f "$compose_file" up -d --no-deps --wait --wait-timeout 180 api
    docker compose --project-name "$canary_project" --env-file "$env_file" -f "$compose_file" exec -T api python -c "$readiness_command"
    ;;
  promote|rollback)
    previous_ref=""
    if previous_ref=$(current_image); then
      [[ "$previous_ref" =~ ^[^[:space:]]+@sha256:[0-9a-f]{64}$ ]] || {
        echo "Current API image is not digest-pinned; refusing a deployment without safe rollback" >&2
        exit 67
      }
    fi
    if ! deploy_candidate; then
      if [[ -n "$previous_ref" ]]; then
        restore_previous "$previous_ref" || {
          echo "CRITICAL: candidate failed and automatic rollback also failed" >&2
          exit 70
        }
      else
        echo "Candidate failed and no previous deployment exists; removing failed API container" >&2
        compose rm -sf api || true
      fi
      exit 1
    fi
    ;;
  *)
    usage
    ;;
esac

echo "$action completed for immutable image digest"
