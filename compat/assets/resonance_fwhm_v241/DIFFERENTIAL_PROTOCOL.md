# Differential validation protocol for compat.resonance_fwhm.v241.fwhm
# (this file is the test harness source; results go to test-report JSON files)

Three independent references, in decreasing independence:

R1. Analytic truth (no Lumerical needed)
    Feed the recipe a synthetic spectrum: T(f) = sum of Lorentzians with KNOWN centre
    f0 and Q. For a Lorentzian, FWHM_f = f0/Q exactly, so the recipe's FWHM estimate must
    converge to f0/Q as sampling gets dense. Fixture set (wavelength domain, c=299792458):
      - single Lorentzian, lambda0=1550nm, Q=500  -> expect lambda0/Q in wavelength? NO:
        Q = lambda/FWHM_lambda holds for wavelength-domain FWHM when FWHM << lambda.
        Fixture asserts |Q_recipe - 500| / 500 <= tol with tol from sampling density.
    Tolerances must be DECLARED from the sample count BEFORE running:
      tol_abs = 0, tol_rel = 2 * (dlambda / FWHM)   (two bracket points' quantisation)
    This is a property-based check, not equivalence to native.

R2. Community 2012 official Q-analysis script (same target behaviour, older version)
    https://github.com/Niccolo-Marcucci/Lumerical-Objects/blob/master/Qanalysis-analysis_script.lsf
    (c) 2012 Lumerical Solutions Inc. It computes Q from the DECAY SLOPE of a Gaussian-
    filtered inverse FFT (40-60% time window), with error estimate delta_Q. It ALSO
    computes an FWHM internally (its own half-maximum bracket scan, lines "find FWHM of
    peak"). Differential check: on the SAME synthetic time signal, recipe Q (FWHM method)
    vs Qanalysis Q (slope method) must agree within the FWHM method's declared tolerance,
    and both within R1 truth. If the slope method is closer to truth, that gap IS the
    documented approximation error of the FWHM approach (goes into limitations, not hidden).

R3. Native findresonances on 2024 R1 (runtime, script-math only - no simulation license use)
    findresonances is PRESENT at 2024 R1 (runtime capture). Generate the same synthetic
    time signal in-script, run native findresonances(time_signal, f_min, f_max) and the
    recipe on its spectrum, compare f0 and Q. This is the true differential test against
    the native implementation. Expected outcome: f0 matches closely; recipe Q deviates by
    the FWHM-vs-harmonic-inversion gap, growing for overlapping/low-Q modes.

Protocol
--------
1. Build fixtures in-script (Lorentzian sum, analytic), no CAD objects needed.
2. Run R1 assertions with pre-declared tolerances.
3. Run R2 by ingesting the 2012 script as an analysis group / script and comparing.
4. Run R3 by calling native findresonances on the synthetic signal.
5. Record ALL raw outputs (fix: fixtures file + outputs file) in the validation report.

Status: harness authored 2026-11-10; execution pending a licensed 2024 R1 session
(current capture session closed). Do NOT mark passed without the raw output files.
