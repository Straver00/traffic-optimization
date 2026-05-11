# SIAVA — Resumen de sesión de desarrollo

**Fecha:** 10/05/2026  
**Rama de trabajo:** `david`  
**Repo:** `c:\Users\usuario\Documents\GitHub\traffic-optimization`

---

## Estado actual del repo

```
traffic-optimization/
├── decision/
│   ├── __init__.py
│   └── adaptive_controller.py      ← controlador heurístico v3 (ACTIVO)
├── simulation/
│   ├── __init__.py
│   └── traci_runner.py
├── evaluation/
│   ├── __init__.py
│   ├── metrics.py                  ← 7 indicadores + steady-state summary
│   ├── benchmark.py                ← compara fijo vs adaptativo
│   └── results/                    ← CSVs y JSONs generados aquí
├── dashboard/
│   ├── dashboard.html              ← dashboard web tiempo real
│   └── serve_dashboard.py          ← servidor HTTP (puerto 8000)
├── intersection_av80_c65/          ← configuración SUMO completa
├── images/                         ← 83 fotos reales cámaras Medellín
├── modulo_percepcion.py            ← YOLOv8 + ByteTrack (del compañero, no integrado)
├── orquestador.py                  ← pipeline del compañero (archivado, no usar)
├── perception.py                   ← script de prueba YOLOv8 (no integrado)
├── yolov8n.pt
└── requirements.txt
```

**Archivos eliminados:** `run_traci_gui.py` (reemplazado por `simulation/traci_runner.py`)

---

## Decisión de arquitectura — ACTUALIZADA

**Arquitectura actual:** controlador heurístico v3 (funcional, en producción)  
**Próximo paso:** reemplazar por agente **DQN** — decisión tomada en sesión 10/05  
**Pendiente:** confirmar entorno de entrenamiento (GPU local vs CPU vs Colab)

La heurística queda como baseline de comparación en el informe:
- Fijo vs Heurística vs DQN

---

## Cómo correr el proyecto

### Demo completa (2 terminales)

**Terminal 1 — servidor dashboard:**
```bash
python dashboard/serve_dashboard.py
```
Abre automáticamente `http://localhost:8000/dashboard/dashboard.html`

**Terminal 2 — simulación:**
```bash
python evaluation/benchmark.py --duration 3600
```

### Solo adaptativo (reutiliza resultados fijos existentes)
```bash
python evaluation/benchmark.py --duration 3600 --skip-fixed
```

---

## Parámetros actuales del controlador v3 (adaptive_controller.py)

| Parámetro | Valor | Nota |
|---|---|---|
| `GREEN_MIN_S` | 15 s | Manual de Señalización Vial 2024 |
| `GREEN_MAX_S` | 90 s | Solo si la fase contraria está vacía |
| `GREEN_MAX_SHARED` | 60 s | Tope cuando ambas fases tienen cola |
| `ALL_RED_S` | 15 s | Fijo — del semaforo.tll.xml |
| `MAX_SKIP_CYCLES` | 1 | Máx. 1 ciclo sin verde por fase |
| `FLOW_WEIGHT_AV80` | 1800 | Actualizado — refleja flujos reales |
| `FLOW_WEIGHT_C65` | 1500 | Actualizado — refleja flujos reales |
| `FLOW_SCALE` | 0.03 | Escala flujo base → magnitud de cola |
| Pesos presión | 80% cola / 20% flujo | Cola observada domina |

---

## Flujos actuales (rutas.rou.xml — hora pico matutina)

| Flujo | veh/h | Tipo |
|---|---|---|
| flow_NS (N→S, Av80) | 900 | car |
| flow_SN (S→N, Av80) | 900 | car |
| flow_EW (E→W, C65) | 600 | car |
| flow_WE (W→E, C65) | 600 | car |
| flow_EN (giro derecha E→N) | 150 | car |
| flow_WS (giro derecha W→S) | 150 | car |

**Total Av80: 1800 veh/h | Total C65: 1500 veh/h**

> Nota: vTypes moto/bus/truck/bicycle están definidos en el XML pero
> ningún flow los usa actualmente. Pendiente decidir si se activan para DQN.

---

## Resultados benchmark 3600s (estado actual — heurística v3)

