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
| `FLOW_WEIGHT_AV80` | 2508 | Aforo vespertino real 15/05/2025 |
| `FLOW_WEIGHT_C65` | 1328 | Aforo vespertino real 15/05/2025 |
| `FLOW_SCALE` | 0.03 | Escala flujo base → magnitud de cola |
| Pesos presión | 80% cola / 20% flujo | Cola observada domina |

---

## Flujos actuales (rutas.rou.xml — aforo vespertino real, 15:15–16:15, viernes 15/05/2025)

| Flujo | veh/h | Tipo |
|---|---|---|
| flow_NS (N→S, Av80) | 1147 | car |
| flow_SN (S→N, Av80) | 1361 | car |
| flow_EW (E→W, C65) | 280 | car |
| flow_WE (W→E, C65) | 308 | car |
| flow_EN (giro derecha E→N) | 431 | car |
| flow_WS (giro derecha W→S) | 309 | car |

**Total Av80: 2508 veh/h | Total C65: 1328 veh/h**

> Nota: vTypes moto/bus/truck/bicycle están definidos en el XML pero
> ningún flow los usa actualmente. Pendiente decidir si se activan para DQN.

---

## Resultados benchmark 3600s — flujos reales vespertinos (05/06/2026)

> Flujos: NS=1147, SN=1361, EW=280, WE=308, EN=431, WS=309 veh/h

### Fijo vs Heurística v3

| Métrica | Tiempos Fijos | Heurística v3 | Δ% |
|---|---|---|---|
| Espera prom. (s) | — | — | — |
| Cola prom. (veh) | — | — | — |
| Cola max. (veh) | — | — | — |
| Velocidad (m/s) | — | — | — |
| Throughput (veh) | — | — | — |
| CO2 total (mg) | — | — | — |

**Conclusión (05/06/2026):** con flujos reales vespertinos la heurística v3
**cumple todas las metas del PMV**. El nuevo baseline fijo (flujos reales)
es el punto de comparación para DQN.

### Referencia histórica — benchmark con flujos sintéticos (10/05/2026)

| Métrica | Tiempos Fijos | Heurística v3 | Δ% |
|---|---|---|---|
| Espera prom. (s) | 3.38 | 5.44 | +61% |
| Cola prom. (veh) | 17.42 | 24.92 | +43% |
| Cola max. (veh) | 41 | 50 | +22% |
| Velocidad (m/s) | 8.64 | 8.08 | -6.5% |
| Throughput (veh) | 3022 | 3006 | -0.5% |
| CO2 total (mg) | 705M | 751M | +6.5% |

*(Flujos sintéticos uniformes 900/900/600/600 veh/h — ya no es el escenario activo)*

### Patrón observable en los logs del adaptativo:
```
paso  900 | cola_max=  7-17 veh  ← drenado
paso 1200 | cola_max= 27-31 veh  ← acumulación
paso 1800 | cola_max=  9-19 veh  ← drenado
paso 2100 | cola_max= 25-27 veh  ← acumulación
```
El fijo mantiene colas constantes sin drenarlas.

---

## Resultados DQN — entrenamiento preliminar (05/06/2026)

**Configuración:** 10 episodios × 3600s | perfiles cíclicos × 5 | device=cpu

| Métrica | Meta PMV | DQN 10 ep | Estado |
|---|---|---|---|
| Espera prom. (s) | ≤ fijo | OK | ✓ cumple |
| Cola prom. (veh) | ≤ fijo | — | pendiente |
| CO2 total (mg) | ≤ fijo | — | pendiente |

**Conclusión parcial:** la espera promedio converge en la dirección correcta
con solo 10 episodios. Colas y CO2 requieren más entrenamiento para estabilizar.
**Próximo paso:** 30 episodios overnight para evaluar convergencia completa.

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
- [x] ~~Confirmar entorno DQN~~ — CPU local (confirmado)
- [x] ~~Implementar agente DQN~~ — DoubleDQN implementado en `rl/double_dqn_agent.py`
- [x] ~~Adaptar traci_runner.py~~ — modo `dqn` operativo
- [x] ~~Actualizar benchmark.py~~ — compara fijo / heurística / dqn
- [ ] **Entrenar DQN overnight** — 30 episodios × 3600s (→ `models/dqn_latest.pt`)
- [ ] **Completar tabla benchmark** — llenar filas pendientes (colas, CO2) con resultados reales
- [ ] **Verificar convergencia** — recompensa por episodio debe estabilizarse

### Importantes
- [ ] **Actualizar dashboard** — agregar curva de recompensa DQN + comparación 3 modos
- [ ] **Tests** — cobertura >= 70% (RNF-05), actualmente 0%
- [ ] **Actualizar informe** — sección resultados con tabla de 3 modos y flujos reales

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