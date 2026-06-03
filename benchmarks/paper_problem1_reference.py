# Copyright (C) 2026, SECQUOIA

"""Generate and compare Paper Problem 1 upstream reference trajectories."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Sequence

if __package__ in {None, ""}:
    repo_root = Path(__file__).resolve().parents[1]
    if (repo_root / "lyopronto").is_dir():
        sys.path.insert(0, str(repo_root))

from lyopronto.pyomo_models.paper_ocp import (
    PaperDiscretization,
    classify_paper_policies,
    compare_paper_problem1_trajectories,
    load_upstream_matlab_trajectory,
    solve_paper_problem1,
)

DEFAULT_UPSTREAM_ROOT = Path(
    os.environ.get(
        "LYOPRONTO_UPSTREAM_ROOT",
        "/home/bernalde/repos/simDAE-optimalcontrol-lyo",
    )
)
DEFAULT_OUTPUT = Path("benchmarks/results/paper_problem1_upstream_reference.mat")
MATLAB_RUNNER = "run_paper_problem1_upstream_reference"


def write_matlab_batch_files(work_dir: Path, upstream_root: Path) -> dict[str, Path]:
    """Write batch-safe MATLAB helper files for the upstream OCP workflow."""
    work_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "runner": work_dir / f"{MATLAB_RUNNER}.m",
        "max_t": work_dir / "SimPy_MaxT.m",
        "max_flux": work_dir / "SimPy_MaxFlux.m",
    }
    files["runner"].write_text(_runner_source(), encoding="utf-8")
    files["max_t"].write_text(
        _python_wrapper_source("SimPy_MaxT", "pyfun_MaxT.py", upstream_root),
        encoding="utf-8",
    )
    files["max_flux"].write_text(
        _python_wrapper_source("SimPy_MaxFlux", "pyfun_MaxFlux.py", upstream_root),
        encoding="utf-8",
    )
    return files


def build_matlab_batch_command(
    matlab_cmd: str,
    work_dir: Path,
    upstream_root: Path,
    output: Path,
    case_name: str = "Case2",
) -> list[str]:
    """Return the MATLAB command that runs the generated batch wrapper."""
    batch = (
        f"addpath({_matlab_string(work_dir)}, '-begin'); "
        f"{MATLAB_RUNNER}("
        f"{_matlab_string(upstream_root)}, "
        f"{_matlab_string(output)}, "
        f"{_matlab_string(case_name)});"
    )
    return [matlab_cmd, "-batch", batch]


def compare_pyomo_to_upstream(
    upstream_mat: Path,
    discretization: PaperDiscretization,
    solver_options: dict[str, float | int],
    require_success: bool = True,
) -> dict[str, float | None]:
    """Solve Paper Problem 1 from an upstream warm start and compare trajectories."""
    upstream_trajectory = load_upstream_matlab_trajectory(upstream_mat)
    pyomo_result = solve_paper_problem1(
        discretization=discretization,
        initialization=upstream_trajectory,
        solver_options=solver_options,
        require_success=require_success,
    )
    if "policies" not in pyomo_result:
        pyomo_result["policies"] = classify_paper_policies(pyomo_result)
    return compare_paper_problem1_trajectories(pyomo_result, upstream_trajectory)


def _runner_source() -> str:
    return """function run_paper_problem1_upstream_reference(upstream_root, output_path, case_name)
code_root = fullfile(upstream_root, 'Code (Conference Version)');
runner_root = fileparts(mfilename('fullpath'));
addpath(runner_root, '-begin');
addpath(fullfile(code_root, 'Input Data'));
addpath(fullfile(code_root, 'Model Equations'));
addpath(fullfile(code_root, 'Events'));
addpath(fullfile(code_root, 'Simulations'));
addpath(fullfile(code_root, 'Calculations'));
addpath(fullfile(code_root, 'Sim_DAE'));
% Keep generated batch-safe wrappers ahead of upstream functions with the same names.
addpath(runner_root, '-begin');

old_dir = pwd;
cleanup = onCleanup(@() cd(old_dir));
cd(code_root);

ip0 = get_inputdata;
ip0 = overwrite_inputdata(ip0, string(case_name));
ip = input_processing(ip0);
sol = Sim_1stDrying_OCP(ip);

t = sol.t;
T = sol.T;
S = sol.S;
Tb = sol.Tb;
dSdt = sol.dSdt;
policy = sol.policy;
tsw = sol.tsw;

output_dir = fileparts(output_path);
if ~isempty(output_dir) && ~exist(output_dir, 'dir')
    mkdir(output_dir);
end
save(output_path, 't', 'T', 'S', 'Tb', 'dSdt', 'policy', 'tsw', '-v7');
end
"""


def _python_wrapper_source(
    function_name: str,
    python_file: str,
    upstream_root: Path,
) -> str:
    python_dir = upstream_root / "Code (Conference Version)" / "Python"
    return f"""function [Tb_opt, t_opt, S_opt] = {function_name}(ip_py)
py_file = {_matlab_string(python_file)};
python_dir = {_matlab_string(python_dir)};

old_dir = pwd;
cleanup = onCleanup(@() cd(old_dir));
cd(python_dir);

output_py = pyrunfile(py_file, 'output_MATLAB', lyo_mpc=ip_py);
Tb_opt = double(output_py{{1}})';
t_opt = double(output_py{{2}})';
S_opt = double(output_py{{3}})';

if numel(Tb_opt) >= 3 && t_opt(3) ~= t_opt(2)
    slope = (Tb_opt(3) - Tb_opt(2)) / (t_opt(3) - t_opt(2));
    Tb_opt(1) = Tb_opt(2) - slope * (t_opt(2) - t_opt(1));
