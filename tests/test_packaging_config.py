from __future__ import annotations

from importlib import metadata
from pathlib import Path
from typing import Any

import pytest

tomllib: Any
try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    tomllib = None


ROOT = Path(__file__).resolve().parents[1]


pytestmark = pytest.mark.skipif(
    tomllib is None,
    reason="tomllib is required to inspect pyproject.toml",
)


def _pyproject() -> dict:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def _requirements(path: Path) -> list[str]:
    requirements: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if value and not value.startswith("#"):
            requirements.append(value)
    return requirements


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_requirements_txt_mirrors_runtime_dependencies() -> None:
    project = _pyproject()["project"]

    assert sorted(_requirements(ROOT / "requirements.txt")) == sorted(
        project["dependencies"]
    )


def test_requirements_dev_delegates_to_dev_extra() -> None:
    assert _requirements(ROOT / "requirements-dev.txt") == ["-e .[dev]"]


def test_pyomo_extra_defines_optional_solver_stack_only() -> None:
    project = _pyproject()["project"]
    optional = project["optional-dependencies"]

    assert optional["pyomo"] == ["pyomo", "idaes-pse"]
    assert "pyomo" not in project["dependencies"]
    assert "idaes-pse" not in project["dependencies"]
    assert _requirements(ROOT / "requirements-dev.txt") == ["-e .[dev]"]


def test_pytest_configuration_has_single_source() -> None:
    config = _pyproject()["tool"]["pytest"]["ini_options"]

    assert not (ROOT / "pytest.ini").exists()
    assert config["testpaths"] == ["tests"]
    assert "--strict-markers" in config["addopts"]
    assert "--disable-warnings" not in config["addopts"]
    assert "--dist=loadgroup" not in config["addopts"]
    assert config["filterwarnings"] == ["default"]
    assert any(marker.startswith("pyomo:") for marker in config["markers"])


def test_required_test_lane_markers_have_policy_descriptions() -> None:
    config = _pyproject()["tool"]["pytest"]["ini_options"]
    markers = {marker.split(":", maxsplit=1)[0]: marker for marker in config["markers"]}

    assert "fast PR lane" in markers["slow"]
    assert "notebook lane" in markers["notebook"]
    assert "Optional future Pyomo/IPOPT" in markers["pyomo"]
    assert "-n 0" in markers["serial"]
    assert "high-level API" in markers["main"]


def test_static_tooling_configuration_is_staged_and_scoped() -> None:
    config = _pyproject()["tool"]
    ruff = config["ruff"]
    mypy = config["mypy"]

    assert ruff["lint"]["select"] == ["F"]
    assert ruff["target-version"] == "py38"
    assert sorted(ruff["lint"]["per-file-ignores"]) == [
        "examples/legacy/ex_knownRp_PD.py",
        "examples/legacy/ex_unknownRp_PD.py",
    ]

    assert mypy["files"] == ["lyopronto"]
    assert mypy["python_version"] == "3.9"
    assert "ignore_errors" not in mypy
    assert "ignore_missing_imports" not in mypy
    assert any(
        override["module"] == ["scipy", "scipy.*"]
        and override["ignore_missing_imports"] is True
        for override in mypy["overrides"]
    )


def test_ci_workflows_use_documented_test_lane_expressions() -> None:
    pr_tests = _text(".github/workflows/pr-tests.yml")
    main_tests = _text(".github/workflows/tests.yml")
    manual_tests = _text(".github/workflows/slow-tests.yml")
    notebook_tests = _text(".github/workflows/rundocs.yml")

    assert (
        'pytest tests/ -n auto -v -m "not slow and not notebook and not pyomo"'
        in pr_tests
    )
    assert 'pytest tests/ -n auto -v -m "not pyomo" --cov=lyopronto' in pr_tests
    assert "github.event.pull_request.draft == false" in pr_tests
    assert 'pytest tests/ -n auto -v -m "not pyomo" --cov=lyopronto' in main_tests
    assert "pip install pyomo" not in pr_tests
    assert "pip install pyomo" not in main_tests
    assert "python -m ruff check lyopronto tests examples main.py" in pr_tests
    assert "python -m ruff check lyopronto tests examples main.py" in main_tests
    assert "python -m mypy lyopronto" in pr_tests
    assert "python -m mypy lyopronto" in main_tests
    assert "continue-on-error: true" in pr_tests
    assert "continue-on-error: true" in main_tests

    assert (
        'pytest tests/ -n auto -v -m "slow and not pyomo" --cov=lyopronto'
        in manual_tests
    )
    assert 'pytest tests/ -n auto -v -m "pyomo" --cov=lyopronto' in manual_tests
    assert 'rc" -eq 5' in manual_tests
    assert 'pip install -e ".[dev,pyomo]"' in manual_tests
    assert "idaes get-extensions --extra petsc" in manual_tests
    assert "pip install pyomo idaes-pse" not in manual_tests
    assert "RUN_SLOW_TESTS" not in manual_tests

    assert 'pytest tests/ -n auto -v -m "notebook" --cov=lyopronto' in notebook_tests
    assert "github.event.pull_request.draft == false" in notebook_tests


def test_local_ci_script_matches_documented_lane_expressions() -> None:
    script = _text("run_local_ci.sh")

    assert 'FAST_EXPR="not slow and not notebook and not pyomo"' in script
    assert 'FULL_EXPR="not pyomo"' in script
    assert 'SLOW_EXPR="slow and not pyomo"' in script
    assert 'NOTEBOOK_EXPR="notebook"' in script
    assert 'PYOMO_EXPR="pyomo"' in script
    assert 'pip install -e ".[dev,pyomo]"' in script
    assert "idaes get-extensions --extra petsc" in script
    assert "pip install pyomo idaes-pse" not in script
    assert "run_pytest_allow_empty" in script
    assert "SKIP_INSTALL=1" in script


def test_contributor_docs_include_ci_and_static_analysis_commands() -> None:
    docs = "\n".join(
        [
            _text("tests/README.md"),
            _text("CONTRIBUTING.md"),
            _text("docs/CI_WORKFLOW_GUIDE.md"),
            _text("docs/CI_SETUP.md"),
            _text("docs/CI_QUICK_REFERENCE.md"),
            _text("docs/JULIA_PARITY_MATRIX.md"),
        ]
    )

    assert (
        'pytest tests/ -n auto -v -m "not slow and not notebook and not pyomo"' in docs
    )
    assert 'pytest tests/ -n auto -v -m "not pyomo" --cov=lyopronto' in docs
    assert "Ruff linting" in docs
    assert "python -m ruff check lyopronto tests examples main.py" in docs
    assert "python -m mypy lyopronto" in docs
    assert "mypy is advisory" in docs
    assert "Ruff formatting and linting are documented local checks" not in docs
    assert "not active CI gates" not in docs
    assert "do not enforce" not in docs
    assert "dedicated CI decision is pending" not in docs
    assert "Warning Policy" in docs
    assert "pytest.warns" in docs
    assert "--disable-warnings" in docs
    assert 'python -m pip install -e ".[dev,pyomo]"' in docs
    assert "idaes get-extensions --extra petsc" in docs
    assert "conda install -c conda-forge ipopt" in docs


def test_legacy_setup_py_metadata_removed() -> None:
    assert not (ROOT / "setup.py").exists()


def test_installed_distribution_version_matches_pyproject() -> None:
    project = _pyproject()["project"]

    try:
        installed_version = metadata.version(project["name"])
    except metadata.PackageNotFoundError:
        pytest.skip("lyopronto distribution is not installed")

    assert installed_version == project["version"]
