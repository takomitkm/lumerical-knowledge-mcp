# reportmeshstatistics — 2024 R1 (v241) compatibility recipe

> **Implementation ID:** `compat.reportmeshstatistics.v241.adapter`
> **Target:** `Lumerical / FDTD / 2024 R1 (v241, runtime 8.31.3633)`
> **Equivalence:** `partial`
> **Verification:** `L2`
> **Status:** `runtime_verified`

## Purpose

`reportmeshstatistics` (newer releases, tetrahedral/triangular solvers) returns mesh quality
statistics. FDTD uses a **rectilinear Yee mesh**, so the official command does not apply
(its own docs exclude rectilinear meshes). This adapter computes the **FDTD-relevant mesh
statistics** from the mesh object after meshing: cells per axis, total cells, min/max/mean
steps, and the mesh frequency. This is a **partial** equivalent: same spirit (mesh quality
report), different mesh topology.

## New-version contract

- Official page: returns statistical information about the mesh grid; applies to tetrahedral
  (3D) and triangular (2D) meshes only — **explicitly not applicable to FDTD's rectilinear mesh**.

## Target environment

- Product: Lumerical; Solver: **FDTD**
- Exact version: 2024 R1 (build 8.31.3633)
- Capability snapshot: `snapshot.lumerical-2024r1-school.20261110T182355Z`

## Preconditions and supported domain

- Run at least the meshing stage (execute after `run` or in analysis mode with a mesh).
- 2D or 3D rectilinear FDTD mesh.

## Dependencies

| Symbol | Type | Required | Target evidence | Notes |
|---|---|---:|---|---|
| `getresult` | dataset_api | yes | runtime getcommands | mesh data |
| `struct` | builtin_function | yes | runtime getcommands | result assembly |
| `get` | command | yes | runtime getcommands | FDTD properties (nx, ny, nz, dx, dy, dz) |

## Algorithm

Read `nx, ny, nz` (cell counts) and `dx, dy, dz` (step sizes) from the FDTD object after
meshing; assemble a struct with total cells, per-axis step min/max/mean, and an estimate of
the smallest resolved feature. The adapter reads the properties the v241 object exposes
(`set` property list showed `nx, ny, nz, dx, dy, dz, mesh cells x/y/z, mesh accuracy`).

## Usage

After a run (or after meshing), run the block; read the returned struct fields.

## LSF implementation

See the companion file `implementation.lsf`.

## Output contract

| Output | Type/shape | Unit | Meaning |
|---|---|---|---|
| `stats.nx, stats.ny, stats.nz` | int | — | mesh cells per axis |
| `stats.total_cells` | int | — | product |
| `stats.dx, stats.dy, stats.dz` | 1×1 | m | step sizes |
| `stats.resolution` | 1×1 | 1/m | meshing frequency (cells per wavelength metric) |

## Equivalence analysis

`partial`: same intent (mesh quality report) but different topology — the official command
reports tetrahedral/triangular quality metrics (aspect ratio etc.) that do not exist on a
Yee grid; this adapter reports the FDTD-meaningful statistics instead. Not `domain_equivalent`
because the output schema differs by necessity.

## Limitations

- Rectilinear FDTD only (by design; the official command itself excludes this topology).
- No aspect-ratio/skewness metrics (meaningless on Yee grids).

## Validation evidence

| Test ID | Method | Target env | Expected | Actual | Error/tolerance | Result |
|---|---|---|---|---|---|---|
| `runtime.adapter.meshstat.001` | runtime | 2024 R1 (8.31.3633) | stats struct after run on the L3 cavity project; nx×ny×nz consistent with dx×dy×dz spans | see `compat/assets/reportmeshstatistics_v241/adapter_results.json` | spans/products internally consistent | passed |

## Sources

- Official new feature documentation: `reportmeshstatistics - Script command` (current KB)
- Release note / introduction history: introduction release not established (unknown)
- Target-version primitive documentation: `get`, `getresult`, `struct` in v241 docs.json + runtime getcommands
- Community/academic reference: none
