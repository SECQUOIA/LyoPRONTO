# Pyomo-Based Optimization for LyoPRONTO

This directory contains Pyomo-based nonlinear programming (NLP) implementations for lyophilization process optimization. These provide an alternative to the scipy-based optimizers with more flexibility for advanced optimization scenarios.

## Overview

### Coexistence Philosophy

The Pyomo implementations **coexist** with scipy-based optimizers - they do not replace them. Both approaches are maintained and tested, allowing users to choose the most appropriate method for their application.

**When to use Scipy (default):**
- Quick design space exploration
- Single-vial optimization
- Production use (stable, well-tested)
- No external solver dependencies

**When to use Pyomo:**
- Advanced NLP features (multi-period, parameter estimation)
- Research applications requiring flexibility
- Integration with other Pyomo-based workflows
- Access to commercial solvers (SNOPT, KNITRO, etc.)

## Modules

### `optimizers.py`
Main user-facing optimizer functions (equivalent to scipy opt_Tsh, opt_Pch, opt_Pch_Tsh).

**Key functions:**
- `optimize_Tsh_pyomo()` - Optimize shelf temperature trajectory with fixed pressure
- `optimize_Pch_pyomo()` - Optimize chamber pressure trajectory with fixed temperature
- `optimize_Pch_Tsh_pyomo()` - Jointly optimize both pressure and temperature

**Features:**
- Multi-period optimization with collocation
- Equipment capability constraints
- Scipy warmstart support
- 4-stage convergence framework (staged_solve)
- SciPy trajectory residual checks and IPOPT replay helpers used by benchmarks

### `model.py`
Multi-period DAE model creation with orthogonal collocation on finite elements.

**Key functions:**
- `create_multi_period_model()` - Build dynamic optimization model
- `warmstart_from_scipy_trajectory()` - Initialize from scipy solution

**Model structure:**
- Time discretization via finite elements + collocation
- 7 decision variables per time point
- Differential-algebraic equations (DAE)
- Equipment capability constraints

### `single_step.py`
Single time-step optimization that replicates one step of the scipy sequential approach.

**Key functions:**
- `create_single_step_model()` - Build Pyomo ConcreteModel
- `solve_single_step()` - Solve model with IPOPT or other NLP solver
- `optimize_single_step()` - Convenience function (create + solve)

**Decision variables (7):**
- `Pch` - Chamber pressure [Torr]
- `Tsh` - Shelf temperature [°C]
- `Tsub` - Sublimation front temperature [°C]
- `Tbot` - Vial bottom temperature [°C]
- `Psub` - Vapor pressure [Torr]
- `dmdt` - Sublimation rate [kg/hr]
- `Kv` - Vial heat transfer coefficient [cal/s/K/cm²]

**Constraints:**
- 5 equality constraints (vapor pressure, sublimation rate, heat balance, etc.)
- 2 inequality constraints (product temperature limit, equipment capability)

**Objective:**
- Minimize `(Pch - Psub)` to maximize sublimation driving force

### `utils.py`
Utility functions for initialization, scaling, and validation.

**Key functions:**
- `initialize_from_scipy()` - Warmstart Pyomo from scipy solution
- `check_solution_validity()` - Validate physical constraints
- `add_scaling_suffix()` - Add scaling for numerical conditioning

### `paper_ocp.py`
Experimental paper-reference direct-transcription benchmark for the primary
drying OCP in Srisuma and Braatz, arXiv:2509.10826v1.

**Key functions:**
- `create_paper_problem1_model()` - Build the orthogonal-collocation Pyomo model
- `create_paper_problem2_model()` - Build Problem 2 with the interface-velocity constraint
- `solve_paper_problem1()` - Solve Paper Problem 1 with IPOPT
- `solve_paper_problem2()` - Solve Paper Problem 2 with IPOPT
- `generate_problem1_policy_initialization()` - Build a policy-based warm start
- `generate_problem2_policy_initialization()` - Build the Problem 2 Policy 3 -> Policy 1 -> Policy 2 warm start
- `initialize_paper_problem1_from_trajectory()` - Seed a model from a trajectory
- `load_upstream_matlab_trajectory()` - Read upstream MATLAB output saved to `.mat`
- `compare_paper_problem1_trajectories()` - Compare Pyomo and upstream metrics
- `classify_paper_policies()` - Infer active Policy 1/Policy 2/Policy 3 regions

