# Lumerical Compatibility Backport Kit — public implementation

Version-aware knowledge service for Lumerical scripting: documentation RAG **plus** a
runtime-evidenced capability registry that answers *"does command X exist on my exact
build, and if not, is there a validated workaround?"*

Three questions, kept strictly apart:

1. **What is the feature?** — official documentation (per-feature description + links)
2. **Is it natively available on the exact target?** — `feature_availability` rows carry
   evidence tiers (`getcommands` runtime snapshot > `syntax_probe` > `official_docs`);
   **documented absence ≠ runtime absence** (we measured 68 commands that are native at
   2024 R1 despite missing from the bundled `docs.json`)
3. **If not, is there a validated alternative?** — `implementations` with an
   equivalence axis (exact / domain_equivalent / approximate / partial / unsupported)
   and an independent verification axis (L0-L4); missing evidence is reported as
   `unknown` with `required_next_evidence`, never guessed

## Architecture (3 processes only, no new ports)

```
rag-mcp  :8901/mcp  (FastMCP; 5 tools; only external boundary)
   │ loopback REST (Bearer)
rag-shim :8900      (FastAPI)
   ├── RAG: bge-m3 embed → Qdrant top-k + Tantivy BM25 → RRF → reranker
   ├── documents: /search /document /collections /ingest /admin/rebuild-bm25
   ├── compat: /compat/lookup /compat/recipe /compat/capabilities
   │       └── compatibility.db (SQLite, 10 tables, opened in-process)
rag-qdrant 127.0.0.1:6333 (user-level systemd; no quantization/HNSW — required on CPUs without AVX)
```

Collections: `lumerical` (current KB + examples), `lumerical_v241` (bundled docs.json),
`lumerical_compat` (authored recipes/adapters, whole-file), `fdtdx` (open-source FDTDX).

## Measured results (2024 R1, build 8.31.3633, real lumapi session)

| asset | equivalence | verification | evidence |
|---|---|---|---|
| `median` via native `sort` | exact | **L2** | 5/5 fixtures exact-equality pass |
| `resonance_fwhm` (peak/FWHM Q analysis) | approximate | **L2** (declared domain) | analytic rel-err 1.2e-6; vs **native `findresonances`** on a real FDTD DBR-cavity run: **gap 2.4e-5** |
| `adddftmonitor` adapter (→ `addpower`) | domain_equivalent | **L2** | fields present after run |
| `reportmeshstatistics` adapter (→ `mesh cells x/y/z`) | partial | **L2** | 267×132×47 cells, steps = span/cells consistent |

Key measured facts (see `compat/`):
- **68 of 120 "new-version" commands are actually native at 2024 R1** — the bundled
  docs.json has documentation gaps, not capability gaps
- 52 genuinely absent commands, classified by portability
  (`compat/absent_commands_inventory.md`)
- **24 commands present at runtime but documented nowhere**
  (`compat/undocumented_runtime_commands.md`), live-probed: `getassertresults` exposes the
  session error buffer; `getlicenseversion` returns the build number;
  `setglobal/getglobal` are in the inventory but not callable from FDTD scripts
  (installation-wide inventory quirk)

## Layout

```
shim/                    rag-shim app + compat module (schema.sql, db.py, repo.py, api.py)
tests/                   16 unit/API tests (no server needed)
compat/assets/           4 authored assets: recipe.md + implementation.lsf + yaml + test reports
capabilities/            capture-kit for the target machine + snapshot layout
compat/runtime_crosscheck.json   606-symbol runtime inventory × doc sources
crawl_zendesk.py etc.    corpus builders (run them yourself; no copyrighted data shipped)
verify_all.py            12-point end-to-end verification sweep
ARCHITECTURE_AND_TESTS.md  full architecture + test record
```

## Notes

- Corpus data (Ansys KB pages, v241 docs.json, .lsf examples) is **not included** — build
  it with `crawl_zendesk.py` / `build_v241.py` from your own installation.
- `_kit` (the original SOP this implements) is not redistributed **but is a required build
  input**: `build_compat_registry.py` exits with an error if
  `_kit/lumerical_compat_backport_kit/` is absent — its evidence seed carries the
  source-history rows (release-note sources) that availability rows reference via foreign
  keys. The methodology is summarized in `ARCHITECTURE_AND_TESTS.md`.
- Requires: Python 3.11+, `fastapi uvicorn httpx tantivy "mcp>=1.2,<2"`, a Qdrant
  instance, and SiliconFlow (or any OpenAI-compatible) embedding/rerank endpoint.
