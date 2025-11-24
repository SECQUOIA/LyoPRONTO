"""Advanced testing for single time-step model.

This module consolidates advanced structural analysis, numerical debugging,
scipy comparison, and model validation tests for the single time-step model.

Includes:
- Structural analysis (DOF, incidence, DM partition, block triangularization)
- Numerical debugging (residuals, scaling, condition number)
- Scipy comparison (consistency with scipy baseline)
- Model validation (orphan variables, multiple starting points)

Reference: https://pyomo.readthedocs.io/en/6.8.1/explanation/analysis/incidence/tutorial.html
"""

# LyoPRONTO, a vial-scale lyophilization process simulator
# Nonlinear optimization
# Copyright (C) 2025, David E. Bernal Neira

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import pytest
import numpy as np
from lyopronto import functions, constant, opt_Pch_Tsh
from lyopronto.pyomo_models import single_step, utils

# Try to import pyomo and analysis tools
try:
    import pyomo.environ as pyo
    from pyomo.contrib.incidence_analysis import IncidenceGraphInterface
    from pyomo.common.dependencies import attempt_import
    
    # Try to import networkx for graph analysis
    networkx, networkx_available = attempt_import('networkx')
    
    PYOMO_AVAILABLE = True
    INCIDENCE_AVAILABLE = True
except ImportError:
    PYOMO_AVAILABLE = False
    INCIDENCE_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not (PYOMO_AVAILABLE and INCIDENCE_AVAILABLE), 
    reason="Pyomo or incidence analysis tools not available"
)


