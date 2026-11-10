# median — 2024 R1 (v241) compatibility recipe

> **Implementation ID:** `compat.median.sort.v241.exact`
> **Target:** `Lumerical / shared / 2024 R1 (v241, runtime build 8.31.3633)`
> **Equivalence:** `exact`
> **Verification:** `L1`
> **Status:** `static_checked`

> **Domain note.** Official `median` contract (current KB): median of a **real-valued**
> matrix; a warning is emitted when the input is not a vector (element order undefined for
> matrices). This recipe implements the documented domain — **real vectors** — where the
> conversion is exact. For non-vector matrices the official command itself has undefined
> element ordering, so `median` there is only well-defined after a flatten; users needing
> matrix medians must state their ordering explicitly.

## Purpose

Provide `median` on 2024 R1, where the runtime capture proves it is **absent**
(not in the 606-symbol getcommands list; direct invocation fails), while `sort` **is native**
(runtime probe `sort([3,1,2]) -> [1,2,3]` passed). Median = middle of the sorted values.

## New-version contract

- Official page: https://optics.ansys.com/hc/en-us/articles/360034926513-median-Script-command
- `out = median(A)` — median of the real-valued matrix `A`; warning if `A` is not a vector.
- Semantics on a sorted vector `x(1..n)`:
  - odd `n`: `x((n+1)/2)`
  - even `n`: `(x(n/2) + x(n/2+1)) / 2`
- Introduced in a release **after** 2024 R1 (absence consistent with docs and runtime).

## Target environment

- Product: Lumerical; Solver: shared
- Exact version: 2024 R1 (build 8.31.3633, school capture)
- Execution context: Script File Editor / Script Prompt / lumapi eval
- Capability snapshot: `snapshot.lumerical-2024r1-school.20261110T182355Z`

## Preconditions and supported domain

- Input `xv` is a **real, finite** vector (no NaN/Inf — sorting with NaN is undefined).
- Complex inputs are outside the documented `median` domain (page says real-valued); do not
  use this recipe for them.

## Dependencies

| Symbol | Type | Required | Target evidence | Notes |
|---|---|---:|---|---|
| `pinch` | command | yes | runtime getcommands (606) | flatten to 1-D |
| `sort` | command | yes | runtime probe passed | ascending order |
| `length` | command | yes | runtime getcommands | n |
| `mod` | command | yes | docs.json (2024 R1) | parity test |
| `if` / `else` | keyword | yes | runtime probes passed | parity branch |

## Algorithm

1. Flatten with `pinch`, sort ascending with native `sort`.
2. Odd `n`: middle element; even `n`: mean of the two middle elements.

Invariants: result lies between `min` and `max` of the input; equals an input element for
odd `n`. Complexity O(n log n) (native sort).

## Usage

Set `xv`, run the block, read `med`. Not a callable: v241 has no user functions
(runtime probe evidence), so this is an input→output block.

## LSF implementation

See the companion file `implementation.lsf` (complete, self-contained).

## Output contract

| Output | Type/shape | Unit | Meaning |
|---|---|---|---|
| `med` | scalar | same as input | median of `xv` |

## Equivalence analysis

On the documented domain (real vectors), this is **exact**: both produce the order
statistic of the same sorted sequence, with identical odd/even rules. Outside that domain
(complex, matrices without explicit ordering, NaN) the official command is documented as
warned/undefined, so equivalence is not claimed.

## Limitations

- Real vectors only (official domain).
- Even-length tie-breaking is identical arithmetic, so no ambiguity.
- Non-finite inputs unsupported (matches upstream undefined behavior rather than emulating it).

## Validation evidence

| Test ID | Method | Target env | Expected | Actual | Error/tolerance | Result |
|---|---|---|---|---|---|---|
| `static.ids.v241.median` | static | docs.json + runtime capture | all dependencies present | all present | n/a | passed |
| `runtime.blocked.median.001` | runtime | 2024 R1 (8.31.3633) | `median` fixtures vs reference values | pending session | n/a | blocked |

Runtime protocol (ready to run in any licensed session): fixtures
`[1,2,4] -> 2`, `[1,2,3,4] -> 2.5`, singleton `[7] -> 7`, unordered `[-3,5,-1] -> -1`,
then compare against the expected order statistics above (exact equality; floats exact).
Differential reference is the arithmetic definition itself, so an exact-equality pass
justifies promoting to **L2** (runtime_verified) with zero tolerance.

## Sources

- Official new feature documentation: https://optics.ansys.com/hc/en-us/articles/360034926513-median-Script-command
- Release note / introduction history: introduction release not established (unknown); absence at 2024 R1 proven by runtime capture
- Target-version primitive documentation: `sort`, `pinch`, `mod` in v241 docs.json + runtime getcommands
- Community/academic reference: none needed (order-statistic definition)
