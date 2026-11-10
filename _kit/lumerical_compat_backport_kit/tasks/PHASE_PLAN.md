# Phased Implementation Plan and Acceptance Checklist

Implement in this order. Do not start by generating a large set of speculative recipes.

## Phase 0 — Repository reconnaissance and baseline

- [ ] Locate rag-shim and rag-mcp repositories/services.
- [ ] Identify current route/tool registration, auth, config, Pydantic schemas, DB conventions and tests.
- [ ] Identify collection allowlists and payload schema.
- [ ] Identify ingestion chunker and BM25 rebuild implementation.
- [ ] Record baseline test results and current collection counts.
- [ ] Back up config and any existing persistent state that migrations may touch.
- [ ] Produce a brief architecture map and change plan before coding.

**Exit:** no code changes yet; exact integration points documented.

## Phase 1 — Registry and SQLite

- [ ] Add `compatibility.db` path to existing config, with sensible deployment default and no credentials.
- [ ] Add schema migration/versioning based on `schema/compatibility.sql`.
- [ ] Add repository/data-access module in rag-shim.
- [ ] Add models for target environments, features/aliases, evidence, feature availability, implementations, dependencies, capability snapshots/items and validation runs.
- [ ] Enforce exact product/solver/version matching.
- [ ] Return `unknown` when evidence is missing.
- [ ] Add unit tests for constraints, multiple implementations, foreign keys and lookup semantics.

**Exit:** DB can be initialized/migrated and queried without starting a new service.

## Phase 2 — Ingestion and fourth collection

- [ ] Add `lumerical_compat` to collection config/validation.
- [ ] Add a chunk/build path for compatibility Markdown while preserving full LSF source retrieval.
- [ ] Required payload metadata is present on every chunk.
- [ ] Add ingestion idempotency tests.
- [ ] Verify Qdrant collection creation/config uses the existing vector dimension and current safe settings.
- [ ] Add new collection to collection listing and search filters.
- [ ] Add compatibility ingestion to existing BM25 index.
- [ ] Test global BM25 rebuild across `lumerical`, `lumerical_v241`, `fdtdx`, `lumerical_compat`.

**Exit:** recipe docs can be ingested and retrieved; existing collections remain searchable.

## Phase 3 — Shim compatibility APIs

- [ ] Add `GET /compat/lookup`.
- [ ] Add `GET /compat/recipe`.
- [ ] Add `GET /compat/capabilities`.
- [ ] Reuse existing Bearer auth and response/error conventions.
- [ ] Resolve recipe via stable `implementation_id` / `recipe_doc_id`, never arbitrary file paths.
- [ ] Add API tests: auth, validation, not-found, unknown evidence, exact version/product/solver isolation.

**Exit:** all three endpoints work locally and are documented.

## Phase 4 — MCP forwarding

- [ ] Add `lookup_lumerical_compatibility` tool.
- [ ] Add `get_lumerical_compat_recipe` tool.
- [ ] Use existing shim URL/auth config.
- [ ] Preserve all existing tools and schemas.
- [ ] Test forwarding and error handling.

**Exit:** dsh can look up a feature and fetch a recipe through the existing MCP endpoint.

## Phase 5 — Evidence and capability snapshot pipeline

- [ ] Add documented snapshot structure for exact target product/solver/update.
- [ ] Preserve raw `getcommands` output.
- [ ] Add separate syntax, signature and runtime probe records.
- [ ] Hash raw snapshot files and store paths/hashes in SQLite.
- [ ] Import snapshots idempotently.
- [ ] Make `GET /compat/capabilities` return provenance for every fact.
- [ ] Seed only evidence-backed historical facts; leave unknown items unknown.

**Exit:** command absence/presence can be distinguished from docs coverage gaps.

## Phase 6 — First reference assets and tests

Start with evidence-rich, bounded work. Do not claim runtime tests unless run on target Lumerical.

Recommended order:
1. Sort semantics and `median` behavior audit (first verify whether target has native `sort`/`median`).
2. API adaptation case: `overlap` dataset input vs older D-card/monitor input; determine if this is a relevant target gap.
3. Resonance FWHM approximation as a clearly labelled approximate analysis, not an exact `findresonances` backport.
4. E-only field similarity as a partial/approximate helper, not strict power overlap. A strict overlap implementation requires E/H and full power-normalization contract.

- [ ] Add sources and contract for each feature.
- [ ] Add recipe files and metadata.
- [ ] Add test fixtures and reports.
- [ ] Index recipe/report docs.
- [ ] Register them in SQLite.

**Exit:** at least one complete example passes static checks; runtime state is honestly marked pending if the target license/runtime is unavailable.

## Phase 7 — End-to-end validation and deployment

- [ ] Run existing shim/mcp test suites.
- [ ] Run new unit/API/MCP/ingestion tests.
- [ ] Verify all collections appear in BM25 after one global rebuild.
- [ ] Verify old MCP tools and old dsh workflows still work.
- [ ] Verify resource/process count remains unchanged.
- [ ] Verify secrets were not written to source or logs.
- [ ] Document migration, ingestion, restart, backup and rollback.
- [ ] Report runtime and differential Lumerical tests as passed or pending with evidence.

**Final acceptance:** all criteria in `AGENT_BRIEF.md` §11 are met, or each unmet item is explicitly reported with a blocker.

## Out of scope unless explicitly approved

- Rewriting RAG ranking/retrieval algorithms.
- Changing embedding/reranker models.
- Adding a new MCP server or process.
- Replacing SQLite with a network database.
- Broad repository cleanup/refactor.
- Automatically generating/claiming hundreds of compatibility recipes.
