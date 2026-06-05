"""
benchmark_2x2.py — Benchmark Escenario 2: red 2×2 con 4 intersecciones.

Modos comparados: tiempos fijos | heurístico (4 controladores) | DQN (4 agentes)

Salida:
    evaluation/results/escenario2_fixed_summary.json
    evaluation/results/escenario2_adaptive_summary.json
    evaluation/results/escenario2_dqn_summary.json
    evaluation/results/escenario2_comparison.json
    evaluation/results/escenario2_comparison.txt
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from simulation.traci_runner import find_binary, setup_traci
from simulation.rl_env_2x2 import _ensure_net_file_2x2, NET_FILE_2x2, ROUTE_FILE_2x2
from decision.traffic_config import TRAFFIC_LIGHTS_2x2, EDGES_2x2
from evaluation.metrics import MetricsCollector

OUTPUT_DIR = ROOT / "evaluation" / "results"

METRICAS_COMPARAR = {
    "espera_prom_s":        ("menor es mejor", "s"),
    "cola_prom_veh":        ("menor es mejor", "veh"),
    "cola_max_veh":         ("menor es mejor", "veh"),
    "velocidad_prom_ms":    ("mayor es mejor", "m/s"),
    "throughput_total_veh": ("mayor es mejor", "veh"),
    "co2_total_mg":         ("menor es mejor", "mg"),
    "efecto_rebote_veh":    ("menor es mejor", "veh"),
}


# ---------------------------------------------------------------------------
# Función de simulación 2×2
# ---------------------------------------------------------------------------

def ejecutar_simulacion_2x2(
    modo: str,
    duracion_s: int = 3600,
    model_path: str | None = None,
) -> dict:
    """
    Corre una simulación completa en la red 2×2 y devuelve el resumen.

    Args:
        modo:       "fixed" | "adaptive" | "dqn"
        duracion_s: duración en segundos SUMO
        model_path: prefijo de ruta de checkpoints DQN (sin _J0.pt)
    """
    setup_traci()
    try:
        import traci  # type: ignore
    except ImportError:
        sys.exit("[benchmark_2x2] Módulo traci no encontrado.")

    from decision.adaptive_controller import AdaptiveController

    _ensure_net_file_2x2()

    binario = find_binary("sumo")
    if not binario:
        sys.exit("[benchmark_2x2] Binario SUMO no encontrado.")

    sumo_cmd = [
        binario,
        "-n", str(NET_FILE_2x2),
        "-r", str(ROUTE_FILE_2x2),
        "--no-step-log",
        "--time-to-teleport", "-1",
        "--quit-on-end",
    ]

    print(f"\n[benchmark_2x2] Corriendo modo: {modo.upper()}")
    traci.start(sumo_cmd)

    # Colectores y controladores por intersección
    colectores: dict[str, MetricsCollector] = {
        tl: MetricsCollector(traci, tl_id=tl, mode=modo)
        for tl in TRAFFIC_LIGHTS_2x2
    }

    if modo == "dqn":
        from decision.dqn_controller import DQNController
        controladores = {
            tl: DQNController(
                traci, tl_id=tl, mode=modo,
                model_path=f"{model_path}_{tl}.pt" if model_path else None,
            )
            for tl in TRAFFIC_LIGHTS_2x2
        }
    else:
        controladores = {
            tl: AdaptiveController(traci, tl_id=tl, mode=modo)
            for tl in TRAFFIC_LIGHTS_2x2
        }

    paso = 0
    historial_rebote: list[float] = []

    try:
        while traci.simulation.getMinExpectedNumber() > 0 and paso < duracion_s:
            traci.simulationStep()
            for tl in TRAFFIC_LIGHTS_2x2:
                controladores[tl].step(paso)
                colectores[tl].collect(paso)
            paso += 1

            if paso % 300 == 0:
                cola_up   = _cola_promedio(traci, ["J0", "J1"])
                cola_down = _cola_promedio(traci, ["J2", "J3"])
                rebote    = cola_down - cola_up
                historial_rebote.append(rebote)
                print(
                    f"  paso {paso:>5} | upstream={cola_up:>5.1f} veh"
                    f" | downstream={cola_down:>5.1f} veh"
                    f" | rebote={rebote:>+5.1f} veh"
                )
    finally:
        traci.close()

    # Guardar CSV por intersección
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for tl, col in colectores.items():
        col.save(OUTPUT_DIR / f"escenario2_{modo}_{tl}_results.csv")

    # Resumen agregado de red
    resumen = _resumen_red(colectores, historial_rebote, modo, duracion_s)
    json_path = OUTPUT_DIR / f"escenario2_{modo}_summary.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(resumen, f, indent=2, ensure_ascii=False)
    print(f"[benchmark_2x2] Resumen guardado -> {json_path}")

    return resumen


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cola_promedio(traci, tl_ids: list[str]) -> float:
    total = 0
    n_aristas = 0
    for tl in tl_ids:
        for aristas in EDGES_2x2[tl].values():
            for arista in aristas:
                try:
                    for vid in traci.edge.getLastStepVehicleIDs(arista):
                        if traci.vehicle.getSpeed(vid) < 0.1:
                            total += 1
                except Exception:
                    pass
                n_aristas += 1
    return total / n_aristas if n_aristas else 0.0


def _resumen_red(
    colectores: dict,
    historial_rebote: list[float],
    modo: str,
    duracion_s: int,
) -> dict:
    """Agrega métricas de los 4 colectores en un resumen de red."""
    sums = {k: [] for k in colectores}
    esperas, colas, velocidades, co2s = [], [], [], []
    throughput_total = 0

    for tl, col in colectores.items():
        resumen_tl = col.summary_steady_state(warmup_steps=300)
        esperas.append(resumen_tl.get("waiting_time_avg_s", 0))
        colas.append(resumen_tl.get("queue_length_avg_veh", 0))
        velocidades.append(resumen_tl.get("speed_avg_ms", 0))
        co2s.append(resumen_tl.get("co2_total_mg", 0))
        throughput_total += resumen_tl.get("throughput_total_veh", 0)

    n = len(colectores)
    efecto_rebote_avg = (
        sum(historial_rebote) / len(historial_rebote) if historial_rebote else 0.0
    )

    return {
        "modo":                 modo,
        "duracion_s":           duracion_s,
        "intersecciones":       TRAFFIC_LIGHTS_2x2,
        "espera_prom_s":        round(sum(esperas) / n, 2),
        "cola_prom_veh":        round(sum(colas) / n, 2),
        "cola_max_veh":         round(max(colas), 2),
        "velocidad_prom_ms":    round(sum(velocidades) / n, 3),
        "throughput_total_veh": throughput_total,
        "co2_total_mg":         round(sum(co2s), 2),
        "efecto_rebote_veh":    round(efecto_rebote_avg, 2),
    }


def calcular_comparacion(base: dict, comparado: dict) -> dict:
    resultados = {}
    for metrica, (direccion, unidad) in METRICAS_COMPARAR.items():
        v_base = base.get(metrica, 0)
        v_comp = comparado.get(metrica, 0)
        pct    = ((v_comp - v_base) / v_base * 100) if v_base != 0 else 0.0
        mejora = (pct < 0) if direccion == "menor es mejor" else (pct > 0)
        resultados[metrica] = {
            "unidad":    unidad,
            "fijo":      round(v_base, 3),
            "comparado": round(v_comp, 3),
            "cambio_pct": round(pct, 2),
            "mejora":    mejora,
        }
    return resultados


def formatear_reporte(
    resumen_fijo: dict,
    resumen_adapt: dict,
    comp_adapt: dict,
    resumen_dqn: dict | None = None,
    comp_dqn: dict | None = None,
) -> str:
    lineas = [
        "=" * 70,
        "  Seminario — Escenario 2: Red 2×2 | Fijo vs. Adaptativo vs. DQN",
        "=" * 70,
        "",
        f"  {'Metrica':<28} {'Fijo':>10} {'Adapt.':>10} {'D%':>8}  {'OK?':>5}",
        "  " + "-" * 60,
    ]

    metas = {
        "espera_prom_s":    ("<= -15 %", -15),
        "co2_total_mg":     ("<= -10 %", -10),
        "efecto_rebote_veh": ("<= -20 %", -20),
    }

    for metrica, datos in comp_adapt.items():
        pct_str = f"{datos['cambio_pct']:+.1f} %"
        ok = "OK" if datos["mejora"] else "--"
        if metrica in metas:
            etiq, umbral = metas[metrica]
            ok = f"OK ({etiq})" if datos["cambio_pct"] <= umbral else f"NO (meta: {etiq})"
        nombre = metrica.replace("_", " ").rstrip()
        lineas.append(
            f"  {nombre:<28} {datos['fijo']:>9.2f} {datos['comparado']:>9.2f}"
            f" {pct_str:>8}  {ok}"
        )

    if comp_dqn and resumen_dqn:
        lineas += [
            "",
            "  " + "-" * 60,
            "  Fijo vs. DQN",
            "  " + "-" * 60,
            f"  {'Metrica':<28} {'Fijo':>10} {'DQN':>10} {'D%':>8}  {'OK?':>5}",
            "  " + "-" * 60,
        ]
        for metrica, datos in comp_dqn.items():
            pct_str = f"{datos['cambio_pct']:+.1f} %"
            ok = "OK" if datos["mejora"] else "--"
            if metrica in metas:
                etiq, umbral = metas[metrica]
                ok = f"OK ({etiq})" if datos["cambio_pct"] <= umbral else f"NO (meta: {etiq})"
            nombre = metrica.replace("_", " ").rstrip()
            lineas.append(
                f"  {nombre:<28} {datos['fijo']:>9.2f} {datos['comparado']:>9.2f}"
                f" {pct_str:>8}  {ok}"
            )

    lineas += [
        "",
        "  Metas del PMV (Escenario 2):",
        "    * Espera prom.: -15 % minimo",
        "    * Emisiones CO2: -10 % minimo",
        "    * Efecto rebote: -20 % (coordinacion entre intersecciones)",
        "=" * 70,
    ]
    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------

def ejecutar_benchmark(
    duracion: int = 3600,
    omitir_fijo: bool = False,
    omitir_dqn: bool = False,
    model_path: str | None = None,
) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_fijo = OUTPUT_DIR / "escenario2_fixed_summary.json"

    if omitir_fijo and json_fijo.exists():
        print("[benchmark_2x2] Reutilizando resumen fijo existente...")
        with open(json_fijo, encoding="utf-8") as f:
            resumen_fijo = json.load(f)
    else:
        resumen_fijo = ejecutar_simulacion_2x2("fixed", duracion)

    resumen_adapt = ejecutar_simulacion_2x2("adaptive", duracion)

    resumen_dqn = None
    comp_dqn    = None
    if not omitir_dqn:
        resumen_dqn = ejecutar_simulacion_2x2("dqn", duracion, model_path)
        comp_dqn    = calcular_comparacion(resumen_fijo, resumen_dqn)

    comp_adapt = calcular_comparacion(resumen_fijo, resumen_adapt)

    comp_json = OUTPUT_DIR / "escenario2_comparison.json"
    with open(comp_json, "w", encoding="utf-8") as f:
        json.dump({
            "fijo":      resumen_fijo,
            "adaptativo": resumen_adapt,
            "dqn":       resumen_dqn,
            "comparacion_adapt": comp_adapt,
            "comparacion_dqn":   comp_dqn,
        }, f, indent=2, ensure_ascii=False)

    reporte = formatear_reporte(
        resumen_fijo, resumen_adapt, comp_adapt, resumen_dqn, comp_dqn
    )
    print("\n" + reporte)

    comp_txt = OUTPUT_DIR / "escenario2_comparison.txt"
    comp_txt.write_text(reporte, encoding="utf-8")
    print(f"\n[benchmark_2x2] Reporte -> {comp_txt}")
    print(f"[benchmark_2x2] JSON    -> {comp_json}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seminario — Benchmark Escenario 2")
    parser.add_argument("--duration",    type=int,  default=3600)
    parser.add_argument("--skip-fixed",  action="store_true")
    parser.add_argument("--skip-dqn",    action="store_true")
    parser.add_argument("--model",       type=str,  default=None,
                        help="Prefijo de ruta checkpoints DQN (p.ej. models/dqn_2x2)")
    args = parser.parse_args()
    ejecutar_benchmark(
        duracion=args.duration,
        omitir_fijo=args.skip_fixed,
        omitir_dqn=args.skip_dqn,
        model_path=args.model,
    )


if __name__ == "__main__":
    main()
