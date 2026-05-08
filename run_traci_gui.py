from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


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
    path = shutil.which(name)
    return path or ""


def ensure_net_file(net_file: Path, scenario_dir: Path, netconvert: str) -> None:
    if net_file.exists():
        return
    cmd = [
        netconvert,
        "--node-files",
        str(scenario_dir / "nodos.nod.xml"),
        "--edge-files",
        str(scenario_dir / "aristas.edg.xml"),
        "--connection-files",
        str(scenario_dir / "conexiones.con.xml"),
        "--tllogic-files",
        str(scenario_dir / "semaforo.tll.xml"),
        "--output-file",
        str(net_file),
    ]
    print("Creating net file with netconvert...")
    subprocess.run(cmd, check=True)


def main() -> None:
    root = Path(__file__).resolve().parent
    scenario_dir = root / "intersection_av80_c65"
    route_file = scenario_dir / "rutas.rou.xml"
    net_file = scenario_dir / "intersection_av80_c65.net.xml"

    if not scenario_dir.exists():
        print(f"Missing folder: {scenario_dir}")
        sys.exit(1)
    if not route_file.exists():
        print(f"Missing route file: {route_file}")
        sys.exit(1)

    sumo_gui = find_binary("sumo-gui")
    netconvert = find_binary("netconvert")

    if not sumo_gui:
        print("Could not find sumo-gui. Ensure SUMO is installed and in PATH.")
        sys.exit(1)
    if not netconvert:
        print("Could not find netconvert. Ensure SUMO is installed and in PATH.")
        sys.exit(1)

    ensure_net_file(net_file, scenario_dir, netconvert)

    sumo_home = os.environ.get("SUMO_HOME")
    if sumo_home:
        tools_dir = Path(sumo_home) / "tools"
        if tools_dir.exists():
            sys.path.append(str(tools_dir))

    try:
        import traci  # type: ignore
    except Exception:
        print("Python module 'traci' not found. Ensure SUMO tools are available.")
        sys.exit(1)

    sumo_cmd = [
        sumo_gui,
        "-n",
        str(net_file),
        "-r",
        str(route_file),
        "--start",
    ]

    print("Starting SUMO GUI with TraCI...")
    traci.start(sumo_cmd)

    try:
        while traci.simulation.getMinExpectedNumber() > 0:
            traci.simulationStep()
            time.sleep(0.05)
    finally:
        traci.close()


if __name__ == "__main__":
    main()
