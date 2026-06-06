"""Entrenamiento de 4 agentes Double DQN independientes en la red 2×2."""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

OUTPUT_DIR = ROOT / "evaluation" / "results"

from rl.config import DQNConfig
from rl.double_dqn_agent import DoubleDQNAgent
from simulation.rl_env_2x2 import SumoDQNEnv2x2
from decision.traffic_config import TRAFFIC_LIGHTS_2x2
from training.train_dqn import DEMAND_PROFILES


def construir_config(device: str) -> DQNConfig:
    base = DQNConfig()
    training = replace(base.training, device=device)
    return DQNConfig(
        action=base.action,
        state=base.state,
        norm=base.norm,
        reward=base.reward,
        exploration=base.exploration,
        training=training,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Entrenamiento Double DQN — Red 2×2")
    parser.add_argument("--episodes",   type=int,   default=30,
                        help="Numero de episodios")
    parser.add_argument("--duration",   type=int,   default=3600,
                        help="Duracion por episodio (s)")
    parser.add_argument("--device",     type=str,   default="cpu",
                        help="Dispositivo torch: cpu | cuda")
    parser.add_argument("--save-every", type=int,   default=5,
                        help="Guardar checkpoints cada N episodios")
    parser.add_argument("--model-path", type=str,   default="models/dqn_2x2",
                        help="Prefijo de ruta para los 4 checkpoints")
    parser.add_argument("--gui",        action="store_true",
                        help="Usar sumo-gui")
    args = parser.parse_args()

    config = construir_config(args.device)
    env    = SumoDQNEnv2x2(config, gui=args.gui, duracion_sim_s=args.duration)

    # Un agente por intersección, cada uno con su propio buffer y red
    agentes: dict[str, DoubleDQNAgent] = {
        tl: DoubleDQNAgent(env.state_dim, env.action_dim, config)
        for tl in TRAFFIC_LIGHTS_2x2
    }

    prefijo = Path(args.model_path)
    prefijo.parent.mkdir(parents=True, exist_ok=True)

    historial_recompensas: list[dict] = []

    for episodio in range(1, args.episodes + 1):
        perfil = DEMAND_PROFILES[(episodio - 1) % len(DEMAND_PROFILES)]
        print(f"[train_2x2] episodio {episodio:>3} | perfil={perfil['name']}")

        obs = env.reset(demand=perfil)
        estados = {tl: obs[tl][0] for tl in TRAFFIC_LIGHTS_2x2}
        acciones_val = {tl: obs[tl][1] for tl in TRAFFIC_LIGHTS_2x2}

        hecho = False
        recompensas_ep = {tl: 0.0 for tl in TRAFFIC_LIGHTS_2x2}
        pasos_ep = 0

        while not hecho:
            acciones = {
                tl: agentes[tl].select_action(
                    estados[tl], acciones_val[tl], training=True
                )
                for tl in TRAFFIC_LIGHTS_2x2
            }

            estados_sig, recompensas, hecho, info = env.step(acciones)

            for tl in TRAFFIC_LIGHTS_2x2:
                agentes[tl].store_transition(
                    estados[tl],
                    acciones[tl],
                    recompensas[tl],
                    estados_sig[tl],
                    hecho,
                    acciones_val[tl],
                    info.acciones_validas[tl],
                )
                agentes[tl].learn()
                recompensas_ep[tl] += recompensas[tl]

            pasos_ep += 1
            estados      = estados_sig
            acciones_val = info.acciones_validas

        recomp_total = sum(recompensas_ep.values())
        print(
            f"[train_2x2] episodio {episodio:>3} | pasos={pasos_ep:>4} "
            f"| recompensa_total={recomp_total:>9.3f} "
            f"| efecto_rebote={info.efecto_rebote:>6.1f} veh"
        )
        historial_recompensas.append({
            "episodio":            episodio,
            "J0":                  round(recompensas_ep["J0"], 4),
            "J1":                  round(recompensas_ep["J1"], 4),
            "J2":                  round(recompensas_ep["J2"], 4),
            "J3":                  round(recompensas_ep["J3"], 4),
            "recompensa_total_red": round(recomp_total, 4),
        })

        if episodio % args.save_every == 0:
            for tl, agente in agentes.items():
                ruta = f"{prefijo}_{tl}.pt"
                agente.save(ruta)
                print(f"[train_2x2] checkpoint guardado -> {ruta}")

    # Guardado final de checkpoints
    for tl, agente in agentes.items():
        ruta = f"{prefijo}_{tl}.pt"
        agente.save(ruta)
        print(f"[train_2x2] modelo final guardado -> {ruta}")

    # Persistir curva de recompensa para análisis posterior
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ruta_curva = OUTPUT_DIR / "entrenamiento_2x2_recompensas.csv"
    campos = ["episodio", "J0", "J1", "J2", "J3", "recompensa_total_red"]
    with open(ruta_curva, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        writer.writerows(historial_recompensas)
    print(f"[train_2x2] curva de recompensa guardada -> {ruta_curva}")


if __name__ == "__main__":
    main()
