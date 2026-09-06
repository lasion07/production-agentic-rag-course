#!/bin/sh
set -eu

# Docker Compose/Kubernetes mount secrets as files. The application still reads
# ordinary environment variables, so translate an explicit allowlist of *_FILE
# variables immediately before exec. Secret values never become image layers.
load_secret() {
    variable_name="$1"
    eval "secret_file=\${${variable_name}_FILE:-}"
    eval "existing_value=\${${variable_name}:-}"

    if [ -z "$secret_file" ]; then
        return
    fi
    if [ -n "$existing_value" ]; then
        echo "Both ${variable_name} and ${variable_name}_FILE are set" >&2
        exit 1
    fi
    if [ ! -r "$secret_file" ]; then
        echo "Secret file for ${variable_name} is not readable" >&2
        exit 1
    fi

    secret_value="$(cat "$secret_file")"
    if [ -z "$secret_value" ]; then
        echo "Secret file for ${variable_name} is empty" >&2
        exit 1
    fi
    export "${variable_name}=${secret_value}"
    unset secret_value
}

for variable_name in \
    API_KEYS \
    POSTGRES_DATABASE_URL \
    OPENAI_API_KEY \
    JINA_API_KEY \
    OPENSEARCH__PASSWORD \
    REDIS__PASSWORD \
    LANGFUSE_PUBLIC_KEY \
    LANGFUSE_SECRET_KEY \
    TELEGRAM__BOT_TOKEN
do
    load_secret "$variable_name"
done

exec "$@"
