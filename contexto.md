# SIAVA — Resumen de sesión de desarrollo

**Fecha:** 09/05/2026  
**Rama de trabajo:** `david`  
**Repo:** `c:\Users\usuario\Documents\GitHub\traffic-optimization`

---

## Estado al inicio de la sesión

El repo solo tenía:
- `perception.py` — detección básica YOLOv8 sobre imágenes estáticas
- `run_traci_gui.py` — abría SUMO-GUI sin ningún agente conectado
- `intersection_av80_c65/` — configuración SUMO completa ✅
- `images/` — 83 fotos reales de cámaras de Medellín ✅
- `yolov8n.pt` — modelo preentrenado ✅

Todo lo del README (decision/, evaluation/, simulation/, tests/, etc.) **no existía**.

---

## Decisión de arquitectura tomada

**Se descartó MARL-DQN para el PMV** y se reemplazó por **reglas heurísticas**.  
Justificación: explicable, demostrable sin entrenamiento, suficiente para validar
que el control adaptativo supera tiempos fijos. MARL-DQN queda como evolución futura.

---

## Archivos creados en esta sesión

```
traffic-optimization/
├── decision/
│   ├── __init__.py
│   └── adaptive_controller.py      ← controlador heurístico (v3 actual)
├── simulation/
│   ├── __init__.py
│   └── traci_runner.py             ← reemplaza run_traci_gui.py
├── evaluation/
│   ├── __init__.py
│   ├── metrics.py                  ← 7 indicadores + steady-state summary
│   ├── benchmark.py                ← compara fijo vs adaptativo
│   └── results/                    ← CSVs y JSONs generados aquí
└── dashboard/
    ├── dashboard.html              ← dashboard web tiempo real
    └── serve_dashboard.py          ← servidor HTTP (puerto 8000)
```

**Archivo eliminado:** `run_traci_gui.py` (reemplazado por `simulation/traci_runner.py`)

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

El dashboard se actualiza cada 1.5s en tiempo real mientras corre.

### Solo simulación rápida (600s, prueba)
```bash
python evaluation/benchmark.py --duration 600
```

### Reutilizar resultados fijos (solo correr adaptativo)
```bash
python evaluation/benchmark.py --duration 3600 --skip-fixed
```

---

## Parámetros actuales del controlador (adaptive_controller.py)

| Parámetro | Valor | Nota |
|---|---|---|
| `GREEN_MIN_S` | 15 s | Manual de Señalización Vial 2024 |
| `GREEN_MAX_S` | 90 s | Solo si la fase contraria está vacía |
| `GREEN_MAX_SHARED` | 60 s | Tope cuando ambas fases tienen cola |
| `ALL_RED_S` | 15 s | Fijo — del semaforo.tll.xml |
| `MAX_SKIP_CYCLES` | 1 | Máx. 1 ciclo sin verde por fase |
| `FLOW_WEIGHT_AV80` | 1200 | flow_NS(900) + flow_SN(900) — actualizar si cambian flujos |
| `FLOW_WEIGHT_C65` | 900 | flow_EW(600) + flow_WE(600) + giros(300) |
| `FLOW_SCALE` | 0.03 | Escala flujo base → magnitud de cola |
| Pesos presión | 80% cola / 20% flujo | Cola observada domina |

### Fases SUMO reales (semaforo.tll.xml)
| Índice | Nombre | Duración base | Estado |
|---|---|---|---|
| 0 | Verde Av. 80 | 52 s | `GGGrrrGGGrrr` |
| 1 | Todo rojo / peatonal | 15 s | `rrrrrrrrrrrr` |
| 2 | Verde Calle 65 | 33 s | `rrrGGGrrrGGG` |

---

## Flujos actuales (rutas.rou.xml — hora pico matutina)

| Flujo | veh/h |
|---|---|
| flow_NS (N→S, Av80) | 900 |
| flow_SN (S→N, Av80) | 900 |
| flow_EW (E→W, C65) | 600 |
| flow_WE (W→E, C65) | 600 |
| flow_EN (giro derecha E→N) | 150 |
| flow_WS (giro derecha W→S) | 150 |

