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


def test_requirements_txt_mirrors_runtime_dependencies() -> None:
    project = _pyproject()["project"]

    assert sorted(_requirements(ROOT / "requirements.txt")) == sorted(
        project["dependencies"]
    )


def test_requirements_dev_delegates_to_dev_extra() -> None:
    assert _requirements(ROOT / "requirements-dev.txt") == ["-e .[dev]"]


def test_pytest_configuration_has_single_source() -> None:
    config = _pyproject()["tool"]["pytest"]["ini_options"]

    assert not (ROOT / "pytest.ini").exists()
    assert config["testpaths"] == ["tests"]
    assert "--strict-markers" in config["addopts"]
    assert any(marker.startswith("pyomo:") for marker in config["markers"])


def test_legacy_setup_py_metadata_removed() -> None:
    assert not (ROOT / "setup.py").exists()


def test_installed_distribution_version_matches_pyproject() -> None:
    project = _pyproject()["project"]

    try:
        installed_version = metadata.version(project["name"])
    except metadata.PackageNotFoundError:
        pytest.skip("lyopronto distribution is not installed")

    assert installed_version == project["version"]
