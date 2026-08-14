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
- `benchmarks/results/pseudosteady_limit/`

## Application-Wide POUNCE Comparison

POUNCE 0.10.0 is exercised through the same Pyomo `ipopt` AMPL/ASL interface
as IPOPT, with only the executable changed. This keeps model generation,
solver options, result loading, and the scientific assertions identical. Run
the complete comparison locally with:

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
optimization; both paper OCPs; GDP nonlinear subproblems; design-space
feasibility and multi-vial optimization; and all six solver-backed notebooks.

The scientific results agree with IPOPT across that matrix. Two differences
remain deliberately visible:

- POUNCE maps `SolvedToAcceptableLevel` to Pyomo status `warning`, where IPOPT
  reports `ok`; both report termination `optimal` and the same
  `accepted_at_acceptable_tol` quality. Paper-OCP tests therefore assert the
  termination and convergence quality rather than one binary's status field.
- On the nonconvex Problem 2 GDP, both neutral starts recover policy order
  `3 -> 1 -> 2` and feasible trajectories, but one POUNCE subproblem exits
  `SolveSucceeded` 25.10 s above the IPOPT objective. This is not a second
  stable local point: restarting the identical fixed-policy NLP with POUNCE
  twice reaches IPOPT's objective and switch times. The initialization-
  invariance assertion is therefore a strict expected failure linked to
  [POUNCE #592](https://github.com/jkitchin/pounce/issues/592), so an upstream
  fix becomes an actionable XPASS.

This is a correctness comparison, not a speed benchmark. Pytest durations mix
model construction, SciPy references, notebook kernels, and GDP master solves
with NLP time, so they are not reported as solver timings.

## Pseudosteady-Limit Solver Baselines

`benchmarks/results/pseudosteady_limit/` holds one JSON file per NLP solver for
the continuation in `examples/pseudosteady_limit_study.py`. Each file records,
for every rung of the heat-capacity ladder, the drying-time endpoint, the
maximum product temperature, the termination condition, the solver status, and
the convergence quality, plus the rung where the ladder stopped.

`convergence_quality` is what separates a rung that met `tol` from one accepted
at `acceptable_tol`; Pyomo reports both as `optimal`, so the termination
condition cannot. Every converged rung of the IPOPT baseline reads
`accepted_at_acceptable_tol`. That is the expected outcome for this
Landau-coordinate transcription rather than a degraded solve — see
`paper_ocp`'s module docstring for the mechanism and for the remedies that were
measured and rejected — but it is not something a reader should have to infer
from the raw solver message. Comparing solvers on this field is why it is
matched against IPOPT's status vocabulary rather than one binary's wording:
POUNCE writes the same statuses as enum names, so both sides classify through
one path (issue #146).

These are tracked rather than ignored because the failing rungs are the point.
The study walks from the paper's transient frozen-region model toward the
pseudosteady formulation, and the lower rungs are progressively stiffer NLPs
that sit past what the current solver stack handles. A solver comparison needs
to know both where a solver agrees and where it gives out, so a baseline that
recorded only the successes would be useless for the comparison it exists to
support.

Regenerate a baseline when the models change, when the solver or its version
changes, or when adding a solver:

```bash
python -m examples.pseudosteady_limit_study \
    --output benchmarks/results/pseudosteady_limit/ipopt.json
```

To compare another solver without committing its baseline:

```bash
python -m examples.pseudosteady_limit_study --solver-executable /path/to/pounce
```

The tracked POUNCE baseline was generated with the pinned release:

```bash
python -m examples.pseudosteady_limit_study \
    --solver-executable "$(command -v pounce)" \
    --output benchmarks/results/pseudosteady_limit/pounce.json
```

### The scaling method is a parameter, not a constant

`nlp_scaling_method` materially changes these results, and no single value is
best for every solver and instance. Measured at `n_z=20, nfe=36, ncp=3`:

| | IPOPT 3.14.16, Problem 1 ladder | POUNCE 0.9.0, `f=1` cold start | POUNCE 0.9.0, `f=0.2` warm started |
| --- | --- | --- | --- |
| `none` | 3 converged rungs | solves | local infeasibility |
| `gradient-based` (default) | **6 converged rungs** | local infeasibility | **solves, 33 iters** |

The default is the solver default for both binaries and is what the recorded
baseline uses, because it is much better for the reference solver and matches
what upstream recommends for this residual regime (jkitchin/pounce#505). Against
POUNCE 0.9.0 it is not uniformly better: it costs the first rung of the
cold-started ladder while winning the warm-started instance.

That POUNCE column is a property of the 0.9.0 *release*, not of the solver.
The `f=1` failure was a defect, reported as jkitchin/pounce#505 and fixed
upstream by jkitchin/pounce#519: a rapid-infeasibility detector with no IPOPT
counterpart armed at `infeas_viol_kappa * constr_viol_tol`, so the
`constr_viol_tol=1e-6` that `paper_ocp` sets dragged its floor inside the
acceptable band and a tighter feasibility tolerance produced an infeasibility
verdict. Built from `main` at `880b360`, POUNCE walks the whole ladder and
matches the IPOPT baseline rung for rung -- every shared endpoint agreeing to
better than 1e-4 h, and the same -0.622% / -0.080% shifts -- where 0.9.0 stops
at the first rung.

The 0.10.0 release contains that fix and now reaches every shared successful
rung through `f=0.05`. Its endpoints differ from IPOPT by at most 1.7e-5 h and
its maximum product temperatures by at most 2e-6 K there. It still reports
Problem 1 `f=0.02` infeasible, while IPOPT converges at that rung and stops at
`f=0.01`; both solvers stop at Problem 2 `f=0.02`. The committed baselines and
`tests/test_pounce_solver_comparison.py` pin both the agreement and that
remaining boundary instead of turning it into a migration verdict.

We keep `constr_viol_tol=1e-6`, because it is the right tolerance for this model
and the coupling was the defect. The table above remains the historical 0.9.0
measurement; the tracked 0.10.0 baseline records what the released fix actually
does on this model.

Use `--nlp-scaling` to vary it, and read `nlp_scaling_method` in each recorded
file to see which value produced it. Do not treat a solver's ladder length as a
property of the solver alone without checking that field.

The IPOPT 3.14.16 and POUNCE 0.10.0 baselines are both committed. The study
runs against any AMPL-convention solver through `--solver-executable`, but a
new baseline still needs a tagged release and its observed convergence boundary
stated beside it before it becomes a repository reference.

Each file records the solver provenance itself: the Pyomo interface used, the
solver identity, and the solver version from `opt.version()`. The interface and
the identity are different things, because a POUNCE run is driven through the
`ipopt` ASL interface and would otherwise be indistinguishable from an IPOPT
run. Executable paths are reduced to a basename so committed artifacts carry no
host-specific paths.

Do not widen the ladder or relax the iteration budget to make a rung converge:
where it stops is the measurement, and it is a property of the solver version as
much as of the model.

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
