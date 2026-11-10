# Agent Task Brief — Extend Existing Lumerical RAG with Compatibility Backport Support

You are modifying an existing deployment. **Inspect the repository and current implementation before changing anything.** Treat this brief as a specification, not permission to replace working components.

## 0. Mandatory first actions

1. Inspect the rag-shim and rag-mcp repositories, current API routes, MCP tools, config loading, DB conventions, Qdrant payload schema, Tantivy indexing/rebuild logic, ingestion pipeline, tests and systemd user services.
2. Write a short map of the existing modules and identify the smallest integration points.
3. Back up relevant config/data and create a migration that can be safely re-run or clearly fails without corrupting data.
4. Do not print, copy into source control, or hard-code Bearer tokens, API keys, private host addresses or credentials.
5. Preserve existing API behavior and all current collections.

## 1. Existing deployment — preserve

- Three processes only: `rag-qdrant`, `rag-shim` (FastAPI :8900), `rag-mcp` (FastMCP :8901).
- rag-mcp remains the only externally exposed MCP endpoint and remains a thin forwarding layer.
- rag-shim continues to own the query flow: SiliconFlow embedding → Qdrant top-k + Tantivy BM25 top-k → filters → RRF → reranker → response.
- Existing Qdrant collections: `lumerical`, `lumerical_v241`, `fdtdx`.
- Tantivy is one shared BM25 index partitioned by payload field `collection`. The rebuild operation must always rebuild across **all** collections, not just the most recently ingested collection.
- Keep existing embedding/reranker models and existing memory/resource budgets. Do not enable Qdrant quantization or HNSW or alter CPU-specific tuning.
- Existing routes and MCP tools must remain backwards compatible.

## 2. Desired architecture

Add:

1. Qdrant collection: `lumerical_compat`.
2. Local SQLite registry: `compatibility.db`, accessed inside existing rag-shim. It is not a service.
3. A compatibility module in rag-shim.
4. REST endpoints in rag-shim:
   - `GET /compat/lookup`
   - `GET /compat/recipe`
   - `GET /compat/capabilities`
5. MCP tools in existing rag-mcp:
   - `lookup_lumerical_compatibility`
   - `get_lumerical_compat_recipe`

No new daemon, MCP server, port, vector service, or third-party database.

## 3. What belongs where

### Existing Qdrant collection `lumerical`
Keep current current/latest official KB and examples. Add useful reference material without creating another collection:
- Official Lumerical scripting tutorials.
- Official command documentation and release notes.
- Official Analysis Group documentation/examples.
- Community scripts such as Lumerical-Objects, clearly marked as community and version scope unknown unless proven.

Use metadata such as `doc_type`, `source_type`, `authority`, `product`, `solver`, `version_scope`, `tested_version`, `introduced_version`, `repository`, `source_url`.

### Existing Qdrant collection `lumerical_v241`
Keep the v241 `docs.json` material as the version-specific documentation evidence. Do not assume it is a complete runtime command inventory. Add actual v241 capability snapshots as structured local files/SQLite records; only ingest snapshot explanations/reports if there is a retrieval benefit.

### New Qdrant collection `lumerical_compat`
Index authored compatibility assets:
- `compatibility_recipe`
- `algorithm_reference`
- `compatibility_analysis`
- `validation_report`

Each indexed document must have a stable `doc_id` / `implementation_id`, target product, solver, exact version, equivalence type, verification level, dependency summary, source references and limitations. Preserve the LSF source as a complete retrievable document; do not split code at arbitrary boundaries.

### SQLite `compatibility.db`
Use it for exact structured relationships and queries—not vector similarity. Keep normalized records for products/target environments, features/aliases, feature availability, implementations, dependencies, capability snapshots/items, evidence sources and validation runs. Use `schema/compatibility.sql` as the starting DDL.

Canonical-source policy:
- SQLite is the runtime registry/source of truth for structured mapping and status.
- Markdown/LSF files are source assets for recipes and are indexed into Qdrant as a searchable projection.
- Raw capability JSON files are immutable evidence snapshots; import/index their structured facts into SQLite, retaining file path and SHA-256.
- Do not maintain a second editable YAML mapping registry that can drift from SQLite. YAML in `templates/` is an authoring template only unless the existing repo already has a canonical registry convention.

## 4. Compatibility semantics — mandatory

