from __future__ import annotations

import configparser
import re
import shlex
from importlib import metadata
from pathlib import Path
from typing import Any, Optional

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


# CI lane parsers assume single-token shell vars and bare or backticked pytest commands.
def _shell_assignments(text: str) -> dict[str, str]:
    assignments = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        name, value = stripped.split("=", maxsplit=1)
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
            continue
        if value.startswith("$("):
            continue

        try:
            parsed = shlex.split(value)
        except ValueError:
            continue
        if len(parsed) == 1:
            assignments[name] = parsed[0]

    return assignments


def _local_ci_lane_expressions(script: str) -> dict[str, str]:
    assignments = _shell_assignments(script)
    return {
        "fast": assignments["FAST_EXPR"],
        "full": assignments["FULL_EXPR"],
        "slow": assignments["SLOW_EXPR"],
        "notebook": assignments["NOTEBOOK_EXPR"],
        "pyomo": assignments["PYOMO_EXPR"],
    }


def _pytest_command_strings(text: str) -> list[str]:
    commands = []
    for line in text.splitlines():
        commands.extend(re.findall(r"`([^`]*\bpytest\s+[^`]*)`", line))

        stripped = line.strip()
        if stripped.startswith("run_pytest_allow_empty pytest "):
            commands.append(stripped)
        elif stripped.startswith("pytest "):
            commands.append(stripped)

    return commands


def _pytest_commands(text: str) -> list[list[str]]:
    commands = []
    allow_empty_prefix = "run_pytest_allow_empty "
    for command_text in _pytest_command_strings(text):
        command_text = command_text.strip().rstrip("\\").strip()
        if command_text.startswith(allow_empty_prefix):
            command_text = command_text[len(allow_empty_prefix) :]

        try:
            commands.append(shlex.split(command_text))
        except ValueError:
            continue

    return commands


def _marker_expression(command: list[str]) -> Optional[str]:
    try:
        marker_index = command.index("-m")
    except ValueError:
        return None

    if marker_index + 1 >= len(command):
        return None
    return command[marker_index + 1]


def _commands_with_marker(text: str, marker_expression: str) -> list[list[str]]:
    return [
        command
        for command in _pytest_commands(text)
        if _marker_expression(command) == marker_expression
    ]


def _single_command_with_marker(text: str, marker_expression: str) -> list[str]:
    commands = _commands_with_marker(text, marker_expression)

    assert len(commands) == 1
    return commands[0]


def _commands_with_targets(text: str, targets: list[str]) -> list[list[str]]:
    return [
        command
        for command in _pytest_commands(text)
        if all(target in command for target in targets)
    ]


def _single_command_with_targets(text: str, targets: list[str]) -> list[str]:
    commands = _commands_with_targets(text, targets)

    assert len(commands) == 1
    return commands[0]


def _has_coverage(command: list[str]) -> bool:
    return any(
        argument == "--cov" or argument.startswith("--cov=") for argument in command
    )


def _has_non_pyomo_cov_config(command: list[str]) -> bool:
    return any(
        argument.startswith("--cov-config=")
        and (".coveragerc.non-pyomo" in argument or "$NON_PYOMO_COV_CONFIG" in argument)
        for argument in command
    )


def _assert_non_pyomo_coverage(command: list[str]) -> None:
    assert "--cov=lyopronto" in command
    assert _has_non_pyomo_cov_config(command)
    assert "--cov-report=term-missing" in command


def _assert_pyomo_coverage(command: list[str]) -> None:
    assert "--cov=lyopronto" in command
    assert not _has_non_pyomo_cov_config(command)
    assert "--cov-report=term-missing" in command


def _assert_no_coverage(command: list[str]) -> None:
    assert not _has_coverage(command)
    assert not _has_non_pyomo_cov_config(command)
    assert "--cov-report=term-missing" not in command


def _assert_marker_mentions(expression: str, marker: str) -> None:
    assert re.search(rf"\b{re.escape(marker)}\b", expression)


def _assert_marker_excludes(expression: str, marker: str) -> None:
    assert re.search(rf"\bnot\s+{re.escape(marker)}\b", expression)


def test_requirements_txt_mirrors_runtime_dependencies() -> None:
    project = _pyproject()["project"]

    assert sorted(_requirements(ROOT / "requirements.txt")) == sorted(project["dependencies"])


def test_requirements_dev_delegates_to_dev_extra() -> None:
    assert _requirements(ROOT / "requirements-dev.txt") == ["-e .[dev]"]


def test_pyomo_extra_defines_optional_solver_stack_only() -> None:
    project = _pyproject()["project"]
    optional = project["optional-dependencies"]

    assert optional["pyomo"] == ["pyomo>=6.7", "idaes-pse>=2.2"]
    assert "pyomo" not in project["dependencies"]
    assert "idaes-pse" not in project["dependencies"]
    assert _requirements(ROOT / "requirements-dev.txt") == ["-e .[dev]"]


