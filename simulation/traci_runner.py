"""
traci_runner.py — Lanzador de simulación SUMO con controlador adaptativo integrado.

Modos:
    python traci_runner.py --mode adaptive   (heurístico adaptativo, por defecto)
    python traci_runner.py --mode fixed      (tiempos fijos, línea base)
    python traci_runner.py --mode gui        (abre SUMO-GUI, sin paso automático)

Salida:
    evaluation/results/escenario1_<mode>_results.csv
    evaluation/results/escenario1_<mode>_summary.json

Uso en benchmark:
    Importar run_simulation() desde benchmark.py
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Resolución de rutas
# ---------------------------------------------------------------------------

ROOT         = Path(__file__).resolve().parent.parent
SCENARIO_DIR = ROOT / "intersection_av80_c65"
NET_FILE     = SCENARIO_DIR / "intersection_av80_c65.net.xml"
ROUTE_FILE   = SCENARIO_DIR / "rutas.rou.xml"
SUMO_CFG     = SCENARIO_DIR / "intersection_av80_c65.sumocfg"
OUTPUT_DIR   = ROOT / "evaluation" / "results"

TL_ID = "J0"   # ID del semáforo en semaforo.tll.xml


# ---------------------------------------------------------------------------
# Helpers de instalación SUMO (idénticos al run_traci_gui.py original)
# ---------------------------------------------------------------------------

def find_binary(name: str) -> str:
    sumo_home = os.environ.get("SUMO_HOME")
    if sumo_home:
        candidate = Path(sumo_home) / "bin" / name
        if candidate.exists():
            return str(candidate)
        if os.name == "nt":
            exe = candidate.with_suffix(".exe")
            if exe.exists():
                return str(exe)
    return shutil.which(name) or ""


def ensure_net_file() -> None:
    source_files = [
        SCENARIO_DIR / "nodos.nod.xml",
        SCENARIO_DIR / "aristas.edg.xml",
        SCENARIO_DIR / "conexiones.con.xml",
        SCENARIO_DIR / "semaforo.tll.xml",
    ]

    if NET_FILE.exists():
        net_mtime = NET_FILE.stat().st_mtime
        if all(src.exists() and src.stat().st_mtime <= net_mtime for src in source_files):
            return
    netconvert = find_binary("netconvert")
    if not netconvert:
        sys.exit("[runner] netconvert no encontrado. Instala SUMO y configura SUMO_HOME.")
    cmd = [
        netconvert,
        "--node-files",       str(SCENARIO_DIR / "nodos.nod.xml"),
        "--edge-files",       str(SCENARIO_DIR / "aristas.edg.xml"),
        "--connection-files", str(SCENARIO_DIR / "conexiones.con.xml"),
        "--tllogic-files",    str(SCENARIO_DIR / "semaforo.tll.xml"),
        "--output-file",      str(NET_FILE),
    ]
    print("[runner] Generando net file con netconvert...")
    subprocess.run(cmd, check=True)


def setup_traci() -> None:
    sumo_home = os.environ.get("SUMO_HOME")
    if sumo_home:
        tools = Path(sumo_home) / "tools"
        if tools.exists() and str(tools) not in sys.path:
            sys.path.insert(0, str(tools))


# ---------------------------------------------------------------------------
# Función principal de simulación — reutilizable desde benchmark.py
# ---------------------------------------------------------------------------

def run_simulation(
    mode: str = "adaptive",
    gui: bool = False,
    sim_duration_s: int = 3600,
    output_dir: Path | None = None,
    model_path: str | None = None,
) -> dict:
    """
    Ejecuta una simulación completa y devuelve el resumen de métricas.

    Args:
        mode:           "adaptive" | "fixed" | "dqn"
        gui:            Si True, usa sumo-gui (sin step automático del runner)
        sim_duration_s: Duración de simulación en segundos SUMO
        output_dir:     Directorio de salida para CSVs
        model_path:     Ruta al modelo DQN (solo modo dqn)

    Returns:
        dict con resumen estadístico (ver MetricsCollector.summary())
    """
    # Importaciones diferidas para no fallar si SUMO no está instalado
    setup_traci()
    try:
        import traci  # type: ignore
    except ImportError:
        sys.exit("[runner] Módulo traci no encontrado. Revisa SUMO_HOME.")

    # Importar módulos propios (compatibles con ejecución desde raíz del repo)
    sys.path.insert(0, str(ROOT))
    from evaluation.metrics import MetricsCollector
    from decision.adaptive_controller import AdaptiveController

    out_dir = output_dir or OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    ensure_net_file()

    binary = find_binary("sumo-gui" if gui else "sumo")
    if not binary:
        sys.exit(f"[runner] Binario SUMO no encontrado ({'sumo-gui' if gui else 'sumo'}).")

    if SUMO_CFG.exists():
        sumo_cmd = [
            binary,
            "--configuration-file", str(SUMO_CFG),
            "--no-step-log",
            "--time-to-teleport", "-1",
            "--quit-on-end",
        ]
    else:
        sumo_cmd = [
            binary,
            "--net-file",    str(NET_FILE),
            "--route-files", str(ROUTE_FILE),
            "--no-step-log",
            "--time-to-teleport", "-1",
            "--quit-on-end",
        ]
    if gui:
        sumo_cmd.append("--start")

    print(f"\n[runner] Iniciando simulacion - modo: {mode.upper()}")
    traci.start(sumo_cmd)

    collector = MetricsCollector(traci, tl_id=TL_ID, mode=mode)
    if mode == "dqn":
        from decision.dqn_controller import DQNController

        controller = DQNController(traci, tl_id=TL_ID, mode=mode, model_path=model_path)
    else:
        controller = AdaptiveController(
            traci,
            tl_id=TL_ID,
            mode=mode if mode in ("adaptive", "fixed") else "adaptive",
        )

    LIVE_FEED = out_dir / "live_feed.json"
    step = 0
    throughput_acc = 0
    co2_acc = 0.0
    historial_modo = {
        "timestamps": [], "espera": [], "cola": [],
        "velocidad": [], "co2": [], "throughput": [],
    }
    try:
        while traci.simulation.getMinExpectedNumber() > 0 and step < sim_duration_s:
            traci.simulationStep()
            controller.step(step)
            snap = collector.collect(step)
            throughput_acc += snap.throughput
            co2_acc += snap.co2_mg
            step += 1

            if step % 10 == 0:
                historial_modo["timestamps"].append(step)
                historial_modo["espera"].append(round(snap.waiting_time_avg, 2))
                historial_modo["cola"].append(snap.queue_length_max)
                historial_modo["velocidad"].append(round(snap.speed_avg, 2))
                historial_modo["co2"].append(int(round(co2_acc, 0)))
                historial_modo["throughput"].append(throughput_acc)
                try:
                    feed_actual = json.loads(LIVE_FEED.read_text(encoding="utf-8")) if LIVE_FEED.exists() else {}
                except Exception:
                    feed_actual = {}
                feed_actual.update({
                    "step": step,
                    "mode": mode,
                    "phase": snap.green_phase_index,
                    "waiting_time_avg": snap.waiting_time_avg,
                    "queue_length_max": snap.queue_length_max,
                    "speed_avg": snap.speed_avg,
                    "throughput_total": throughput_acc,
                    mode: historial_modo,
                })
                try:
                    LIVE_FEED.write_text(json.dumps(feed_actual), encoding="utf-8")
                except Exception:
                    pass

            if step % 300 == 0:
                print(
                    f"  paso {step:>5} | espera_avg={snap.waiting_time_avg:>6.1f}s "
                    f"| cola_max={snap.queue_length_max:>3} veh "
                    f"| fase={snap.green_phase_index}"
                )
    finally:
        traci.close()

    # Guardar CSV y resumen JSON
    csv_path  = out_dir / f"escenario1_{mode}_results.csv"
    json_path = out_dir / f"escenario1_{mode}_summary.json"

    collector.save(csv_path)
    summary = collector.summary_steady_state(warmup_steps=300)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"[runner] Resumen guardado -> {json_path}")
    print(f"[runner] Resumen: {json.dumps(summary, indent=2)}")

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Seminario — Runner de simulación SUMO")
    parser.add_argument(
        "--mode",
        choices=["adaptive", "fixed", "dqn", "gui"],
        default="adaptive",
        help="adaptive: heurístico | fixed: tiempos fijos | dqn: Double DQN | gui: alias de --mode adaptive --gui",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Abrir SUMO-GUI en lugar del modo headless (combinable con cualquier --mode)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Ruta al modelo DQN (solo modo dqn)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=3600,
        help="Duración de la simulación en segundos SUMO (default: 3600)",
    )
    args = parser.parse_args()

    gui  = args.gui or (args.mode == "gui")
    mode = "adaptive" if args.mode == "gui" else args.mode

    run_simulation(mode=mode, gui=gui, sim_duration_s=args.duration, model_path=args.model)


if __name__ == "__main__":
    main()