This module uses SI/Kelvin units from the paper/upstream code and is separate
from LyoPRONTO's cm/Torr/degC production APIs. The supported validation target
for Problem 1 is the paper-reported scalar behavior: Policy 1 -> Policy 2, a
switch time near 2.4 h, and path-constraint satisfaction. Problem 2 adds the
240 K product-temperature limit, 260 K shelf-temperature upper bound, and
`2.8e-7 m/s` interface-velocity path constraint; the coarse validation tracks
the expected Policy 3 -> Policy 1 -> Policy 2 sequence.

The validated default solves use a coarse `n_z=5` mesh. For Problem 1, the
upstream paper's `n_z=20` spatial mesh is also covered by a slow validation test
using IPOPT acceptable termination (`acceptable_tol=1e-3`,
`acceptable_iter=5`).

An upstream `.mat` reference can be generated only when the local machine has a
compatible MATLAB/Python/GEKKO solver stack for
`PrakitrSrisuma/simDAE-optimalcontrol-lyo`. The paper reports MATLAB R2024b,
Python 3.10, GEKKO, and 64-bit Windows 11, but it does not pin the
GEKKO/APMonitor solver version; modern setups may still fail inside the
upstream GEKKO solve. Use this command as a best-effort diagnostic, not as the
primary validation gate:

```bash
python benchmarks/paper_problem1_reference.py generate \
  --upstream-root /home/bernalde/repos/simDAE-optimalcontrol-lyo \
  --output benchmarks/results/paper_problem1_upstream_reference.mat
```

The command writes batch-safe MATLAB wrappers outside the upstream clone and
requires MATLAB Python to import GEKKO for the upstream Policy 2 segment. A
future `--matlab-python` option could make interpreter selection easier, but it
would not by itself fix GEKKO/APMonitor solver crashes. If a known-good artifact
is available, compare it against a Pyomo solve with:

```bash
python benchmarks/paper_problem1_reference.py compare-pyomo \
  benchmarks/results/paper_problem1_upstream_reference.mat \
  --n-z 20 --nfe 12 --ncp 3
```

## Installation

### 1. Install Pyomo

```bash
pip install pyomo
```

### 2. Install a Nonlinear Solver

Pyomo requires an external NLP solver. The recommended solver is **IPOPT** (open-source):

#### Option A: Install via IDAES Extensions (Recommended)

```bash
pip install idaes-pse
idaes get-extensions
```

This installs IPOPT and other solvers in `~/.idaes/bin/`. No additional configuration needed!

#### Option B: Install IPOPT via Conda

```bash
conda install -c conda-forge ipopt
```

#### Option C: Install IPOPT Binary

Download precompiled binaries from:
- https://github.com/coin-or/Ipopt/releases

Place the `ipopt` executable in your system PATH.

#### Option D: Build IPOPT from Source

See: https://coin-or.github.io/Ipopt/INSTALL.html

### 3. Verify Installation

```python
import pyomo.environ as pyo

# Check if IPOPT is available
opt = pyo.SolverFactory('ipopt')
print(f"IPOPT available: {opt.available()}")
```

## Usage

### Basic Example

```python
from lyopronto import functions
from lyopronto.pyomo_models import single_step

# Define configuration
vial = {'Av': 3.80, 'Ap': 3.14}
product = {'R0': 1.4, 'A1': 16.0, 'A2': 0.0, 'T_pr_crit': -5.0}
ht = {'KC': 2.75e-4, 'KP': 8.93e-4, 'KD': 0.46}

# Calculate initial product length
Lpr0 = functions.Lpr0_FUN(2.0, 3.14, 0.05)
Lck = 0.5  # Current dried cake length [cm]

# Solve single-step optimization
solution = single_step.optimize_single_step(
    vial, product, ht, Lpr0, Lck,
    Pch_bounds=(0.05, 0.5),
    Tsh_bounds=(-50, 50),
    tee=True  # Show solver output
)

print(f"Optimal Pch: {solution['Pch']:.4f} Torr")
print(f"Optimal Tsh: {solution['Tsh']:.2f} °C")
```

### Advanced: Warmstart from Scipy

