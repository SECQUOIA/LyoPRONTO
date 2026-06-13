from __future__ import annotations

from importlib import metadata
import subprocess
import sys

import pytest

import lyopronto


def _run_python(repo_root, code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )


def test_top_level_import_does_not_import_matplotlib(repo_root) -> None:
    result = _run_python(
        repo_root,
        "\n".join(
            [
                "import sys",
                "import lyopronto",
                "loaded = [name for name in sys.modules if name.startswith('matplotlib')]",
                "assert not loaded, loaded",
            ]
        ),
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_common_top_level_compat_imports_remain_available(repo_root) -> None:
    result = _run_python(
        repo_root,
        "\n".join(
            [
                "import sys",
                "from lyopronto import Q_, calc_knownRp, execute_simulation",
                "assert Q_(1, 'hour').magnitude == 1",
                "assert calc_knownRp.__name__ == 'lyopronto.calc_knownRp'",
                "assert callable(execute_simulation)",
                "loaded = [name for name in sys.modules if name.startswith('matplotlib')]",
                "assert not loaded, loaded",
            ]
        ),
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_public_version_matches_distribution_metadata() -> None:
    try:
        expected = metadata.version("lyopronto")
    except metadata.PackageNotFoundError:
        pytest.skip("lyopronto distribution is not installed")

    assert lyopronto.__version__ == expected
