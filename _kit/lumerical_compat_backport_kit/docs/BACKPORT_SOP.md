# LSF Compatibility / Backport SOP

## 1. Purpose

This SOP governs any attempt to recreate a newer Lumerical feature using an older Lumerical product/version. The objective is semantic correctness, not merely generating syntactically valid LSF.

## 2. Fundamental distinction

- **Syntax translation:** translating expressions/constructs while preserving language-level behavior.
- **API adaptation:** preserving a feature while changing the interface or input representation.
- **Algorithmic backport:** implementing a newer capability using older primitives.
- **Approximate substitute:** providing a related calculation that does not preserve the complete feature contract.

Do not label all four as “translation” or “equivalent implementation.”

## 3. Mandatory workflow

### Step 1 — Identify the target precisely

Record:
- Lumerical product (not just “Lumerical”).
- Solver/module (FDTD, MODE, DGTD, FEEM, etc.).
- Exact release and update (e.g. distinguish `2024 R1` from `2024 R1.1`).
- Build number if available.
- Script execution context (Script Prompt, Script File Editor, Analysis Group setup/analysis script, object-specific context, Python API, etc.).

### Step 2 — Write the new-feature contract

Use official docs, command reference, release notes, examples and, where necessary, known algorithms/papers.

The contract must state:
- Purpose and mathematical/physical definition.
- Input names, types, shapes, ordering, coordinate axes and units.
- Accepted real/complex values and data structures.
- Default arguments and optional parameters.
- Output shape/type/column or attribute meaning.
- Normalization, sign/conjugation and orientation conventions.
- Boundary/empty/NaN/Inf behavior and error behavior.
- Side effects and execution-context restrictions.
- Product/solver availability and version history.
- What is explicitly unknown.

Do not infer semantics from a command name.

### Step 3 — Establish actual target capabilities

Use target product's `?getcommands;` output as one evidence source. It lists commands available in the current script workspace. Also test:
- Language syntax/keywords independently.
- Function or command signature.
- Supported data types and shapes.
- Context restrictions.
- Relevant side effects.

Keep documentation evidence separate from runtime evidence. A missing `docs.json` row is `unknown`, not `absent`.

### Step 4 — Search before reimplementing

Search in this order:
1. Exact native command in the target product/update.
2. Older native command with equivalent semantics.
3. Official alternate workflow or Analysis Group implementation.
4. Parameter/data adapter that exposes an existing capability.
5. Algorithm assembled from target-version primitives.
6. Approximate substitute, clearly labelled.

Prefer native command or parameter adapter over custom algorithm. Do not recreate a command that already exists in the target environment.

### Step 5 — Build a constrained implementation

Declare:
- Preconditions and supported input domain.
- Required primitive dependencies.
- Algorithm and invariants.
- Output contract.
- Error/empty-input policy.
- Side effects and variable scope.
- Known limitations and unsupported cases.

Avoid hidden global-state assumptions. If target LSF lacks functions or a desired construct, use only a tested alternative (e.g. inline script block or a supported loop construct). Do not assume language features based on current documentation alone.

### Step 6 — Validate

Use the test levels below. Keep all raw outputs and target environment facts. A static whitelist check does not prove runtime behavior or algorithm correctness.

## 4. Semantic-preservation obligations

For a requested new feature `F` and proposed old implementation `G`, define an input domain `D` and observable contract `Obs`.

The target is:

`for all x in D: Obs(F(x)) == Obs(G(x))`

For floating-point numerical operations, define an explicit error policy such as:

`abs(F(x)-G(x)) <= abs_tol + rel_tol * abs(F(x))`

This is not sufficient by itself for a physical operation. Also compare units, coordinate conventions, normalization, result structure, errors and side effects.

Every backport must explicitly define `D`. Without a bounded input domain and full observable contract, universal equivalence cannot be claimed.

### Obligations checklist

- [ ] Same mathematical/physical quantity.
- [ ] Same input interpretation and dimensionality.
- [ ] Same units and coordinate frame.
- [ ] Same complex conjugation and sign conventions.
- [ ] Same normalization and integration/summation domain.
- [ ] Same output schema and ordering (or documented adapter mapping).
- [ ] Same relevant edge/error behavior.
- [ ] Same relevant side effects and context requirements.
- [ ] Numeric tolerances defined before comparison.
- [ ] Unsupported conditions stated explicitly.

## 5. Verification levels

