"""Entorno SUMO para entrenamiento DQN en red 2×2 (4 intersecciones independientes)."""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from decision.traffic_config import (
    ALL_RED_S,
    DECISION_STEP_S,
    EDGES_2x2,
    GREEN_MAX_S,
    GREEN_MAX_SHARED,
    GREEN_MIN_S,
    PHASE_ALL_RED_AV80,
    PHASE_ALL_RED_C65,
    PHASE_GREEN_AV80,
    PHASE_GREEN_C65,
    PHASE_YELLOW_AV80,
    PHASE_YELLOW_C65,
    TRAFFIC_LIGHTS_2x2,
    YELLOW_S,
)
from rl.config import DQNConfig
from simulation.traci_runner import find_binary, setup_traci

ROOT         = Path(__file__).resolve().parent.parent
SCENARIO_DIR = ROOT / "red_2x2"
NET_FILE_2x2 = SCENARIO_DIR / "red_2x2.net.xml"
ROUTE_FILE_2x2 = SCENARIO_DIR / "rutas.rou.xml"


def _ensure_net_file_2x2() -> None:
    """Compila red_2x2.net.xml con netconvert si está desactualizada."""
    import subprocess, sys
    fuentes = [
        SCENARIO_DIR / "nodos.nod.xml",
        SCENARIO_DIR / "aristas.edg.xml",
        SCENARIO_DIR / "conexiones.con.xml",
        SCENARIO_DIR / "semaforo.tll.xml",
    ]
    if NET_FILE_2x2.exists():
        mtime = NET_FILE_2x2.stat().st_mtime
        if all(f.exists() and f.stat().st_mtime <= mtime for f in fuentes):
            return
    netconvert = find_binary("netconvert")
    if not netconvert:
        sys.exit("[rl_env_2x2] netconvert no encontrado. Instala SUMO y configura SUMO_HOME.")
    cmd = [
        netconvert,
        "--node-files",       str(SCENARIO_DIR / "nodos.nod.xml"),
        "--edge-files",       str(SCENARIO_DIR / "aristas.edg.xml"),
        "--connection-files", str(SCENARIO_DIR / "conexiones.con.xml"),
        "--tllogic-files",    str(SCENARIO_DIR / "semaforo.tll.xml"),
        "--output-file",      str(NET_FILE_2x2),
    ]
    print("[rl_env_2x2] Generando red_2x2.net.xml con netconvert...")
    subprocess.run(cmd, check=True)


# ---------------------------------------------------------------------------
# Dataclasses de estado por intersección
# ---------------------------------------------------------------------------

@dataclass
class EstadoInterseccion:
    """Estado interno de una intersección controlada por DQN."""
    tl_id: str
    fase_verde_actual: int = PHASE_GREEN_AV80
    tiempo_verde: int = 0
    fin_planeado: int = GREEN_MIN_S


@dataclass
class InfoPaso2x2:
    """Información de retorno de step() para la red 2×2."""
    acciones_validas: Dict[str, List[int]]
    pasos: int
    espera_red: float       # promedio de red
    cola_red: float         # promedio de red
    velocidad_red: float
    co2_total: float
    throughput_total: int
    efecto_rebote: float    # diferencia de cola entre upstream (J0/J1) y downstream (J2/J3)


# ---------------------------------------------------------------------------
# Extractor de estado local por intersección (variante 2×2)
# ---------------------------------------------------------------------------