def test_dev_extra_includes_test_diagnostics_plugins() -> None:
    project = _pyproject()["project"]
    dev_dependencies = project["optional-dependencies"]["dev"]

    assert "pytest-timeout>=2.2.0" in dev_dependencies
    assert any(dependency.startswith("pytest-xdist") for dependency in dev_dependencies)


def test_pytest_configuration_has_single_source() -> None:
    config = _pyproject()["tool"]["pytest"]["ini_options"]

    assert not (ROOT / "pytest.ini").exists()
    assert config["testpaths"] == ["tests"]
    assert "--strict-markers" in config["addopts"]
    assert "--durations=25" in config["addopts"]
    assert "--timeout=600" in config["addopts"]
    assert "--timeout-method=thread" in config["addopts"]
    assert "--disable-warnings" not in config["addopts"]
    assert "--dist=loadgroup" not in config["addopts"]
    assert config["filterwarnings"] == ["default"]
    assert any(marker.startswith("pyomo:") for marker in config["markers"])


def test_non_pyomo_coverage_config_omits_optional_pyomo_models() -> None:
    config = configparser.ConfigParser()
    path = ROOT / ".coveragerc.non-pyomo"

    assert config.read(str(path)) == [str(path)]
    omit = [value.strip() for value in config["run"]["omit"].splitlines() if value.strip()]

    assert omit == ["lyopronto/pyomo_models/*"]


def test_required_test_lane_markers_have_policy_descriptions() -> None:
    config = _pyproject()["tool"]["pytest"]["ini_options"]
    markers = {marker.split(":", maxsplit=1)[0]: marker for marker in config["markers"]}

    assert "fast PR lane" in markers["slow"]
    assert "notebook lane" in markers["notebook"]
    assert "Implemented optional Pyomo" in markers["pyomo"]
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
        override["module"] == ["scipy", "scipy.*"] and override["ignore_missing_imports"] is True
        for override in mypy["overrides"]
    )


