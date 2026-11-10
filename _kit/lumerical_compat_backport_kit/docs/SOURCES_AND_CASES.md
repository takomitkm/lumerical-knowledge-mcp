# Existing Cases, Official References and Version-Evidence Notes

This file is a curated source list for ingestion and for reviewing compatibility claims. Treat official documentation as authoritative for the documented scope, not as proof that every installed product/update has identical runtime behavior. Capture the exact target runtime separately.

## A. Community implementation case: Lumerical-Objects Qanalysis

**Repository:** https://github.com/Niccolo-Marcucci/Lumerical-Objects

**Relevant source:** https://github.com/Niccolo-Marcucci/Lumerical-Objects/blob/master/Qanalysis-analysis_script.lsf

The script header identifies it as a Q analysis script and contains a 2012 Lumerical Solutions copyright notice. It obtains time-domain E/H monitor data, uses `fftw`, combines spectral power across monitors, finds peaks with `findpeaks`, estimates peak FWHM, applies Gaussian filters around each resonance, uses `invfft` to return filtered signals to the time domain, estimates decay slopes, and derives Q and an error estimate. It creates datasets for Q and spectrum and optionally plots intermediate/final data.

**What it proves:** LSF primitives can be composed into a multi-stage optical analysis workflow. It is a valuable implementation/reference pattern and a strong source for algorithmic decomposition, dataset output and Analysis Group packaging.

**What it does not prove:** It is not a drop-in implementation of the newer `findresonances` command. The official `findresonances` documentation describes filter diagonalization/harmonic inversion of time traces. A frequency-spectrum FWHM estimate or the archived Qanalysis routine has different assumptions/outputs and must not be marked as equivalent without a specific validated contract.

Potential second file to inspect in the same repository: `Qanalysis_sphere.lsf` (verify its exact path/content before ingesting).

## B. Official Ansys scripting and API references

### 1. Scripting language by category

https://optics.ansys.com/hc/en-us/articles/360037228834-Lumerical-scripting-language-By-category

Use for the current command taxonomy and product applicability. The page explicitly notes that not all commands are available in all products. It is a current KB reference, not a target-version command inventory.

### 2. `getcommands`

https://optics.ansys.com/hc/en-us/articles/360034931693-getcommands-Script-command

Official description: returns script commands available in the current script workspace; syntax is `?getcommands;`.

Use it as runtime evidence for command presence in the exact workspace/product. It does not by itself verify command signatures, every accepted type/shape, semantic behavior, all language keywords or other contexts.

### 3. `function`

https://optics.ansys.com/hc/en-us/articles/360034923573-function-Script-command

Official reference describes user-defined functions, arbitrary input variables and one output, global-scope definition, and loading a function from a separate script file. The version in which a particular target installation first gained this support must be established separately; do not infer it from the current command page.

### 4. `sort`

https://optics.ansys.com/hc/en-us/articles/360034406654-sort-Script-command

Official page says `sort` was introduced in 2018a R6. It sorts ascending by default or descending with the optional boolean argument. Complex values are ordered by magnitude then angle. The input is treated as a linear array while the output preserves the shape of the input matrix.

**Implication:** do not create a v241 sort backport solely because `sort` is absent from a particular v241 `docs.json`. Check the actual product/runtime first.

### 5. `findresonances`

Command reference:
https://optics.ansys.com/hc/en-us/articles/360034925953-findresonances-Script-command

2019a release notes:
https://optics.ansys.com/hc/en-us/articles/1500008744061-2019a-Release-Notes

The 2019a release notes identify `findresonances` as a new script command. The command reference describes filter diagonalization/harmonic inversion and returns six columns: frequency, decay constant, Q factor, amplitude, phase and error estimate. Its documented input consists of time, signal and a two-entry frequency interval. The docs also discuss signal-window, excitation, frequency-window, signal-length and low-Q limitations.

**Implication:** the FWHM code fragment from the original discussion is a distinct approximate spectrum-analysis method, not an equivalent recreation of this command's full contract.

### 6. Analysis Groups

https://optics.ansys.com/hc/en-us/articles/360034382454-Analysis-Groups-Simulation-object

Official documentation explains that analysis groups can contain monitors and scripts, use grouped monitor data for analysis, expose user properties as inputs and return configured output parameters. The setup script and analysis script have different responsibilities and scope. The analysis script does not use the global variable space of the Script Prompt / Script File Editor and cannot access monitors/sources outside the group.

**Implication:** a reusable compatibility feature may be packaged as an Analysis Group when the product/context supports it; do not assume it behaves like an ordinary `.lsf` script block.

### 7. File I/O and User Defined Functions lesson

https://innovationspace.ansys.com/courses/courses/lumerical-scripting-file-i-o-and-functions/lessons/file-i-o-and-user-defined-functions-lesson-1/