class ExtractorEstadoLocal:
    """Versión de StateExtractor parametrizada por intersección."""

    def __init__(self, traci_module, tl_id: str, config: DQNConfig) -> None:
        self._t = traci_module
        self._tl_id = tl_id
        self._config = config
        self._edges_av80 = EDGES_2x2[tl_id]["AV80"]
        self._edges_c65  = EDGES_2x2[tl_id]["C65"]

    def construir_estado(self, fase: int, tiempo_en_fase: int) -> Tuple[List[float], int, int]:
        """Devuelve (vector_estado, cola_av80, cola_c65)."""
        q_av80_0, q_av80_1 = self._colas_aristas(self._edges_av80)
        q_c65_0,  q_c65_1  = self._colas_aristas(self._edges_c65)

        cola_av80 = q_av80_0 + q_av80_1
        cola_c65  = q_c65_0  + q_c65_1

        espera_avg, velocidad_avg, ocupacion, throughput = self._metricas_globales()
        norm = self._config.norm

        estado: List[float] = [
            q_av80_0 / norm.queue_scale,
            q_av80_1 / norm.queue_scale,
            q_c65_0  / norm.queue_scale,
            q_c65_1  / norm.queue_scale,
        ]
        if self._config.state.include_waiting_time:
            estado.append(espera_avg / norm.waiting_time_scale)
        if self._config.state.include_speed_avg:
            estado.append(velocidad_avg / norm.speed_scale)
        if self._config.state.include_occupancy:
            estado.append(ocupacion / norm.occupancy_scale)
        if self._config.state.include_phase_one_hot:
            estado.extend([
                1.0 if fase == PHASE_GREEN_AV80 else 0.0,
                1.0 if fase == PHASE_GREEN_C65  else 0.0,
                1.0 if fase in (PHASE_YELLOW_AV80, PHASE_YELLOW_C65) else 0.0,
                1.0 if fase in (PHASE_ALL_RED_AV80, PHASE_ALL_RED_C65) else 0.0,
            ])
        if self._config.state.include_phase_time:
            estado.append(min(tiempo_en_fase / norm.phase_time_scale, 1.0))

        return estado, cola_av80, cola_c65

    def _colas_aristas(self, aristas: List[str]) -> List[int]:
        threshold = self._config.state.queue_speed_threshold
        conteos = []
        for arista in aristas:
            conteo = 0
            try:
                for vid in self._t.edge.getLastStepVehicleIDs(arista):
                    if self._t.vehicle.getSpeed(vid) < threshold:
                        conteo += 1
            except Exception:
                pass
            conteos.append(conteo)
        return conteos

    def _metricas_globales(self) -> Tuple[float, float, float, int]:
        t = self._t
        try:
            vehiculos = t.vehicle.getIDList()
            n = len(vehiculos)
            espera = sum(t.vehicle.getWaitingTime(v) for v in vehiculos) / n if n else 0.0
            velocidad = sum(t.vehicle.getSpeed(v) for v in vehiculos) / n if n else 0.0
        except Exception:
            espera, velocidad = 0.0, 0.0
        try:
            det_ids = t.lanearea.getIDList()
            occ_vals = [t.lanearea.getLastStepOccupancy(d) for d in det_ids]
            ocupacion = sum(occ_vals) / len(occ_vals) if occ_vals else 0.0
        except Exception:
            ocupacion = 0.0
        try:
            throughput = t.simulation.getArrivedNumber()
        except Exception:
            throughput = 0
        return espera, velocidad, ocupacion, throughput


# ---------------------------------------------------------------------------
# Entorno principal
# ---------------------------------------------------------------------------

