"""Pinned scientific reference scenario metadata.

These scenarios are intentionally compact summaries of the current scientific
workflows. Expected values come from the current implementation snapshot on
2026-06-14, after syncing to ``origin/main`` for issue #69. They are not new
model equations.
"""

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class ReferenceScenario:
    """Metadata and pinned values for a scientific reference scenario."""

    name: str
    category: str
    input_units: Mapping[str, str]
    output_units: Mapping[str, str]
    expected: Mapping[str, Any]
    tolerances: Mapping[str, float]
    tolerance_notes: Mapping[str, str]
    provenance: str


LEGACY_PRIMARY_DRYING_INPUT_UNITS = {
    "vial.Av": "cm^2",
    "vial.Ap": "cm^2",
    "vial.Vfill": "mL",
    "product.cSolid": "g/mL",
    "product.R0": "cm^2 hr Torr / g",
    "product.A1": "cm hr Torr / g",
    "product.A2": "1 / cm",
    "product.T_pr_crit": "degC, when provided",
    "ht.KC": "cal / s / K / cm^2",
    "ht.KP": "cal / s / K / cm^2 / Torr",
    "ht.KD": "dimensionless",
    "Pchamber.setpt": "Torr",
    "Pchamber.dt_setpt": "min",
    "Pchamber.ramp_rate": "Torr / min",
    "Tshelf.init": "degC",
    "Tshelf.setpt": "degC",
    "Tshelf.dt_setpt": "min",
    "Tshelf.ramp_rate": "degC / min",
    "dt": "hr",
}

LEGACY_PRIMARY_DRYING_OUTPUT_UNITS = {
    "time": "hr",
    "Tsub": "degC",
    "Tbot": "degC",
    "Tshelf": "degC",
    "Pchamber": "mTorr",
    "sublimation_flux": "kg / hr / m^2",
    "percent_dried": "%",
}

OPTIMIZER_EXTRA_INPUT_UNITS = {
    "Pchamber.min": "Torr",
    "Pchamber.max": "Torr",
    "Tshelf.min": "degC",
    "Tshelf.max": "degC",
    "eq_cap.a": "kg / hr",
    "eq_cap.b": "kg / hr / Torr",
    "nVial": "count",
}


