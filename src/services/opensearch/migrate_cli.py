"""CLI for controlled OpenSearch versioned-index migrations."""

import argparse
import json
from typing import Sequence

from src.config import get_settings
from src.services.opensearch.factory import make_opensearch_client_fresh
from src.services.opensearch.index_config_hybrid import ARXIV_PAPERS_CHUNKS_MAPPING
from src.services.opensearch.migrations import VersionedIndexMigrator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="Create a shadow generation")
    prepare.add_argument("generation")
    prepare.add_argument("--source-index")

    cutover = subparsers.add_parser("cutover", help="Atomically cut over both aliases")
    cutover.add_argument("generation")
    cutover.add_argument("--allow-empty", action="store_true")

    rollback = subparsers.add_parser("rollback", help="Point both aliases to a retained generation")
    rollback.add_argument("generation")

    subparsers.add_parser(
        "bootstrap",
        help="Idempotently provision the configured generation, aliases and RRF pipeline",
    )
    subparsers.add_parser("status", help="Show current alias targets")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    opensearch = make_opensearch_client_fresh(settings)
    migrator = VersionedIndexMigrator(
        opensearch.client,
        base_name=opensearch.index_base_name,
        read_alias=opensearch.read_alias,
        write_alias=opensearch.write_alias,
        mapping=ARXIV_PAPERS_CHUNKS_MAPPING,
    )

    if args.command == "bootstrap":
        result = opensearch.setup_indices(force=False)
    elif args.command == "prepare":
        result = migrator.prepare_generation(
            args.generation,
            source_index=args.source_index,
        )
        result["rrf_pipeline_created"] = opensearch._create_rrf_pipeline(force=False)
    elif args.command == "cutover":
        result = migrator.cutover(
            migrator.physical_name(args.generation),
            allow_empty=args.allow_empty,
        )
    elif args.command == "rollback":
        result = migrator.rollback(migrator.physical_name(args.generation))
    else:
        result = {
            "read_alias": opensearch.read_alias,
            "read_targets": sorted(migrator.alias_targets(opensearch.read_alias)),
            "write_alias": opensearch.write_alias,
            "write_targets": sorted(migrator.alias_targets(opensearch.write_alias)),
        }

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
