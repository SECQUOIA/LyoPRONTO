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

We keep `constr_viol_tol=1e-6`, because it is the right tolerance for this model
and the coupling was the defect. The table above therefore stays as measured on
the installable release, and doubles as the regression check for when #519
ships.

Use `--nlp-scaling` to vary it, and read `nlp_scaling_method` in each recorded
file to see which value produced it. Do not treat a solver's ladder length as a
property of the solver alone without checking that field.

Only the IPOPT baseline is committed. The study runs against any
AMPL-convention solver through `--solver-executable`, but a recorded
non-IPOPT baseline needs the trade-off above stated beside it to be read
correctly. A POUNCE baseline also needs a tagged release to pin rather than a
local build of `main`, which is what currently carries the fix. Those belong
with the wider solver-comparison work rather than here.

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