REFERENCE_SCENARIOS = {
    "known_rp_primary_drying": ReferenceScenario(
        name="known-Rp primary drying",
        category="tolerance-based numerical solver regression",
        input_units=LEGACY_PRIMARY_DRYING_INPUT_UNITS,
        output_units=LEGACY_PRIMARY_DRYING_OUTPUT_UNITS,
        expected={
            "rows": 666,
            "drying_time_hr": 6.65,
            "max_tsub_c": -14.775995136695942,
            "max_tbot_c": -14.775132657774503,
            "final_tsh_c": 20.000000000000004,
            "pch_mtorr": 150.0,
            "max_flux_kg_hr_m2": 1.1318639867810498,
            "final_percent_dried": 99.95636353779062,
        },
        tolerances={
            "drying_time_hr": 0.01,
            "max_tsub_c": 1e-6,
            "max_tbot_c": 1e-6,
            "final_tsh_c": 1e-9,
            "pch_mtorr": 1e-9,
            "max_flux_kg_hr_m2": 1e-9,
            "final_percent_dried": 1e-9,
        },
        tolerance_notes={
            "drying_time_hr": "one integration output step for dt=0.01 hr",
            "temperature": "strict drift guard for deterministic legacy solver",
            "pressure": "constant pressure setpoint conversion guard",
            "flux_and_completion": "strict drift guard for deterministic output",
        },
        provenance=(
            "Current implementation snapshot for the web-interface primary "
            "drying case documented by test_data/reference_primary_drying.csv."
        ),
    ),
    "unknown_rp_estimation": ReferenceScenario(
        name="unknown-Rp estimation from temperature series",
        category="tolerance-based numerical estimation regression",
        input_units={
            **LEGACY_PRIMARY_DRYING_INPUT_UNITS,
            "temperature_data.time": "hr",
            "temperature_data.Tbot": "degC",
        },
        output_units={
            **LEGACY_PRIMARY_DRYING_OUTPUT_UNITS,
            "product_res.time": "hr",
            "product_res.Lck": "cm",
            "product_res.Rp": "cm^2 hr Torr / g",
            "fit.R0": "cm^2 hr Torr / g",
            "fit.A1": "cm hr Torr / g",
            "fit.A2": "1 / cm",
        },
        expected={
            "rows_output": 453,
            "rows_product_res": 453,
            "final_time_hr": 4.509673182,
            "final_percent_dried": 78.36059476265791,
            "final_Lck_cm": 0.5422089639410883,
            "final_Rp_cm2_hr_torr_g": 3.3821253189769926,
            "fit_R0": 0.020891238211435268,
            "fit_A1": 7.843343952386052,
            "fit_A2": 0.5081479992090868,
        },
        tolerances={
            "final_time_hr": 1e-9,
            "final_percent_dried": 1e-8,
            "final_Lck_cm": 1e-9,
            "final_Rp_cm2_hr_torr_g": 1e-8,
            "fit_R0": 5e-8,
            "fit_A1": 5e-8,
            "fit_A2": 5e-8,
        },
        tolerance_notes={
            "estimation_outputs": (
                "tight drift guard for deterministic temperature-series "
                "post-processing"
            ),
            "fit_parameters": "strict scipy curve_fit regression guard",
        },
        provenance=(
            "Current implementation snapshot using test_data/temperature.txt "
            "and the legacy unknown-Rp fitting workflow."
        ),
    ),
    "shelf_temperature_optimizer": ReferenceScenario(
        name="shelf-temperature optimizer",
        category="slow tolerance-based optimizer regression",
        input_units={
            **LEGACY_PRIMARY_DRYING_INPUT_UNITS,
            **OPTIMIZER_EXTRA_INPUT_UNITS,
        },
        output_units=LEGACY_PRIMARY_DRYING_OUTPUT_UNITS,
        expected={
            "rows": 214,
            "drying_time_hr": 2.1229609132911493,
            "max_tbot_c": -4.999999999999864,
            "max_tsh_c": 120.0,
            "pch_mtorr": 150.0,
            "max_flux_kg_hr_m2": 3.4579088693244953,
            "final_percent_dried": 100.0,
        },
        tolerances={
            "drying_time_hr": 1e-6,
            "max_tbot_c": 1e-6,
            "max_tsh_c": 1e-9,
            "pch_mtorr": 1e-9,
            "max_flux_kg_hr_m2": 1e-8,
            "final_percent_dried": 1e-9,
        },
        tolerance_notes={
            "optimizer_solution": "strict drift guard for deterministic optimizer path",
            "constraints": "temperature and pressure constraints should remain pinned",
        },
        provenance=(
            "Current implementation snapshot for the fixed-pressure optimizer "
            "case corresponding to test_data/reference_opt_Tsh.csv."
        ),
    ),
    "pressure_optimizer": ReferenceScenario(
        name="pressure optimizer",
        category="slow tolerance-based optimizer regression",
        input_units={
            **LEGACY_PRIMARY_DRYING_INPUT_UNITS,
            **OPTIMIZER_EXTRA_INPUT_UNITS,
        },
        output_units=LEGACY_PRIMARY_DRYING_OUTPUT_UNITS,
        expected={
            "rows": 425,
            "drying_time_hr": 4.238515035519084,
            "max_tbot_c": -4.999999999999997,
            "min_pch_mtorr": 50.0,
            "max_pch_mtorr": 1864.9085798268761,
            "max_flux_kg_hr_m2": 1.8235104103738298,
            "final_percent_dried": 100.0,
        },
        tolerances={
            "drying_time_hr": 1e-6,
            "max_tbot_c": 1e-6,
            "min_pch_mtorr": 1e-9,
            "max_pch_mtorr": 1e-6,
            "max_flux_kg_hr_m2": 1e-8,
            "final_percent_dried": 1e-9,
        },
        tolerance_notes={
            "optimizer_solution": "strict drift guard for deterministic optimizer path",
            "constraints": "pressure bounds and critical-temperature limit are pinned",
        },
        provenance=(
            "Current implementation snapshot for the stable pressure optimizer "
            "summary; reference_opt_Pch.csv is not compared elementwise because "
            "the existing tests document that fixture as poorly formulated."
        ),
    ),
    "freezing": ReferenceScenario(
        name="freezing",
        category="tolerance-based numerical solver regression",
        input_units={
            "vial.Av": "cm^2",
            "vial.Ap": "cm^2",
            "vial.Vfill": "mL",
            "product.Tpr0": "degC",
            "product.Tf": "degC",
            "product.Tn": "degC",
            "product.cSolid": "g/mL",
            "h_freezing": "W / m^2 / K",
            "Tshelf.init": "degC",
            "Tshelf.setpt": "degC",
            "Tshelf.dt_setpt": "min",
            "Tshelf.ramp_rate": "degC / min",
            "dt": "hr",
        },
        output_units={
            "time": "hr",
            "Tshelf": "degC",
            "Tproduct": "degC",
        },
        expected={
            "rows": 302,
            "final_time_hr": 2.99,
            "nucleation_time_hr": 0.42,
            "crystallization_start_hr": 0.42,
            "final_product_temp_c": -39.99999999994218,
            "final_shelf_temp_c": -40.0,
        },
        tolerances={
            "final_time_hr": 0.01,
            "nucleation_time_hr": 0.01,
            "crystallization_start_hr": 0.01,
            "final_product_temp_c": 1e-6,
            "final_shelf_temp_c": 1e-9,
        },
        tolerance_notes={
            "phase_times": "one output step for dt=0.01 hr",
            "temperatures": "strict drift guard after long final hold",
        },
        provenance=(
            "Current implementation snapshot matching the existing "
            "test_data/reference_freezing.csv case."
        ),
    ),
    "design_space": ReferenceScenario(
        name="design space 3x3 grid",
        category="tolerance-based design-space regression",
        input_units={
            **LEGACY_PRIMARY_DRYING_INPUT_UNITS,
            **OPTIMIZER_EXTRA_INPUT_UNITS,
            "design_space.Tshelf.setpt": "degC grid",
            "design_space.Pchamber.setpt": "Torr grid",
        },
        output_units={
            "shelf_results[0]": "degC, max product temperature",
            "shelf_results[1]": "hr, drying time",
            "shelf_results[2:4]": "kg / hr / m^2, sublimation flux summaries",
            "product_results[0]": "degC",
            "product_results[1]": "hr",
            "eq_cap_results[2]": "kg / hr / m^2",
        },
        expected={
            "shelf_shape": (5, 3, 3),
            "product_shape": (5, 2),
            "eq_shape": (3, 3),
            "shelf_Tmax_grid_c": (
                (-29.641483916834, -28.306572316177, -27.193598066213),
                (-25.583718459092, -24.251607009356, -23.133303153496),
                (-22.305465514782, -20.967983573797, -19.83954286939),
            ),
            "shelf_drying_time_grid_hr": (
                (24.57, 25.45, 26.63),
                (16.07, 15.66, 15.40),
                (11.76, 11.16, 10.70),
            ),
            "product_T_values_c": (-25.0, -25.0),
            "product_drying_time_values_hr": (10.77, 14.09),
            "eq_flux_values_kg_hr_m2": (
                3.224722337804,
                7.90577089268,
                12.586819447556,
            ),
        },
        tolerances={
            "shelf_Tmax_grid_c": 1e-9,
            "shelf_drying_time_grid_hr": 1e-9,
            "product_T_values_c": 1e-9,
            "product_drying_time_values_hr": 1e-9,
            "eq_flux_values_kg_hr_m2": 1e-9,
        },
        tolerance_notes={
            "grids": "strict drift guard for deterministic design-space summaries",
            "shapes": "exact grid topology guard",
        },
        provenance=(
            "Current implementation snapshot of the 3 shelf-temperature by "
            "3 chamber-pressure design-space grid."
        ),
    ),
    "typed_pikal": ReferenceScenario(
        name="typed Pikal workflow",
        category="Julia parity and typed solver regression",
        input_units={
            "Rp": "Pint quantity, cm^2 hr Torr / g family",
            "hf0": "Pint quantity, cm",
            "csolid": "Pint quantity, g / mL",
            "rho_solution": "Pint quantity, g / mL",
            "Kshf": "Pint quantity, cal / s / K / cm^2 family",
            "Av": "Pint quantity, cm^2",
            "Ap": "Pint quantity, cm^2",
            "pch": "Pint ramped variable, mTorr",
            "Tsh": "Pint ramped variable, K",
        },
        output_units={
            "drying_time": "hr",
            "tf": "degC",
            "hf": "cm",
            "legacy_percent_dried": "%",
            "legacy_flux": "kg / hr / m^2",
        },
        expected={
            "drying_time_hr": 44.54253207738847,
            "final_tf_c": -32.218671888920085,
            "final_hf_cm": 1.000000642188692e-10,
            "legacy_final_percent_dried": 99.99999999049668,
            "final_flux_kg_hr_m2": 0.19084197380576443,
        },
        tolerances={
            "drying_time_hr": 1e-6,
            "final_tf_c": 1e-6,
            "final_hf_cm": 1e-12,
            "legacy_final_percent_dried": 1e-8,
            "final_flux_kg_hr_m2": 1e-9,
        },
        tolerance_notes={
            "typed_solver": "strict drift guard for typed Pikal solver output",
            "legacy_adapter": "ensures typed output still maps to legacy columns",
        },
        provenance=(
            "Current implementation snapshot of the sucrose Pikal typed "
            "benchmark used as a Julia parity case."
        ),
    ),
    "typed_rf": ReferenceScenario(
        name="typed RF workflow",
        category="typed RF solver and energy-accounting regression",
        input_units={
            "Rp": "Pint quantity, cm^2 hr Torr / g family",
            "hf0": "Pint quantity, cm",
            "csolid": "Pint quantity, g / mL",
            "rho_solution": "Pint quantity, g / mL",
            "Kshf": "Pint quantity, cal / s / K / cm^2 family",
            "pch": "Pint ramped variable, mTorr",
            "Tsh": "Pint ramped variable, K",
            "P_per_vial": "Pint ramped variable, W / vial",
            "frequency": "Pint quantity, GHz",
            "RF coupling parameters": "Pint quantities, mixed SI and cgs",
        },
        output_units={
            "drying_time": "hr",
            "tf": "degC",
            "tvw": "degC",
            "mf": "g",
            "qrf_f": "W",
            "qrf_vw": "W",
            "QRFf": "Wh",
            "QRFvw": "Wh",
        },
        expected={
            "drying_time_hr": 14.34394713594476,
            "final_tf_c": -8.66540660668062,
            "final_tvw_c": 26.087654982289337,
            "final_mf_g": 4.9999999684786374e-08,
            "qrf_f_watt_initial": 0.004417549595616937,
            "qrf_vw_watt_initial": 0.10817810344244311,
            "QRFf_Wh": 0.04303919931006228,
            "QRFvw_Wh": 1.5517009970451676,
        },
        tolerances={
            "drying_time_hr": 1e-6,
            "final_tf_c": 1e-6,
            "final_tvw_c": 1e-6,
            "final_mf_g": 1e-12,
            "qrf_f_watt_initial": 1e-12,
            "qrf_vw_watt_initial": 1e-12,
            "QRFf_Wh": 1e-10,
            "QRFvw_Wh": 1e-10,
        },
        tolerance_notes={
            "typed_solver": "strict drift guard for typed RF solver output",
            "energy_accounting": "pins RF heat integration key results",
        },
        provenance=(
            "Current implementation snapshot of the synthetic typed RF workflow "
            "used by the RF solver and energy-accounting tests."
        ),
    ),
}
