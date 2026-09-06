#!/bin/sh
set -eu

load_secret() {
    variable_name="$1"
    eval "secret_file=\${${variable_name}_FILE:-}"
    eval "existing_value=\${${variable_name}:-}"
    if [ -z "$secret_file" ]; then
        return
    fi
    if [ -n "$existing_value" ] || [ ! -r "$secret_file" ]; then
        echo "Invalid secret configuration for ${variable_name}" >&2
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
    AIRFLOW__DATABASE__SQL_ALCHEMY_CONN \
    POSTGRES_DATABASE_URL \
    OPENAI_API_KEY \
    JINA_API_KEY \
    OPENSEARCH__PASSWORD
do
    load_secret "$variable_name"
done

exec "$@"
