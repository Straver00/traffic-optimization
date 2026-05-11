"""
metrics.py — Captura y agrega indicadores de tráfico desde SUMO/TraCI.

Indicadores registrados (7):
  1. waiting_time_avg   — tiempo promedio de espera por vehículo (s)
  2. queue_length_max   — longitud máxima de cola en cualquier acceso (veh)
  3. throughput         — vehículos que completaron su ruta en el intervalo
  4. occupancy_avg      — ocupación promedio de detectores (%)
  5. speed_avg          — velocidad media de todos los vehículos en red (m/s)
  6. green_phase_dist   — distribución de tiempo verde entre fases (%)
  7. co2_relative       — emisiones CO₂ relativas al paso anterior (mg)
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional


# ---------------------------------------------------------------------------
# Estructura de un snapshot de métricas (un paso de simulación)
# ---------------------------------------------------------------------------

@dataclass
class TrafficSnapshot:
    step: int
    waiting_time_avg: float       # s
    queue_length_max: int         # veh
    throughput: int               # veh completados en este paso
    occupancy_avg: float          # %
    speed_avg: float              # m/s
    green_phase_index: int        # fase activa del semáforo (0 = Av80, 1 = C65)
    co2_mg: float                 # mg emitidos en este paso
    controller_mode: str          # "fixed" | "adaptive"


# ---------------------------------------------------------------------------
# Recolector principal — se instancia una vez por simulación
# ---------------------------------------------------------------------------

class MetricsCollector:
    """
    Uso:
        collector = MetricsCollector(traci, tl_id="J0", mode="adaptive")
        for step in sim_loop:
            snapshot = collector.collect(step)

        collector.save("results/escenario1_results.csv")
        summary = collector.summary()
    """

    def __init__(self, traci_module, tl_id: str, mode: str = "fixed"):
        self._traci = traci_module
        self._tl_id = tl_id
        self._mode = mode
        self._snapshots: List[TrafficSnapshot] = []
        self._prev_arrived = 0

    # ------------------------------------------------------------------
    # Colección por paso
    # ------------------------------------------------------------------

    def collect(self, step: int) -> TrafficSnapshot:
        t = self._traci

        # Todos los vehículos activos en red
        vehicles = t.vehicle.getIDList()
        n = len(vehicles)

        waiting_times = [t.vehicle.getWaitingTime(v) for v in vehicles]
        speeds        = [t.vehicle.getSpeed(v)        for v in vehicles]
        co2_vals      = [t.vehicle.getCO2Emission(v)  for v in vehicles]

        waiting_avg = sum(waiting_times) / n if n else 0.0
        speed_avg   = sum(speeds) / n        if n else 0.0
        co2_total   = sum(co2_vals)

        # Cola: vehículos con velocidad < 0.1 m/s (prácticamente detenidos)
        queue_max = sum(1 for s in speeds if s < 0.1)

        # Throughput: diferencia de vehículos llegados al destino
        arrived_now   = t.simulation.getArrivedNumber()
        throughput     = arrived_now
        self._prev_arrived = arrived_now

        # Ocupación promedio (si hay detectores de lazo definidos; si no, 0)
        try:
            det_ids  = t.lanearea.getIDList()
            occ_vals = [t.lanearea.getLastStepOccupancy(d) for d in det_ids]
            occupancy = sum(occ_vals) / len(occ_vals) if occ_vals else 0.0
        except Exception:
            occupancy = 0.0

        # Fase activa del semáforo
        try:
            phase_index = t.trafficlight.getPhase(self._tl_id)
        except Exception:
            phase_index = -1

        snap = TrafficSnapshot(
            step=step,
            waiting_time_avg=round(waiting_avg, 3),
            queue_length_max=queue_max,
            throughput=throughput,
            occupancy_avg=round(occupancy, 3),
            speed_avg=round(speed_avg, 3),
            green_phase_index=phase_index,
            co2_mg=round(co2_total, 3),
            controller_mode=self._mode,
        )
        self._snapshots.append(snap)
        return snap

    # ------------------------------------------------------------------
    # Persistencia
    # ------------------------------------------------------------------

    def save(self, output_path: str | Path) -> None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not self._snapshots:
            return
        fieldnames = list(asdict(self._snapshots[0]).keys())
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for snap in self._snapshots:
                writer.writerow(asdict(snap))
        print(f"[metrics] Guardado {len(self._snapshots)} registros -> {path}")

    # ------------------------------------------------------------------
    # Resumen estadístico
    # ------------------------------------------------------------------

    def summary(self) -> dict:
        if not self._snapshots:
            return {}
        waits  = [s.waiting_time_avg  for s in self._snapshots]
        queues = [s.queue_length_max  for s in self._snapshots]
        speeds = [s.speed_avg         for s in self._snapshots]
        co2s   = [s.co2_mg            for s in self._snapshots]
        total_throughput = sum(s.throughput for s in self._snapshots)

        return {
            "controller_mode":       self._mode,
            "steps_recorded":        len(self._snapshots),
            "waiting_time_avg_s":    round(sum(waits)  / len(waits),  2),
            "waiting_time_max_s":    round(max(waits),                2),
            "queue_length_avg_veh":  round(sum(queues) / len(queues), 2),
            "queue_length_max_veh":  max(queues),
            "speed_avg_ms":          round(sum(speeds) / len(speeds), 3),
            "throughput_total_veh":  total_throughput,
            "co2_total_mg":          round(sum(co2s),                 2),
        }

    def summary_steady_state(self, warmup_steps: int = 300) -> dict:
        """
        Resumen estadístico excluyendo los primeros warmup_steps pasos
        (periodo de calentamiento del controlador).
        Usa mediana para espera y cola (más robusta a picos).
        """
        snaps = [s for s in self._snapshots if s.step >= warmup_steps]
        if not snaps:
            return self.summary()

        import statistics
        waits  = [s.waiting_time_avg  for s in snaps]
        queues = [s.queue_length_max  for s in snaps]
        speeds = [s.speed_avg         for s in snaps]
        co2s   = [s.co2_mg            for s in snaps]
        total_throughput = sum(s.throughput for s in snaps)

        return {
            "controller_mode":            self._mode,
            "steps_recorded":             len(snaps),
            "warmup_excluded_steps":      warmup_steps,
            "waiting_time_avg_s":         round(statistics.mean(waits),   2),
            "waiting_time_median_s":      round(statistics.median(waits),  2),
            "waiting_time_max_s":         round(max(waits),                2),
            "queue_length_avg_veh":       round(statistics.mean(queues),   2),
            "queue_length_median_veh":    round(statistics.median(queues),  2),
            "queue_length_max_veh":       max(queues),
            "speed_avg_ms":               round(statistics.mean(speeds),   3),
            "throughput_total_veh":       total_throughput,
            "co2_total_mg":               round(sum(co2s),                 2),
        }