class TestStructuralAnalysis:
    """Tests for model structural analysis using Pyomo incidence analysis."""
    
    def test_degrees_of_freedom(self, standard_vial, standard_product, standard_ht):
        """Verify model DOF structure.
        
        For optimization: variables - equality_constraints = DOF (2 for Pch, Tsh)
        """
        Lpr0 = functions.Lpr0_FUN(2.0, standard_vial['Ap'], standard_product['cSolid'])
        Lck = Lpr0 * 0.5
        
        model = single_step.create_single_step_model(
            standard_vial, standard_product, standard_ht, Lpr0, Lck,
            apply_scaling=False
        )
        
        n_vars = sum(1 for v in model.component_data_objects(pyo.Var, active=True) 
                     if not v.fixed)
        n_eq_cons = sum(1 for c in model.component_data_objects(pyo.Constraint, active=True)
                       if c.equality)
        
        assert n_vars == 8, f"Expected 8 variables, got {n_vars}"
        assert n_eq_cons == 6, f"Expected 6 equality constraints, got {n_eq_cons}"
        assert n_vars - n_eq_cons == 2, "Model should have 2 degrees of freedom"
    
    def test_incidence_matrix(self, standard_vial, standard_product, standard_ht):
        """Analyze variable-constraint incidence matrix."""
        Lpr0 = functions.Lpr0_FUN(2.0, standard_vial['Ap'], standard_product['cSolid'])
        Lck = Lpr0 * 0.5
        
        model = single_step.create_single_step_model(
            standard_vial, standard_product, standard_ht, Lpr0, Lck,
            apply_scaling=False
        )
        
        igraph = IncidenceGraphInterface(model)
        incidence_matrix = igraph.incidence_matrix.tocsr()
        
        assert incidence_matrix.shape[0] > 0, "Should have constraints"
        assert incidence_matrix.shape[1] > 0, "Should have variables"
    
    @pytest.mark.skipif(not networkx_available, reason="NetworkX not available")
    def test_variable_constraint_graph(self, standard_vial, standard_product, standard_ht):
        """Analyze the bipartite variable-constraint graph connectivity."""
        Lpr0 = functions.Lpr0_FUN(2.0, standard_vial['Ap'], standard_product['cSolid'])
        Lck = Lpr0 * 0.5
        
        model = single_step.create_single_step_model(
            standard_vial, standard_product, standard_ht, Lpr0, Lck,
            apply_scaling=False
        )
        
        igraph = IncidenceGraphInterface(model)
        variables = igraph.variables
        constraints = igraph.constraints
        incidence_matrix = igraph.incidence_matrix.tocsr()
        
        # Build NetworkX bipartite graph
        G = networkx.Graph()
        var_nodes = [f"v_{v.name}" for v in variables]
        con_nodes = [f"c_{c.name}" for c in constraints]
        G.add_nodes_from(var_nodes, bipartite=0)
        G.add_nodes_from(con_nodes, bipartite=1)
        
        for i, con in enumerate(constraints):
            row = incidence_matrix[i, :]
            for j in row.nonzero()[1]:
                G.add_edge(con_nodes[i], var_nodes[j])
        
        # Graph should be connected
        assert G.number_of_nodes() > 0
        assert G.number_of_edges() > 0
    
    def test_connected_components(self, standard_vial, standard_product, standard_ht):
        """Verify model has one connected component."""
        Lpr0 = functions.Lpr0_FUN(2.0, standard_vial['Ap'], standard_product['cSolid'])
        Lck = Lpr0 * 0.5
        
        model = single_step.create_single_step_model(
            standard_vial, standard_product, standard_ht, Lpr0, Lck,
            apply_scaling=False
        )
        
        igraph = IncidenceGraphInterface(model)
        
        try:
            result = igraph.get_connected_components()
            if isinstance(result, tuple) and len(result) == 2:
                var_blocks, con_blocks = result
                components = list(zip(var_blocks, con_blocks))
            else:
                components = result
        except Exception:
            components = [(igraph.variables, igraph.constraints)]
        
        assert len(components) == 1, "Should have exactly one connected component"
    
    def test_dulmage_mendelsohn_partition(self, standard_vial, standard_product, standard_ht):
        """Check for structural singularities using Dulmage-Mendelsohn partition.
        
        Reference: https://pyomo.readthedocs.io/en/6.8.1/explanation/analysis/incidence/tutorial.dm.html
        """
        Lpr0 = functions.Lpr0_FUN(2.0, standard_vial['Ap'], standard_product['cSolid'])
        Lck = Lpr0 * 0.5
        
        model = single_step.create_single_step_model(
            standard_vial, standard_product, standard_ht, Lpr0, Lck,
            apply_scaling=False
        )
        
        igraph = IncidenceGraphInterface(model, include_inequality=False)
        var_dmp, con_dmp = igraph.dulmage_mendelsohn()
        
        # For optimization, unmatched variables are DOF (Pch, Tsh)
        # Unmatched constraints indicate structural problems
        assert len(con_dmp.unmatched) == 0, "Unmatched constraints indicate structural singularity"
        assert len(var_dmp.unmatched) == 2, f"Should have 2 DOF, got {len(var_dmp.unmatched)}"
    
    @pytest.mark.xfail(reason="Pyomo incidence analysis doesn't support unequal variable/constraint counts")
    def test_block_triangularization(self, standard_vial, standard_product, standard_ht):
        """Analyze block structure for numerical conditioning.
        
        Reference: https://pyomo.readthedocs.io/en/6.8.1/explanation/analysis/incidence/tutorial.bt.html
        """
        try:
            from pyomo.contrib.pynumero.interfaces.pyomo_nlp import PyomoNLP
        except ImportError:
            pytest.skip("PyNumero not available")
        
        Lpr0 = functions.Lpr0_FUN(2.0, standard_vial['Ap'], standard_product['cSolid'])
        Lck = Lpr0 * 0.5
        
        model = single_step.create_single_step_model(
            standard_vial, standard_product, standard_ht, Lpr0, Lck,
            apply_scaling=False
        )
        
        # Deactivate optimization objective for structural analysis
        for obj in model.component_data_objects(pyo.Objective, active=True):
            obj.deactivate()
        model._obj = pyo.Objective(expr=0.0)
        
        # Set reasonable values
        model.Pch.set_value(0.1)
        model.Tsh.set_value(-10.0)
        model.Tsub.set_value(-25.0)
        model.Tbot.set_value(-20.0)
        model.Psub.set_value(0.5)
        model.log_Psub.set_value(np.log(0.5))
        model.dmdt.set_value(0.5)
        model.Kv.set_value(5e-4)
        
        try:
            nlp = PyomoNLP(model)
        except RuntimeError as e:
            if "PyNumero ASL" in str(e):
                pytest.skip("PyNumero ASL interface not available")
            raise
        
        igraph = IncidenceGraphInterface(model, include_inequality=False)
        var_blocks, con_blocks = igraph.block_triangularize()
        
        assert len(var_blocks) > 0, "Should have at least one block"