Never infer runtime absence solely from a missing entry in `docs.json` or online KB difference.

For each candidate function, determine:
- Exact product and solver (FDTD, MODE, DGTD, FEEM, etc.).
- Exact software version/update/build (do not collapse 2024 R1 and 2024 R1.1).
- Documentation evidence and release-note history.
- Actual runtime command availability where possible (`?getcommands;`).
- Syntax/keyword support and the actual signature separately. `getcommands` lists commands in the current script workspace; it does not prove every argument form, type, side effect or syntax feature.
- Input/output data types, dimensions, coordinate axes, units, complex-number behavior, normalization, defaults, errors, side effects and execution context.

Use these independent dimensions:

**Availability status:** `native`, `absent`, `partial`, `unknown`, `not_applicable`.

**Equivalence:** `exact`, `domain_equivalent`, `approximate`, `partial`, `unsupported`.

**Verification level:** `L0`, `L1`, `L2`, `L3`, `L4`.

- L0 `unverified`: proposal only.
- L1 `static_checked`: static dependency/grammar checks only.
- L2 `runtime_verified`: actual target Lumerical product/version executes successfully for declared tests.
- L3 `differential_verified`: L2 plus comparison against the newer/native reference on a declared test domain, with error metrics and edge cases.
- L4 `equivalence_proven`: a formal proof for an explicit contract/input domain, plus validation that the implementation and runtime assumptions satisfy the proof model. Rare; do not award casually.

A test passing on sample cases is not a universal proof. `L3` means tested differential agreement over a declared test set/domain, not proof for all possible inputs.

## 5. Version evidence already checked — use as initial research leads, not a substitute for runtime capture

- `findresonances`: Ansys 2019a Release Notes says the command was introduced in 2019a. The current command documentation describes filter diagonalization and returns six columns: frequency, decay constant, Q, amplitude, phase, error estimate. Check target product/runtime; do not recreate it merely because it is absent from v241 docs.json.
- `sort`: official command page says introduced in 2018a R6; complex values are sorted by magnitude then angle; input is treated as a linear array while output preserves shape. Check target product/runtime and duplicate behavior if relevant.
- `modeoverlap`: introduced in 2022 R2.2 in conjunction with raw FEEM mode data and DGTD frequency-domain field data. Do not treat this as universally available in every solver/product.
- `overlap` / `expand` / `expand2`: 2024 R2.3 added rectilinear dataset arguments for FDTD/MODE. That is an input API extension; the underlying overlap/coupling operation existed earlier. Keep distinct from `modeoverlap`.
- `python` LSF command: introduced in 2024 R1.1. Verify exact update level.
- `median`, `print`, `function`, `while`, JSON commands and all other original diff items: status is not established by this brief. Verify from exact-product docs, release history and runtime probes. Never propagate unverified claims.

## 6. REST API contract

Follow the existing response envelope, auth dependency, error conventions, logging and API style. Do not invent a second auth system.

### `GET /compat/lookup`
Required query params:
- `feature` (canonical command/feature name or alias)
- `target_version` (exact label, e.g. `2024 R1`; must not be only `v241` if ambiguous)
Optional:
- `product`
- `solver`

Return structured facts:
- canonical feature and aliases
- target product/solver/version
- availability status and evidence basis
- matching native/adapter/backport implementations
- equivalence and verification levels
- dependencies and their capability status
- recipe `doc_id` / implementation id
- assumptions, preconditions and limitations
- official source/document IDs

If evidence is missing, return `unknown`, not `absent`.

### `GET /compat/recipe`
Accept an exact `implementation_id` (preferred) or a fully qualified feature + target. Resolve the stable `recipe_doc_id`, then retrieve the full recipe using the existing document retrieval path. Never accept arbitrary filesystem paths from callers.

Return complete Markdown/LSF content, metadata, dependency list, validation state, limitations and references.

### `GET /compat/capabilities`
Accept a target environment id or exact product/solver/version selector. Return the recorded capability snapshot, capture timestamp, hash, command presence and syntax/signature probe results. Make clear whether a value came from docs, `getcommands`, syntax probe or runtime invocation.

All new routes must use the existing Bearer auth and standard input validation. Keep them read-only except for existing admin ingestion/migration workflows.

## 7. MCP contract

Add only two tools to existing FastMCP:

