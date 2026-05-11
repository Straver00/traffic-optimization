"""
benchmark.py — Compara controlador de tiempos fijos vs. adaptativo heurístico.

Uso:
    python evaluation/benchmark.py
    python evaluation/benchmark.py --duration 1800
    python evaluation/benchmark.py --skip-fixed   (solo corre adaptativo, reutiliza CSV fijo previo)

Salida:
    evaluation/results/escenario1_fixed_results.csv
    evaluation/results/escenario1_adaptive_results.csv
    evaluation/results/escenario1_comparison.json   ← tabla de variación (% de mejora)
    evaluation/results/escenario1_comparison.txt    ← reporte legible
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from simulation.traci_runner import run_simulation, OUTPUT_DIR


# ---------------------------------------------------------------------------
# Métricas que se comparan y su dirección de mejora
# ---------------------------------------------------------------------------

METRICS_TO_COMPARE = {
    "waiting_time_avg_s":   ("menor es mejor", "s"),
    "queue_length_avg_veh": ("menor es mejor", "veh"),
    "queue_length_max_veh": ("menor es mejor", "veh"),
    "speed_avg_ms":         ("mayor es mejor", "m/s"),
    "throughput_total_veh": ("mayor es mejor", "veh"),
    "co2_total_mg":         ("menor es mejor", "mg"),
}


def compute_comparison(fixed: dict, adaptive: dict) -> dict:
    """Calcula variación porcentual y determina si es mejora."""
    results = {}
    for metric, (direction, unit) in METRICS_TO_COMPARE.items():
        v_fixed    = fixed.get(metric, 0)
        v_adaptive = adaptive.get(metric, 0)

        if v_fixed == 0:
            pct = 0.0
        else:
            pct = ((v_adaptive - v_fixed) / v_fixed) * 100

        # "mejora" significa reducción si menor-es-mejor, aumento si mayor-es-mejor
        if direction == "menor es mejor":
            improved = pct < 0
        else:
            improved = pct > 0

        results[metric] = {
            "unit":       unit,
            "fixed":      round(v_fixed,    3),
            "adaptive":   round(v_adaptive, 3),
            "change_pct": round(pct,         2),
            "improved":   improved,
            "direction":  direction,
        }
    return results


def format_report(comparison: dict, fixed_summary: dict, adaptive_summary: dict) -> str:
    lines = [
        "=" * 65,
        "  Seminario - Escenario 1: Comparacion Tiempos Fijos vs. Adaptativo",
        "=" * 65,
        f"  Pasos registrados (fijo):       {fixed_summary.get('steps_recorded', '?')}",
        f"  Pasos registrados (adaptativo): {adaptive_summary.get('steps_recorded', '?')}",
        "",
        f"  {'Metrica':<28} {'Fijo':>10} {'Adapt.':>10} {'D%':>8}  {'OK?':>5}",
        "  " + "-" * 60,
    ]

    targets = {
        "waiting_time_avg_s":   ("<= -15 %", -15),
        "co2_total_mg":         ("<= -10 %", -10),
    }

    for metric, data in comparison.items():
        pct_str = f"{data['change_pct']:+.1f} %"
        ok_mark = "OK" if data["improved"] else "--"

        # Verificar meta mínima si aplica
        if metric in targets:
            label, threshold = targets[metric]
            if data["change_pct"] <= threshold:
                ok_mark = f"OK ({label})"
            else:
                ok_mark = f"NO (meta: {label})"

        name = metric.replace("_", " ").replace("avg", "prom.").replace("max", "max.")
        lines.append(
            f"  {name:<28} {data['fixed']:>9.2f} {data['adaptive']:>9.2f}"
            f" {pct_str:>8}  {ok_mark}"
        )

    lines += [
        "",
        "  Metas del PMV (Escenario 1):",
        "    * Tiempo de espera: -15 % minimo       <- ver waiting_time_avg_s",
        "    * Emisiones CO2:   -10 % a -15 %       <- ver co2_total_mg",
        "=" * 65,
    ]
    return "\n".join(lines)


def run_benchmark(duration: int = 3600, skip_fixed: bool = False) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    fixed_json    = OUTPUT_DIR / "escenario1_fixed_summary.json"
    adaptive_json = OUTPUT_DIR / "escenario1_adaptive_summary.json"

    # --- Tiempos fijos ---
    if skip_fixed and fixed_json.exists():
        print("[benchmark] Reutilizando resultados fijos existentes...")
        with open(fixed_json, encoding="utf-8") as f:
            fixed_summary = json.load(f)
    else:
        print("\n[benchmark] >> Corriendo simulacion con TIEMPOS FIJOS...")
        fixed_summary = run_simulation(mode="fixed", sim_duration_s=duration)

    # --- Adaptativo ---
    print("\n[benchmark] >> Corriendo simulacion con CONTROL ADAPTATIVO...")
    adaptive_summary = run_simulation(mode="adaptive", sim_duration_s=duration)

    # --- Comparación ---
    comparison = compute_comparison(fixed_summary, adaptive_summary)

    comp_json = OUTPUT_DIR / "escenario1_comparison.json"
    with open(comp_json, "w", encoding="utf-8") as f:
        json.dump({
            "fixed":      fixed_summary,
            "adaptive":   adaptive_summary,
            "comparison": comparison,
        }, f, indent=2, ensure_ascii=False)

    report = format_report(comparison, fixed_summary, adaptive_summary)
    print("\n" + report)

    comp_txt = OUTPUT_DIR / "escenario1_comparison.txt"
    comp_txt.write_text(report, encoding="utf-8")
    print(f"\n[benchmark] Reporte guardado -> {comp_txt}")
    print(f"[benchmark] JSON guardado     -> {comp_json}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seminario — Benchmark Escenario 1")
    parser.add_argument("--duration",   type=int,  default=3600,
                        help="Duración en segundos SUMO (default: 3600)")
    parser.add_argument("--skip-fixed", action="store_true",
                        help="Reutilizar CSV de tiempos fijos existente")
    args = parser.parse_args()
    run_benchmark(duration=args.duration, skip_fixed=args.skip_fixed)


if __name__ == "__main__":
    main()