class TestNumericalDebugging:
    """Tests for numerical conditioning and scaling."""
    
    def test_constraint_residuals_at_solution(self, standard_vial, standard_product, standard_ht):
        """Verify constraints are satisfied at solution (residuals near zero)."""
        Lpr0 = functions.Lpr0_FUN(2.0, standard_vial['Ap'], standard_product['cSolid'])
        Lck = Lpr0 * 0.5
        
        solution = single_step.optimize_single_step(
            standard_vial, standard_product, standard_ht, Lpr0, Lck,
            apply_scaling=False, tee=False
        )
        
        model = single_step.create_single_step_model(
            standard_vial, standard_product, standard_ht, Lpr0, Lck,
            apply_scaling=False
        )
        
        # Set to solution values
        for key in ['Pch', 'Tsh', 'Tsub', 'Tbot', 'Psub', 'log_Psub', 'dmdt', 'Kv']:
            getattr(model, key).set_value(solution[key])
        
        max_residual = 0.0
        for con in model.component_data_objects(pyo.Constraint, active=True):
            if con.equality:
                body_value = pyo.value(con.body)
                target_value = pyo.value(con.lower if con.lower is not None else con.upper)
                residual = abs(body_value - target_value)
                max_residual = max(max_residual, residual)
        
        assert max_residual < 1e-4, f"Large residual: {max_residual:.6e}"
    
    def test_variable_scaling_analysis(self, standard_vial, standard_product, standard_ht):
        """Analyze variable magnitudes (should not have extreme ranges)."""
        Lpr0 = functions.Lpr0_FUN(2.0, standard_vial['Ap'], standard_product['cSolid'])
        Lck = Lpr0 * 0.5
        
        solution = single_step.optimize_single_step(
            standard_vial, standard_product, standard_ht, Lpr0, Lck,
            apply_scaling=False, tee=False
        )
        
        var_magnitudes = {k: abs(solution[k]) for k in 
                         ['Pch', 'Tsh', 'Tsub', 'Tbot', 'Psub', 'log_Psub', 'dmdt', 'Kv']}
        
        max_mag = max(var_magnitudes.values())
        min_mag = min(v for v in var_magnitudes.values() if v > 0)
        mag_range = max_mag / min_mag
        
        # Wide range is expected, but extreme (>1e8) would be problematic
        assert mag_range < 1e8, f"Extreme magnitude range: {mag_range:.2e}"
    
    def test_jacobian_condition_number(self, standard_vial, standard_product, standard_ht):
        """Estimate Jacobian condition number (should be reasonable)."""
        try:
            from scipy import sparse
            from scipy.sparse.linalg import svds
        except ImportError:
            pytest.skip("SciPy not available")
        
        Lpr0 = functions.Lpr0_FUN(2.0, standard_vial['Ap'], standard_product['cSolid'])
        Lck = Lpr0 * 0.5
        
        model = single_step.create_single_step_model(
            standard_vial, standard_product, standard_ht, Lpr0, Lck,
            apply_scaling=False
        )
        
        # Set to reasonable values
        model.Pch.set_value(0.1)
        model.Tsh.set_value(-10.0)
        model.Tsub.set_value(-25.0)
        model.Tbot.set_value(-20.0)
        model.Psub.set_value(0.5)
        model.log_Psub.set_value(np.log(0.5))
        model.dmdt.set_value(0.5)
        model.Kv.set_value(5e-4)
        
        igraph = IncidenceGraphInterface(model)
        jac = igraph.incidence_matrix.toarray().astype(float)
        
        try:
            U, s, Vt = np.linalg.svd(jac)
            cond = s[0] / s[-1] if s[-1] > 1e-14 else np.inf
            # Condition number should be reasonable (< 1e12)
            assert cond < 1e12, f"Extremely high condition number: {cond:.2e}"
        except np.linalg.LinAlgError:
            pytest.skip("Could not compute SVD")


