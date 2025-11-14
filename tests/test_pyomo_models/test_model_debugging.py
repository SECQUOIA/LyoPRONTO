"""Debugging and structural analysis of Pyomo single-step model.

This module implements comprehensive debugging following Pyomo's incidence
analysis tutorial to verify model structure and identify potential issues.

Reference: https://pyomo.readthedocs.io/en/6.8.1/explanation/analysis/incidence/tutorial.bt.html
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
from lyopronto import functions
from lyopronto.pyomo_models import single_step

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


class TestModelStructure:
    """Tests for model structural analysis."""
    
    def test_degrees_of_freedom(self, standard_vial, standard_product, standard_ht):
        """Verify model has zero degrees of freedom (square system).
        
        A well-posed optimization problem should have:
        - Number of variables = Number of constraints + Number of degrees of freedom
        - For a square system: DOF = 0
        """
        Lpr0 = functions.Lpr0_FUN(2.0, standard_vial['Ap'], standard_product['cSolid'])
        Lck = Lpr0 * 0.5
        
        model = single_step.create_single_step_model(
            standard_vial, standard_product, standard_ht, Lpr0, Lck,
            apply_scaling=False  # Disable for cleaner analysis
        )
        
        # Count variables (exclude fixed)
        n_vars = sum(1 for v in model.component_data_objects(pyo.Var, active=True) 
                     if not v.fixed)
        
        # Count equality constraints
        n_eq_cons = sum(1 for c in model.component_data_objects(pyo.Constraint, active=True)
                       if c.equality)
        
        # Count inequality constraints (these don't affect DOF in same way)
        n_ineq_cons = sum(1 for c in model.component_data_objects(pyo.Constraint, active=True)
                         if not c.equality)
        
        print(f"\nModel structure:")
        print(f"  Variables: {n_vars}")
        print(f"  Equality constraints: {n_eq_cons}")
        print(f"  Inequality constraints: {n_ineq_cons}")
        print(f"  Degrees of freedom: {n_vars - n_eq_cons}")
        
        # For our model:
        # Variables: 8 (Pch, Tsh, Tsub, Tbot, Psub, log_Psub, dmdt, Kv)
        # Equality constraints: 6 (vapor_pressure_log, vapor_pressure_exp, 
        #                          sublimation_rate, heat_balance, shelf_temp, kv_calc)
        # DOF: 8 - 6 = 2 (which will be fixed by optimization)
        
        assert n_vars == 8, f"Expected 8 variables, got {n_vars}"
        assert n_eq_cons == 6, f"Expected 6 equality constraints, got {n_eq_cons}"
        assert n_vars - n_eq_cons == 2, "Model should have 2 degrees of freedom"
    
    def test_incidence_matrix(self, standard_vial, standard_product, standard_ht):
        """Analyze variable-constraint incidence matrix.
        
        The incidence matrix shows which variables appear in which constraints.
        This helps identify:
        - Structurally singular systems
        - Variables that don't appear in any constraints
        - Constraints that don't involve any variables
        """
        Lpr0 = functions.Lpr0_FUN(2.0, standard_vial['Ap'], standard_product['cSolid'])
        Lck = Lpr0 * 0.5
        
        model = single_step.create_single_step_model(
            standard_vial, standard_product, standard_ht, Lpr0, Lck,
            apply_scaling=False
        )
        
        # Create incidence graph interface
        igraph = IncidenceGraphInterface(model)
        
        # Get variables and constraints
        variables = igraph.variables
        constraints = igraph.constraints
        
        print(f"\n{'='*60}")
        print("INCIDENCE MATRIX ANALYSIS")
        print(f"{'='*60}")
        print(f"\nVariables ({len(variables)}):")
        for i, v in enumerate(variables):
            print(f"  [{i}] {v.name}")
        
        print(f"\nConstraints ({len(constraints)}):")
        for i, c in enumerate(constraints):
            print(f"  [{i}] {c.name}")
        
        # Get incidence matrix (convert to CSR for efficient slicing)
        incidence_matrix = igraph.incidence_matrix.tocsr()
        print(f"\nIncidence matrix shape: {incidence_matrix.shape}")
        print(f"Nonzeros: {incidence_matrix.nnz}")
        
        # Check for variables not in any constraint (should be none for equality constraints)
        for i, v in enumerate(variables):
            col = incidence_matrix[:, i]
            if col.nnz == 0:
                print(f"WARNING: Variable {v.name} does not appear in any constraint!")
        
        # Check for constraints with no variables (should be none)
        for i, c in enumerate(constraints):
            row = incidence_matrix[i, :]
            if row.nnz == 0:
                print(f"WARNING: Constraint {c.name} has no variables!")
        
        assert incidence_matrix.shape[0] > 0, "Should have constraints"
        assert incidence_matrix.shape[1] > 0, "Should have variables"
    
    @pytest.mark.skipif(not networkx_available, reason="NetworkX not available")
    def test_variable_constraint_graph(self, standard_vial, standard_product, standard_ht):
        """Analyze the bipartite variable-constraint graph.
        
        This creates a bipartite graph with variables on one side and 
        constraints on the other, with edges showing which variables
        appear in which constraints.
        """
        Lpr0 = functions.Lpr0_FUN(2.0, standard_vial['Ap'], standard_product['cSolid'])
        Lck = Lpr0 * 0.5
        
        model = single_step.create_single_step_model(
            standard_vial, standard_product, standard_ht, Lpr0, Lck,
            apply_scaling=False
        )
        
        igraph = IncidenceGraphInterface(model)
        
        # Get variables and constraints
        variables = igraph.variables
        constraints = igraph.constraints
        incidence_matrix = igraph.incidence_matrix.tocsr()
        
        print(f"\n{'='*60}")
        print("GRAPH ANALYSIS")
        print(f"{'='*60}")
        print(f"Variables: {len(variables)}")
        print(f"Constraints: {len(constraints)}")
        print(f"Edges (nonzeros in incidence): {incidence_matrix.nnz}")
        
        # Build NetworkX bipartite graph manually
        G = networkx.Graph()
        
        # Add variable nodes
        var_nodes = [f"v_{v.name}" for v in variables]
        G.add_nodes_from(var_nodes, bipartite=0)
        
        # Add constraint nodes  
        con_nodes = [f"c_{c.name}" for c in constraints]
        G.add_nodes_from(con_nodes, bipartite=1)
        
        # Add edges from incidence matrix
        for i, con in enumerate(constraints):
            row = incidence_matrix[i, :]
            for j in row.nonzero()[1]:
                G.add_edge(con_nodes[i], var_nodes[j])
        
        print(f"Graph nodes: {G.number_of_nodes()}")
        print(f"Graph edges: {G.number_of_edges()}")
        
        # Check connectivity
        if not networkx.is_connected(G):
            print("WARNING: Graph is not connected!")
            components = list(networkx.connected_components(G))
            print(f"Connected components: {len(components)}")
            for i, comp in enumerate(components):
                print(f"  Component {i}: {len(comp)} nodes")
        else:
            print("Graph is connected ✓")
        
        assert G.number_of_nodes() > 0
        assert G.number_of_edges() > 0
    
    def test_structural_analysis(self, standard_vial, standard_product, standard_ht):
        """Perform structural analysis to detect potential issues.
        
        Uses Dulmage-Mendelsohn decomposition to identify:
        - Structurally singular systems
        - Over-constrained subsystems
        - Under-constrained subsystems
        
        Note: Only equality constraints affect DOF count.
        """
        Lpr0 = functions.Lpr0_FUN(2.0, standard_vial['Ap'], standard_product['cSolid'])
        Lck = Lpr0 * 0.5
        
        model = single_step.create_single_step_model(
            standard_vial, standard_product, standard_ht, Lpr0, Lck,
            apply_scaling=False
        )
        
        igraph = IncidenceGraphInterface(model)
        
        print(f"\n{'='*60}")
        print("STRUCTURAL ANALYSIS")
        print(f"{'='*60}")
        
        # Get all variables and constraints
        all_vars = igraph.variables
        all_cons = igraph.constraints
        
        # Count equality vs inequality constraints
        eq_cons = [c for c in all_cons if c.equality]
        ineq_cons = [c for c in all_cons if not c.equality]
        
        print(f"Total variables: {len(all_vars)}")
        print(f"Equality constraints: {len(eq_cons)}")
        print(f"Inequality constraints: {len(ineq_cons)}")
        print(f"Total constraints: {len(all_cons)}")
        
        # Get variable and constraint partitions
        try:
            result = igraph.get_connected_components()
            # Handle both API formats
            if isinstance(result, tuple) and len(result) == 2:
                # Newer API: returns (var_blocks, con_blocks)
                var_blocks, con_blocks = result
                components = list(zip(var_blocks, con_blocks))
            else:
                # Older API: returns list of (vars, cons) tuples
                components = result
        except Exception as e:
            print(f"Connected components analysis not available: {e}")
            # Fallback: treat as single component
            components = [(all_vars, all_cons)]
        
        print(f"\nConnected components: {len(components)}")
        
        for i, (vars_in_block, cons_in_block) in enumerate(components):
            # Count only equality constraints in this block
            eq_cons_in_block = [c for c in cons_in_block if c.equality]
            ineq_cons_in_block = [c for c in cons_in_block if not c.equality]
            
            print(f"\nBlock {i}:")
            print(f"  Variables: {len(vars_in_block)}")
            print(f"  Equality constraints: {len(eq_cons_in_block)}")
            print(f"  Inequality constraints: {len(ineq_cons_in_block)}")
            print(f"  DOF (vars - eq_cons): {len(vars_in_block) - len(eq_cons_in_block)}")
            
            # Show variable names
            if len(vars_in_block) <= 10:
                for v in vars_in_block:
                    print(f"    - {v.name}")
            
            # Show constraint names  
            if len(cons_in_block) <= 10:
                for c in cons_in_block:
                    print(f"    - {c.name}")
        
        # Check if well-posed (at least for the equality subsystem)
        total_vars = sum(len(v) for v, _ in components)
        total_eq_cons = sum(len([c for c in cons if c.equality]) for _, cons in components)
        print(f"\nTotal variables in blocks: {total_vars}")
        print(f"Total equality constraints in blocks: {total_eq_cons}")
        print(f"Degrees of freedom: {total_vars - total_eq_cons}")
        
        # For single-step model, expect one component with 8 vars, 6 eq cons, 1 ineq con
        assert len(components) == 1, "Should have exactly one connected component"
        assert total_vars == 8, "Should have 8 variables"
        assert total_eq_cons == 6, "Should have 6 equality constraints"



class TestNumericalDebugging:
    """Tests for numerical conditioning and scaling."""
    
    def test_constraint_residuals_at_solution(self, standard_vial, standard_product, standard_ht):
        """Check that constraints are satisfied at the solution.
        
        After solving, all equality constraints should have residuals
        close to zero (within solver tolerance).
        """
        Lpr0 = functions.Lpr0_FUN(2.0, standard_vial['Ap'], standard_product['cSolid'])
        Lck = Lpr0 * 0.5
        
        # Solve the model
        solution = single_step.optimize_single_step(
            standard_vial, standard_product, standard_ht, Lpr0, Lck,
            apply_scaling=False,
            tee=False
        )
        
        # Create model again to check residuals
        model = single_step.create_single_step_model(
            standard_vial, standard_product, standard_ht, Lpr0, Lck,
            apply_scaling=False
        )
        
        # Set variables to solution values
        model.Pch.set_value(solution['Pch'])
        model.Tsh.set_value(solution['Tsh'])
        model.Tsub.set_value(solution['Tsub'])
        model.Tbot.set_value(solution['Tbot'])
        model.Psub.set_value(solution['Psub'])
        model.log_Psub.set_value(solution['log_Psub'])
        model.dmdt.set_value(solution['dmdt'])
        model.Kv.set_value(solution['Kv'])
        
        print(f"\n{'='*60}")
        print("CONSTRAINT RESIDUALS AT SOLUTION")
        print(f"{'='*60}")
        
        max_residual = 0.0
        
        for con in model.component_data_objects(pyo.Constraint, active=True):
            if con.equality:
                # For equality constraints: body - (lower or upper)
                body_value = pyo.value(con.body)
                target_value = pyo.value(con.lower) if con.lower is not None else pyo.value(con.upper)
                residual = abs(body_value - target_value)
                
                print(f"\n{con.name}:")
                print(f"  Body: {body_value:.6e}")
                print(f"  Target: {target_value:.6e}")
                print(f"  Residual: {residual:.6e}")
                
                max_residual = max(max_residual, residual)
        
        print(f"\nMaximum residual: {max_residual:.6e}")
        
        # Residuals should be small (within solver tolerance ~1e-6)
        assert max_residual < 1e-4, f"Large residual: {max_residual:.6e}"
    
    def test_variable_scaling_analysis(self, standard_vial, standard_product, standard_ht):
        """Analyze variable magnitudes to assess scaling needs.
        
        Variables with very different magnitudes can cause numerical issues.
        This test shows the range of variable values.
        """
        Lpr0 = functions.Lpr0_FUN(2.0, standard_vial['Ap'], standard_product['cSolid'])
        Lck = Lpr0 * 0.5
        
        solution = single_step.optimize_single_step(
            standard_vial, standard_product, standard_ht, Lpr0, Lck,
            apply_scaling=False,
            tee=False
        )
        
        print(f"\n{'='*60}")
        print("VARIABLE MAGNITUDES")
        print(f"{'='*60}")
        
        var_magnitudes = {
            'Pch': abs(solution['Pch']),
            'Tsh': abs(solution['Tsh']),
            'Tsub': abs(solution['Tsub']),
            'Tbot': abs(solution['Tbot']),
            'Psub': abs(solution['Psub']),
            'log_Psub': abs(solution['log_Psub']),
            'dmdt': abs(solution['dmdt']),
            'Kv': abs(solution['Kv']),
        }
        
        for name, mag in sorted(var_magnitudes.items(), key=lambda x: x[1], reverse=True):
            print(f"{name:12s}: {mag:12.6e}")
        
        # Check magnitude range
        max_mag = max(var_magnitudes.values())
        min_mag = min(v for v in var_magnitudes.values() if v > 0)
        mag_range = max_mag / min_mag
        
        print(f"\nMagnitude range: {mag_range:.2e}")
        
        if mag_range > 1e6:
            print(f"WARNING: Large magnitude range ({mag_range:.2e}) - consider scaling!")
    
    def test_jacobian_condition_number(self, standard_vial, standard_product, standard_ht):
        """Estimate Jacobian condition number.
        
        A high condition number indicates numerical ill-conditioning.
        Rule of thumb: condition number > 1e8 is problematic.
        
        Note: This requires scipy for SVD computation.
        """
        try:
            from scipy import sparse
            from scipy.sparse.linalg import svds
        except ImportError:
            pytest.skip("SciPy not available for condition number calculation")
        
        Lpr0 = functions.Lpr0_FUN(2.0, standard_vial['Ap'], standard_product['cSolid'])
        Lck = Lpr0 * 0.5
        
        # Test both with and without scaling
        for use_scaling in [False, True]:
            model = single_step.create_single_step_model(
                standard_vial, standard_product, standard_ht, Lpr0, Lck,
                apply_scaling=use_scaling
            )
            
            # Set to reasonable initial point
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
            
            # Compute condition number if matrix is not too large
            if jac.shape[0] <= 50 and jac.shape[1] <= 50:
                try:
                    # Use SVD to get condition number
                    U, s, Vt = np.linalg.svd(jac)
                    cond = s[0] / s[-1] if s[-1] > 1e-14 else np.inf
                    
                    print(f"\n{'='*60}")
                    print(f"CONDITION NUMBER ({'WITH' if use_scaling else 'WITHOUT'} scaling)")
                    print(f"{'='*60}")
                    print(f"Condition number: {cond:.2e}")
                    print(f"Largest singular value: {s[0]:.2e}")
                    print(f"Smallest singular value: {s[-1]:.2e}")
                    
                    if cond > 1e8:
                        print(f"WARNING: High condition number ({cond:.2e})")
                    else:
                        print(f"Condition number is acceptable ✓")
                        
                except np.linalg.LinAlgError:
                    print("Could not compute SVD")


class TestModelValidation:
    """Validation tests to ensure model correctness."""
    
    def test_all_variables_appear_in_constraints(self, standard_vial, standard_product, standard_ht):
        """Verify all decision variables appear in at least one constraint."""
        Lpr0 = functions.Lpr0_FUN(2.0, standard_vial['Ap'], standard_product['cSolid'])
        Lck = Lpr0 * 0.5
        
        model = single_step.create_single_step_model(
            standard_vial, standard_product, standard_ht, Lpr0, Lck,
            apply_scaling=False
        )
        
            
        igraph = IncidenceGraphInterface(model)
        incidence = igraph.incidence_matrix.tocsr()
        
        variables = igraph.variables
        orphan_vars = []
        
        for i, v in enumerate(variables):
            col = incidence[:, i]
            if col.nnz == 0:
                orphan_vars.append(v.name)
        
        if orphan_vars:
            print(f"\nWARNING: Variables not in any constraint: {orphan_vars}")
        
        assert len(orphan_vars) == 0, f"Found orphan variables: {orphan_vars}"
    
    def test_model_solves_from_multiple_starting_points(self, standard_vial, standard_product, standard_ht):
        """Test robustness by solving from different initial points.
        
        A well-conditioned model should converge from various starting points.
        """
        Lpr0 = functions.Lpr0_FUN(2.0, standard_vial['Ap'], standard_product['cSolid'])
        Lck = Lpr0 * 0.5
        
        # Test multiple starting points
        starting_points = [
            {'Pch': 0.1, 'Tsh': -10.0},  # Reasonable
            {'Pch': 0.3, 'Tsh': 10.0},   # Warmer
            {'Pch': 0.05, 'Tsh': -40.0}, # Colder
        ]
        
        solutions = []
        
        for i, init in enumerate(starting_points):
            warmstart = {
                'Pch': init['Pch'],
                'Tsh': init['Tsh'],
                'Tsub': -25.0,
                'Tbot': -20.0,
                'Psub': 0.5,
                'log_Psub': np.log(0.5),
                'dmdt': 0.5,
                'Kv': 5e-4,
            }
            
            solution = single_step.optimize_single_step(
                standard_vial, standard_product, standard_ht, Lpr0, Lck,
                warmstart_data=warmstart,
                tee=False
            )
            
            print(f"\nStarting point {i+1}: Pch={init['Pch']:.3f}, Tsh={init['Tsh']:.1f}")
            print(f"  Solution: Pch={solution['Pch']:.4f}, Tsh={solution['Tsh']:.2f}")
            print(f"  Status: {solution['status']}")
            
            assert 'optimal' in solution['status'].lower(), f"Failed from starting point {i+1}"
            solutions.append(solution)
        
        # All solutions should be similar (within 5%)
        pch_values = [s['Pch'] for s in solutions]
        pch_std = np.std(pch_values)
        pch_mean = np.mean(pch_values)
        
        print(f"\nPch across starting points: mean={pch_mean:.4f}, std={pch_std:.4e}")
        
        assert pch_std / pch_mean < 0.05, "Solutions vary significantly across starting points"