Official learning material covering project file manipulation, text/binary data I/O and user-defined functions. Useful for researching JSON/file serialization alternatives, but it does not itself establish that a particular file API or function syntax is available in every older target release.

## C. Release-history facts that affect the original v241 diff

| Feature/change | Official evidence | Safe interpretation |
|---|---|---|
| `sort` | Introduced in 2018a R6 | Expected to predate a 2024 R1 installation in documented supporting products; still confirm product/runtime |
| `findresonances` | Introduced in 2019a | Expected to predate a 2024 R1 installation in documented supporting products; verify exact solver/runtime |
| `modeoverlap` | 2022 R2.2 release notes | Added in conjunction with raw FEEM mode data and DGTD frequency-domain field data; do not generalize to all products |
| `python` LSF command | 2024 R1.1 release notes | Distinguish 2024 R1 from R1.1; verify exact installed update |
| `overlap`, `expand`, `expand2` accepting rectilinear datasets | 2024 R2.3 release notes | A newer input/API capability for FDTD/MODE, not the introduction of the underlying overlap function |
| `median`, `print`, `function`, `while`, JSON commands and other original diff items | Not established by the sources in this kit | Keep `unknown` until exact-version docs/release history/runtime probes establish status |

### 8. `modeoverlap` — 2022 R2.2 Release Notes

https://optics.ansys.com/hc/en-us/articles/8194158041491-2022-R2-2-Release-Notes

The release notes say the new `modeoverlap` script command can use raw mode data from FEEM or raw frequency-domain field data from DGTD to calculate overlaps between FEEM mode profiles and between FEEM modes and DGTD frequency-domain fields.

### 9. `overlap` / `expand` / `expand2` dataset arguments — 2024 R2.3 Release Notes

https://optics.ansys.com/hc/en-us/articles/35079732252819-2024-R2-3-Release-Notes

The release notes say these commands (FDTD/MODE, Lumerical script language and Python API) now accept rectilinear datasets; previously inputs were d-card or monitor names. This distinction is an excellent API-adaptation case study: the core operation existed, but the accepted input representation was extended.

### 10. `python` LSF command — 2024 R1.1 Release Notes

https://optics.ansys.com/hc/en-us/articles/25979841863443-2024-R1-1-Release-Notes

The release notes identify a new `python` command in Lumerical Script Language for executing a Python script file with the configured Python interpreter. The update level matters: do not collapse 2024 R1 and 2024 R1.1.

## D. How to ingest these sources

Recommended records in `lumerical`:

- Official command pages: `doc_type=command`, `source_type=official`, `authority=ansys`.
- Learning material: `doc_type=tutorial`, `source_type=official`.
- Release notes: `doc_type=release_note`, `source_type=official`, include exact `introduced_version` or `changed_version` only when explicitly stated.
- Qanalysis source: `doc_type=community_example`, `source_type=community`, repository and source URL retained; version scope should be `unknown` unless tested.

Do not copy release-note facts into SQLite as runtime `native` status for every solver. Record the release fact as evidence; create product/solver/version availability entries only after the target scope has been established.

## E. Core source URLs

- Lumerical scripting language by category: https://optics.ansys.com/hc/en-us/articles/360037228834-Lumerical-scripting-language-By-category
- `getcommands`: https://optics.ansys.com/hc/en-us/articles/360034931693-getcommands-Script-command
- `function`: https://optics.ansys.com/hc/en-us/articles/360034923573-function-Script-command
- `sort`: https://optics.ansys.com/hc/en-us/articles/360034406654-sort-Script-command
- `findresonances`: https://optics.ansys.com/hc/en-us/articles/360034925953-findresonances-Script-command
- 2019a Release Notes: https://optics.ansys.com/hc/en-us/articles/1500008744061-2019a-Release-Notes
- Analysis Groups: https://optics.ansys.com/hc/en-us/articles/360034382454-Analysis-Groups-Simulation-object
- File I/O and User Defined Functions: https://innovationspace.ansys.com/courses/courses/lumerical-scripting-file-i-o-and-functions/lessons/file-i-o-and-user-defined-functions-lesson-1/
- 2022 R2.2 Release Notes: https://optics.ansys.com/hc/en-us/articles/8194158041491-2022-R2-2-Release-Notes
- 2024 R2.3 Release Notes: https://optics.ansys.com/hc/en-us/articles/35079732252819-2024-R2-3-Release-Notes
- 2024 R1.1 Release Notes: https://optics.ansys.com/hc/en-us/articles/25979841863443-2024-R1-1-Release-Notes
- Lumerical-Objects Qanalysis script: https://github.com/Niccolo-Marcucci/Lumerical-Objects/blob/master/Qanalysis-analysis_script.lsf