| Métrica | Tiempos Fijos | Heurística v3 | Δ% |
|---|---|---|---|
| Espera prom. (s) | 3.38 | 5.44 | +61% |
| Cola prom. (veh) | 17.42 | 24.92 | +43% |
| Cola max. (veh) | 41 | 50 | +22% |
| Velocidad (m/s) | 8.64 | 8.08 | -6.5% |
| Throughput (veh) | 3022 | 3006 | -0.5% |
| CO2 total (mg) | 705M | 751M | +6.5% |

**Conclusión:** la heurística no supera al fijo en flujo constante — resultado
conocido en la literatura. El argumento de la entrega es el ciclo detección-drenaje
y el comportamiento ante demanda variable, NO la espera promedio.

### Patrón observable en los logs del adaptativo:
```
paso  900 | cola_max=  7-17 veh  ← drenado
paso 1200 | cola_max= 27-31 veh  ← acumulación
paso 1800 | cola_max=  9-19 veh  ← drenado
paso 2100 | cola_max= 25-27 veh  ← acumulación
```
El fijo mantiene colas constantes de 17-25 veh sin drenarlas nunca.

---

## Tuneo intentado en sesión 10/05 (descartado)

| Cambio | Resultado |
|---|---|
| FLOW_WEIGHT 1200/900 → 1800/1500 | Sin efecto (+0.1%) |
| GREEN_MAX_S=60, GREEN_MAX_SHARED=45 | Empeoró (+105% espera) |
| Controlador v4 (presión acumulada) | Empeoró (+105% espera, cola_max=57) |

**Conclusión:** la heurística de cola instantánea tiene un límite estructural
en flujo constante. Se decide pasar a DQN como arquitectura definitiva.

---

## Argumento para la entrega (Opción B — decidido en sesión)

**No usar "menor espera promedio"** — los tiempos fijos bien calibrados
ganan en flujo constante. Ese resultado es conocido en la literatura.

**Argumento correcto:**
> *"El sistema fijo mantiene colas permanentes de 17-43 vehículos.
> El adaptativo las drena periódicamente a 7-9 vehículos.
> En condiciones de demanda variable (hora pico vs valle), el adaptativo
> supera al fijo porque ajusta los tiempos — algo que el fijo no puede
> hacer por definición."*

**El Escenario 2 (red 2×2)** es donde el valor real se demuestra:
coordinación entre intersecciones es imposible con tiempos fijos.

---

## Bugs resueltos (histórico)

| Bug | Causa | Fix |
|---|---|---|
| `UnicodeEncodeError` | Windows cp1252 no soporta ▶→✓Δ | Reemplazar por ASCII |
| `phase index 3 not in [0,2]` | XML tiene 3 fases, no 4 | Eliminar fases amarillo |
| `Can not switch to program '0'` | ID es `programa_av80_c65` | Actualizar PROGRAM_ID |
| Timer inicial = 0 | Disparaba advance_phase en paso 1 | Inicializar en FALLBACK_GREEN_AV80 |
| Dashboard 404 en JSONs | Rutas relativas desde /dashboard/ | Rutas absolutas /evaluation/results/... |

---

## Pendientes para la próxima sesión

### Críticos
- [ ] **Confirmar entorno DQN** — GPU local / CPU / Colab
- [ ] **Implementar agente DQN** en `decision/dqn_agent.py`
      - Espacio de estados: colas N/S/E/W + fase actual + tiempo en fase
      - Acciones: mantener fase / cambiar fase
      - Reward: negativo proporcional a cola total + penalización por cambio innecesario
- [ ] **Adaptar traci_runner.py** para modo "dqn" además de "fixed" y "adaptive"
- [ ] **Entrenar el agente** (mínimo 100 episodios de 3600s)
- [ ] **Actualizar benchmark.py** — agregar modo dqn a la comparación

### Importantes
- [ ] **Actualizar dashboard** — contar historia del drenaje de colas (Opción B)
- [ ] **Tests** — cobertura >= 70% (RNF-05), actualmente 0%
- [ ] **Actualizar informe** — sección resultados con argumento correcto

### Deseables
- [ ] **Escenario 2** — red 2×2 con coordinación entre intersecciones
- [ ] **perception.py** — refactorizar en módulos separados
- [ ] Activar vTypes mixtos (moto/bus/truck) en rutas.rou.xml para DQN

---

## Warnings de SUMO (no críticos)

```
Warning: Missing yellow phase in tlLogic 'J0'...
Warning: Vehicle performs emergency braking...
```
Ambos son informativos. Funcionamiento correcto.

---

*Continuar esta sesión pegando este README como contexto inicial.*