def test_ci_workflows_use_documented_test_lane_expressions() -> None:
    script = _text("run_local_ci.sh")
    lane_expressions = _local_ci_lane_expressions(script)
    pyomo_light_targets = _shell_assignments(script)["PYOMO_LIGHT_TARGETS"].split()
    pr_tests = _text(".github/workflows/pr-tests.yml")
    main_tests = _text(".github/workflows/tests.yml")
    full_validation = _text(".github/workflows/full-validation.yml")
    manual_tests = _text(".github/workflows/slow-tests.yml")
    notebook_tests = _text(".github/workflows/rundocs.yml")
    pyomo_tests = _text(".github/workflows/pyomo-tests.yml")
    workflow_text = "\n".join(
        [
            pr_tests,
            main_tests,
            full_validation,
            manual_tests,
            notebook_tests,
            pyomo_tests,
        ]
    )
    fast_pr_command = _single_command_with_marker(pr_tests, lane_expressions["fast"])
    for marker in ["slow", "notebook", "pyomo"]:
        _assert_marker_excludes(lane_expressions["fast"], marker)
    _assert_no_coverage(fast_pr_command)
    assert not _commands_with_marker(pr_tests, lane_expressions["full"])

    full_non_pyomo_commands = (
        _commands_with_marker(main_tests, lane_expressions["full"])
        + _commands_with_marker(full_validation, lane_expressions["full"])
        + _commands_with_marker(manual_tests, lane_expressions["full"])
    )
    assert len(full_non_pyomo_commands) == 3
    _assert_marker_excludes(lane_expressions["full"], "pyomo")
    for command in full_non_pyomo_commands:
        _assert_non_pyomo_coverage(command)

    slow_command = _single_command_with_marker(manual_tests, lane_expressions["slow"])
    _assert_marker_mentions(lane_expressions["slow"], "slow")
    _assert_marker_excludes(lane_expressions["slow"], "pyomo")
    _assert_non_pyomo_coverage(slow_command)

    notebook_command = _single_command_with_marker(
        notebook_tests, lane_expressions["notebook"]
    )
    _assert_marker_mentions(lane_expressions["notebook"], "notebook")
    _assert_non_pyomo_coverage(notebook_command)

    manual_pyomo_command = _single_command_with_marker(
        manual_tests, lane_expressions["pyomo"]
    )
    _assert_marker_mentions(lane_expressions["pyomo"], "pyomo")
    _assert_pyomo_coverage(manual_pyomo_command)

    pyomo_light_command = _single_command_with_targets(pyomo_tests, pyomo_light_targets)
    _assert_no_coverage(pyomo_light_command)

    assert "codecov/codecov-action" not in pr_tests
    assert "pr-non-pyomo" not in pr_tests
    assert "full-non-pyomo:" not in pr_tests
    assert "full-validation" in full_validation
    assert "schedule:" in full_validation
    assert "tags:" in full_validation
    assert "lyopronto/*.py" in full_validation
    assert "tests/*.py" in full_validation
    assert "tests/test_*.py" not in full_validation
    assert "github.event.pull_request.draft" in full_validation
    assert "needs.validation-scope.outputs.run_full" in full_validation
    assert "--cov-report=term-missing" in workflow_text
    assert "--cov-report=xml:coverage.xml" not in workflow_text
    assert "coverage.xml" not in workflow_text
    assert "codecov/codecov-action" not in workflow_text
    assert "CODECOV_TOKEN" not in workflow_text
    assert "fail_ci_if_error" not in workflow_text
    assert "main-non-pyomo" not in workflow_text
    assert "pip install pyomo" not in pr_tests
    assert "pip install pyomo" not in main_tests
    assert "pip install pyomo" not in full_validation
    assert "pip install pyomo" not in notebook_tests
    assert 'pip install -e ".[dev,pyomo]"' not in pr_tests
    assert 'pip install -e ".[dev,pyomo]"' not in main_tests
    assert 'pip install -e ".[dev,pyomo]"' not in full_validation
    assert 'pip install -e ".[dev,pyomo]"' not in notebook_tests
    assert "idaes get-extensions --extra petsc" not in pr_tests
    assert "idaes get-extensions --extra petsc" not in main_tests
    assert "idaes get-extensions --extra petsc" not in full_validation
    assert "idaes get-extensions --extra petsc" not in notebook_tests
    assert "python -m ruff check lyopronto tests examples main.py" in pr_tests
    assert "python -m ruff check lyopronto tests examples main.py" in main_tests
    assert "python -m mypy lyopronto" in pr_tests
    assert "python -m mypy lyopronto" in main_tests
    assert "continue-on-error: true" in pr_tests
    assert "continue-on-error: true" in main_tests
    assert "--durations=25" not in workflow_text

    assert "manual-${{ inputs.lane }}" not in manual_tests
    assert "manual-validation" not in manual_tests
    assert 'rc" -eq 5' in manual_tests
    assert 'pip install -e ".[dev,pyomo]"' in manual_tests
    assert "idaes get-extensions --extra petsc" in manual_tests
    assert "pip install pyomo idaes-pse" not in manual_tests
    assert "RUN_SLOW_TESTS" not in manual_tests

    assert "github.event.pull_request.draft == false" in notebook_tests

    assert "--cov-config=.coveragerc.non-pyomo" not in pyomo_tests
    assert "lyopronto/pyomo_models/**" in pyomo_tests
    assert "tests/test_pyomo_models/**" in pyomo_tests
    assert 'pip install -e ".[dev,pyomo]"' in pyomo_tests
    assert "pytest -n 0 -v" in pyomo_tests
    assert "idaes get-extensions --extra petsc" in pyomo_tests
    assert "Install IPOPT with: idaes get-extensions --extra petsc" in pyomo_tests
    assert (
        "Alternative local install: conda install -c conda-forge ipopt" in pyomo_tests
    )
    assert "continue-on-error: true" in pyomo_tests
    assert (
        "tests/test_pyomo_models/test_single_step.py::test_single_step_solves_and_matches_scipy_reference"
        in pyomo_tests
    )
    assert (
        "tests/test_pyomo_models/test_trajectory.py::test_trajectory_solves_and_matches_scipy_reference"
        in pyomo_tests
    )


def test_local_ci_script_matches_documented_lane_expressions() -> None:
    script = _text("run_local_ci.sh")
    assignments = _shell_assignments(script)
    lane_expressions = _local_ci_lane_expressions(script)

    fast_command = _single_command_with_marker(script, "$FAST_EXPR")
    for marker in ["slow", "notebook", "pyomo"]:
        _assert_marker_excludes(lane_expressions["fast"], marker)
    _assert_no_coverage(fast_command)

    for variable in ["FULL_EXPR", "SLOW_EXPR", "NOTEBOOK_EXPR"]:
        command = _single_command_with_marker(script, f"${variable}")
        _assert_non_pyomo_coverage(command)

    _assert_marker_excludes(lane_expressions["full"], "pyomo")
    _assert_marker_mentions(lane_expressions["slow"], "slow")
    _assert_marker_excludes(lane_expressions["slow"], "pyomo")
    _assert_marker_mentions(lane_expressions["notebook"], "notebook")

    pyomo_light_commands = [
        command
        for command in _pytest_commands(script)
        if "$PYOMO_LIGHT_TARGETS" in command
    ]
    assert len(pyomo_light_commands) == 1
    assert assignments["PYOMO_LIGHT_TARGETS"].split() == [
        "tests/test_pyomo_models",
        "tests/test_pyomo_solver.py",
    ]
    _assert_no_coverage(pyomo_light_commands[0])

    pyomo_command = _single_command_with_marker(script, "$PYOMO_EXPR")
    _assert_marker_mentions(lane_expressions["pyomo"], "pyomo")
    _assert_pyomo_coverage(pyomo_command)

    assert assignments["NON_PYOMO_COV_CONFIG"] == ".coveragerc.non-pyomo"
    assert "--cov-report=xml:coverage.xml" not in script
    assert "coverage.xml" not in script
    assert "--durations=25" not in script
    assert "pyomo-light" in script
    assert 'pip install -e ".[dev,pyomo]"' in script
    assert "idaes get-extensions --extra petsc" in script
    assert "pip install pyomo idaes-pse" not in script
    assert "run_pytest_allow_empty" in script
    assert "SKIP_INSTALL=1" in script