class SumoDQNEnv2x2:
    """
    Entorno gym-style para 4 agentes DQN independientes en la red 2×2.

    reset() → Dict[str, (estado, acciones_validas)]
    step(acciones: Dict[str, int]) → (estados, recompensas, done, info)
    """

    def __init__(
        self,
        config: DQNConfig,
        gui: bool = False,
        duracion_sim_s: int = 3600,
    ) -> None:
        self._config = config
        self._gui = gui
        self._duracion_sim_s = duracion_sim_s
        self._traci = None

        self._estados: Dict[str, EstadoInterseccion] = {
            tl: EstadoInterseccion(tl_id=tl) for tl in TRAFFIC_LIGHTS_2x2
        }
        self._extractores: Dict[str, ExtractorEstadoLocal] = {}
        self._paso = 0
        self._temp_route_file: Optional[str] = None

    @property
    def state_dim(self) -> int:
        """Dimensión del vector de estado (igual para cada agente)."""
        dim = 4
        if self._config.state.include_waiting_time:  dim += 1
        if self._config.state.include_speed_avg:     dim += 1
        if self._config.state.include_occupancy:     dim += 1
        if self._config.state.include_phase_one_hot: dim += 4
        if self._config.state.include_phase_time:    dim += 1
        return dim

    @property
    def action_dim(self) -> int:
        return self._config.action.size()

    # ------------------------------------------------------------------
    # reset / step / close
    # ------------------------------------------------------------------

    def reset(
        self, demand: Optional[dict] = None
    ) -> Dict[str, Tuple[List[float], List[int]]]:
        """
        Reinicia la simulación.
        Devuelve {tl_id: (estado, acciones_validas)} para cada intersección.
        """
        self.close()
        setup_traci()
        import traci  # type: ignore

        _ensure_net_file_2x2()

        binario = find_binary("sumo-gui" if self._gui else "sumo")
        if not binario:
            raise RuntimeError("Binario SUMO no encontrado")

        archivo_rutas = self._escribir_rutas_temporales(demand)
        self._temp_route_file = archivo_rutas

        sumo_cmd = [
            binario,
            "-n", str(NET_FILE_2x2),
            "-r", archivo_rutas,
            "--no-step-log",
            "--time-to-teleport", "-1",
            "--quit-on-end",
        ]
        if self._gui:
            sumo_cmd.append("--start")

        traci.start(sumo_cmd)
        self._traci = traci

        for tl in TRAFFIC_LIGHTS_2x2:
            self._estados[tl] = EstadoInterseccion(tl_id=tl)
            self._extractores[tl] = ExtractorEstadoLocal(traci, tl, self._config)
            self._set_fase(tl, PHASE_GREEN_AV80, GREEN_MIN_S)

        self._paso = 0

        return {
            tl: self._snapshot_agente(tl)
            for tl in TRAFFIC_LIGHTS_2x2
        }

    def step(
        self, acciones: Dict[str, int]
    ) -> Tuple[
        Dict[str, List[float]],
        Dict[str, float],
        bool,
        InfoPaso2x2,
    ]:
        if not self._traci:
            raise RuntimeError("Entorno no inicializado. Llama reset() primero.")

        metricas_intervalo: Dict[str, _MetricasIntervalo] = {
            tl: _MetricasIntervalo() for tl in TRAFFIC_LIGHTS_2x2
        }
        cambios: Dict[str, bool] = {tl: False for tl in TRAFFIC_LIGHTS_2x2}

        for tl in TRAFFIC_LIGHTS_2x2:
            accion = acciones.get(tl, self._config.action.keep_idx)
            est = self._estados[tl]
            max_dur = self._max_duracion(tl)
            acciones_val = self._acciones_validas(tl, max_dur)

            if accion not in acciones_val:
                accion = self._config.action.keep_idx

            if (
                accion == self._config.action.switch_idx
                and est.tiempo_verde >= GREEN_MIN_S
            ):
                metricas_intervalo[tl].acumular(self._ejecutar_secuencia_cambio(tl))
                cambios[tl] = True
            else:
                if accion == self._config.action.extend_idx:
                    self._extender_fin_planeado(tl, max_dur)
                metricas_intervalo[tl].acumular(self._ejecutar_pasos(DECISION_STEP_S))
                est.tiempo_verde += DECISION_STEP_S

                if not self._terminado():
                    if est.tiempo_verde >= max_dur or est.tiempo_verde >= est.fin_planeado:
                        metricas_intervalo[tl].acumular(self._ejecutar_secuencia_cambio(tl))
                        cambios[tl] = True

        terminado = self._terminado()
        estados_sig: Dict[str, List[float]] = {}
        recompensas:  Dict[str, float]      = {}
        acciones_val_sig: Dict[str, List[int]] = {}

        for tl in TRAFFIC_LIGHTS_2x2:
            estado_v, _ , _ = self._extractores[tl].construir_estado(
                self._estados[tl].fase_verde_actual,
                self._estados[tl].tiempo_verde,
            )
            estados_sig[tl] = estado_v
            recompensas[tl] = self._calcular_recompensa(metricas_intervalo[tl], cambios[tl])
            acciones_val_sig[tl] = self._acciones_validas(tl, self._max_duracion(tl))

        # Métricas agregadas de red
        met_red = self._agregar_metricas(metricas_intervalo)
        efecto_rebote = self._calcular_efecto_rebote()

        info = InfoPaso2x2(
            acciones_validas=acciones_val_sig,
            pasos=DECISION_STEP_S,
            espera_red=met_red.espera_avg,
            cola_red=met_red.cola_avg,
            velocidad_red=met_red.velocidad_avg,
            co2_total=met_red.co2_total,
            throughput_total=met_red.throughput_total,
            efecto_rebote=efecto_rebote,
        )

        if terminado:
            self.close()

        return estados_sig, recompensas, terminado, info

    def close(self) -> None:
        if self._traci is not None:
            try:
                self._traci.close()
            except Exception:
                pass
        if self._temp_route_file and self._temp_route_file != str(ROUTE_FILE_2x2):
            try:
                Path(self._temp_route_file).unlink(missing_ok=True)
            except Exception:
                pass
        self._traci = None
        self._extractores = {}
        self._temp_route_file = None

    # ------------------------------------------------------------------
    # Helpers internos
    # ------------------------------------------------------------------

    def _snapshot_agente(self, tl: str) -> Tuple[List[float], List[int]]:
        est = self._estados[tl]
        estado_v, _, _ = self._extractores[tl].construir_estado(
            est.fase_verde_actual, est.tiempo_verde
        )
        max_dur = self._max_duracion(tl)
        return estado_v, self._acciones_validas(tl, max_dur)

    def _acciones_validas(self, tl: str, max_dur: int) -> List[int]:
        est = self._estados[tl]
        acciones = [self._config.action.keep_idx]
        if est.fin_planeado < max_dur:
            acciones.append(self._config.action.extend_idx)
        if est.tiempo_verde >= GREEN_MIN_S:
            acciones.append(self._config.action.switch_idx)
        if est.tiempo_verde >= max_dur:
            acciones = [self._config.action.switch_idx]
        return acciones

    def _max_duracion(self, tl: str) -> int:
        est = self._estados[tl]
        _, cola_av80, cola_c65 = self._extractores[tl].construir_estado(
            est.fase_verde_actual, est.tiempo_verde
        )
        cola_secundaria = cola_c65 if est.fase_verde_actual == PHASE_GREEN_AV80 else cola_av80
        return GREEN_MAX_S if cola_secundaria == 0 else GREEN_MAX_SHARED

    def _extender_fin_planeado(self, tl: str, max_dur: int) -> None:
        est = self._estados[tl]
        if est.fin_planeado >= max_dur:
            return
        extension = min(self._config.action.extend_step_s, max_dur - est.fin_planeado)
        if extension <= 0:
            return
        est.fin_planeado += extension
        restante = max(est.fin_planeado - est.tiempo_verde, 1)
        self._traci.trafficlight.setPhaseDuration(tl, restante)

    def _ejecutar_pasos(self, n: int) -> "_MetricasIntervalo":
        met = _MetricasIntervalo()
        for _ in range(n):
            self._traci.simulationStep()
            self._paso += 1
            met.actualizar(self._traci)
            if self._terminado():
                break
        return met

    def _ejecutar_secuencia_cambio(self, tl: str) -> "_MetricasIntervalo":
        met = _MetricasIntervalo()
        est = self._estados[tl]
        if est.fase_verde_actual == PHASE_GREEN_AV80:
            fase_amarillo = PHASE_YELLOW_AV80
            fase_todo_rojo = PHASE_ALL_RED_AV80
            siguiente_verde = PHASE_GREEN_C65
        else:
            fase_amarillo = PHASE_YELLOW_C65
            fase_todo_rojo = PHASE_ALL_RED_C65
            siguiente_verde = PHASE_GREEN_AV80

        self._set_fase(tl, fase_amarillo, YELLOW_S)
        met.acumular(self._ejecutar_pasos(YELLOW_S))
        if self._terminado():
            return met

        self._set_fase(tl, fase_todo_rojo, ALL_RED_S)
        met.acumular(self._ejecutar_pasos(ALL_RED_S))
        if self._terminado():
            return met

        est.fase_verde_actual = siguiente_verde
        est.tiempo_verde = 0
        est.fin_planeado = GREEN_MIN_S
        self._set_fase(tl, siguiente_verde, GREEN_MIN_S)
        return met

    def _set_fase(self, tl: str, fase: int, duracion: int) -> None:
        self._traci.trafficlight.setPhase(tl, fase)
        self._traci.trafficlight.setPhaseDuration(tl, duracion)
        self._estados[tl].fase_verde_actual = fase

    def _calcular_recompensa(self, met: "_MetricasIntervalo", cambio: bool) -> float:
        cfg = self._config.reward
        reward = (
            -cfg.w_queue    * (met.cola_avg    / cfg.queue_scale)
            -cfg.w_wait     * (met.espera_avg  / cfg.waiting_time_scale)
            +cfg.w_speed    * (met.velocidad_avg / cfg.speed_scale)
            +cfg.w_throughput * (met.throughput_total / cfg.throughput_scale)
            -cfg.w_co2      * (met.co2_total   / cfg.co2_scale)
            -cfg.w_switch   * (1.0 if cambio else 0.0)
        )
        return reward

    def _agregar_metricas(
        self, mets: Dict[str, "_MetricasIntervalo"]
    ) -> "_MetricasIntervalo":
        agregado = _MetricasIntervalo()
        n = len(mets)
        for m in mets.values():
            agregado.pasos += m.pasos
            agregado.suma_espera += m.suma_espera
            agregado.suma_cola   += m.suma_cola
            agregado.suma_velocidad += m.suma_velocidad
            agregado.co2_total   += m.co2_total
            agregado.throughput_total += m.throughput_total
        # Promediar espera/cola/velocidad entre los 4 agentes
        if n > 0:
            agregado.suma_espera    /= n
            agregado.suma_cola      /= n
            agregado.suma_velocidad /= n
        return agregado

    def _calcular_efecto_rebote(self) -> float:
        """
        Diferencia de cola máxima entre intersecciones upstream (J0, J1)
        y downstream (J2, J3) en el corredor Av. 80.
        Valor positivo = congestión aguas abajo mayor que aguas arriba.
        """
        if not self._traci:
            return 0.0
        try:
            def cola_tl(tl: str) -> int:
                total = 0
                for arista in EDGES_2x2[tl]["AV80"] + EDGES_2x2[tl]["C65"]:
                    try:
                        for vid in self._traci.edge.getLastStepVehicleIDs(arista):
                            if self._traci.vehicle.getSpeed(vid) < 0.1:
                                total += 1
                    except Exception:
                        pass
                return total

            upstream   = (cola_tl("J0") + cola_tl("J1")) / 2
            downstream = (cola_tl("J2") + cola_tl("J3")) / 2
            return downstream - upstream
        except Exception:
            return 0.0

    def _terminado(self) -> bool:
        if not self._traci:
            return True
        return (
            self._traci.simulation.getMinExpectedNumber() <= 0
            or self._paso >= self._duracion_sim_s
        )

    def _escribir_rutas_temporales(self, demand: Optional[dict]) -> str:
        """Genera un .rou.xml temporal con flujos del perfil dado (solo flows NS/SN/EW/WE)."""
        if demand is None:
            return str(ROUTE_FILE_2x2)

        texto = Path(ROUTE_FILE_2x2).read_text(encoding="utf-8")

        # Actualizar flujos por corredor escalando con los valores del perfil
        mapping = {
            "flow_NS_W": demand["flow_NS"],
            "flow_NS_E": demand["flow_NS"],
            "flow_SN_W": demand["flow_SN"],
            "flow_SN_E": demand["flow_SN"],
            "flow_EW_N": demand["flow_EW"],
            "flow_EW_S": demand["flow_EW"],
            "flow_WE_N": demand["flow_WE"],
            "flow_WE_S": demand["flow_WE"],
        }
        for flow_id, veh_h in mapping.items():
            texto = re.sub(
                rf'(<flow\s[^>]*id="{flow_id}"[^>]*)\bvehsPerHour="[^"]*"',
                rf'\1vehsPerHour="{veh_h}"',
                texto,
            )

        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".rou.xml", delete=False,
            encoding="utf-8", dir=SCENARIO_DIR,
        )
        tmp.write(texto)
        tmp.flush()
        tmp.close()
        return tmp.name


