-- Lumerical Compatibility Registry schema
-- SQLite; run with foreign_keys=ON. Keep this file migration-controlled.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT OR IGNORE INTO schema_meta(key, value) VALUES ('schema_version', '1');

CREATE TABLE IF NOT EXISTS target_environments (
    target_id TEXT PRIMARY KEY,
    product TEXT NOT NULL,
    solver TEXT NOT NULL,
    version_label TEXT NOT NULL,
    update_label TEXT NOT NULL DEFAULT '',
    build_number TEXT NOT NULL DEFAULT '',
    platform TEXT,
    captured_at TEXT,
    capture_notes TEXT,
    UNIQUE(product, solver, version_label, update_label, build_number)
);

CREATE TABLE IF NOT EXISTS features (
    feature_id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL UNIQUE,
    feature_kind TEXT NOT NULL DEFAULT 'command'
        CHECK(feature_kind IN ('command','language_construct','workflow','algorithm','data_api','other')),
    description TEXT
);

CREATE TABLE IF NOT EXISTS feature_aliases (
    alias TEXT NOT NULL,
    feature_id TEXT NOT NULL REFERENCES features(feature_id) ON DELETE CASCADE,
    context TEXT,
    PRIMARY KEY(alias, feature_id)
);
CREATE INDEX IF NOT EXISTS idx_feature_aliases_alias ON feature_aliases(alias);

