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
