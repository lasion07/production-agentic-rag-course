# Week 7 retrieval diagnostics — approved answer dataset v0

Run date: 2026-09-09

Corpus: three public arXiv papers, versioned OpenSearch alias

Mode: hybrid BM25 + vector + native RRF

## Baseline (`candidate_multiplier=4`)

- W7A-01: gold chunk candidate rank 3, selected rank 1 — final context.
- W7A-02: gold chunk candidate rank 2, selected rank 1 — final context.
- W7A-03: gold chunk candidate rank 2, selected rank 2 — final context.
- W7A-04: gold chunk absent from 16 candidates — candidate-generation miss.
- W7A-05: gold chunk absent from 16 candidates — candidate-generation miss.
- W7A-06: gold chunk candidate rank 15, selected rank 4 — final context.
- W7A-07:
  - Diffusion gold chunk candidate rank 7, selected rank 3 — final context.
  - TaFo gold chunk absent from 24 candidates — candidate-generation miss.

Gold context coverage: 4/7 complete cases. W7A-07 is incomplete because only one
of its two required gold chunks reaches final context.

An evidence-fragment check against the selected chunks confirms this is not merely
an overly strict chunk-ID oracle:

- W7A-05 selected chunks repeat the `1.8 Million` corpus fact, but none contains
  the required `15.6%-26.5%` improvement range.
- W7A-07 selected TaFo chunks likewise omit that improvement range.
- W7A-04 selected chunks do not contain the reviewed quantization bound/regime
  evidence from the gold chunk.

## Sensitivity (`candidate_multiplier=8`)

- W7A-04 gold appears at candidate rank 14 but is not selected.
- W7A-05 gold appears at candidate rank 25 but is not selected.
- W7A-06 gold appears at candidate rank 15 but is no longer selected.
- W7A-07 TaFo gold appears at candidate rank 38 but is not selected; Diffusion
  gold remains selected.

Increasing candidate depth alone therefore moves misses from candidate generation
to context selection and can regress an existing pass. It is not an acceptable fix.

## Decision

For W7A-01 no retrieval change is currently justified; retain it as a regression
case because earlier runs missed the same chunk.

For W7A-07, implement query decomposition first so each named paper/claim receives
its own retrieval opportunity, then fuse the candidates. Add coverage-aware final
selection so both requested paper/claim groups receive evidence. Do not implement
neighbor expansion yet: these probes do not show that the missing gold evidence is
adjacent to an already selected chunk, so that hypothesis is unsupported.

W7A-04 and W7A-05 should remain diagnostic cases during the same change. The
acceptance target is 7/7 complete gold-context coverage without regressing W7A-06.

## Course-close E2E verification

Run date: 2026-09-09

Runtime: rebuilt Docker API, OpenAI `gpt-5.4-mini-2026-03-17`, Jina embeddings,
OpenSearch corpus with 81 chunks

- The live answer-contract runner passed all seven cases: `passed:7 failed:0`.
- W7A-07 returned both quantitative ranges and attributed each range to the
  correct paper.
- Trace `1185e281a4f058cc557a7015f0afd172` contains 22 observations and records
  one retrieval round with 12 candidates and three selected chunks.
- Root metadata contains bounded-cardinality execution summaries only. Detailed
  candidate diagnostics contain chunk IDs, paper IDs, ranks and scores, but no
  chunk text. Raw public-paper content remains available in observation I/O under
  the explicitly approved `LANGFUSE_CAPTURE_CONTENT=True` policy.

The direct retrieval probe and the full agent answer gate measure different
contracts. Candidate coverage is retained as a diagnostic signal; the graduation
answer contract passed 7/7 because the full graph can use its bounded retrieval
and rewrite behavior. Query decomposition and coverage-aware selection therefore
remain post-course improvements rather than course-completion blockers.
