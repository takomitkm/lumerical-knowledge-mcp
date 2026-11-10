# Lumerical Compatibility / Backport System — Agent Implementation Kit

**Purpose:** extend the existing Lumerical RAG service with version-aware feature lookup, compatibility recipes, and evidence-backed validation—without adding a new MCP service, daemon, port, or vector database.

## Read this first

1. `AGENT_BRIEF.md` — copy this file to the coding agent as the task brief.
2. `docs/IMPLEMENTATION_SPEC.md` — architecture, data model, API and ingestion requirements.
3. `docs/BACKPORT_SOP.md` — rules for producing and validating old-version implementations.
4. `tasks/PHASE_PLAN.md` — implementation order and acceptance criteria.
5. `schema/compatibility.sql` and `templates/` — database DDL and record templates.
6. `docs/SOURCES_AND_CASES.md` — verified official/community references and version facts.

## Existing system (preserve it)

- `rag-qdrant`: Qdrant on loopback, current memory budget about 700 MB.
- `rag-shim`: FastAPI on port 8900, Bearer authentication; owns embedding, Qdrant + Tantivy BM25, RRF, reranking, ingest, document retrieval, collection listing and BM25 rebuild.
- `rag-mcp`: FastMCP on port 8901; the only externally exposed MCP surface; thinly calls rag-shim.
- Qdrant collections today: `lumerical`, `lumerical_v241`, `fdtdx`.
- Tantivy: one BM25 index, separated by the `collection` payload field; rebuilding it must continue to include every collection.
- Embedding/reranking use the existing SiliconFlow services. Keep the existing models and query pipeline.

The intended change is one new Qdrant collection (`lumerical_compat`), one local SQLite file, a compatibility module inside `rag-shim`, three REST endpoints, and two MCP tools. No new long-running process is required.

## Important evidence corrections

Do not assume that every command present in the current online KB but absent from the v241 `docs.json` is new or unavailable in v241.

- Official Ansys documentation says `findresonances` was introduced in 2019a.
- Official Ansys documentation says `sort` was introduced in 2018a R6.
- `modeoverlap` was introduced in 2022 R2.2 for raw mode data from FEEM / frequency-domain field data from DGTD; do not generalize this to all products/solvers.
- The `python` LSF command was introduced in 2024 R1.1; distinguish 2024 R1 from 2024 R1.1.
- In 2024 R2.3, `overlap`, `expand` and `expand2` gained rectilinear-dataset arguments for FDTD/MODE. This is a parameter/API extension, not the introduction of the underlying overlap computation.
- The introduction/support status of `median`, `print`, `function`, `while`, JSON commands and the other reported KB differences must be checked against the exact installed target product/update and, where possible, the real runtime. Do not hard-code earlier conversational claims as facts.

## Non-goals

- Do not rewrite the existing RAG stack.
- Do not create a separate compatibility MCP or REST service.
- Do not add PostgreSQL, Neo4j, Redis, another vector DB, or another embedding/reranker provider.
- Do not claim algorithmic equivalence merely because a script passes static checks or runs once.
- Do not modify the existing Qdrant CPU/quantization/HNSW settings. The host is resource-constrained and current settings were chosen deliberately.
- Do not make up Lumerical runtime test results. Runtime/differential tests require an actual target installation and appropriate license.

## Deliverables expected from the coding agent

- A working SQLite schema/migration and local DB path integrated into rag-shim.
- A fourth collection, `lumerical_compat`, ingested through the existing `/ingest` pipeline and included in the global BM25 rebuild.
- Compatibility lookup, recipe retrieval and capability snapshot REST endpoints.
- Two MCP tools that call the existing shim.
- An ingestion/indexing path for recipes and validation reports.
- Tests for DB logic, API auth/validation, MCP forwarding, metadata filtering and ingestion/BM25 rebuild.
- Documentation of the deployment/configuration and limitations.
- A report listing what is implemented, what remains blocked by lack of Lumerical runtime access, and exact test outcomes.