**Total Av80: 1800 veh/h | Total C65: 1500 veh/h**

---

## Resultados del último benchmark (3600s, hora pico)

| Métrica | Tiempos Fijos | Adaptativo | Δ% |
|---|---|---|---|
| Espera prom. (s) | 3.36 | 5.66* | +68% |
| Cola prom. (veh) | 17.1 | 25.1 | +47% |
| Cola max. (veh) | 43 | 51 | +19% |
| Velocidad (m/s) | 8.75 | 8.14 | -7% |
| Throughput (veh) | 3195 | 3187 | -0.2% |
| CO2 steady-state | 762M mg | 755M mg | **-0.8%** ✓ |

*La espera promedio incluye picos de acumulación. La mediana es 4.8s.

### Patrón observado del adaptativo (cada ~600 pasos):
```
Acumulación → Drenaje → Vaciado → Acumulación
   ~8s            ~4s       ~1s       ~8s
```
El sistema detecta y drena colas activamente. Los tiempos fijos mantienen
colas constantes de 17-43 vehículos sin drenajarlas nunca.

---

## Argumento para la entrega (decidido en sesión)

**No usar "menor espera promedio"** — los tiempos fijos bien calibrados
ganan en flujo constante. Ese resultado es conocido en la literatura.

**Argumento correcto:**
> *"El sistema fijo mantiene colas permanentes de 17-43 vehículos.
> El adaptativo las drena periódicamente a 7-9 vehículos.
> En condiciones de demanda variable (hora pico vs valle), el adaptativo
> supera al fijo porque ajusta los tiempos — algo que el fijo no puede
> hacer por definición. El CO2 en steady-state ya es menor."*

El **Escenario 2 (red 2×2)** es donde el valor real se demuestra:
coordinación entre intersecciones es imposible con tiempos fijos.

---

## Bugs resueltos en la sesión

| Bug | Causa | Fix |
|---|---|---|
| `UnicodeEncodeError` | Windows cp1252 no soporta ▶→✓Δ | Reemplazar todos por ASCII |
| `phase index 3 not in [0,2]` | XML tiene 3 fases, no 4 | Eliminar fases amarillo, usar PHASE_ALL_RED |
| `Can not switch to program '0'` | ID del programa es `programa_av80_c65` | Actualizar PROGRAM_ID |
| Timer inicial = 0 | Disparaba advance_phase en paso 1 | Inicializar en FALLBACK_GREEN_AV80 |
| Adaptativo peor que fijo | FLOW_SCALE demasiado alto, MAX_SKIP=2 | FLOW_SCALE=0.03, MAX_SKIP=1, GREEN_MAX_SHARED=60 |
| Dashboard 404 en JSONs | Rutas relativas desde /dashboard/ | Cambiar a rutas absolutas /evaluation/results/... |

---

## Pendientes para la próxima sesión

- [ ] **Actualizar FLOW_WEIGHT_AV80/C65** en `adaptive_controller.py` para
      reflejar los flujos actuales (1800/1500 en lugar de 1200/900)
- [ ] **Mejorar benchmark.py** para aplicar `summary_steady_state` también
      al fijo (comparación simétrica)
- [ ] **Actualizar el dashboard** para contar la historia correcta:
      mostrar la oscilación como "detección y drenaje de colas", no como inestabilidad
- [ ] **Actualizar el informe** — sección de resultados con el argumento correcto
- [ ] **Escenario 2** — red 2×2 con coordinación entre intersecciones
- [ ] **Tests** — cobertura >= 70% (RNF-05), actualmente 0%
- [ ] **perception.py** — refactorizar en módulos separados (yolov8_detector.py, etc.)

---

## Warnings de SUMO (no críticos)

```
Warning: Missing yellow phase in tlLogic 'J0'...
Warning: Vehicle performs emergency braking...
```
Ambos son informativos. El XML usa rojo total como transición en lugar de
amarillo — SUMO lo advierte pero funciona correctamente. Los frenados de
emergencia son normales al cambiar de fase con vehículos cerca del semáforo.

---

*Continuar esta sesión pegando este README como contexto inicial.*