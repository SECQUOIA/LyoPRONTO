import sys
import numpy as np
from pathlib import Path

# Ensure local benchmarks/scripts is on sys.path so `import diagnostics` succeeds
repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo_root / "benchmarks" / "scripts"))

from benchmarks.scripts import validate as validate_mod
from benchmarks.src import adapters as adapters_mod


def make_traj(time, Tsub, Tsh, Pch_Torr, frac):
    """Helper to create trajectory array in expected shape (N x 7).

    Columns: time [hr], Tsub, Tbot, Tsh, Pch [mTorr], flux, frac_dried
    """
    time = np.array(time, dtype=float)
    n = time.size
    Tsub = np.array(Tsub, dtype=float)
    Tbot = Tsub - 0.5  # dummy
    Pch_mTorr = np.array(Pch_Torr, dtype=float) * 1000.0
    flux = np.zeros(n)
    arr = np.vstack([
        time,
        np.array(Tsub, dtype=float),
        np.array(Tbot, dtype=float),
        np.array(Tsh, dtype=float),
        Pch_mTorr,
        flux,
        np.array(frac, dtype=float),
    ]).T
    return arr


def test_validate_constraints_basic_pass():
    # Simple trajectory that meets all constraints
    traj = make_traj(
        time=[0.0, 1.0, 2.0],
        Tsub=[-40.0, -39.5, -39.0],
        Tsh=[-35.0, -34.5, -34.0],
        Pch_Torr=[0.1, 0.1, 0.1],
        frac=[0.0, 0.5, 1.0],
    )
    res = validate_mod.validate_constraints(traj, T_pr_crit=-25.0)
    assert bool(res["dryness_ok"]) is True
    assert bool(res["temperature_ok"]) is True
    assert bool(res["constraints_satisfied"]) is True


def test_validate_constraints_ramp_violation():
    # Create a trajectory with a large Tsh ramp that will violate a 1.0 °C/hr limit
    traj = make_traj(
        time=[0.0, 0.5, 1.0],  # half-hour steps
        Tsub=[-40.0, -40.0, -40.0],
        Tsh=[-35.0, 0.0, 35.0],  # big jumps
        Pch_Torr=[0.1, 0.1, 0.1],
        frac=[0.0, 0.5, 1.0],
    )
    # ramp_Tsh_max in °C/hr set to small value to force violation
    res = validate_mod.validate_constraints(traj, T_pr_crit=-25.0, ramp_Tsh_max=1.0)
    assert bool(res["ramp_Tsh_ok"]) is False
    assert res["max_Tsh_ramp_violation"] > 0.0
    assert bool(res["constraints_satisfied"]) is False


def test_pyomo_adapter_applies_ramp_overrides(monkeypatch):
    # Monkeypatch the pyomo optimizer runner to avoid heavy solves
    def fake_runner(*args, **kwargs):
        # Return a small empty output and metadata with safe defaults
        return {
            "output": np.empty((0, 7)),
            "metadata": {
                "objective_time_hr": 0.0,
                "status": None,
                "termination_condition": None,
                "ipopt_iterations": None,
                "n_points": 0,
                "staged_solve_success": None,
                "mesh_info": {"nfe_applied": 0},
            },
        }

    monkeypatch.setattr(adapters_mod.pyomo_opt, "optimize_Pch_pyomo", fake_runner)
    monkeypatch.setattr(adapters_mod.pyomo_opt, "optimize_Tsh_pyomo", fake_runner)
    monkeypatch.setattr(adapters_mod.pyomo_opt, "optimize_Pch_Tsh_pyomo", fake_runner)

    vial = {"Av": 1.0}
    product = {"R0": 0.4}
    ht = {"KC": 1e-4}
    eq_cap = {}
    nVial = 1
    scenario = {}

    ramps = {"Tsh_max": 3.0, "Pch_max": 0.05}
    out = adapters_mod.pyomo_adapter(
        "both",
        vial,
        product,
        ht,
        eq_cap,
        nVial,
        scenario,
        dt=0.01,
        warmstart=False,
        method="fd",
        n_elements=10,
        n_collocation=3,
        effective_nfe=False,
        ramp_rates=ramps,
        solver_timeout=30,
    )

    # Ensure ramp_constraints in adapter reflect overrides applied
    assert out.get("ramp_constraints") is not None
    rc = out["ramp_constraints"]
    assert rc["Tsh"] == ramps["Tsh_max"]
    assert rc["Pch"] == ramps["Pch_max"]