CREATE TABLE IF NOT EXISTS evidence_sources (
    source_id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL
        CHECK(source_type IN ('official_command_doc','official_tutorial','release_note','runtime_snapshot','syntax_probe','signature_probe','community_repo','project_test','paper','other')),
    authority TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT,
    published_or_updated TEXT,
    version_scope TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS document_refs (
    doc_id TEXT PRIMARY KEY,
    collection TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    title TEXT NOT NULL,
    source_path TEXT,
    source_id TEXT REFERENCES evidence_sources(source_id) ON DELETE SET NULL,
    qdrant_point_id TEXT,
    metadata_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_document_refs_collection_type ON document_refs(collection, doc_type);

CREATE TABLE IF NOT EXISTS capability_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    target_id TEXT NOT NULL REFERENCES target_environments(target_id) ON DELETE CASCADE,
    captured_at TEXT NOT NULL,
    commands_file TEXT,
    environment_file TEXT,
    syntax_probes_file TEXT,
    commands_sha256 TEXT,
    snapshot_sha256 TEXT,
    capture_method TEXT NOT NULL DEFAULT 'manual',
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_capability_snapshots_target ON capability_snapshots(target_id, captured_at);

CREATE TABLE IF NOT EXISTS capability_items (
    snapshot_id TEXT NOT NULL REFERENCES capability_snapshots(snapshot_id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    symbol_type TEXT NOT NULL
        CHECK(symbol_type IN ('command','keyword','operator','builtin_function','data_type','dataset_api','other')),
    presence TEXT NOT NULL CHECK(presence IN ('present','absent','unknown','not_applicable')),
    signature_status TEXT NOT NULL DEFAULT 'unknown'
        CHECK(signature_status IN ('verified','partially_verified','not_tested','unknown','not_applicable')),
    evidence_method TEXT NOT NULL
        CHECK(evidence_method IN ('getcommands','syntax_probe','signature_probe','runtime_invocation','official_docs','manual','unknown')),
    details_json TEXT,
    notes TEXT,
    PRIMARY KEY(snapshot_id, symbol, symbol_type)
);
CREATE INDEX IF NOT EXISTS idx_capability_items_symbol ON capability_items(symbol, symbol_type, presence);

CREATE TABLE IF NOT EXISTS feature_availability (
    feature_id TEXT NOT NULL REFERENCES features(feature_id) ON DELETE CASCADE,
    target_id TEXT NOT NULL REFERENCES target_environments(target_id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK(status IN ('native','absent','partial','unknown','not_applicable')),
    evidence_basis TEXT NOT NULL DEFAULT 'unknown'
        CHECK(evidence_basis IN ('official_docs','release_notes','getcommands','syntax_probe','signature_probe','runtime_invocation','multiple','unknown')),
    source_id TEXT REFERENCES evidence_sources(source_id) ON DELETE SET NULL,
    snapshot_id TEXT REFERENCES capability_snapshots(snapshot_id) ON DELETE SET NULL,
    checked_at TEXT,
    notes TEXT,
    PRIMARY KEY(feature_id, target_id)
);
CREATE INDEX IF NOT EXISTS idx_feature_availability_target_status ON feature_availability(target_id, status);

CREATE TABLE IF NOT EXISTS implementations (
    implementation_id TEXT PRIMARY KEY,
    feature_id TEXT NOT NULL REFERENCES features(feature_id) ON DELETE CASCADE,
    target_id TEXT NOT NULL REFERENCES target_environments(target_id) ON DELETE CASCADE,
    implementation_kind TEXT NOT NULL
        CHECK(implementation_kind IN ('native','adapter','backport','workaround')),
    equivalence TEXT NOT NULL
        CHECK(equivalence IN ('exact','domain_equivalent','approximate','partial','unsupported')),
    verification_level TEXT NOT NULL DEFAULT 'L0'
        CHECK(verification_level IN ('L0','L1','L2','L3','L4')),
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK(status IN ('draft','candidate','static_checked','runtime_verified','differential_verified','proven','blocked','deprecated')),
    recipe_doc_id TEXT REFERENCES document_refs(doc_id) ON DELETE SET NULL,
    source_path TEXT,
    contract_json TEXT NOT NULL DEFAULT '{}',
    preconditions TEXT,
    assumptions TEXT,
    limitations TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_implementations_feature_target ON implementations(feature_id, target_id, status);
CREATE INDEX IF NOT EXISTS idx_implementations_verification ON implementations(verification_level, equivalence);

CREATE TABLE IF NOT EXISTS implementation_dependencies (
    implementation_id TEXT NOT NULL REFERENCES implementations(implementation_id) ON DELETE CASCADE,
    dependency_name TEXT NOT NULL,
    dependency_type TEXT NOT NULL
        CHECK(dependency_type IN ('command','keyword','operator','builtin_function','data_type','dataset_api','file','external_runtime','other')),
    required INTEGER NOT NULL DEFAULT 1 CHECK(required IN (0,1)),
    target_presence TEXT NOT NULL DEFAULT 'unknown'
        CHECK(target_presence IN ('present','absent','unknown','not_applicable')),
    capability_snapshot_id TEXT REFERENCES capability_snapshots(snapshot_id) ON DELETE SET NULL,
    evidence_source_id TEXT REFERENCES evidence_sources(source_id) ON DELETE SET NULL,
    notes TEXT,
    PRIMARY KEY(implementation_id, dependency_name, dependency_type)
);
CREATE INDEX IF NOT EXISTS idx_implementation_dependencies_name ON implementation_dependencies(dependency_name, dependency_type, target_presence);

CREATE TABLE IF NOT EXISTS validation_runs (
    validation_run_id TEXT PRIMARY KEY,
    implementation_id TEXT NOT NULL REFERENCES implementations(implementation_id) ON DELETE CASCADE,
    target_id TEXT NOT NULL REFERENCES target_environments(target_id) ON DELETE CASCADE,
    test_suite_id TEXT,
    test_method TEXT NOT NULL
        CHECK(test_method IN ('static','syntax_probe','unit','runtime','differential','physics_integration','formal')),
    result TEXT NOT NULL CHECK(result IN ('passed','failed','partial','skipped','blocked')),
    run_at TEXT NOT NULL,
    runner TEXT,
    report_doc_id TEXT REFERENCES document_refs(doc_id) ON DELETE SET NULL,
    report_path TEXT,
    metrics_json TEXT,
    input_fixture_ids TEXT,
    notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_validation_runs_impl ON validation_runs(implementation_id, run_at);

-- Enforce that L4 is never silently assigned through ordinary insert defaults; application logic
-- must require a formal validation record and explicit review before promoting to L4.

