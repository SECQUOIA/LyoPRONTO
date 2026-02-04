# LyoPRONTO Architecture

This document describes the high-level architecture of LyoPRONTO, a vial-scale lyophilization (freeze-drying) process simulator.

## Table of Contents
1. [System Overview](#system-overview)
2. [Module Structure](#module-structure)
3. [Data Flow](#data-flow)
4. [Current vs Target Architecture](#current-vs-target-architecture)
5. [Key Design Decisions](#key-design-decisions)

---

## System Overview

LyoPRONTO simulates pharmaceutical freeze-drying processes at the vial scale. It models two key phases:

1. **Freezing**: Solidification of the liquid formulation
2. **Primary Drying**: Sublimation of ice from the frozen product

The simulator uses fundamental heat and mass transfer equations to predict process behavior and optimize operating conditions.

### Core Capabilities
- ✅ Primary drying simulation with known product resistance (scipy)
- ✅ Primary drying simulation with unknown resistance (scipy, parameter fitting)
- ✅ Optimization of chamber pressure and/or shelf temperature (scipy)
- ✅ Design space generation (scipy-based)
- 🚧 Freezing phase simulation (partial)
- 🎯 Multi-period simultaneous optimization with Pyomo (planned - will coexist with scipy)

---

## Module Structure

```
lyopronto/
├── functions.py          # Core physics equations (no dependencies)
├── constant.py           # Physical constants and conversions
├── calc_knownRp.py       # Primary drying simulator (known Rp, scipy)
├── calc_unknownRp.py     # Primary drying simulator (unknown Rp, scipy)
├── opt_Pch_Tsh.py        # Optimize both Pch and Tsh (scipy)
├── opt_Pch.py            # Optimize Pch only (scipy)
├── opt_Tsh.py            # Optimize Tsh only (scipy)
├── design_space.py       # Design space generator (scipy)
├── freezing.py           # Freezing phase calculations
└── pyomo_models/         # Pyomo-based optimization (PLANNED)
    ├── __init__.py
    ├── single_step.py    # Single time-step optimization
    ├── multi_period.py   # Full trajectory optimization
    └── utils.py          # Pyomo helper functions

tests/
├── conftest.py           # Shared test fixtures and helpers
├── test_functions.py     # Unit tests for functions.py
├── test_calculators.py   # Integration tests for calculators (scipy)
├── test_pyomo_models.py  # Tests for Pyomo models (PLANNED)
└── test_regression.py    # Regression and consistency tests
```

### Dependency Graph

```
constant.py (no dependencies)
    ↓
functions.py (depends on: constant)
    ↓
    ├─→ calc_knownRp.py (depends on: functions, constant)
    ├─→ calc_unknownRp.py (depends on: functions, constant)
    ├─→ freezing.py (depends on: functions, constant)
    └─→ opt_*.py (depends on: functions, constant, calc_knownRp)
            ↓
        design_space.py (depends on: opt_*)
```

### Module Descriptions

#### `constant.py`
**Purpose**: Define physical constants and unit conversions

**Key Constants**:
- `dHs = 678` cal/g - Heat of sublimation for ice
- `k_ice = 0.0059` cal/cm/s/K - Thermal conductivity of ice
- `rho_ice = 0.918` g/mL - Density of ice
- `Torr_to_mTorr = 1000` - Pressure conversion

**No dependencies**, pure data module.

---

#### `functions.py`
**Purpose**: Core physics functions for lyophilization modeling

**Key Functions**:
- `Vapor_pressure(T)` - Antoine equation for water vapor pressure
- `Lpr0_FUN(Vfill, Ap, rho_solid)` - Initial product fill height
- `Rp_FUN(Lck, R0, A1, A2)` - Product resistance (mass transfer)
- `Kv_FUN(Pch, Lck, KC, KP, KD)` - Vial heat transfer coefficient
- `sub_rate(...)` - Sublimation rate calculation
- `T_sub_solver_FUN(...)` - Implicit solver for sublimation temperature
- `calc_step(...)` - Calculate state at a single time point
- `fill_output(...)` - Format results with unit conversions

**Dependencies**: `constant`, `scipy.optimize.fsolve`, `numpy`

**Design Philosophy**: Pure functions, no side effects, fully testable

---

#### `calc_knownRp.py`
**Purpose**: Primary drying simulator when product resistance parameters (R0, A1, A2) are known

**Main Function**: `dry(vial, product, Pch, Tsh, Tstep=100)`

**Inputs**:
- `vial` (dict): Geometry (Av, Ap, Vfill)
- `product` (dict): Properties (R0, A1, A2, rho_solid)
- `Pch` (float): Chamber pressure (Torr)
- `Tsh` (float): Shelf temperature (°C)
- `Tstep` (int): Number of time points for output

**Output**: numpy array (n, 7) with columns:
1. time (hr)
2. Tsub (°C)
3. Tbot (°C)
4. Tsh (°C)
5. Pch (mTorr)
6. flux (kg/hr/m²)
7. percent_dried (0-100%)

**Method**: Uses `scipy.integrate.solve_ivp` with BDF method to integrate the ODE:
```
dL/dt = f(L, t)  where L is ice layer thickness
```

**Dependencies**: `functions`, `constant`, `scipy.integrate`, `numpy`

---

#### `calc_unknownRp.py`
**Purpose**: Primary drying simulator when resistance is unknown; heat transfer parameters (KC, KP, KD) are provided instead

**Similar to** `calc_knownRp.py` but uses different parameter set

**Status**: Partially tested (11% coverage)

---

#### `opt_Pch_Tsh.py`
**Purpose**: Optimize both chamber pressure (Pch) and shelf temperature (Tsh) to minimize drying time

**Main Function**: `optimize(vial, product, constraints)`

**Method**: 
- Uses `scipy.optimize.minimize` with sequential quadratic programming (SLSQP)
- At each optimization step, calls `calc_knownRp.dry()` to simulate full drying cycle
- Objective: minimize total drying time
- Constraints: maximum product temperature, pressure bounds, temperature bounds

**Current Limitations**:
- **Sequential optimization**: Optimizes at each time step independently
- **Computationally expensive**: Full simulation per function evaluation
- **Local optimum**: May not find global optimum

**Target**: Replace with Pyomo NLP for simultaneous optimization across all time periods

---

#### `opt_Pch.py` and `opt_Tsh.py`
**Purpose**: Single-variable optimization (pressure only or temperature only)

**Similar to** `opt_Pch_Tsh.py` but with one degree of freedom

---

#### `design_space.py`
**Purpose**: Generate design space (map of feasible operating conditions)

**Method**: Grid search over Pch and Tsh, evaluating constraints at each point

**Status**: Partially tested (14% coverage)

---

#### `freezing.py`
**Purpose**: Simulate freezing phase (solidification)

**Status**: Partially implemented (19% coverage)

---

## Data Flow

### Typical Simulation Flow

```
User Input
  ├─ Vial geometry (Av, Ap, Vfill)
  ├─ Product properties (R0, A1, A2, rho_solid)
  └─ Process conditions (Pch, Tsh)
    ↓
  [calc_knownRp.dry()]
    ↓
  Initialize: L0 = Lpr0 (full ice layer)
    ↓
  ┌─────────────────────────┐
  │  Integration Loop       │
  │  (scipy.integrate)      │
  │                         │
  │  At each time point:    │
  │  1. Calculate state     │ ← [calc_step()]
  │     - Rp from Lck       │ ← [Rp_FUN()]
  │     - Kv from Pch, Lck  │ ← [Kv_FUN()]
  │     - Solve for Tsub    │ ← [T_sub_solver_FUN()]
  │     - Calculate dmdt    │ ← [sub_rate()]
  │  2. Compute dL/dt       │
  │  3. Check if done       │
  │     (L ≤ 0?)            │
  └─────────────────────────┘
    ↓
  Format output with unit conversions
    ↓
  Return: numpy array (n, 7)
```

### Physics at Each Time Step

```
Given: Pch, Tsh, L (ice thickness)

1. Product Resistance
   Lck = Lpr0 - L              [dried cake thickness]
   Rp = R0 + A1*Lck/(1+A2*Lck) [mass transfer resistance]

2. Heat Transfer Coefficient
   Kv = KC + KP*Pch + KD*Lck   [heat transfer to vial]

3. Energy Balance (implicit in Tsub)
   Q_in = Kv * Av * (Tsh - Tbot)     [heat from shelf]
   Q_out = dmdt * dHs                [heat for sublimation]
   Q_in = Q_out                      [steady state]

4. Mass Transfer
   Psub = f(Tsub)                    [vapor pressure at sublimation front]
   dmdt = Ap/Rp * (Psub - Pch)       [sublimation rate]

5. Integration
   dL/dt = -dmdt / (rho_ice * Ap)    [ice layer shrinks]
```

### Optimization Flow (Current - scipy)

```
User Input
  ├─ Vial and product specs
  └─ Constraints (T_max, Pch_min, Pch_max, etc.)
    ↓
  [opt_Pch_Tsh.optimize()]
    ↓
  Initial guess: (Pch_0, Tsh_0)
    ↓
  ┌─────────────────────────────────┐
  │  Optimization Loop              │
  │  (scipy.optimize.minimize)      │
  │                                 │
  │  At each iteration:             │
  │  1. Current guess: (Pch, Tsh)   │
  │  2. Run full simulation         │ ← [calc_knownRp.dry()]
  │  3. Extract drying time         │
  │  4. Check constraints           │
  │     (T_max, bounds, etc.)       │
  │  5. Update guess                │
  └─────────────────────────────────┘
    ↓
  Return: optimal (Pch, Tsh, time)
```

**Problem**: Simulates entire drying cycle at each optimization iteration (expensive!)

---

## Scipy vs Pyomo: Two Complementary Approaches

**Important**: LyoPRONTO provides **two alternative optimization approaches** that coexist in the codebase. Users can choose the one that fits their needs.

### Scipy Approach (Current - Proven)

**Location**: `lyopronto/opt_*.py`, `calc_*.py`

**Approach**: Sequential optimization
- At each time step, solve optimization independently
- Use result as initial guess for next step
- Time steps are decoupled

**Advantages**:
- ✅ Simple to implement
- ✅ Proven convergence with scipy.optimize
- ✅ No complex dependencies

**Limitations**:
- ⚠️ Computationally expensive (O(n) simulations per optimization)
- ⚠️ Cannot optimize time-varying control strategies
- ⚠️ May miss global optimum
- ⚠️ No guarantee of dynamic feasibility

**Use Cases**:
- ✅ Single-vial optimization with constant setpoints
- ✅ Quick design space exploration
- ✅ Well-understood formulations
- ✅ Production runs (proven, reliable)

---

### Pyomo Approach (Planned - Advanced)

**Location**: `lyopronto/pyomo_models/` (to be created)

**Approach**: Simultaneous optimization
- Formulate entire drying process as single NLP
- All time periods optimized together
- Constraints link time steps

**Advantages**:
- ✅ Finds better optima (global with good initialization)
- ✅ Can optimize time-varying control (Pch(t), Tsh(t))
- ✅ Enforces dynamic constraints explicitly
- ✅ More efficient for complex multi-objective problems
- ✅ Enables parameter estimation and robust optimization

**Challenges**:
- ⚠️ Requires careful model formulation
- ⚠️ Numerical stability (exp, log, implicit equations)
- ⚠️ Initialization critical for convergence
- ⚠️ Debugging more complex
- ⚠️ Requires additional dependencies (Pyomo, IPOPT)

**Use Cases**:
- ✅ Multi-vial batch optimization
- ✅ Time-varying control policies
- ✅ Parameter estimation from experimental data
- ✅ Robust optimization under uncertainty
- ✅ Research and advanced development

---

### Integration Roadmap

See `PYOMO_ROADMAP.md` for detailed 10-week plan. Key phases:

**Phase 1** (Weeks 1-2): Single time-step Pyomo model
- Create alongside scipy (not replacing)
- Validate against scipy baseline
- Build test infrastructure

**Phase 2** (Weeks 3-5): Multi-period formulation
- Discretize time domain
- Add dynamic constraints
- Implement warmstart from scipy

**Phase 3** (Weeks 6-8): Advanced features
- Time-varying control policies
- Multi-vial optimization
- Robust optimization

**Phase 4** (Weeks 9-10): Integration and validation
- Provide unified API for both scipy and Pyomo
- Performance benchmarking and comparison
- Documentation and examples showing both approaches

---

## Key Design Decisions

### 1. Pure Function Design (`functions.py`)

**Decision**: All physics functions are pure (no side effects)

**Rationale**:
- Testability: Easy to write unit tests
- Composability: Functions can be combined freely
- Reusability: Can use in scipy, Pyomo, or other frameworks
- Debugging: No hidden state to track

**Example**:
```python
# Pure function - always same output for same input
Psub = Vapor_pressure(Tsub)

# Not: class with state that must be managed
# self.Psub = self.calculate_vapor_pressure()
```

### 2. Output Format with Unit Conversions

**Decision**: Convert units in output (Pch → mTorr, dried → percentage)

**Rationale**:
- Internal calculations use Torr (cleaner equations)
- Output uses mTorr (common in industry)
- Percentage 0-100 is human-readable
- All conversions in one place (`fill_output()` / `calc_step()`)

**Trade-off**: Requires careful attention to units when parsing output

### 3. ODE Integration with Events

**Decision**: Use `solve_ivp` with termination event (L=0)

**Rationale**:
- Adaptive time stepping (efficient)
- Event detection (stops exactly at completion)
- BDF method (good for stiff equations)
- Standard scipy interface

**Alternative considered**: Fixed time step integration (simpler but less efficient)

### 4. Implicit Solver for Temperature

**Decision**: Use `fsolve` to solve energy balance implicitly for Tsub

**Rationale**:
- Energy balance is implicit in Tsub (Psub = f(Tsub) → dmdt → Q_out)
- More robust than iterative approximation
- Converges reliably with good initial guess

**Challenge for Pyomo**: Need to reformulate as explicit constraint (see examples)

### 5. Test-Driven Development

**Decision**: Write tests before Pyomo implementation

**Rationale**:
- Validates scipy baseline behavior
- Defines acceptance criteria for Pyomo
- Prevents regressions
- Documents expected behavior

**Result**: 53 tests, 100% passing, before starting Pyomo work

### 6. Modular Optimization

**Decision**: Separate optimization (`opt_*.py`) from simulation (`calc_*.py`)

**Rationale**:
- Single Responsibility Principle
- Can swap optimizers without changing simulator
- Easier to test and debug
- Clear interface between components

**Integration plan**: Keep scipy simulators/optimizers, add Pyomo models in parallel module

### 7. Dictionary-Based Configuration

**Decision**: Use dictionaries for vial and product specifications

**Rationale**:
- Flexible (easy to add parameters)
- Self-documenting (keys are parameter names)
- Easy to serialize (JSON, YAML)
- Python idiomatic

**Example**:
```python
vial = {
    'Av': 3.14,      # cm²
    'Ap': 2.86,      # cm²
    'Vfill': 3.0,    # mL
}
```

**Alternative considered**: Classes or namedtuples (more structured but less flexible)

---

## System Boundaries and Assumptions

### What LyoPRONTO Models

✅ **Heat transfer**:
- Shelf → Vial bottom (conduction/radiation)
- Vial bottom → Sublimation front (conduction through ice and dried cake)

✅ **Mass transfer**:
- Sublimation at ice-vapor interface
- Vapor transport through dried cake (resistance Rp)
- Vapor removal by vacuum system (controlled Pch)

✅ **Product resistance**:
- Depends on dried cake thickness
- Characterized by parameters R0, A1, A2

### What LyoPRONTO Does NOT Model

❌ **Multi-vial effects**:
- Edge vials vs center vials
- Radiation between vials
- Chamber-scale gradients

❌ **Secondary drying**:
- Desorption of bound water
- Residual moisture dynamics

❌ **Product structure**:
- Pore size distribution
- Cake collapse
- Morphology changes

❌ **Equipment dynamics**:
- Shelf temperature control dynamics
- Pressure control dynamics
- Transients between steps

These are intentional simplifications to keep the model tractable while capturing the dominant physics.

---

## Performance Characteristics

### Typical Runtimes (scipy-based)

| Operation | Time | Notes |
|-----------|------|-------|
| Single simulation | ~0.1-1 s | Depends on Tstep |
| Optimization (2 vars) | ~10-60 s | Depends on convergence |
| Parametric study (5×5 grid) | ~2-5 min | 25 simulations |
| Design space (10×10 grid) | ~10-30 min | 100 simulations |

### Expected with Pyomo

| Operation | Expected Time | Notes |
|-----------|---------------|-------|
| Single step optimization | ~0.5-2 s | First solve |
| Multi-period (warmstart) | ~2-10 s | With scipy init |
| Time-varying control | ~5-30 s | Depends on periods |

**Note**: Pyomo expected to be faster for complex optimizations due to simultaneous approach, but slower for simple single-step problems due to overhead.

---

## Extension Points

Future developers can extend LyoPRONTO in these directions:

### 1. New Physics Models
Add to `functions.py`:
- Non-linear vial heat transfer
- Temperature-dependent product resistance
- Anisotropic thermal conductivity

### 2. New Simulators
Create new `calc_*.py` modules:
- Secondary drying
- Annealing phase
- Multi-stage processes

### 3. New Optimizers
Create new `opt_*.py` modules:
- Multi-objective optimization
- Robust optimization (uncertainty)
- Real-time optimization

### 4. New Outputs
Extend `fill_output()`:
- Additional state variables
- Derived quantities (e.g., energy consumption)
- Different unit systems

### 5. Pyomo Features
Enhance Pyomo models:
- Complementarity constraints
- Integer variables (discrete decisions)
- Stochastic programming

---

## References

For more details:
- **Testing**: See `tests/README.md`
- **Pyomo Transition**: See `PYOMO_ROADMAP.md`
- **Code Examples**: See `examples/README.md`
- **Physics Details**: See `PHYSICS_REFERENCE.md`
- **Getting Started**: See `GETTING_STARTED.md`

---

## Questions?

When making architectural decisions:
1. **Preserve modularity** - Keep functions pure and composable
2. **Maintain test coverage** - Write tests for new features
3. **Document assumptions** - Be explicit about what's modeled
4. **Profile performance** - Measure before optimizing
5. **Plan for extension** - Design for future enhancements
