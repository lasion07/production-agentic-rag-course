"""Controlled OpenSearch physical-index migrations with atomic alias cutover."""

import re
from typing import Any, Dict, Optional, Set

_SAFE_INDEX_NAME = re.compile(r"^[a-zA-Z0-9._-]+$")


class VersionedIndexMigrator:
    """Prepare, cut over and roll back versioned OpenSearch indexes."""

    def __init__(
        self,
        client: Any,
        *,
        base_name: str,
        read_alias: str,
        write_alias: str,
        mapping: Dict[str, Any],
    ) -> None:
        self.client = client
        self.base_name = base_name
        self.read_alias = read_alias
        self.write_alias = write_alias
        self.mapping = mapping

    def physical_name(self, generation: str) -> str:
        if not _SAFE_INDEX_NAME.fullmatch(generation):
            raise ValueError("OpenSearch index generation contains unsafe characters")
        return f"{self.base_name}-{generation}"

    def create_generation(self, generation: str) -> tuple[str, bool]:
        target = self.physical_name(generation)
        if self.client.indices.exists(index=target):
            return target, False
        try:
            self.client.indices.create(index=target, body=self.mapping)
        except Exception as exc:
            if "resource_already_exists_exception" not in str(exc):
                raise
            return target, False
        return target, True

    def prepare_generation(
        self,
        generation: str,
        *,
        source_index: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a shadow index and optionally copy documents into it."""
        target, created = self.create_generation(generation)
        copied = 0
        source_count = None
        if source_index:
            if not self.client.indices.exists(index=source_index):
                raise RuntimeError(f"OpenSearch source index does not exist: {source_index}")
            source_count = int(self.client.count(index=source_index).get("count", 0))
            response = self.client.reindex(
                body={"source": {"index": source_index}, "dest": {"index": target}},
                wait_for_completion=True,
                refresh=True,
            )
            failures = response.get("failures", [])
            if failures:
                raise RuntimeError(
                    f"OpenSearch reindex into {target} had {len(failures)} failure(s)"
                )
            copied = int(response.get("created", 0)) + int(response.get("updated", 0))
            target_count = int(self.client.count(index=target).get("count", 0))
            if target_count != source_count:
                raise RuntimeError(
                    "OpenSearch reindex count mismatch: "
                    f"source={source_count} target={target_count}"
                )
        else:
            target_count = int(self.client.count(index=target).get("count", 0))
        return {
            "target": target,
            "created": created,
            "documents_copied": copied,
            "source_document_count": source_count,
            "target_document_count": target_count,
        }

    def alias_targets(self, alias: str) -> Set[str]:
        if not self.client.indices.exists_alias(name=alias):
            return set()
        return set(self.client.indices.get_alias(name=alias))

    def cutover(self, target: str, *, allow_empty: bool = False) -> Dict[str, Any]:
        """Atomically point read/write aliases at one validated physical index."""
        if not _SAFE_INDEX_NAME.fullmatch(target):
            raise ValueError("OpenSearch target index contains unsafe characters")
        if not target.startswith(f"{self.base_name}-"):
            raise ValueError("OpenSearch target is outside the managed index namespace")
        if not self.client.indices.exists(index=target):
            raise RuntimeError(f"OpenSearch target index does not exist: {target}")
        self._validate_mapping(target)
        count = int(self.client.count(index=target).get("count", 0))
        if count == 0 and not allow_empty:
            raise RuntimeError(f"Refusing to cut over to empty index: {target}")

        old_read = self.alias_targets(self.read_alias)
        old_write = self.alias_targets(self.write_alias)
        actions = []
        for index in sorted(old_read):
            actions.append({"remove": {"index": index, "alias": self.read_alias}})
        for index in sorted(old_write):
            actions.append({"remove": {"index": index, "alias": self.write_alias}})
        actions.extend(
            [
                {"add": {"index": target, "alias": self.read_alias}},
                {
                    "add": {
                        "index": target,
                        "alias": self.write_alias,
                        "is_write_index": True,
                    }
                },
            ]
        )
        response = self.client.indices.update_aliases(body={"actions": actions})
        if isinstance(response, dict) and not response.get("acknowledged", False):
            raise RuntimeError("OpenSearch alias cutover was not acknowledged")
        return {
            "target": target,
            "document_count": count,
            "previous_read_indices": sorted(old_read),
            "previous_write_indices": sorted(old_write),
        }

    def rollback(self, target: str) -> Dict[str, Any]:
        """Roll both aliases back to a retained physical generation."""
        return self.cutover(target)

    def _validate_mapping(self, target: str) -> None:
        response = self.client.indices.get_mapping(index=target)
        actual = response[target]["mappings"]
        expected = self.mapping["mappings"]
        actual_properties = actual.get("properties", {})
        expected_properties = expected.get("properties", {})
        missing = sorted(set(expected_properties) - set(actual_properties))
        if missing:
            raise RuntimeError(
                f"OpenSearch target mapping is missing required fields: {missing}"
            )
        if actual.get("dynamic") != expected.get("dynamic"):
            raise RuntimeError("OpenSearch target mapping has an incompatible dynamic policy")
        expected_dimension = expected_properties["embedding"]["dimension"]
        actual_dimension = actual_properties["embedding"].get("dimension")
        if actual_dimension != expected_dimension:
            raise RuntimeError(
                "OpenSearch target embedding dimension mismatch: "
                f"expected={expected_dimension} actual={actual_dimension}"
            )

    def ensure_initial_generation(
        self,
        target: str,
        *,
        source_index: Optional[str] = None,
    ) -> bool:
        """Provision a new empty deployment without mutating an existing alias."""
        read_targets = self.alias_targets(self.read_alias)
        write_targets = self.alias_targets(self.write_alias)
        if read_targets or write_targets:
            if read_targets != write_targets or len(read_targets) != 1:
                raise RuntimeError("OpenSearch read/write aliases are inconsistent")
            return False

        if not self.client.indices.exists(index=target):
            try:
                self.client.indices.create(index=target, body=self.mapping)
                created = True
            except Exception as exc:
                if "resource_already_exists_exception" not in str(exc):
                    raise
                created = False
        else:
            created = False
        if source_index and self.client.indices.exists(index=source_index):
            source_count = int(self.client.count(index=source_index).get("count", 0))
            response = self.client.reindex(
                body={"source": {"index": source_index}, "dest": {"index": target}},
                wait_for_completion=True,
                refresh=True,
            )
            if response.get("failures"):
                raise RuntimeError("Initial OpenSearch legacy reindex had failures")
            target_count = int(self.client.count(index=target).get("count", 0))
            if target_count != source_count:
                raise RuntimeError(
                    "Initial OpenSearch legacy reindex count mismatch: "
                    f"source={source_count} target={target_count}"
                )
        self.cutover(target, allow_empty=True)
        return created
