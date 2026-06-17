# Contributor Documentation

## Testing

To install test dependencies, run

```bash
python -m pip install -e ".[dev]"
```

inside the LyoPRONTO directory (next to `pyproject.toml`).

For fast PR-style feedback, execute

```bash
./run_local_ci.sh fast
```

which runs

```bash
pytest tests/ -n auto -v -m "not slow and not notebook and not pyomo"
```

Before marking a PR ready for review, run the full non-Pyomo lane when
practical:

```bash
./run_local_ci.sh full
```

which runs

```bash
pytest tests/ -n auto -v -m "not pyomo" --cov=lyopronto --cov-report=xml:coverage.xml --cov-report=term-missing
```

Notebook, slow, and optional Pyomo validation are separate lanes:
`./run_local_ci.sh notebook`, `./run_local_ci.sh slow`, and
`./run_local_ci.sh pyomo`.

## Documentation

Documentation build has different dependencies, installable by

```bash
python -m pip install -e ".[docs]"
```

Run a local build with:

```bash
mkdocs build
```

Preview locally with:

```bash
mkdocs serve
```

Docs publishing uses `mike` in `.github/workflows/docs.yml`. Pull requests
build a `pr-<number>` docs version, pushes to `main` deploy `dev`, and
published releases deploy the release version plus `latest`.

On the off chance that the documentation gets really broken, you can do the following to deploy a new version of it to GitHub Pages:

```bash
git fetch
git switch [branch with desired docs]
mike delete [broken docs version] # if necessary
mike deploy [new docs version] # if necessary
git switch gh-pages
git push origin gh-pages
```

### Helpful references for how to get documentation generated

https://realpython.com/python-project-documentation-with-mkdocs/ for a tutorial on MkDocs

https://entangled.github.io/mkdocs-plugin/setup/ because it would be nice to use for examples & tests

https://github.com/jimporter/mike?tab=readme-ov-file for versioning the docs


## Linting and formatting

Ruff linting is enforced in CI with the scoped Pyflakes rule set in
`pyproject.toml`:

```bash
python -m ruff check lyopronto tests examples main.py
```

mypy is advisory in CI while remaining project type issues are handled in
follow-up work:

```bash
python -m mypy lyopronto
```

Do not claim broad formatting enforcement unless a future workflow actually
enforces it.
