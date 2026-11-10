# Package manifest

| Path | Purpose |
|---|---|
| `AGENT_BRIEF.md` | Copy/send this as the coding agent's main task instruction. |
| `README.md` | Project overview and important architectural constraints. |
| `docs/IMPLEMENTATION_SPEC.md` | Detailed target architecture, data placement, schema concepts, API contracts, retrieval flow and ops rules. |
| `docs/BACKPORT_SOP.md` | Semantic-preservation and validation rules for LSF backports. |
| `docs/SOURCES_AND_CASES.md` | Curated Ansys/community references, case-study interpretation and evidence corrections. |
| `tasks/PHASE_PLAN.md` | Ordered implementation phases and acceptance criteria. |
| `schema/compatibility.sql` | SQLite registry DDL (schema version 1). |
| `schema/evidence_seed.sql` | Optional initial feature/source records; intentionally does not assert target-version availability. |
| `templates/implementation.yaml` | Recipe metadata authoring template. |
| `templates/recipe.md` | Human-readable compatibility recipe template. |
| `templates/environment.json` | Exact target installation metadata template. |
| `templates/capability-snapshot.json` | Immutable capability snapshot manifest template. |
| `templates/commands.json` | Normalized `getcommands` snapshot template. |
| `templates/syntax-probes.json` | Separate syntax/signature probe template. |
| `templates/test-report.json` | Runtime/differential test report template. |

## Suggested handoff

Give the coding agent `AGENT_BRIEF.md` first and attach the complete ZIP. Tell it to inspect the current repository and report the existing integration points before editing. The detailed spec and templates are supporting contract material.

## Validation performed on this package

- `compatibility.sql` executed successfully with SQLite.
- `evidence_seed.sql` executed successfully after the schema.
- The seed produces 10 feature identifiers and 11 source records.
- The seed creates no v241 `feature_availability` assertions; runtime availability remains to be captured.
- JSON template syntax is validated during package build.

This package specifies work; it does not claim the user's running RAG service has already been modified.
