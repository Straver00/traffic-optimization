"""Train Double DQN agent in SUMO environment."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rl.config import DQNConfig
from rl.double_dqn_agent import DoubleDQNAgent
from simulation.rl_env import SumoDQNEnv

# Perfiles de demanda (veh/h) para variar la carga entre episodios.
# TODO: para que estos perfiles tengan efecto real, SumoDQNEnv.reset() debe
# aceptar un parámetro `demand_profile: dict` y regenerar (o seleccionar) el
# archivo de rutas correspondiente antes de llamar a traci.start(). Por ahora
# el perfil se selecciona y se imprime, pero la simulación sigue usando
# ROUTE_FILE estático (rutas.rou.xml).
DEMAND_PROFILES = [
    # Valle (~40% del pico real vespertino 15/05/2025)
    {
        "name": "Valle",
        "flow_NS": 459,
        "flow_SN": 544,
        "flow_EW": 112,
        "flow_WE": 123,
    },
    # Pico normal — valores exactos del aforo vespertino (15:15-16:15, 15/05/2025)
    {
        "name": "Pico normal",
        "flow_NS": 1147,
        "flow_SN": 1361,
        "flow_EW": 280,
        "flow_WE": 308,
    },
    # Pico extremo (~120% del pico real, hora vespertina extrema)
    {
        "name": "Pico extremo",
        "flow_NS": 1376,
        "flow_SN": 1633,
        "flow_EW": 336,
        "flow_WE": 370,
    },
    # Asimétrico 1 — Av80 cargada N→S, C65 baja
    {
        "name": "Asimetrico 1",
        "flow_NS": 1400,
        "flow_SN": 900,
        "flow_EW": 180,
        "flow_WE": 200,
    },
    # Asimétrico 2 — Av80 cargada S→N, C65 equilibrada
    {
        "name": "Asimetrico 2",
        "flow_NS": 700,
        "flow_SN": 1500,
        "flow_EW": 300,
        "flow_WE": 280,
    },
]


def build_config(device: str) -> DQNConfig:
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
    parser = argparse.ArgumentParser(description="Entrenamiento Double DQN en SUMO")
    parser.add_argument("--episodes", type=int, default=50, help="Numero de episodios")
    parser.add_argument("--duration", type=int, default=3600, help="Duracion por episodio (s)")
    parser.add_argument("--device", type=str, default="cpu", help="Dispositivo torch: cpu | cuda")
    parser.add_argument("--save-every", type=int, default=10, help="Guardar modelo cada N episodios")
    parser.add_argument("--model-path", type=str, default="models/dqn_latest.pt", help="Ruta de guardado")
    parser.add_argument("--gui", action="store_true", help="Usar sumo-gui")
    args = parser.parse_args()

    config = build_config(args.device)
    env = SumoDQNEnv(config, gui=args.gui, sim_duration_s=args.duration)
    agent = DoubleDQNAgent(env.state_dim, env.action_dim, config)

    model_path = Path(args.model_path)
    model_path.parent.mkdir(parents=True, exist_ok=True)

    for episode in range(1, args.episodes + 1):
        profile = DEMAND_PROFILES[(episode - 1) % len(DEMAND_PROFILES)]
        print(f"[train] episodio {episode:>3} | perfil={profile['name']}")

        state, valid_actions = env.reset(demand=profile)
        done = False
        episode_reward = 0.0
        steps = 0

        while not done:
            action = agent.select_action(state, valid_actions, training=True)
            next_state, reward, done, info = env.step(action)
            agent.store_transition(state, action, reward, next_state, done, valid_actions, info.valid_actions)
            agent.learn()

            episode_reward += reward
            steps += 1
            state = next_state
            valid_actions = info.valid_actions

        print(f"[train] episodio {episode:>3} | pasos={steps:>4} | recompensa={episode_reward:>8.3f}")

        if episode % args.save_every == 0:
            agent.save(str(model_path))
            print(f"[train] modelo guardado -> {model_path}")

    agent.save(str(model_path))
    print(f"[train] modelo final guardado -> {model_path}")


if __name__ == "__main__":
    main()