| Level | Name | Minimum evidence | What it does NOT prove |
|---|---|---|---|
| L0 | `unverified` | Proposed implementation and contract draft | Syntax, execution or correctness |
| L1 | `static_checked` | Dependency names and static syntax/pattern checks against captured target evidence | Runtime availability, signature, numerical correctness |
| L2 | `runtime_verified` | Executes in exact target product/solver/version for recorded cases | Equivalence outside tested cases |
| L3 | `differential_verified` | L2 + comparison against native/new reference over documented test domain, fixtures and tolerance | Universal correctness for all possible inputs |
| L4 | `equivalence_proven` | Formal proof for explicit domain and contract, with runtime assumptions checked | Behavior outside the proved domain or undocumented vendor behavior |

Only assign the highest level whose requirements are actually satisfied. Runtime tests require access to the specified Lumerical installation and appropriate license. Never fabricate them.

## 6. Equivalence labels

| Label | Meaning |
|---|---|
| `exact` | Same observable contract for the declared supported domain; no material missing outputs/behaviors |
| `domain_equivalent` | Equivalent only under explicitly stated preconditions/input domain |
| `approximate` | A related numerical/physical estimate; measurable or known differences remain |
| `partial` | Only a subset of the original feature contract is implemented |
| `unsupported` | No defensible old-version implementation identified |

The equivalence label and verification level are independent. A mathematically approximate algorithm may be L3-tested as an approximation without becoming exact.

## 7. Required test families

### A. Static / dependency checks
- Every command/builtin/operator/data type is in the exact target capability snapshot or separately justified.
- Keywords and grammar constructs have separate syntax probe evidence.
- No accidental calls to the newer command remain in code.
- No undocumented dependencies, hidden files, or external runtime are assumed.

### B. Unit and property tests
Choose tests based on function class:
- Empty and singleton input.
- Odd/even array lengths.
- Duplicates and ties.
- Monotonic and non-monotonic coordinates.
- Real and complex inputs.
- Row/column/matrix shapes.
- Boundary and out-of-range values.
- NaN/Inf where supported.
- Repeated runs and variable-name collisions.

### C. Differential tests
Run newer native feature `F` and old backport `G` against the same input fixtures. Compare:
- output structure and field names;
- numerical values with predeclared absolute/relative tolerances;
- ordering and matching of multiple outputs;
- errors/empty outcomes;
- side effects when observable.

### D. Physics / integration tests
Use analytical cases or trusted benchmark simulations. Record mesh, boundary conditions, source, monitor, time/frequency range and solver settings necessary to reproduce results.

### E. Formal reasoning
For algorithms such as sorting, document invariants (ordered output and preservation of multiset). For numerical algorithms, document mathematical assumptions and error bounds. Do not call a test suite a formal proof.

## 8. Function-class-specific cautions

### Sorting / median
- Match real/complex sorting semantics, ascending/descending order, matrix flattening/shape preservation, NaN handling, empty input and even/odd median behavior.
- Official Lumerical `sort` semantics include complex sort by magnitude then angle and linear-array sorting with output shape preserved. Check the target runtime before writing a replacement.

### Resonance analysis
- Distinguish time-domain harmonic inversion/filter diagonalization from frequency-domain peak/FWHM estimates.
- A peak/FWHM algorithm does not reproduce all `findresonances` outputs (decay constant, amplitude, phase and error estimate) and must not be named as an exact drop-in replacement.
- Define sampling, signal window, source turn-off, peak separation, noise and line-shape assumptions.

### Mode overlap / coupling
- Distinguish `modeoverlap`, `overlap`, field similarity and power-normalized electromagnetic coupling.
- A normalized E-field inner product is not automatically equivalent to the E×H power overlap calculation.
- Define field components, conjugation, direction/orientation, integration surface, mesh alignment/interpolation, material/normalization assumptions and units.
- Distinguish FEEM/DGTD `modeoverlap` support from FDTD/MODE `overlap` API extensions.

### JSON / serialization
- Define valid JSON grammar, escaping, Unicode, number formatting, null/boolean support, arrays/objects, nested structures, duplicate keys and round-trip expectations.
- String concatenation alone is not a JSON serializer unless escaping and all value types are handled correctly.

### GDS / geometry
- Verify layer/datatype, units, coordinate precision, hierarchy, paths, polygons, transforms, cell references and round-trip geometry.
- File import success alone does not prove geometry equivalence.

## 9. Recipe review checklist

Before a recipe can be marked L1 or above:
- [ ] Exact target product/solver/version identified.
- [ ] New-feature contract linked to official source(s).
- [ ] Target primitive evidence linked to runtime capability snapshot or official version docs.
- [ ] All dependencies enumerated.
- [ ] Preconditions/input domain documented.
- [ ] Output schema documented.
- [ ] Equivalence label justified.
- [ ] Verification level matches actual tests.
- [ ] Tests and reports linked by stable IDs.
- [ ] Known limitations are visible in both metadata and Markdown.
- [ ] Recipe name does not imply stronger equivalence than it has.
