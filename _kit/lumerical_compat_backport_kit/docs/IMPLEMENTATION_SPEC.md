# Implementation Specification

## 1. Goal and boundary

Extend the existing Lumerical RAG into a version-aware documentation and compatibility system. The system must answer three separate questions:

1. What does the new-version feature mean and what is its official contract?
2. Is the feature natively available in the exact target product/solver/version?
3. If not, is there a validated adapter or backport implementation, and what is its equivalence/verification status?

This is a capability and evidence system, not merely a semantic search enhancement.

## 2. Existing topology

```text
Notebook dsh / school dsh / REST or CLI
                 │
                 ▼
       rag-mcp :8901 (FastMCP)
       only external MCP boundary
                 │ loopback REST
                 ▼
       rag-shim :8900 (FastAPI, Bearer)
       ├── embedding: SiliconFlow bge-m3 (1024 dimensions)
       ├── Qdrant retrieval: top 50
       ├── Tantivy BM25: top 50, one shared index
       ├── metadata filters
       ├── RRF (k=60): top 20
       ├── SiliconFlow reranker: bge-reranker-v2-m3
       ├── ingest / document / collections / health
       └── global BM25 rebuild
                 │
          ┌──────┴─────────┐
          ▼                ▼
       Qdrant           SQLite file
       127.0.0.1        compatibility.db
          │
          └──── Tantivy BM25 shared index
```

Existing process budgets and Qdrant hardware-specific settings remain unchanged. SQLite is not a new daemon.

## 3. Collections and content taxonomy

| Collection | Role | Additions |
|---|---|---|
| `lumerical` | General/current official Lumerical knowledge | Tutorials, release notes, command references and community reference scripts, all correctly labelled |
| `lumerical_v241` | Version-specific v241 documentation, currently sourced from the installed `docs.json` | Keep as a source of docs evidence; do not treat it as a complete runtime capability inventory |
| `lumerical_compat` | Authored compatibility knowledge | Recipes, algorithm references, compatibility analyses, validation reports |
| `fdtdx` | Independent FDTDX documentation/API | No changes in this scope |

### Required payload metadata

Reuse existing field names if the current payload schema already has equivalents. Otherwise add these fields consistently:

- `doc_id`: stable logical document identifier, independent of Qdrant point ID.
- `doc_type`: `command`, `tutorial`, `release_note`, `community_example`, `compatibility_recipe`, `algorithm_reference`, `compatibility_analysis`, `validation_report`.
- `source_type`: `official`, `community`, `user_authored`, `generated`.
- `authority`: e.g. `ansys`, `community`, `project`.
- `source_url`, `source_title`, `source_id`.
- `product`, `solver` (solver may be null when genuinely shared).
- `version_scope`, `tested_version`, `introduced_version`, `removed_version` when known; never infer missing versions.
- `target_version` for a compatibility implementation.
- `feature_id`, `implementation_id` for compatibility assets.
- `equivalence`, `verification_level`, `status`.
- `dependencies` or a concise dependency summary.
- `limitations` and `preconditions`.
- Existing breadcrumb, title, body and chunk metadata remain intact.

Do not set `tested_version` just because an online document is currently visible. Do not call a community script official.

## 4. Structured registry

Use SQLite as the runtime source of truth for structured mapping. The Qdrant `lumerical_compat` collection is a retrieval projection of Markdown/LSF docs—not the authoritative relationship store.

### Entities

- **Target environment:** exact product, solver, version/update/build, platform and capture time.
- **Feature:** canonical function/command/feature identifier, aliases and description.
- **Feature availability:** native/absent/partial/unknown/not-applicable for a particular target environment, with evidence.
- **Implementation:** native, adapter, backport or workaround; equivalence and verification level.
- **Dependency:** command, keyword, operator, builtin, data type or API needed by an implementation.
- **Capability snapshot:** immutable captured files and their hash.
- **Evidence source:** official doc, release note, runtime probe, community source or test result.
- **Validation run:** test method, target environment, pass/fail/partial outcome, report and metrics.
- **Document reference:** stable document ID and collection for retrieval.

The provided SQL schema is a starting implementation. Agent may align names/types to existing project conventions while preserving semantic constraints.

### Do not conflate the status dimensions

**Availability** answers whether a feature is available in a particular product/solver/version.

**Equivalence** answers how closely a fallback implementation matches the requested feature.

**Verification level** answers what evidence/tests have been completed.

They must be stored independently.

## 5. Capability snapshots

Capture the exact environment on which scripts are expected to run. `?getcommands;` returns commands available in the current script workspace. It is valuable evidence, but it does not establish all syntax keywords, argument signatures, data types or semantics.

For each product/solver/update combination, retain:

```text
capabilities/<product>/<solver>/<exact-version>/
  environment.json
  commands.json
  syntax_probes.json
  capture-notes.md
```

- `environment.json`: product, solver, exact version/update/build, OS, capture time and license/runtime availability (do not include private license keys).
- `commands.json`: raw `getcommands` output and normalized symbol list.
- `syntax_probes.json`: separately tested syntax/keyword forms and command-signature probes.
- `capture-notes.md`: how the snapshot was collected, errors and limitations.

Store the snapshot file paths and SHA-256 in SQLite. Import normalized symbol facts into the capability tables. Never overwrite old snapshots; capture a new immutable snapshot when the installation changes.

## 6. Recipe and asset layout

