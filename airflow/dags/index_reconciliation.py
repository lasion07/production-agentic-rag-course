from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from arxiv_ingestion.indexing import reconcile_index_consistency

default_args = {
    "owner": "arxiv-curator",
    "depends_on_past": False,
    "start_date": datetime(2025, 8, 8),
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
}

dag = DAG(
    "opensearch_consistency_reconciliation",
    default_args=default_args,
    description="Heal due PostgreSQL/OpenSearch paper-version inconsistencies",
    schedule="15 * * * *",
    max_active_runs=1,
    catchup=False,
    tags=["papers", "opensearch", "reconciliation"],
)

reconcile_task = PythonOperator(
    task_id="reconcile_index_consistency",
    python_callable=reconcile_index_consistency,
    dag=dag,
)
