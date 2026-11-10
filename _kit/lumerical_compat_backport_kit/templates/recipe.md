# <Feature> — <target version> compatibility recipe

> **Implementation ID:** `<implementation_id>`  
> **Target:** `<product> / <solver> / <exact version + update>`  
> **Equivalence:** `exact | domain_equivalent | approximate | partial | unsupported`  
> **Verification:** `L0 | L1 | L2 | L3 | L4`  
> **Status:** `draft | candidate | static_checked | runtime_verified | differential_verified | proven | blocked`

## Purpose

Describe what this implements and which newer feature/API it relates to.

## New-version contract

State the official algorithm/semantics, parameters, input/output schemas, units, defaults, data dimensions, error behavior and relevant side effects. Link authoritative documentation and release notes.

## Target environment

- Product:
- Solver:
- Exact version/update:
- Build:
- Execution context:
- Capability snapshot ID:

## Preconditions and supported domain

List all assumptions and input restrictions. Do not omit restrictions that make a numerical approximation valid.

## Dependencies

| Symbol | Type | Required | Target evidence | Notes |
|---|---|---:|---|---|
| `<name>` | command/keyword/operator/builtin/data type | yes/no | snapshot/probe/source ID | |

## Algorithm

Explain the calculation, invariants, coordinate conventions, normalization, numeric precision and failure paths.

## Usage

List required input variables and the expected output variables. Avoid claiming the snippet is a callable function if target LSF/context does not support it.

## LSF implementation

```lsf
# Insert the complete implementation or link to the exact companion .lsf file.
```

## Output contract

| Output | Type/shape | Unit | Meaning |
|---|---|---|---|
| | | | |

## Equivalence analysis

Explain precisely which observable behaviors match and which do not. State the supported input domain.

## Limitations

- 

## Validation evidence

| Test ID | Method | Target env | Expected | Actual | Error/tolerance | Result |
|---|---|---|---|---|---|---|
| | | | | | | |

Do not raise verification level without evidence from the exact target environment.

## Sources

- Official new feature documentation:
- Release note / introduction history:
- Target-version primitive documentation:
- Community or academic reference (if any):
