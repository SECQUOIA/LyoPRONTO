# Pyomo Status

Pyomo support is optional and isolated under `lyopronto.pyomo_models`. It does
not change the legacy SciPy calculators or their public output arrays.

## Implemented

- `single_step.py` builds and solves one primary-drying optimization point with
  the legacy heat-transfer and mass-transfer equations.
- `trajectory.py` builds a multi-period primary-drying trajectory model over a
  fixed uniform time grid.
- Pyomo tests are marked `pyomo` and are skip-safe when Pyomo or IPOPT is not
  installed.

## Trajectory Discretization

The first trajectory implementation uses backward Euler for dried cake length:

```text
Lck[t] = Lck[t - 1] + dt * dLdt[t]
```

The model enforces the algebraic primary-drying physics at every time node:

- vapor pressure from sublimation-front temperature
- sublimation mass transfer
- frozen-layer heat balance
- shelf-to-vial energy balance
- pressure-dependent vial heat transfer
- optional product-temperature and equipment-capability limits

Chamber pressure, shelf temperature, dried cake length, temperatures,
sublimation rate, vapor pressure, and heat-transfer coefficient are time-indexed
Pyomo variables. Chamber-pressure and shelf-temperature profiles can be fixed
from legacy ramp schedules, or bounded and constrained by per-hour ramp limits.

The final dried target is represented as a lower bound on the final dried cake
fraction. Targets must remain below 100% because the frozen-layer heat balance
is singular when no frozen layer remains.

## Warmstarts

`trajectory_initialization_from_scipy_output` converts a legacy SciPy
trajectory table into Pyomo initial values. It converts pressure from mTorr to
Torr, sublimation flux to kg/hr/vial, and percent dried to cake length.

`apply_trajectory_warmstart` can apply that mapping, or any compatible indexed
mapping, to an existing trajectory model.

## Roadmap Planning

Future Pyomo planning remains in GitHub issue
[#80](https://github.com/SECQUOIA/LyoPRONTO/issues/80) and its child issues.
Keep this page focused on implemented behavior and current usage notes.
