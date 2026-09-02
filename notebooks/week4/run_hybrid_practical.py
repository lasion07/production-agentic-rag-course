"""Index the three course papers and compare BM25, vector, and hybrid retrieval.

This script intentionally limits external embedding disclosure to the three public
arXiv papers used by the Week 4 practical.
"""

import asyncio
import argparse
from dataclasses import dataclass
from statistics import mean
from typing import Any

from sqlalchemy import select

from src.db.factory import make_database
from src.models.paper import Paper
from src.services.indexing.factory import make_hybrid_indexing_service


TARGET_ARXIV_IDS = (
    "2508.11110v1",
    "2508.11112v1",
    "2508.11121v1",
)


@dataclass(frozen=True)
class EvaluationQuery:
    query: str
    relevant_arxiv_id: str
    group: str


EVALUATION_QUERIES = (
    EvaluationQuery(
        query="using diffusion models to repair and generate source code",
        relevant_arxiv_id="2508.11110v1",
        group="lexical",
    ),
    EvaluationQuery(
        query="piecewise affine regularization for quantization with optimization guarantees",
        relevant_arxiv_id="2508.11112v1",
        group="lexical",
    ),
    EvaluationQuery(
        query="predicting spreadsheet table formatting automatically",
        relevant_arxiv_id="2508.11121v1",
        group="lexical",
    ),
    EvaluationQuery(
        query="a stochastic denoising process that fixes defects in computer programs",
        relevant_arxiv_id="2508.11110v1",
        group="paraphrase",
    ),
    EvaluationQuery(
        query="compressing learned models into low precision representations without losing accuracy",
        relevant_arxiv_id="2508.11112v1",
        group="paraphrase",
    ),
    EvaluationQuery(
        query="automatically styling spreadsheet cells by learning patterns from nearby rows and columns",
        relevant_arxiv_id="2508.11121v1",
        group="paraphrase",
    ),
)


def paper_to_dict(paper: Paper) -> dict[str, Any]:
    return {
        "id": paper.id,
        "arxiv_id": paper.arxiv_id,
        "title": paper.title,
        "authors": paper.authors,
        "abstract": paper.abstract,
        "categories": paper.categories,
        "published_date": paper.published_date,
        "raw_text": paper.raw_text,
        "sections": paper.sections,
    }


def ranked_unique_papers(hits: list[dict[str, Any]], limit: int = 3) -> list[str]:
    ranked: list[str] = []
    seen: set[str] = set()
    for hit in hits:
        arxiv_id = hit.get("arxiv_id")
        if arxiv_id and arxiv_id not in seen:
            seen.add(arxiv_id)
            ranked.append(arxiv_id)
        if len(ranked) == limit:
            break
    return ranked


def metrics_at_k(ranking: list[str], relevant_id: str, k: int = 3) -> dict[str, float]:
    top_k = ranking[:k]
    relevant_count = int(relevant_id in top_k)
    rank = top_k.index(relevant_id) + 1 if relevant_id in top_k else None
    return {
        "precision": relevant_count / k,
        "recall": float(relevant_count),
        "rr": 1.0 / rank if rank else 0.0,
    }


async def main(skip_index: bool = False) -> None:
    database = make_database()
    try:
        with database.get_session() as session:
            papers = list(
                session.scalars(
                    select(Paper)
                    .where(Paper.arxiv_id.in_(TARGET_ARXIV_IDS), Paper.raw_text.is_not(None))
                    .order_by(Paper.arxiv_id)
                )
            )
            paper_data = [paper_to_dict(paper) for paper in papers]

        found_ids = tuple(paper["arxiv_id"] for paper in paper_data)
        if found_ids != TARGET_ARXIV_IDS:
            raise RuntimeError(f"Expected exactly {TARGET_ARXIV_IDS}, found {found_ids}")

        indexing = make_hybrid_indexing_service()
        setup = indexing.opensearch_client.setup_indices(force=False)
        print(f"Index setup: {setup}")
        print(f"Authorized public papers: {len(paper_data)}")

        # Fail fast on an invalid/revoked key before sending any paper content.
        preflight_embedding = await indexing.embeddings_client.embed_query(
            "Week 4 embedding authentication preflight"
        )
        if len(preflight_embedding) != 1024:
            raise RuntimeError(
                f"Expected a 1024-dimensional preflight vector, got {len(preflight_embedding)}"
            )
        print("Jina preflight: authenticated, 1024 dimensions")

        if skip_index:
            current_stats = indexing.opensearch_client.get_index_stats()
            if current_stats.get("document_count", 0) == 0:
                raise RuntimeError("Cannot skip indexing because the hybrid index is empty")
            print(f"Indexing skipped; existing index stats: {current_stats}")
        else:
            stats = await indexing.index_papers_batch(paper_data, replace_existing=True)
            print(f"Indexing stats: {stats}")
            if stats["total_errors"] or stats["total_chunks_indexed"] == 0:
                raise RuntimeError("Indexing did not complete successfully")

        all_metrics: dict[str, list[dict[str, float]]] = {
            "bm25": [],
            "vector": [],
            "hybrid": [],
        }

        for case_number, case in enumerate(EVALUATION_QUERIES, start=1):
            query_embedding = await indexing.embeddings_client.embed_query(case.query)
            bm25 = indexing.opensearch_client.search_unified(
                query=case.query, size=10, use_hybrid=False
            )
            vector = indexing.opensearch_client.search_chunks_vector(
                query_embedding=query_embedding, size=10
            )
            hybrid = indexing.opensearch_client.search_unified(
                query=case.query,
                query_embedding=query_embedding,
                size=10,
                use_hybrid=True,
            )

            print(f"\nQuery {case_number} [{case.group}]: {case.query}")
            print(f"Relevant paper: {case.relevant_arxiv_id}")
            for mode, response in (("bm25", bm25), ("vector", vector), ("hybrid", hybrid)):
                hits = response.get("hits", [])
                ranking = ranked_unique_papers(hits, limit=3)
                metrics = metrics_at_k(ranking, case.relevant_arxiv_id, k=3)
                all_metrics[mode].append(metrics)
                chunk_top5 = [hit.get("arxiv_id") for hit in hits[:5]]
                print(
                    f"  {mode:6} papers={ranking} chunk_top5={chunk_top5} "
                    f"P@3={metrics['precision']:.3f} "
                    f"R@3={metrics['recall']:.3f} RR={metrics['rr']:.3f}"
                )

        print("\nMacro averages")
        for mode, values in all_metrics.items():
            print(
                f"  {mode:6} "
                f"P@3={mean(item['precision'] for item in values):.3f} "
                f"R@3={mean(item['recall'] for item in values):.3f} "
                f"MRR={mean(item['rr'] for item in values):.3f}"
            )

        print(f"\nFinal index stats: {indexing.opensearch_client.get_index_stats()}")
    finally:
        database.teardown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--skip-index",
        action="store_true",
        help="Reuse the existing OpenSearch index and only run evaluation queries.",
    )
    args = parser.parse_args()
    asyncio.run(main(skip_index=args.skip_index))