Suggested logical layout (adapt to the repository's conventions):

```text
lumerical/
  sources/
    official/tutorials/
    official/release_notes/
    community/<repository>/
  compatibility/
    recipes/<feature>/<target-version>/
      README.md
      implementation.lsf
      metadata.yaml
  capabilities/<product>/<solver>/<exact-version>/
  tests/<implementation-id>/
    fixtures/
    expected/
    reports/
  data/compatibility.db
```

For each recipe:
- Keep one complete executable `.lsf` source file.
- Keep one human-readable Markdown contract explaining algorithm and limitations.
- Keep structured metadata (YAML template provided) or equivalent SQLite record.
- Use stable `implementation_id` across all three assets.
- Do not use a recipe name that impersonates an exact native command if it is merely approximate. Example: `resonance_fwhm_v241`, not `findresonances_v241`, when the algorithm is FWHM-based rather than filter diagonalization.

## 7. Ingestion behavior

Use the existing ingestion machinery and chunk builder. Add `lumerical_compat` to allowlists/config and test paths.

For compatibility recipes:
- One logical document per recipe, with stable `doc_id`.
- Keep LSF code intact in chunks or retrieve the original full document after selecting it.
- Add metadata to every chunk: collection, doc_id, doc_type, feature_id, implementation_id, target_version, product, solver, equivalence and verification level.
- Ensure the document breadcrumb identifies the feature and target release.
- Store official/community source links in the content and payload.

For validation reports:
- Index concise report summaries for semantic search.
- Store the complete report as a retrievable document/file.
- Never index secrets, local license data or internal access tokens.

After ingestion, call the existing global Tantivy rebuild once all collections have been included. Never rebuild an index using only the latest ingestion batch or one collection.

## 8. REST API design

Keep the existing response envelope and auth. Suggested semantics:

### `GET /compat/lookup`

Parameters:
- `feature` required.
- `target_version` required and exact.
- `product` optional only if the feature/environment is unambiguous.
- `solver` optional only if unambiguous.

Lookup algorithm:
1. Resolve feature alias to canonical `feature_id`.
2. Resolve exact target environment; do not fuzzy-match a major release when an update label matters.
3. Query availability and evidence.
4. Query all implementations valid for that target.
5. Resolve dependencies and capability statuses.
6. Return native availability first; otherwise candidates ranked by equivalence and verification, not by semantic similarity alone.
7. If environment/evidence is missing, return `unknown` and explain what must be captured.

Example response shape (adapt to existing JSON envelope):

```json
{
  "feature": {"id":"median", "canonical_name":"median", "query_name":"median"},
  "target": {"product":"FDTD", "solver":"FDTD", "version":"2024 R1"},
  "availability": {"status":"unknown", "evidence_basis":[], "notes":"No runtime snapshot recorded"},
  "implementations": [],
  "required_next_evidence": ["getcommands snapshot", "syntax/runtime probe"]
}
```

The example is deliberately `unknown`; absence of a database row is not proof of absence.

### `GET /compat/recipe`

Preferred parameter: `implementation_id`.

Return the metadata and complete recipe body. Resolve `recipe_doc_id` through existing document retrieval, not a user-supplied filesystem path. Include dependency evidence, preconditions, limitations and validation level.

### `GET /compat/capabilities`

Accept `target_id` or exact product/solver/version selectors. Return snapshot metadata and symbol results. Every returned fact must identify its evidence basis: `getcommands`, syntax probe, signature/runtime probe, official docs, or unknown.

## 9. MCP changes

Add two tools to the existing FastMCP app:

- `lookup_lumerical_compatibility`
- `get_lumerical_compat_recipe`

The MCP process remains thin. It calls only the shim endpoints, uses existing auth/config, and does not import Qdrant/SQLite logic. `lookup` returns enough facts for an agent to choose native, adapter, backport, approximate fallback or unsupported. `get_recipe` returns the exact code/contract/evidence for an implementation ID.

## 10. Search interaction

Use exact SQLite lookup first for feature/version mapping. Use vector/BM25 search for semantic discovery and explanatory material.

Suggested agent flow:

1. Identify requested feature, product, solver and exact target version.
2. Call `lookup_lumerical_compatibility`.
3. If native: retrieve the official command doc and use native syntax.
4. If an adapter/backport exists: call `get_lumerical_compat_recipe`; retrieve source evidence as needed.
5. Check every dependency against the target capability snapshot.
6. If unknown: do not assume missing or present; ask for/capture a runtime snapshot or mark status unknown.
7. If no recipe exists: search `lumerical` for official tutorials, `lumerical_v241` for target docs and `lumerical_compat` for related algorithms; any generated candidate starts at L0.
8. State equivalence, verification level, preconditions and limitations with generated code.

## 11. Operational handling

- Use the existing configuration system for DB path, not a hard-coded user home path.
- Back up SQLite before migration; use explicit schema versioning.
- Enable foreign keys on every SQLite connection. Set a bounded busy timeout. Decide WAL based on current filesystem/backup conventions and document it.
- Keep transactions short. Do not hold DB locks while calling Qdrant, embedding, reranking or Lumerical.
- Use prepared statements; validate all user input.
- No arbitrary file path retrieval from APIs.
- Logs must not include bearer tokens or secrets.
- Do not cache all registry/snapshot data indefinitely; measure before adding caches.

## 12. Rollback

- New SQLite schema can be backed up/restored independently.
- New Qdrant collection can be removed without touching the old three collections, but only after confirming the exact collection name and that no old collection data is affected.
- Remove/disable new routes and MCP tools if deployment fails; existing routes/tools should continue functioning.
- Restore prior config and SQLite backup. Do not delete/rebuild the old collections as a rollback shortcut.
