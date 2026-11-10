# adddftmonitor — 2024 R1 (v241) compatibility recipe

> **Implementation ID:** `compat.adddftmonitor.v241.adapter`
> **Target:** `Lumerical / FDTD / 2024 R1 (v241, runtime 8.31.3633)`
> **Equivalence:** `domain_equivalent`
> **Verification:** `L2`
> **Status:** `runtime_verified`

## Purpose

`adddftmonitor` (newer releases) adds a frequency-domain field-profile monitor in one call.
This recipe is an **API adapter**: on 2024 R1 the identical capability exists through
`addpower` (or `addprofile`) — the DFT over the simulation window is what those monitors
already do. The adapter maps the new command's arguments onto the v241 properties.

## New-version contract

- `adddftmonitor;` — add a frequency-domain field profile monitor (defaults).
- `adddftmonitor(struct_data);` — add and set properties from a struct.
- Source: current KB, `adddftmonitor - Script command`.

## Target environment

- Product: Lumerical; Solver: **FDTD**
- Exact version: 2024 R1 (build 8.31.3633, school capture)
- Capability snapshot: `snapshot.lumerical-2024r1-school.20261110T182355Z`

## Preconditions and supported domain

- v241 FDTD only (the adapter targets the FDTD solver; other solvers keep native commands).
- `struct_data` keys map 1:1 to v241 monitor property names (see table); unknown keys are
  ignored with a console note rather than erroring.

## Dependencies

| Symbol | Type | Required | Target evidence | Notes |
|---|---|---:|---|---|
| `addpower` | command | yes | runtime getcommands (606) | freq-domain field monitor |
| `set` | command | yes | runtime getcommands | property mapping |
| `struct` | builtin_function | yes | runtime getcommands | struct_data input |

## Algorithm

Property mapping (new name → v241 property):

| new / struct key | v241 property | notes |
|---|---|---|
| (position) | `x, y, z, x span, y span, z span` | identical |
| `frequency points` | `frequency points` | identical |
| `spatial interpolation` | `spatial interpolation` | identical |
| `output power` | (n/a) | v241 field monitors always store fields |
| type selection | `monitor type` | 2D Z-normal etc., same enum |

## Usage

Set `struct_data` (may be an empty struct), run the block. The monitor is added and
selected; property errors are reported, never fatal.

## LSF implementation

See the companion file `implementation.lsf`.

## Output contract

| Output | Type/shape | Unit | Meaning |
|---|---|---|---|
| (object) | FDTD object | — | freq-domain monitor named per input |

## Equivalence analysis

`domain_equivalent`: the monitor object produced is the same v241 object the newer command
creates (both are DFT-over-window field monitors); only the entry-point name and struct
interface differ. Not `exact` because the newer struct keys are accepted more permissively
than this mapping.

## Limitations

- FDTD solver only.
- Struct keys not in the mapping table are skipped (v241 has no dynamic property set).

## Validation evidence

| Test ID | Method | Target env | Expected | Actual | Error/tolerance | Result |
|---|---|---|---|---|---|---|
| `runtime.adapter.dftmon.001` | runtime | 2024 R1 (8.31.3633) | monitor added, type/fields readable, data after run | see `compat/assets/adddftmonitor_v241/adapter_results.json` | exact property match | passed |

## Sources

- Official new feature documentation: `adddftmonitor - Script command` (current KB)
- Release note / introduction history: introduction release not established (unknown)
- Target-version primitive documentation: `addpower`, `set` in v241 docs.json + runtime getcommands
- Community/academic reference: none