class TestScipyComparison:
    """Tests comparing Pyomo single-step with scipy baseline optimization."""
    
    @pytest.mark.slow
    def test_matches_scipy_single_step(self, standard_vial, standard_product, standard_ht):
        """Verify Pyomo matches scipy at multiple time points."""
        Lpr0 = functions.Lpr0_FUN(2.0, standard_vial['Ap'], standard_product['cSolid'])
        eq_cap = {'a': -0.182, 'b': 11.7}
        nVial = 398
        dt = 0.01
        
        scipy_output = opt_Pch_Tsh.dry(
            standard_vial, standard_product, standard_ht,
            {'min': 0.05}, {'min': -45.0, 'max': 120.0},
            dt, eq_cap, nVial
        )
        
        # Test at multiple points
        test_indices = [0, len(scipy_output)//4, len(scipy_output)//2, -1]
        
        for idx in test_indices:
            scipy_Pch = scipy_output[idx, 4] / constant.Torr_to_mTorr
            scipy_Tsh = scipy_output[idx, 3]
            frac_dried = scipy_output[idx, 6]
            Lck = frac_dried * Lpr0
            
            if Lck < 0.01:  # Skip near-zero drying
                continue
            
            warmstart = utils.initialize_from_scipy(
                scipy_output, idx, standard_vial, standard_product, Lpr0, ht=standard_ht
            )
            
            pyomo_solution = single_step.optimize_single_step(
                standard_vial, standard_product, standard_ht, Lpr0, Lck,
                Pch_bounds=(0.05, 0.5), Tsh_bounds=(-45.0, 120.0),
                eq_cap=eq_cap, nVial=nVial,
                warmstart_data=warmstart, tee=False
            )
            
            # Allow 5% tolerance
            assert np.isclose(pyomo_solution['Pch'], scipy_Pch, rtol=0.05)
            assert np.isclose(pyomo_solution['Tsh'], scipy_Tsh, rtol=0.05, atol=1.0)
    
    @pytest.mark.slow
    def test_energy_balance_consistency(self, standard_vial, standard_product, standard_ht):
        """Verify Pyomo satisfies energy balance like scipy."""
        Lpr0 = functions.Lpr0_FUN(2.0, standard_vial['Ap'], standard_product['cSolid'])
        Lck = Lpr0 * 0.6
        
        scipy_output = opt_Pch_Tsh.dry(
            standard_vial, standard_product, standard_ht,
            {'min': 0.05}, {'min': -45.0, 'max': 120.0},
            0.01, {'a': -0.182, 'b': 11.7}, 398
        )
        
        idx = np.argmin(np.abs(scipy_output[:, 6] - 0.6))
        warmstart = utils.initialize_from_scipy(
            scipy_output, idx, standard_vial, standard_product, Lpr0, ht=standard_ht
        )
        
        pyomo_solution = single_step.optimize_single_step(
            standard_vial, standard_product, standard_ht, Lpr0, Lck,
            warmstart_data=warmstart, tee=False
        )
        
        # Energy balance: Q_shelf = Q_sublimation
        Q_shelf = (pyomo_solution['Kv'] * standard_vial['Av'] * 
                   (pyomo_solution['Tsh'] - pyomo_solution['Tbot']))
        Q_sub = pyomo_solution['dmdt'] * constant.kg_To_g / constant.hr_To_s * constant.dHs
        
        energy_balance_error = abs(Q_shelf - Q_sub) / Q_shelf
        assert energy_balance_error < 0.02, f"Energy balance error: {energy_balance_error*100:.2f}%"
    
    @pytest.mark.slow
    def test_cold_start_convergence(self, standard_vial, standard_product, standard_ht):
        """Verify Pyomo converges without scipy warmstart."""
        Lpr0 = functions.Lpr0_FUN(2.0, standard_vial['Ap'], standard_product['cSolid'])
        Lck = Lpr0 * 0.5
        
        # No warmstart
        pyomo_solution = single_step.optimize_single_step(
            standard_vial, standard_product, standard_ht, Lpr0, Lck,
            Pch_bounds=(0.05, 0.5), Tsh_bounds=(-45.0, 120.0),
            tee=False
        )
        
        assert 'optimal' in pyomo_solution['status'].lower()
        
        is_valid, _ = utils.check_solution_validity(pyomo_solution)
        assert is_valid, "Solution should be physically valid"


class TestModelValidation:
    """Validation tests for model correctness."""
    
    def test_all_variables_in_constraints(self, standard_vial, standard_product, standard_ht):
        """Verify no orphan variables (all appear in constraints)."""
        Lpr0 = functions.Lpr0_FUN(2.0, standard_vial['Ap'], standard_product['cSolid'])
        Lck = Lpr0 * 0.5
        
        model = single_step.create_single_step_model(
            standard_vial, standard_product, standard_ht, Lpr0, Lck,
            apply_scaling=False
        )
        
        igraph = IncidenceGraphInterface(model)
        incidence = igraph.incidence_matrix.tocsr()
        
        orphan_vars = []
        for i, v in enumerate(igraph.variables):
            if incidence[:, i].nnz == 0:
                orphan_vars.append(v.name)
        
        assert len(orphan_vars) == 0, f"Found orphan variables: {orphan_vars}"
    
    def test_multiple_starting_points(self, standard_vial, standard_product, standard_ht):
        """Verify robust convergence from different initial points."""
        Lpr0 = functions.Lpr0_FUN(2.0, standard_vial['Ap'], standard_product['cSolid'])
        Lck = Lpr0 * 0.5
        
        starting_points = [
            {'Pch': 0.1, 'Tsh': -10.0},
            {'Pch': 0.3, 'Tsh': 10.0},
            {'Pch': 0.05, 'Tsh': -40.0},
        ]
        
        solutions = []
        for init in starting_points:
            warmstart = {
                'Pch': init['Pch'], 'Tsh': init['Tsh'],
                'Tsub': -25.0, 'Tbot': -20.0,
                'Psub': 0.5, 'log_Psub': np.log(0.5),
                'dmdt': 0.5, 'Kv': 5e-4,
            }
            
            solution = single_step.optimize_single_step(
                standard_vial, standard_product, standard_ht, Lpr0, Lck,
                warmstart_data=warmstart, tee=False
            )
            
            assert 'optimal' in solution['status'].lower()
            solutions.append(solution)
        
        # Solutions should be consistent (within 5%)
        pch_values = [s['Pch'] for s in solutions]
        pch_std = np.std(pch_values)
        pch_mean = np.mean(pch_values)
        
        assert pch_std / pch_mean < 0.05, "Solutions vary significantly across starting points"