```python
from lyopronto import opt_Pch_Tsh
from lyopronto.pyomo_models import single_step, utils

# Run scipy optimization first
scipy_output = opt_Pch_Tsh.dry(vial, product, ht, Pch, Tsh, dt, eq_cap, nVial)

# Extract warmstart data for a specific time step
warmstart = utils.initialize_from_scipy(
    scipy_output,
    time_index=10,
    vial=vial,
    product=product,
    Lpr0=Lpr0
)

# Solve Pyomo with warmstart
model = single_step.create_single_step_model(vial, product, ht, Lpr0, Lck)
solution = single_step.solve_single_step(model, warmstart_data=warmstart)
```

### Running the Example Script

```bash
python examples/example_pyomo_optimizer.py
```

## Testing

Run Pyomo-specific tests:

```bash
# All Pyomo tests
pytest tests/test_pyomo_models/ -v

# Basic model creation (fast)
pytest tests/test_pyomo_models/test_model_single_step.py::TestSingleStepModel -v

# Solver tests (slow, requires IPOPT)
pytest tests/test_pyomo_models/test_model_single_step.py::TestSingleStepSolver -v -m slow
```

**Note:** Solver tests are marked as `@pytest.mark.slow` and require IPOPT to be installed.

## Troubleshooting

### "IPOPT not available"

**Solution:** Install IPOPT solver (see Installation section above)

### Solver fails to converge

**Try these approaches:**

1. **Use warmstart initialization:**
   ```python
   # Initialize from scipy solution
   warmstart = utils.initialize_from_scipy(...)
   solution = solve_single_step(model, warmstart_data=warmstart)
   ```

2. **Adjust solver options:**
   ```python
   # Modify single_step.py solve_single_step() or use direct solver access
   opt = pyo.SolverFactory('ipopt')
   opt.options['max_iter'] = 5000
   opt.options['tol'] = 1e-5
   results = opt.solve(model, tee=True)
   ```

3. **Check variable bounds:**
   - Ensure bounds are physically reasonable
   - Tighten bounds if convergence issues persist

4. **Enable scaling:**
   ```python
   from lyopronto.pyomo_models import utils
   utils.add_scaling_suffix(model)
   ```

### "Pyomo not found" import error

**Solution:** Install Pyomo
```bash
pip install pyomo
```

### Test failures

**Common causes:**
- IPOPT not installed (solver tests will fail)
- Numerical tolerance issues (adjust test tolerances)
- Different solver versions (results may vary slightly)

## Development Roadmap

### Phase 1: Single-Step Model ✅ (Current)
- [x] Basic Pyomo model structure
- [x] Constraint formulation
- [x] Solver integration (IPOPT)
- [x] Comparison tests vs scipy
- [x] Documentation and examples

### Phase 2: Multi-Period Optimization ✅
- [x] Time-discretized simultaneous optimization
- [x] ODE constraints with orthogonal collocation
- [x] Full trajectory optimization
- [x] Performance benchmarks vs scipy sequential
- [x] SciPy trajectory residual checks and IPOPT replay validation

### Phase 3: Advanced Features (Future)
- [ ] Parameter estimation (R0, A1, A2 from experimental data)
- [ ] Multi-vial batch optimization
- [ ] Robust optimization under uncertainty
- [ ] Design space generation

## Contributing

When contributing Pyomo code:

1. **Maintain coexistence** - Do not modify scipy modules
2. **Add tests** - Compare against scipy baseline
3. **Document** - Include NumPy-style docstrings
4. **Validate** - Ensure physical reasonableness of results

See [`CONTRIBUTING.md`](../../CONTRIBUTING.md) for general guidelines.

## References

- **Pyomo Documentation:** https://pyomo.readthedocs.io/
- **IPOPT Solver:** https://coin-or.github.io/Ipopt/
- **LyoPRONTO Architecture:** [`docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md)
- **Pyomo Roadmap:** [`docs/PYOMO_ROADMAP.md`](../../docs/PYOMO_ROADMAP.md)
- **Coexistence Philosophy:** [`docs/COEXISTENCE_PHILOSOPHY.md`](../../docs/COEXISTENCE_PHILOSOPHY.md)

## License

Same as LyoPRONTO - GNU General Public License v3.0 or later.
See [`LICENSE.txt`](../../LICENSE.txt) for details.
