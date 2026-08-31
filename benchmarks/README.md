# Benchmark Artifacts

`benchmarks/results/` contains a small set of tracked reference artifacts plus
locally generated benchmark outputs. Local benchmark runs can produce JSONL,
CSV, PNG, and processed summary files; those generated outputs are ignored by
default so they do not get committed accidentally.

## Tracked Reference Results

The following paths are intentionally version controlled because they are
reference artifacts used for development, testing, or documentation:

- `benchmarks/results/archive/*.jsonl`
- `benchmarks/results/archive/*.png`
- `benchmarks/results/both_ramp_test/`
- `benchmarks/results/both_test/`
- `benchmarks/results/debug_fd/`
- `benchmarks/results/pch_test/`
- `benchmarks/results/test/`
- `benchmarks/results/test_validation/`

## Application-Wide POUNCE Comparison

POUNCE 0.10.0 is exercised through the same Pyomo `ipopt` AMPL/ASL interface
as IPOPT, with only the executable changed. This keeps model generation,
solver options, result loading, and the scientific assertions identical. Run
the complete comparison locally with the same command used by the automatic
Pyomo-sensitive PR job:

```bash
sudo apt-get install glpk-utils
./run_local_ci.sh pounce
```

The `pounce` extra pins both `pounce-solver` and `pyomo-pounce` to 0.10.0 so a
later release cannot silently change the result. The lane covers the
single-step and fixed-trajectory models; known-Rp replay, the unknown-Rp hybrid
fit, and simultaneous synthetic Rp/Kv parameter estimation; fixed-horizon
pressure, shelf-temperature, and joint optimization; both DAE discretizations
for all three controls; rate limits; shadow prices; sensitivity and robust
optimization; design-space feasibility and multi-vial optimization; and the
solver-backed notebooks. The scientific results agree with IPOPT across that
matrix.

This is a correctness comparison, not a speed benchmark. Pytest durations mix
model construction, SciPy references, and notebook kernels with NLP time, so
they are not reported as solver timings.

## Migrated: Pseudosteady-Limit Solver Baselines

The paper-reference pseudosteady-limit continuation study, its recorded
IPOPT/POUNCE baselines (`pseudosteady_limit/`), and their regeneration and
scaling-method guidance migrated to
[SECQUOIA/LyoGDP-Benchmarks](https://github.com/SECQUOIA/LyoGDP-Benchmarks)
(issue #150). Regenerate or extend those baselines there.

Do not add new benchmark reference data by dropping files into an ignored local
run directory. If a new benchmark artifact needs to become a repository
reference, keep it small, document why it is needed, and update `.gitignore`
only for the exact reference path or directory being added.

## Local Regeneration

Run benchmark commands from the repository root and write new outputs under a
new run name in `benchmarks/results/`, for example
`benchmarks/results/<case-name>/` or `benchmarks/results/<case-name>.jsonl`.
Those paths are ignored by default.

Before opening a PR, check:

```bash
git status --short
git status --ignored --short benchmarks/results/
```

The first command should not list local benchmark outputs. The second command
can be used to confirm that regenerated outputs are ignored.