def test_contributor_docs_include_ci_and_static_analysis_commands() -> None:
    script = _text("run_local_ci.sh")
    assignments = _shell_assignments(script)
    lane_expressions = _local_ci_lane_expressions(script)
    pyomo_light_targets = assignments["PYOMO_LIGHT_TARGETS"].split()
    docs = "\n".join(
        [
            _text("tests/README.md"),
            _text("CONTRIBUTING.md"),
            _text("docs/dev.md"),
            _text("docs/technical/julia-parity.md"),
        ]
    )

    fast_commands = _commands_with_marker(docs, lane_expressions["fast"])
    assert fast_commands
    for command in fast_commands:
        _assert_no_coverage(command)

    for lane in ["full", "slow", "notebook"]:
        commands = _commands_with_marker(docs, lane_expressions[lane])
        assert commands
        for command in commands:
            _assert_non_pyomo_coverage(command)

    pyomo_commands = _commands_with_marker(docs, lane_expressions["pyomo"])
    assert pyomo_commands
    for command in pyomo_commands:
        _assert_pyomo_coverage(command)

    pyomo_light_commands = _commands_with_targets(docs, pyomo_light_targets)
    assert pyomo_light_commands
    for command in pyomo_light_commands:
        _assert_no_coverage(command)

    assert "--cov-report=term-missing" in docs
    assert "--cov-report=xml:coverage.xml" not in docs
    assert ".coveragerc.non-pyomo" in docs
    assert "Codecov uploads are not configured" in docs
    assert "--durations=25" in docs
    assert "--timeout=600" in docs
    assert "--timeout-method=thread" in docs
    assert "Full Validation workflow" in docs
    assert "full-validation" in docs
    assert "nightly" in docs
    assert "tag" in docs
    assert "require the `Full non-Pyomo validation` job" in docs
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
    assert "./run_local_ci.sh pyomo-light" in docs
    assert "branch-protection required status checks" in docs
    assert "job-level non-blocking" in docs


def test_docs_inventory_classifies_retained_markdown_files() -> None:
    inventory = _text("docs/README.md")
    docs_dir = ROOT / "docs"

    retained = sorted(path.relative_to(docs_dir).as_posix() for path in docs_dir.rglob("*.md"))
    for path in retained:
        assert f"`{path}`" in inventory

    for filename in [
        "CI_SETUP.md",
        "CI_WORKFLOW_GUIDE.md",
        "CI_QUICK_REFERENCE.md",
        "SLOW_TEST_STRATEGY.md",
        "CI_PERFORMANCE_OPTIMIZATION.md",
        "GETTING_STARTED.md",
        "ARCHITECTURE.md",
        "TYPED_API_GUIDE.md",
        "explanation.md",
        "ci-testing.md",
        "tutorials.md",
        "technical/pyomo-status.md",
    ]:
        assert not (docs_dir / filename).exists()
        assert f"`{filename}`" in inventory


def test_copilot_instructions_do_not_link_removed_docs() -> None:
    instructions = _text(".github/copilot-instructions.md")

    for removed_path in [
        "docs/ARCHITECTURE.md",
        "docs/GETTING_STARTED.md",
        "docs/PHYSICS_REFERENCE.md",
        "docs/PYOMO_STATUS.md",
        "docs/ci-testing.md",
        "docs/tutorials.md",
        "docs/technical/pyomo-status.md",
    ]:
        assert removed_path not in instructions

    for current_path in [
        "docs/reference.md",
        "docs/dev.md",
        "docs/how-to-guides.md",
        "docs/technical/physics-reference.md",
    ]:
        assert current_path in instructions


def test_legacy_setup_py_metadata_removed() -> None:
    assert not (ROOT / "setup.py").exists()


def test_installed_distribution_version_matches_pyproject() -> None:
    project = _pyproject()["project"]

    try:
        installed_version = metadata.version(project["name"])
    except metadata.PackageNotFoundError:
        pytest.skip("lyopronto distribution is not installed")

    assert installed_version == project["version"]
