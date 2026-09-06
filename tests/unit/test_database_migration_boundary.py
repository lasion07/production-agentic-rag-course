import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.db.interfaces.postgresql import Base, PostgreSQLDatabase
from src.schemas.database.config import PostgreSQLSettings


def test_database_startup_checks_connectivity_without_mutating_schema():
    engine = MagicMock()
    engine.url.database = "rag_db"
    connection = MagicMock()
    engine.connect.return_value.__enter__.return_value = connection
    database = PostgreSQLDatabase(
        PostgreSQLSettings(database_url="postgresql://user:password@db/rag_db")
    )

    with (
        patch("src.db.interfaces.postgresql.create_engine", return_value=engine),
        patch.object(Base.metadata, "create_all") as create_all,
    ):
        database.startup()

    connection.execute.assert_called_once()
    create_all.assert_not_called()


def test_alembic_revision_is_discoverable():
    revision_path = (
        Path(__file__).parents[2]
        / "migrations"
        / "versions"
        / "20260906_0001_paper_consistency_state.py"
    )
    spec = importlib.util.spec_from_file_location("paper_consistency_revision", revision_path)
    assert spec is not None and spec.loader is not None
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)

    assert revision.revision == "20260906_0001"
    assert revision.down_revision == "5f2621c13b39"

    head_path = (
        Path(__file__).parents[2]
        / "migrations"
        / "versions"
        / "20260907_0002_drop_consistency_server_defaults.py"
    )
    head_spec = importlib.util.spec_from_file_location("consistency_defaults_revision", head_path)
    assert head_spec is not None and head_spec.loader is not None
    head = importlib.util.module_from_spec(head_spec)
    head_spec.loader.exec_module(head)
    assert head.revision == "20260907_0002"
    assert head.down_revision == revision.revision

    final_path = (
        Path(__file__).parents[2]
        / "migrations"
        / "versions"
        / "20260907_0003_drop_redundant_arxiv_id_index.py"
    )
    final_spec = importlib.util.spec_from_file_location("arxiv_index_revision", final_path)
    assert final_spec is not None and final_spec.loader is not None
    final_revision = importlib.util.module_from_spec(final_spec)
    final_spec.loader.exec_module(final_revision)
    assert final_revision.revision == "20260907_0003"
    assert final_revision.down_revision == head.revision

    integrity_path = (
        Path(__file__).parents[2]
        / "migrations"
        / "versions"
        / "20260907_0004_ensure_arxiv_id_unique.py"
    )
    integrity_spec = importlib.util.spec_from_file_location(
        "arxiv_integrity_revision", integrity_path
    )
    assert integrity_spec is not None and integrity_spec.loader is not None
    integrity_revision = importlib.util.module_from_spec(integrity_spec)
    integrity_spec.loader.exec_module(integrity_revision)
    assert integrity_revision.revision == "20260907_0004"
    assert integrity_revision.down_revision == final_revision.revision
