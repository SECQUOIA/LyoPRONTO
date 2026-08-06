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
maximum product temperature, the termination condition, and the solver status,
plus the rung where the ladder stopped.

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
python -m examples.pseudosteady_limit_study \
    --solver-executable /path/to/pounce \
    --output benchmarks/results/pseudosteady_limit/pounce.json
```

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
