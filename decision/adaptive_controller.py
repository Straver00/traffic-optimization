"""
adaptive_controller.py - Controlador semafórico heurístico adaptativo v3.

Logica de decision (reglas heuristicas):
  - Cada ciclo, mide la cola de vehiculos en cada acceso (N/S vs E/W).
  - Combina cola observada (80%) con peso de flujo base (20%) para calcular
    la presion de cada fase y asignar verde proporcional.
  - Aplica un tope de verde maximo proporcional: si la cola secundaria tiene
    vehiculos, la primaria no puede recibir mas de GREEN_MAX_SHARED.
  - Respeta los limites del Manual de Senalizacion Vial 2024:
      verde minimo: 15 s  |  verde maximo: 90 s
  - Garantiza que ningun acceso supere 1 ciclo consecutivo sin verde (equidad).
  - Ante cualquier excepcion TraCI, activa fallback a tiempos fijos en < 2 s (RF-04).

Fases SUMO reales (semaforo.tll.xml - programID "programa_av80_c65"):
    Fase 0 - Verde Av. 80    (N<->S)  - duracion base 52 s  | GGGrrrGGGrrr
    Fase 1 - Amarillo Av. 80 (N<->S)  - 3 s fijo            | yyyrrryyyrrr
    Fase 2 - Todo rojo Av80           - 15 s fijo           | rrrrrrrrrrrr
    Fase 3 - Verde Calle 65 (E<->W)   - duracion base 33 s  | rrrGGGrrrGGG
    Fase 4 - Amarillo Calle 65 (E<->W)- 3 s fijo            | rrryyyrrryyy
    Fase 5 - Todo rojo C65            - 15 s fijo           | rrrrrrrrrrrr
"""

from __future__ import annotations
import time

from decision.traffic_config import (
    ALL_RED_S,
    EDGES_AV80,
    EDGES_C65,
    FALLBACK_GREEN_AV80,
    FALLBACK_GREEN_C65,
    FLOW_WEIGHT_AV80,
    FLOW_WEIGHT_C65,
    GREEN_MAX_S,
    GREEN_MAX_SHARED,
    GREEN_MIN_S,
    MAX_SKIP_CYCLES,
    PHASE_GREEN_AV80,
    PHASE_GREEN_C65,
    PHASE_ALL_RED_AV80,
    PHASE_ALL_RED_C65,
    PHASE_YELLOW_AV80,
    PHASE_YELLOW_C65,
    PROGRAM_ID,
    YELLOW_S,
)


class AdaptiveController:

    def __init__(self, traci_module, tl_id: str = "J0", mode: str = "adaptive"):
        self._t     = traci_module
        self._tl_id = tl_id
        self._mode  = mode

        self._current_phase: int   = PHASE_GREEN_AV80
        self._phase_timer:   int   = FALLBACK_GREEN_AV80
        self._skip_av80:     int   = 0
        self._skip_c65:      int   = 0
        self._fallback_active: bool = False
        self._last_phase_set_time: float = 0.0

        try:
            self._t.trafficlight.setPhase(self._tl_id, PHASE_GREEN_AV80)
            self._t.trafficlight.setPhaseDuration(self._tl_id, FALLBACK_GREEN_AV80)
        except Exception:
            pass

    def step(self, sim_step: int) -> None:
        if self._mode == "fixed":
            return
        self._phase_timer -= 1
        if self._phase_timer > 0:
            return
        try:
            self._advance_phase()
            self._fallback_active = False
        except Exception as exc:
            print(f"[controller] ERROR TraCI en paso {sim_step}: {exc}")
            self._activate_fallback()

    @property
    def fallback_active(self) -> bool:
        return self._fallback_active

    @property
    def current_phase(self) -> int:
        return self._current_phase

    def _advance_phase(self) -> None:
        phase = self._current_phase

        if phase == PHASE_GREEN_AV80:
            self._set_phase(PHASE_YELLOW_AV80, YELLOW_S)

        elif phase == PHASE_YELLOW_AV80:
            self._set_phase(PHASE_ALL_RED_AV80, ALL_RED_S)

        elif phase == PHASE_ALL_RED_AV80:
            duration = self._decide_green(
                EDGES_C65, EDGES_AV80,
                self._skip_av80,
                FLOW_WEIGHT_C65, FLOW_WEIGHT_AV80,
            )
            self._skip_av80 += 1
            self._skip_c65 = 0
            self._set_phase(PHASE_GREEN_C65, duration)

        elif phase == PHASE_GREEN_C65:
            self._set_phase(PHASE_YELLOW_C65, YELLOW_S)

        elif phase == PHASE_YELLOW_C65:
            self._set_phase(PHASE_ALL_RED_C65, ALL_RED_S)

        elif phase == PHASE_ALL_RED_C65:
            duration = self._decide_green(
                EDGES_AV80, EDGES_C65,
                self._skip_c65,
                FLOW_WEIGHT_AV80, FLOW_WEIGHT_C65,
            )
            self._skip_c65 += 1
            self._skip_av80 = 0
            self._set_phase(PHASE_GREEN_AV80, duration)

    def _decide_green(
        self,
        edges_primary:         list[str],
        edges_secondary:       list[str],
        skip_secondary:        int,
        flow_weight_primary:   int,
        flow_weight_secondary: int,
    ) -> int:
        if skip_secondary >= MAX_SKIP_CYCLES:
            return GREEN_MIN_S

        q_primary   = self._queue_length(edges_primary)
        q_secondary = self._queue_length(edges_secondary)

        green_max = GREEN_MAX_S if q_secondary == 0 else GREEN_MAX_SHARED

        FLOW_SCALE = 0.03
        p = 0.8 * q_primary   + 0.2 * flow_weight_primary   * FLOW_SCALE
        s = 0.8 * q_secondary + 0.2 * flow_weight_secondary * FLOW_SCALE
        total = p + s

        if total == 0:
            return GREEN_MIN_S

        ratio    = p / total
        duration = GREEN_MIN_S + (green_max - GREEN_MIN_S) * ratio
        return int(round(duration))

    def _queue_length(self, edges: list[str]) -> int:
        count = 0
        for edge in edges:
            try:
                veh_ids = self._t.edge.getLastStepVehicleIDs(edge)
                for vid in veh_ids:
                    if self._t.vehicle.getSpeed(vid) < 0.1:
                        count += 1
            except Exception:
                pass
        return count

    def _set_phase(self, phase_index: int, duration_s: int) -> None:
        self._t.trafficlight.setPhase(self._tl_id, phase_index)
        self._t.trafficlight.setPhaseDuration(self._tl_id, duration_s)
        self._current_phase = phase_index
        self._phase_timer   = duration_s
        self._last_phase_set_time = time.time()

    def _activate_fallback(self) -> None:
        if self._fallback_active:
            return
        print("[controller] FALLBACK activado -> tiempos fijos")
        t0 = time.time()
        try:
            self._t.trafficlight.setProgram(self._tl_id, PROGRAM_ID)
        except Exception as e:
            print(f"[controller] No se pudo restaurar programa: {e}")
        elapsed_ms = (time.time() - t0) * 1000
        print(f"[controller] Fallback completado en {elapsed_ms:.1f} ms")
        self._fallback_active = True
