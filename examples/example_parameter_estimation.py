"""Estimate product resistance from the canonical measured temperature trace.

This maintained script uses the same reusable computation as the original
unknown-Rp documentation notebook. The inverse-temperature preprocessing and
SciPy parameter fit are implemented in ``original_workflow_parity``; this file
owns console presentation and optional generated outputs.

Run from the repository root with ``python examples/example_parameter_estimation.py``.
It writes a timestamped CSV and ``parameter_estimation_results.png`` under
``examples/outputs/``.
"""

from __future__ import annotations

import csv
import time
from pathlib import Path

import matplotlib.pyplot as plt

if __package__:
    from .original_workflow_parity import (
        TEMPERATURE_DATA,
        fit_unknown_rp_scipy,
        load_temperature_data,
        preprocess_unknown_rp,
    )
else:
    from original_workflow_parity import (
        TEMPERATURE_DATA,
        fit_unknown_rp_scipy,
        load_temperature_data,
        preprocess_unknown_rp,
    )


OUTPUT_DIR = Path(__file__).parent / "outputs"


def save_results(output, fit, output_dir: Path = OUTPUT_DIR) -> Path:
    """Write fitted parameters and the legacy trajectory to a CSV file."""
    output_dir.mkdir(exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S", time.localtime())
    csv_path = output_dir / f"lyopronto_parameter_estimation_{timestamp}.csv"
    with csv_path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["LyoPRONTO Parameter Estimation Results"])
        writer.writerow(["R0 [cm^2 hr Torr/g]", fit.R0])
        writer.writerow(["A1 [cm hr Torr/g]", fit.A1])
        writer.writerow(["A2 [1/cm]", fit.A2])
        writer.writerow(["Sum squared Rp residuals [(cm^2 hr Torr/g)^2]", fit.objective])
        writer.writerow([])
        writer.writerow(
            [
                "Time [hr]",
                "Sublimation Temperature [degC]",
                "Vial Bottom Temperature [degC]",
                "Shelf Temperature [degC]",
                "Chamber Pressure [mTorr]",
                "Sublimation Flux [kg/hr/m^2]",
                "Percent Dried [0-100]",
            ]
        )
        writer.writerows(output)
    return csv_path


def save_plot(
    output,
    product_resistance,
    time_exp,
    tbot_exp,
    output_dir: Path = OUTPUT_DIR,
) -> Path:
    """Plot measured/replayed temperature, resistance, flux, and drying progress."""
    output_dir.mkdir(exist_ok=True)
    figure, axes = plt.subplots(2, 2, figsize=(12, 9))
    axes[0, 0].plot(time_exp, tbot_exp, "k.", label="Measured")
    axes[0, 0].plot(output[:, 0], output[:, 2], "r-", label="Legacy replay")
    axes[0, 0].set(xlabel="Time [hr]", ylabel="Vial-bottom temperature [degC]")
    axes[0, 1].plot(product_resistance[:, 1], product_resistance[:, 2])
    axes[0, 1].set(
        xlabel="Cake length [cm]",
        ylabel="Product resistance [cm^2 hr Torr/g]",
    )
    axes[1, 0].plot(output[:, 0], output[:, 5])
    axes[1, 0].set(xlabel="Time [hr]", ylabel="Sublimation flux [kg/hr/m^2]")
    axes[1, 1].plot(output[:, 0], output[:, 6])
    axes[1, 1].set(xlabel="Time [hr]", ylabel="Percent dried [0-100]", ylim=(0, 105))
    for axis in axes.flat:
        axis.grid(alpha=0.3)
    axes[0, 0].legend()
    figure.tight_layout()
    png_path = output_dir / "parameter_estimation_results.png"
    figure.savefig(png_path, dpi=150, bbox_inches="tight")
    plt.close(figure)
    return png_path


def main() -> None:
    """Run the maintained legacy-preprocessing/SciPy-fit example."""
    time_exp, tbot_exp = load_temperature_data()
    output, product_resistance = preprocess_unknown_rp()
    fit = fit_unknown_rp_scipy(product_resistance)

    print(f"Measured input: {TEMPERATURE_DATA} ({len(time_exp)} points)")
    print("Estimated product-resistance parameters:")
    print(f"  R0 = {fit.R0:.8f} cm^2 hr Torr/g")
    print(f"  A1 = {fit.A1:.8f} cm hr Torr/g")
    print(f"  A2 = {fit.A2:.8f} 1/cm")
    print(f"  sum squared Rp residuals = {fit.objective:.8f}")

    csv_path = save_results(output, fit)
    png_path = save_plot(output, product_resistance, time_exp, tbot_exp)
    print(f"Saved {csv_path}")
    print(f"Saved {png_path}")


if __name__ == "__main__":
    main()
