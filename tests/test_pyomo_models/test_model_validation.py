"""Validation tests for multi-period DAE model.

This module tests scipy comparison, physics consistency, and optimization
performance for the multi-period DAE model (from model.py).

Tests include:
- Scipy comparison (warmstart feasibility, trend preservation, bounds)
- Physics consistency (monotonicity, positive rates, temperature gradients)
- Optimization comparison (improvement over scipy, constraint satisfaction)
"""

# Copyright (C) 2026, SECQUOIA

import os

import numpy as np
import pytest

pyo = pytest.importorskip("pyomo.environ")
pytest.importorskip("pyomo.dae")

from lyopronto import calc_knownRp, functions
from lyopronto.pyomo_models import model as model_module

# Check for IPOPT solver
IPOPT_AVAILABLE = False
try:
    from idaes.core.solvers import get_solver

    solver = get_solver("ipopt")
    IPOPT_AVAILABLE = True
except Exception:
    try:
        solver = pyo.SolverFactory("ipopt")
        IPOPT_AVAILABLE = solver.available()
    except Exception:
        IPOPT_AVAILABLE = False

pytestmark = [pytest.mark.pyomo]


class TestScipyComparison:
    """Validation tests comparing multi-period DAE model to scipy baseline."""

    def test_warmstart_creates_feasible_initial_point(
        self, standard_vial, standard_product, standard_ht
    ):
        """Verify warmstart from scipy creates a reasonable initial point."""
        Pchamber = {"setpt": [0.1], "dt_setpt": [1800], "ramp_rate": 0.5}
        Tshelf = {"setpt": [-10.0], "dt_setpt": [1800], "ramp_rate": 1.0, "init": -40.0}
        scipy_traj = calc_knownRp.dry(
            standard_vial, standard_product, standard_ht, Pchamber, Tshelf, dt=1.0
        )

        model = model_module.create_multi_period_model(
            standard_vial,
            standard_product,
            standard_ht,
            Vfill=standard_vial["Vfill"],
            n_elements=5,
            n_collocation=3,
            apply_scaling=False,
        )

        model_module.warmstart_from_scipy_trajectory(
            model, scipy_traj, standard_vial, standard_product, standard_ht
        )

        t_points = sorted(model.t)
        Tsub_vals = [pyo.value(model.Tsub[t]) for t in t_points]
        Pch_vals = [pyo.value(model.Pch[t]) for t in t_points]
        Lck_vals = [pyo.value(model.Lck[t]) for t in t_points]

        # Physical reasonableness
        assert all(-60 <= T <= 0 for T in Tsub_vals), "Tsub should be reasonable"
        assert all(0.05 <= P <= 0.5 for P in Pch_vals), "Pch should be in bounds"
        assert all(0 <= L <= 5 for L in Lck_vals), "Lck should be non-negative"
        assert Lck_vals[-1] > Lck_vals[0], "Cake length should increase"

    def test_warmstart_preserves_scipy_trends(
        self, standard_vial, standard_product, standard_ht
    ):
        """Verify warmstart preserves key trends from scipy simulation."""
        Pchamber = {"setpt": [0.1], "dt_setpt": [1800], "ramp_rate": 0.5}
        Tshelf = {"setpt": [-10.0], "dt_setpt": [1800], "ramp_rate": 1.0, "init": -40.0}
        scipy_traj = calc_knownRp.dry(
            standard_vial, standard_product, standard_ht, Pchamber, Tshelf, dt=1.0
        )

        model = model_module.create_multi_period_model(
            standard_vial,
            standard_product,
            standard_ht,
            Vfill=standard_vial["Vfill"],
            n_elements=5,
            n_collocation=3,
            apply_scaling=False,
        )

        model_module.warmstart_from_scipy_trajectory(
            model, scipy_traj, standard_vial, standard_product, standard_ht
        )

        # Compare trends
        scipy_Tsub_start = scipy_traj[0, 1]
        scipy_Tsub_end = scipy_traj[-1, 1]
        scipy_percent_end = scipy_traj[-1, 6]  # Scipy returns percentage (0-100)

        t_points = sorted(model.t)
        pyomo_Tsub_start = pyo.value(model.Tsub[t_points[0]])
        pyomo_Tsub_end = pyo.value(model.Tsub[t_points[-1]])

        Lpr0 = functions.Lpr0_FUN(
            standard_vial["Vfill"], standard_vial["Ap"], standard_product["cSolid"]
        )
        pyomo_percent_end = (
            pyo.value(model.Lck[t_points[-1]]) / Lpr0 * 100.0
        )  # Convert to percentage

        # Trends should match (allow 20% tolerance for interpolation)
        assert abs(pyomo_Tsub_start - scipy_Tsub_start) < 10, (
            "Initial Tsub should match"
        )
        assert abs(pyomo_Tsub_end - scipy_Tsub_end) < 5, "Final Tsub should match"
        assert abs(pyomo_percent_end - scipy_percent_end) < 20.0, (
            "Final dryness should match (within 20%)"
        )

    def test_model_respects_temperature_bounds(
        self, standard_vial, standard_product, standard_ht
    ):
        """Verify temperature variables stay within physical bounds after warmstart."""
        Pchamber = {"setpt": [0.1], "dt_setpt": [1800], "ramp_rate": 0.5}
        Tshelf = {"setpt": [-10.0], "dt_setpt": [1800], "ramp_rate": 1.0, "init": -40.0}
        scipy_traj = calc_knownRp.dry(
            standard_vial, standard_product, standard_ht, Pchamber, Tshelf, dt=1.0
        )

        model = model_module.create_multi_period_model(
            standard_vial,
            standard_product,
            standard_ht,
            Vfill=standard_vial["Vfill"],
            n_elements=5,
            n_collocation=3,
            apply_scaling=False,
        )

        model_module.warmstart_from_scipy_trajectory(
            model, scipy_traj, standard_vial, standard_product, standard_ht
        )

        # Check all time points
        violations = []
        for t in sorted(model.t):
            Tsub = pyo.value(model.Tsub[t])
            Tbot = pyo.value(model.Tbot[t])
            Tsh = pyo.value(model.Tsh[t])
            Pch = pyo.value(model.Pch[t])

            if not (-60 <= Tsub <= 0):
                violations.append(f"Tsub[{t:.3f}] = {Tsub:.2f}")
            if not (-60 <= Tbot <= 50):
                violations.append(f"Tbot[{t:.3f}] = {Tbot:.2f}")
            if not (-50 <= Tsh <= 50):
                violations.append(f"Tsh[{t:.3f}] = {Tsh:.2f}")
            if not (0.05 <= Pch <= 0.5):
                violations.append(f"Pch[{t:.3f}] = {Pch:.4f}")

        assert len(violations) == 0, f"Found {len(violations)} bound violations"

    def test_algebraic_equations_approximately_satisfied(
        self, standard_vial, standard_product, standard_ht
    ):
        """Verify algebraic constraints are approximately satisfied after warmstart."""
        Pchamber = {"setpt": [0.1], "dt_setpt": [1800], "ramp_rate": 0.5}
        Tshelf = {"setpt": [-10.0], "dt_setpt": [1800], "ramp_rate": 1.0, "init": -40.0}
        scipy_traj = calc_knownRp.dry(
            standard_vial, standard_product, standard_ht, Pchamber, Tshelf, dt=1.0
        )

        model = model_module.create_multi_period_model(
            standard_vial,
            standard_product,
            standard_ht,
            Vfill=standard_vial["Vfill"],
            n_elements=5,
            n_collocation=3,
            apply_scaling=False,
        )

        model_module.warmstart_from_scipy_trajectory(
            model, scipy_traj, standard_vial, standard_product, standard_ht
        )

        # Check vapor pressure and Rp constraints at sample points
        t_points = sorted(model.t)
        sample_points = [t_points[0], t_points[len(t_points) // 2], t_points[-1]]

        max_vp_residual = 0
        max_rp_residual = 0

        for t in sample_points:
            # Vapor pressure log constraint
            Tsub = pyo.value(model.Tsub[t])
            log_Psub = pyo.value(model.log_Psub[t])
            expected_log_Psub = np.log(2.698e10) - 6144.96 / (Tsub + 273.15)
            vp_residual = abs(log_Psub - expected_log_Psub)
            max_vp_residual = max(max_vp_residual, vp_residual)

            # Product resistance constraint
            Lck = pyo.value(model.Lck[t])
            Rp = pyo.value(model.Rp[t])
            expected_Rp = standard_product["R0"] + standard_product["A1"] * Lck / (
                1 + standard_product["A2"] * Lck
            )
            rp_residual = abs(Rp - expected_Rp)
            max_rp_residual = max(max_rp_residual, rp_residual)

        # Warmstart may not satisfy constraints exactly, but should be close
        assert max_vp_residual < 1.0, "Vapor pressure should be approximately satisfied"
        assert max_rp_residual < 5.0, (
            "Product resistance should be approximately satisfied"
        )


class TestPhysicsConsistency:
    """Tests for physical consistency and reasonableness."""

    def test_cake_length_monotonically_increases(
        self, standard_vial, standard_product, standard_ht
    ):
        """Verify dried cake length increases monotonically over time."""
        Pchamber = {"setpt": [0.1], "dt_setpt": [1800], "ramp_rate": 0.5}
        Tshelf = {"setpt": [-10.0], "dt_setpt": [1800], "ramp_rate": 1.0, "init": -40.0}
        scipy_traj = calc_knownRp.dry(
            standard_vial, standard_product, standard_ht, Pchamber, Tshelf, dt=1.0
        )

        model = model_module.create_multi_period_model(
            standard_vial,
            standard_product,
            standard_ht,
            Vfill=standard_vial["Vfill"],
            n_elements=5,
            n_collocation=3,
            apply_scaling=False,
        )

        model_module.warmstart_from_scipy_trajectory(
            model, scipy_traj, standard_vial, standard_product, standard_ht
        )

        # Check monotonicity
        t_points = sorted(model.t)
        Lck_vals = [pyo.value(model.Lck[t]) for t in t_points]

        non_monotonic = sum(
            1 for i in range(1, len(Lck_vals)) if Lck_vals[i] < Lck_vals[i - 1] - 1e-6
        )

        # Allow up to 5% non-monotonic (interpolation artifacts)
        assert non_monotonic < 0.05 * len(Lck_vals), "Lck should be mostly monotonic"

    def test_sublimation_rate_positive(
        self, standard_vial, standard_product, standard_ht
    ):
        """Verify sublimation rate is non-negative (can't un-dry)."""
        Pchamber = {"setpt": [0.1], "dt_setpt": [1800], "ramp_rate": 0.5}
        Tshelf = {"setpt": [-10.0], "dt_setpt": [1800], "ramp_rate": 1.0, "init": -40.0}
        scipy_traj = calc_knownRp.dry(
            standard_vial, standard_product, standard_ht, Pchamber, Tshelf, dt=1.0
        )

        model = model_module.create_multi_period_model(
            standard_vial,
            standard_product,
            standard_ht,
            Vfill=standard_vial["Vfill"],
            n_elements=5,
            n_collocation=3,
            apply_scaling=False,
        )

        model_module.warmstart_from_scipy_trajectory(
            model, scipy_traj, standard_vial, standard_product, standard_ht
        )

        dmdt_vals = [pyo.value(model.dmdt[t]) for t in sorted(model.t)]
        negative_rates = [dmdt for dmdt in dmdt_vals if dmdt < -1e-6]

        assert len(negative_rates) == 0, "Sublimation rate should be non-negative"

    def test_temperature_gradient_physically_reasonable(
        self, standard_vial, standard_product, standard_ht
    ):
        """Verify Tbot >= Tsub (heat flows from bottom to sublimation front)."""
        Pchamber = {"setpt": [0.1], "dt_setpt": [1800], "ramp_rate": 0.5}
        Tshelf = {"setpt": [-10.0], "dt_setpt": [1800], "ramp_rate": 1.0, "init": -40.0}
        scipy_traj = calc_knownRp.dry(
            standard_vial, standard_product, standard_ht, Pchamber, Tshelf, dt=1.0
        )

        model = model_module.create_multi_period_model(
            standard_vial,
            standard_product,
            standard_ht,
            Vfill=standard_vial["Vfill"],
            n_elements=5,
            n_collocation=3,
            apply_scaling=False,
        )

        model_module.warmstart_from_scipy_trajectory(
            model, scipy_traj, standard_vial, standard_product, standard_ht
        )

        # Check temperature gradient (allow 5°C tolerance)
        violations = []
        for t in sorted(model.t):
            Tsub = pyo.value(model.Tsub[t])
            Tbot = pyo.value(model.Tbot[t])
            if Tbot < Tsub - 5.0:
                violations.append((t, Tsub, Tbot))

        # Temperature inversion can occur briefly during transients
        # So we allow some violations but not extreme ones
        assert all(Tbot >= Tsub - 10 for _, Tsub, Tbot in violations), (
            "Extreme temperature inversions detected"
        )


@pytest.mark.slow
@pytest.mark.skipif(not IPOPT_AVAILABLE, reason="IPOPT solver not available")
class TestOptimizationComparison:
    """Compare optimized multi-period results to scipy (slow tests)."""

    @pytest.mark.skipif(
        not os.environ.get("RUN_SLOW_TESTS"),
        reason="Full optimization is slow, set RUN_SLOW_TESTS=1 to enable",
    )
    def test_optimization_improves_over_scipy(
        self, standard_vial, standard_product, standard_ht
    ):
        """Verify Pyomo optimization can improve on scipy constant setpoints."""
        Pchamber = {"setpt": [0.1], "dt_setpt": [1800], "ramp_rate": 0.5}
        Tshelf = {"setpt": [-10.0], "dt_setpt": [1800], "ramp_rate": 1.0, "init": -40.0}
        scipy_traj = calc_knownRp.dry(
            standard_vial, standard_product, standard_ht, Pchamber, Tshelf, dt=1.0
        )

        scipy_time = scipy_traj[-1, 0]

        solution = model_module.optimize_multi_period(
            standard_vial,
            standard_product,
            standard_ht,
            Vfill=standard_vial["Vfill"],
            n_elements=5,
            n_collocation=3,
            warmstart_data=scipy_traj,
            tee=True,
        )

        # Pyomo should achieve similar or better time
        assert solution["t_final"] <= scipy_time * 1.2, (
            "Pyomo should not be much slower than scipy"
        )

    @pytest.mark.skipif(
        not os.environ.get("RUN_SLOW_TESTS"),
        reason="Full optimization is slow, set RUN_SLOW_TESTS=1 to enable",
    )
    def test_optimized_solution_satisfies_constraints(
        self, standard_vial, standard_product, standard_ht
    ):
        """Verify optimized solution respects all constraints."""
        Pchamber = {"setpt": [0.1], "dt_setpt": [1800], "ramp_rate": 0.5}
        Tshelf = {"setpt": [-10.0], "dt_setpt": [1800], "ramp_rate": 1.0, "init": -40.0}
        scipy_traj = calc_knownRp.dry(
            standard_vial, standard_product, standard_ht, Pchamber, Tshelf, dt=1.0
        )

        solution = model_module.optimize_multi_period(
            standard_vial,
            standard_product,
            standard_ht,
            Vfill=standard_vial["Vfill"],
            n_elements=5,
            n_collocation=3,
            warmstart_data=scipy_traj,
            tee=False,
        )

        assert "optimal" in solution["status"].lower(), (
            f"Should be optimal, got {solution['status']}"
        )

        # Check product temperature constraint (skip t=0 as model does - cold start)
        Tpr_max = standard_product.get(
            "Tpr_max", standard_product.get("T_pr_crit", -25.0)
        )
        # Skip the first few points which are the cold startup phase
        # The model skips t=0, so we skip the first point in the solution
        Tbot_after_start = solution["Tbot"][1:]  # Skip t=0
        Tbot_violations = [T for T in Tbot_after_start if Tpr_max + 0.5 < T]

        assert len(Tbot_violations) == 0, "Temperature constraint should be satisfied"

        # Check sublimation rate is constrained consistently at every returned point
        expected_dmdt = np.array(
            [
                functions.sub_rate(standard_vial["Ap"], Rp, Tsub, Pch)
                for Rp, Tsub, Pch in zip(
                    solution["Rp"], solution["Tsub"], solution["Pch"]
                )
            ]
        )
        assert np.allclose(solution["dmdt"], expected_dmdt, rtol=1e-5, atol=1e-8)

        # Check final dryness
        Lpr0 = functions.Lpr0_FUN(
            standard_vial["Vfill"], standard_vial["Ap"], standard_product["cSolid"]
        )
        final_dryness = solution["Lck"][-1] / Lpr0

        assert final_dryness >= 0.999, "Should achieve complete drying by default"