end
end
"""


def _matlab_string(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _validate_upstream_root(upstream_root: Path) -> None:
    required = (
        upstream_root
        / "Code (Conference Version)"
        / "Simulations"
        / "Sim_1stDrying_OCP.m"
    )
    if not required.is_file():
        raise FileNotFoundError(
            f"upstream root does not contain expected file: {required}"
        )


def _trajectory_summary(mat_path: Path) -> dict[str, float | int | None]:
    trajectory = load_upstream_matlab_trajectory(mat_path)
    switch_times = trajectory.get("policies", {}).get("switch_times_hr", [])
    switch_times = list(switch_times)
    return {
        "n_points": int(len(trajectory["states"]["time_s"])),
        "drying_time_hr": float(trajectory["metrics"]["drying_time_hr"]),
        "first_switch_time_hr": (
            float(switch_times[0]) if len(switch_times) > 0 else None
        ),
        "terminal_interface_position_m": float(
            trajectory["metrics"]["terminal_interface_position_m"]
        ),
        "max_product_temperature_K": float(
            trajectory["metrics"]["max_product_temperature_K"]
        ),
    }


def _solver_options(args: argparse.Namespace) -> dict[str, float | int]:
    options: dict[str, float | int] = {
        "print_level": args.print_level,
        "max_iter": args.max_iter,
    }
    if args.tol is not None:
        options["tol"] = args.tol
    if args.acceptable_tol is not None:
        options["acceptable_tol"] = args.acceptable_tol
    if args.acceptable_iter is not None:
        options["acceptable_iter"] = args.acceptable_iter
    return options


def _add_pyomo_solve_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--n-z", type=int, default=20)
    parser.add_argument("--nfe", type=int, default=12)
    parser.add_argument("--ncp", type=int, default=3)
    parser.add_argument("--terminal-drying-fraction", type=float, default=0.995)
    parser.add_argument("--max-iter", type=int, default=3000)
    parser.add_argument("--tol", type=float, default=1.0e-5)
    parser.add_argument("--acceptable-tol", type=float, default=1.0e-3)
    parser.add_argument("--acceptable-iter", type=int, default=5)
    parser.add_argument("--print-level", type=int, default=0)
    parser.add_argument(
        "--allow-unsuccessful-pyomo",
        action="store_true",
        help="Extract and compare the Pyomo trajectory even if IPOPT is not optimal.",
    )


def _discretization_from_args(args: argparse.Namespace) -> PaperDiscretization:
    return PaperDiscretization(
        n_z=args.n_z,
        nfe=args.nfe,
        ncp=args.ncp,
        terminal_drying_fraction=args.terminal_drying_fraction,
    )


def _prepare_work_dir(args: argparse.Namespace) -> tuple[Path, tempfile.TemporaryDirectory | None]:
    if args.work_dir is not None:
        work_dir = args.work_dir
        work_dir.mkdir(parents=True, exist_ok=True)
        return work_dir, None
    if args.runner_only or args.keep_workdir:
        return Path(tempfile.mkdtemp(prefix="lyopronto-paper-problem1-")), None
    temp_dir = tempfile.TemporaryDirectory(prefix="lyopronto-paper-problem1-")
    return Path(temp_dir.name), temp_dir


def _run_generate(args: argparse.Namespace) -> int:
    upstream_root = args.upstream_root.resolve()
    output = args.output.resolve()
    _validate_upstream_root(upstream_root)
    work_dir, cleanup = _prepare_work_dir(args)
    try:
        write_matlab_batch_files(work_dir, upstream_root)
        command = build_matlab_batch_command(
            args.matlab,
            work_dir,
            upstream_root,
            output,
            args.case,
        )
        print(f"MATLAB work dir: {work_dir}")
        print(f"Command: {shlex.join(command)}")
        if args.runner_only:
            return 0

        subprocess.run(command, check=True)
        print(json.dumps(_trajectory_summary(output), indent=2, sort_keys=True))
        if args.compare_pyomo:
            comparison = compare_pyomo_to_upstream(
                output,
                _discretization_from_args(args),
                _solver_options(args),
                require_success=not args.allow_unsuccessful_pyomo,
            )
            print(json.dumps(comparison, indent=2, sort_keys=True))
    finally:
        if cleanup is not None:
            cleanup.cleanup()
    return 0


def _run_compare_pyomo(args: argparse.Namespace) -> int:
    comparison = compare_pyomo_to_upstream(
        args.upstream_mat,
        _discretization_from_args(args),
        _solver_options(args),
        require_success=not args.allow_unsuccessful_pyomo,
    )
    print(json.dumps(comparison, indent=2, sort_keys=True))
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser(
        "generate",
        help="Run upstream MATLAB/GEKKO and export a Paper Problem 1 .mat file.",
    )
    generate.add_argument("--upstream-root", type=Path, default=DEFAULT_UPSTREAM_ROOT)
    generate.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    generate.add_argument("--case", default="Case2")
    generate.add_argument("--matlab", default=os.environ.get("MATLAB", "matlab"))
    generate.add_argument("--work-dir", type=Path, default=None)
    generate.add_argument("--runner-only", action="store_true")
    generate.add_argument("--keep-workdir", action="store_true")
    generate.add_argument("--compare-pyomo", action="store_true")
    _add_pyomo_solve_options(generate)
    generate.set_defaults(func=_run_generate)

    compare = subparsers.add_parser(
        "compare-pyomo",
        help="Solve Pyomo from an upstream .mat warm start and print deviations.",
    )
    compare.add_argument("upstream_mat", type=Path)
    _add_pyomo_solve_options(compare)
    compare.set_defaults(func=_run_compare_pyomo)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