- `lookup_lumerical_compatibility(feature, target_version, product?, solver?)`
- `get_lumerical_compat_recipe(implementation_id)`

The tools must call rag-shim over loopback using the existing configuration and auth handling. They must not query Qdrant/SQLite directly. Preserve current three tools and their signatures.

`lookup` should return enough information for the agent to decide whether to use native command, parameter adapter, compatibility recipe, or refuse to claim equivalence. `get_recipe` returns the full recipe and evidence.

## 8. Retrieval and indexing

- Add `lumerical_compat` to collection configuration/allowlists, collection listing, ingestion tests and BM25 rebuild coverage.
- Reuse existing embedding, Qdrant upsert, BM25, RRF and reranker path; no new model or provider.
- Keep the one Tantivy index and global rebuild behavior.
- Compatibility search should filter by collection and relevant payload fields (`doc_type`, `target_version`, `product`, `solver`, `equivalence`, `verification_level`) where appropriate.
- Do not vectorize SQLite rows as the only mapping mechanism. Exact feature lookup uses SQLite; semantic retrieval uses Qdrant/Tantivy.
- Preserve full code blocks and keep recipe source identifiers across chunks.
- If the current payload schema has a naming convention, extend it instead of creating incompatible duplicate keys.

## 9. Resource and operational constraints

- No additional long-running service.
- SQLite is a local file opened by rag-shim. Use transactions, foreign keys, a busy timeout and safe backup/migration practices. WAL may be used if consistent with the host filesystem and existing backup approach; document the choice.
- Keep memory use bounded. Do not load all recipes or all capability snapshots into a permanent in-memory cache unless measurements justify it.
- Do not alter Qdrant quantization/HNSW/CPU-specific settings.
- Existing service names, ports, user-level systemd/linger setup and network exposure remain unchanged.
- Keep credentials and private endpoint configuration in existing environment/config files, not in the package or code.

## 10. Required tests

### Unit tests
- SQLite migration is repeatable/idempotent or has explicit migration versions.
- Foreign keys and uniqueness constraints work.
- Lookup distinguishes native / absent / partial / unknown / not_applicable.
- Multiple implementations per feature are supported.
- Product/solver/version isolation works.
- A missing evidence record never becomes `absent` by default.

### API tests
- Existing routes remain unchanged.
- New routes require existing Bearer auth.
- Missing/invalid query params return the project's normal 4xx envelope.
- Unknown features and missing recipes return controlled 404/empty outcomes.
- No arbitrary path traversal is possible.

### MCP tests
- New tools forward to shim correctly.
- Existing MCP tools remain compatible.
- Auth/config errors are surfaced without leaking tokens.

### Ingestion/index tests
- `lumerical_compat` accepts recipe and report docs.
- Payload metadata is preserved.
- Tantivy single-index rebuild contains all collections, including all three old collections plus `lumerical_compat`.
- Re-ingest is idempotent according to existing document identity policy.

### Compatibility validation
- Static parser/allowlist checks are labelled L1 only.
- Runtime checks must be run in the target Lumerical product/version and license environment.
- Differential/physics tests must store input fixture IDs, reference output, actual output, absolute/relative errors and declared valid domain.
- If the coding environment has no Lumerical installation/license, implement harness/templates and mark runtime validation pending. Do not claim L2/L3.

## 11. Acceptance criteria

The task is complete only when:

1. Existing 3-process architecture and ports are unchanged.
2. Existing endpoints/tools/collections still work.
3. `lumerical_compat` exists and is indexed by both Qdrant and Tantivy.
4. SQLite schema and migration are integrated into rag-shim.
5. All three compatibility REST routes work with existing auth.
6. Two MCP tools work through rag-shim.
7. Lookup gives product/solver/version-specific facts and returns unknown where evidence is missing.
8. A recipe can be retrieved by stable ID and contains code, dependencies, preconditions, equivalence, verification level and limitations.
9. Automated tests pass; unavailable runtime tests are explicitly listed as blocked/pending.
10. Documentation includes backup, migration, ingestion, BM25 rebuild, deployment and rollback steps.
11. No secrets or private LAN endpoint literals are added to source files.

## 12. Recommended implementation order

Follow `tasks/PHASE_PLAN.md`. Make small commits. At the end of each phase, report changed files, tests run, tests not run and risks. Do not do speculative refactors outside scope.
