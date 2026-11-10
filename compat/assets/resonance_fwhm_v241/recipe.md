# findresonances — 2024 R1 (v241) compatibility recipe

> **Implementation ID:** `compat.resonance_fwhm.v241.fwhm`
> **Target:** `Lumerical / shared / 2024 R1 (v241)`
> **Equivalence:** `approximate`
> **Verification:** `L1`
> **Status:** `static_checked`

> **READ FIRST — native command likely exists.** Release notes place `findresonances` at
> **2019a**, which predates 2024 R1. Its absence from the bundled v241 `docs.json` is a
> **documentation gap**, not proof of absence. At runtime, check `?getcommands;` and use the
> native command if present; this recipe is an **approximate substitute** (spectral
> peak/FWHM analysis), not a harmonic-inversion backport.

## Purpose

`findresonances` (newer releases) extracts resonance frequency, decay constant, Q, amplitude and
phase from a **time trace** using harmonic inversion. This recipe does **not** reproduce that
algorithm. It provides a bounded, clearly-labelled analysis on the v241 primitives: peak
detection on a spectral magnitude plus FWHM/Q estimation. It is useful when a spectrum is
available; it is not a drop-in replacement.

## New-version contract

- Official command: `findresonances` (Scripting Language, current KB).
- Input: time trace of a real or complex signal plus a frequency window `[f_min, f_max]`.
- Output: frequency, decay constant, Q-factor, amplitude, phase per resonance.
- Algorithm: harmonic inversion (filter-diagonalization style), not local peak picking.
- Source: https://optics.ansys.com/hc/en-us/articles/360034925953-findresonances-Script-command
- **Not available in `docs.json` of the v241 installation** — documented absence only, runtime
  presence unknown until a capability snapshot is captured.

## Target environment

- Product: Lumerical
- Solver: shared (target is the installation-wide command set; per-solver runtime not captured)
- Exact version/update: 2024 R1 (build label v241)
- Execution context: Script File Editor / Script Prompt
- Capability snapshot ID: *(none — runtime capture blocked, see validation)*

## Preconditions and supported domain

- `ds` must be a dataset (from `getresult`/`getsweepresult`) exposing `.lambda` and `.T`
  (or an equivalent 1-D magnitude spectrum).
- Spectrum magnitude must be real, positive and dominated by one Lorentzian-like response per
  resonance; strongly overlapping or Fano-shaped resonances invalidate the FWHM estimate.
- Only peaks above `prom_frac × max(T)` are reported.

## Dependencies

| Symbol | Type | Required | Target evidence | Notes |
|---|---|---:|---|---|
| `getresult` | dataset_api | yes | docs-json-v241 | fetch monitor result |
| `pinch` | command | yes | docs-json-v241 | flatten to 1-D |
| `abs` | command | yes | docs-json-v241 | magnitude |
| `max` | command | yes | docs-json-v241 | normalise |
| `length` | command | yes | docs-json-v241 | point count |
| `findpeaks` | command | yes | docs-json-v241 | peak positions |
| `matrix` | command | yes | docs-json-v241 | preallocate outputs |
| `num2str` | command | yes | docs-json-v241 | reporting |
| `if` / `for` / `break` | keyword | yes | docs-json-v241 (keyword list) | control flow |

## Algorithm

1. Flatten `lambda` and `|T|` to 1-D; normalise by `max(|T|)`.
2. `findpeaks(Tn, nmax)` → peak indices (v241 returns the largest peaks).
3. For each peak above the prominence threshold, scan left/right for the half-maximum bracket.
4. Linear two-point interpolation gives the half-maximum wavelengths `lamL`, `lamR`.
5. `FWHM = |lamR - lamL|`, `Q = lam0 / FWHM`.

Invariants: `FWHM >= 0`; `Q > 0` only when a half-maximum bracket exists on both sides.
Failure paths: a peak without brackets yields `FWHM = 0`, `Q = 0` (never NaN).

## Usage

Set `ds` (and optionally `nmax`, `prom_frac`), run the block, read `res_lambda`, `res_T`,
`res_FWHM`, `res_Q`. v241 has no user-defined functions, so this is an input→output block,
not a callable.

## LSF implementation

See the companion file `implementation.lsf` (complete, self-contained).

## Output contract

| Output | Type/shape | Unit | Meaning |
|---|---|---|---|
| `res_lambda` | 1×N matrix | m (wavelength) | peak centre |
| `res_T` | 1×N matrix | same as `ds.T` | peak magnitude |
| `res_FWHM` | 1×N matrix | m | −3 dB width from half-maximum |
| `res_Q` | 1×N matrix | 1 (dimensionless) | `lambda/FWHM` |

## Equivalence analysis

Matches: reporting resonance **positions** and a Q-like figure for isolated Lorentzian peaks.
Does not match: harmonic inversion accuracy, decay constant, amplitude/phase, robustness to
overlapping modes, and time-domain-only inputs. Therefore `approximate` substitute
(workaround class per the SOP — approximate substitute, labelled), not an exact/domain
backport.

## Limitations

- No decay constant / phase output.
- Requires a spectral dataset; cannot work from a raw time trace.
- Fails on overlapping resonances and on non-Lorentzian line shapes.
- `findpeaks(y,n)` returns the largest peaks; small resonances may be omitted.

## Validation evidence

| Test ID | Method | Target env | Expected | Actual | Error/tolerance | Result |
|---|---|---|---|---|---|---|
| `static.ids.v241` | static | docs.json (2024 R1) | every called symbol exists | all 11 symbols present | n/a | passed |
| `runtime.blocked.001` | runtime | 2024 R1 runtime | peak/Q within tolerance | not run (no license/runtime) | n/a | blocked |

`L1` only: static identifier check against the v241 `docs.json`. Runtime and differential
validation are **pending**; do not promote this level without target-runtime evidence.

## Sources

- Official new feature documentation: https://optics.ansys.com/hc/en-us/articles/360034925953-findresonances-Script-command
- Release note / introduction history: https://optics.ansys.com/hc/en-us/articles/1500008744061-2019a-Release-Notes (introduced 2019a — predates 2024 R1)
- Target-version primitive documentation: `<install>/api/python/docs.json` (2024 R1)
- Community/academic reference: none used
