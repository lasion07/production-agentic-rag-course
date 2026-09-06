from unittest.mock import MagicMock

import pytest
from src.services.opensearch.migrations import VersionedIndexMigrator


def make_migrator() -> tuple[VersionedIndexMigrator, MagicMock]:
    client = MagicMock()
    mapping = {
        "mappings": {
            "dynamic": "strict",
            "properties": {"embedding": {"type": "knn_vector", "dimension": 2}},
        }
    }
    migrator = VersionedIndexMigrator(
        client,
        base_name="papers-chunks",
        read_alias="papers-chunks-read",
        write_alias="papers-chunks-write",
        mapping=mapping,
    )
    client.indices.get_mapping.side_effect = lambda *, index: {
        index: mapping,
    }
    return migrator, client


def test_cutover_updates_read_and_write_aliases_in_one_atomic_request():
    migrator, client = make_migrator()
    client.indices.exists.return_value = True
    client.indices.exists_alias.return_value = True
    client.indices.get_alias.side_effect = [
        {"papers-chunks-v1": {}},
        {"papers-chunks-v1": {}},
    ]
    client.count.return_value = {"count": 42}

    result = migrator.cutover("papers-chunks-v2")

    actions = client.indices.update_aliases.call_args.kwargs["body"]["actions"]
    assert actions == [
        {"remove": {"index": "papers-chunks-v1", "alias": "papers-chunks-read"}},
        {"remove": {"index": "papers-chunks-v1", "alias": "papers-chunks-write"}},
        {"add": {"index": "papers-chunks-v2", "alias": "papers-chunks-read"}},
        {
            "add": {
                "index": "papers-chunks-v2",
                "alias": "papers-chunks-write",
                "is_write_index": True,
            }
        },
    ]
    assert result["previous_read_indices"] == ["papers-chunks-v1"]
    assert result["document_count"] == 42


def test_cutover_rejects_empty_candidate_by_default():
    migrator, client = make_migrator()
    client.indices.exists.return_value = True
    client.count.return_value = {"count": 0}

    with pytest.raises(RuntimeError, match="empty index"):
        migrator.cutover("papers-chunks-v2")

    client.indices.update_aliases.assert_not_called()


def test_initial_generation_copies_legacy_index_before_alias_cutover():
    migrator, client = make_migrator()
    client.indices.exists_alias.return_value = False
    client.indices.exists.side_effect = [False, True, True]
    client.count.side_effect = [{"count": 7}, {"count": 7}, {"count": 7}]
    client.reindex.return_value = {"created": 7, "updated": 0, "failures": []}

    created = migrator.ensure_initial_generation(
        "papers-chunks-v1",
        source_index="papers-chunks",
    )

    assert created is True
    client.indices.create.assert_called_once_with(
        index="papers-chunks-v1",
        body={
            "mappings": {
                "dynamic": "strict",
                "properties": {
                    "embedding": {"type": "knn_vector", "dimension": 2}
                },
            }
        },
    )
    client.reindex.assert_called_once()
    client.indices.update_aliases.assert_called_once()


def test_initial_generation_repairs_partial_target_before_alias_cutover():
    migrator, client = make_migrator()
    client.indices.exists_alias.return_value = False
    client.indices.exists.side_effect = [True, True, True]
    client.count.side_effect = [{"count": 7}, {"count": 7}, {"count": 7}]
    client.reindex.return_value = {"created": 4, "updated": 3, "failures": []}

    created = migrator.ensure_initial_generation(
        "papers-chunks-v1",
        source_index="papers-chunks",
    )

    assert created is False
    client.reindex.assert_called_once()
    client.indices.update_aliases.assert_called_once()


def test_initial_generation_rejects_partial_copy_before_alias_cutover():
    migrator, client = make_migrator()
    client.indices.exists_alias.return_value = False
    client.indices.exists.side_effect = [True, True]
    client.count.side_effect = [{"count": 7}, {"count": 4}]
    client.reindex.return_value = {"created": 1, "updated": 3, "failures": []}

    with pytest.raises(RuntimeError, match="reindex count mismatch"):
        migrator.ensure_initial_generation(
            "papers-chunks-v1",
            source_index="papers-chunks",
        )

    client.indices.update_aliases.assert_not_called()


def test_rollback_reuses_the_same_atomic_cutover_contract():
    migrator, client = make_migrator()
    client.indices.exists.return_value = True
    client.indices.exists_alias.return_value = True
    client.indices.get_alias.side_effect = [
        {"papers-chunks-v2": {}},
        {"papers-chunks-v2": {}},
    ]
    client.count.return_value = {"count": 10}

    result = migrator.rollback("papers-chunks-v1")

    assert result["target"] == "papers-chunks-v1"
    client.indices.update_aliases.assert_called_once()


def test_cutover_rejects_incompatible_embedding_mapping():
    migrator, client = make_migrator()
    client.indices.exists.return_value = True
    client.indices.get_mapping.side_effect = None
    client.indices.get_mapping.return_value = {
        "papers-chunks-v2": {
            "mappings": {
                "dynamic": "strict",
                "properties": {
                    "embedding": {"type": "knn_vector", "dimension": 768}
                },
            }
        }
    }

    with pytest.raises(RuntimeError, match="dimension mismatch"):
        migrator.cutover("papers-chunks-v2")

    client.indices.update_aliases.assert_not_called()
