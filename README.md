# Semaforos - Simulacion SUMO

## Requisitos

- Python 3.9+ instalado y en PATH
- SUMO instalado (sumo y sumo-gui en PATH)
- Windows PowerShell recomendado

Nota: si usas percepcion (YOLO), puede ser necesario instalar PyTorch
segun tu GPU/CPU. Si `pip install -r requirements.txt` no instala
`torch`, sigue la guia oficial de PyTorch.

## Instalacion

1) Crear y activar entorno virtual:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2) Actualizar pip e instalar dependencias:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

3) Verificar SUMO:

```powershell
sumo-gui -v
```

Si ese comando falla, agrega SUMO a PATH.

## Configuracion rapida

Edita [orquestador.py](orquestador.py) y ajusta:

- `USAR_DEMANDA_SINTETICA` (True/False)
- `USAR_DEMANDA_PERCEPCION` (True/False)
- `FUENTES_PERCEPCION` si usas videos
- Parametros de demanda sintetica en el bloque `SINT_*`

Por defecto, la demanda sintetica esta activa y la percepcion desactivada.

## Ejecutar

```powershell
python .\orquestador.py
```

Si usas percepcion, asegurate de tener los videos y `yolov8n.pt` en la raiz.

## Notas

- La demanda se inyecta via TraCI; no hay flujos fijos en `rutas.rou.xml`.
- Si quieres calibrar el control adaptativo, ajusta `VEL_REF_KMH` y
  `FACTOR_CONGESTION` en [orquestador.py](orquestador.py).