# ---------------------------------------------------------------------------
# Métricas de intervalo (acumula snapshots durante un step)
# ---------------------------------------------------------------------------

class _MetricasIntervalo:
    def __init__(self) -> None:
        self.pasos = 0
        self.suma_espera = 0.0
        self.suma_cola   = 0.0
        self.suma_velocidad = 0.0
        self.co2_total   = 0.0
        self.throughput_total = 0

    def actualizar(self, traci) -> None:
        vehiculos = traci.vehicle.getIDList()
        n = len(vehiculos)
        self.pasos += 1
        if n:
            self.suma_espera    += sum(traci.vehicle.getWaitingTime(v) for v in vehiculos) / n
            self.suma_cola      += sum(1 for v in vehiculos if traci.vehicle.getSpeed(v) < 0.1)
            self.suma_velocidad += sum(traci.vehicle.getSpeed(v) for v in vehiculos) / n
            self.co2_total      += sum(traci.vehicle.getCO2Emission(v) for v in vehiculos)
        self.throughput_total += traci.simulation.getArrivedNumber()

    def acumular(self, otro: "_MetricasIntervalo") -> None:
        self.pasos            += otro.pasos
        self.suma_espera      += otro.suma_espera
        self.suma_cola        += otro.suma_cola
        self.suma_velocidad   += otro.suma_velocidad
        self.co2_total        += otro.co2_total
        self.throughput_total += otro.throughput_total

    @property
    def espera_avg(self) -> float:
        return self.suma_espera / self.pasos if self.pasos else 0.0

    @property
    def cola_avg(self) -> float:
        return self.suma_cola / self.pasos if self.pasos else 0.0

    @property
    def velocidad_avg(self) -> float:
        return self.suma_velocidad / self.pasos if self.pasos else 0.0
