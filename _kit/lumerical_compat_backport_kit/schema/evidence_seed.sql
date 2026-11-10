-- Optional evidence seed. Run after compatibility.sql.
-- These are source-history records and feature identifiers only.
-- They intentionally do NOT assert availability for a specific v241 product/solver.
PRAGMA foreign_keys = ON;

INSERT OR IGNORE INTO evidence_sources
(source_id, source_type, authority, title, url, version_scope, notes)
VALUES
('ansys.lsf.by_category', 'official_command_doc', 'ansys', 'Lumerical scripting language - By category', 'https://optics.ansys.com/hc/en-us/articles/360037228834-Lumerical-scripting-language-By-category', 'current online KB', 'Current command taxonomy; product applicability varies.'),
('ansys.getcommands', 'official_command_doc', 'ansys', 'getcommands - Script command', 'https://optics.ansys.com/hc/en-us/articles/360034931693-getcommands-Script-command', 'current online KB', 'Lists commands available in the current script workspace; does not prove signatures or semantics.'),
('ansys.sort', 'official_command_doc', 'ansys', 'sort - Script command', 'https://optics.ansys.com/hc/en-us/articles/360034406654-sort-Script-command', 'introduced 2018a R6', 'Official page states introduction version and complex sort behavior.'),
('ansys.findresonances', 'official_command_doc', 'ansys', 'findresonances - Script command', 'https://optics.ansys.com/hc/en-us/articles/360034925953-findresonances-Script-command', 'introduced 2019a', 'Filter diagonalization/harmonic inversion command contract.'),
('ansys.release.2019a', 'release_note', 'ansys', '2019a Release Notes', 'https://optics.ansys.com/hc/en-us/articles/1500008744061-2019a-Release-Notes', '2019a', 'Identifies findresonances as a new script command.'),
('ansys.analysis_groups', 'official_tutorial', 'ansys', 'Analysis Groups - Simulation object', 'https://optics.ansys.com/hc/en-us/articles/360034382454-Analysis-Groups-Simulation-object', 'current online KB', 'Describes setup/analysis script roles and scoping.'),
('ansys.file_io_functions_lesson', 'official_tutorial', 'ansys', 'File I/O and User Defined Functions - Lesson 1', 'https://innovationspace.ansys.com/courses/courses/lumerical-scripting-file-i-o-and-functions/lessons/file-i-o-and-user-defined-functions-lesson-1/', 'course publication approximately 2021', 'Covers file handling and user-defined functions.'),
('ansys.release.2022r2.2', 'release_note', 'ansys', '2022 R2.2 Release Notes', 'https://optics.ansys.com/hc/en-us/articles/8194158041491-2022-R2-2-Release-Notes', '2022 R2.2', 'Introduces modeoverlap for FEEM/DGTD raw mode/field data.'),
('ansys.release.2024r2.3', 'release_note', 'ansys', '2024 R2.3 Release Notes', 'https://optics.ansys.com/hc/en-us/articles/35079732252819-2024-R2-3-Release-Notes', '2024 R2.3', 'Adds rectilinear dataset inputs to overlap, expand and expand2 in FDTD/MODE.'),
('ansys.release.2024r1.1', 'release_note', 'ansys', '2024 R1.1 Release Notes', 'https://optics.ansys.com/hc/en-us/articles/25979841863443-2024-R1-1-Release-Notes', '2024 R1.1', 'Introduces the LSF python command.'),
('community.lumerical_objects.qanalysis', 'community_repo', 'community', 'Lumerical-Objects Qanalysis-analysis_script.lsf', 'https://github.com/Niccolo-Marcucci/Lumerical-Objects/blob/master/Qanalysis-analysis_script.lsf', 'version scope unknown', 'Archived script with 2012 Lumerical Solutions copyright header; reference implementation, not an equivalence proof.');

INSERT OR IGNORE INTO features(feature_id, canonical_name, feature_kind, description)
VALUES
('findresonances', 'findresonances', 'command', 'Time-domain harmonic inversion/filter diagonalization to extract resonance parameters.'),
('sort', 'sort', 'command', 'Sorts matrix values; documented complex ordering and shape behavior.'),
('modeoverlap', 'modeoverlap', 'command', 'FEEM/DGTD raw mode/field overlap command; solver/product scope matters.'),
('overlap_dataset_input', 'overlap_dataset_input', 'data_api', 'Ability to pass rectilinear datasets to overlap/expand/expand2 in FDTD/MODE.'),
('python_lsf_command', 'python', 'command', 'Execute a Python script file from Lumerical Script Language; introduced in 2024 R1.1.'),
('median', 'median', 'command', 'Version/product availability and exact semantics require verification.'),
('function', 'function', 'language_construct', 'User-defined LSF function syntax; exact target-version support must be established.'),
('print', 'print', 'command', 'Version/product availability and exact semantics require verification.'),
('jsonload', 'jsonload', 'command', 'Version/product availability and exact semantics require verification.'),
('jsonsave', 'jsonsave', 'command', 'Version/product availability and exact semantics require verification.');
