import os
import time
import random
import math
import traci

from modulo_percepcion import (
    inicializar_modulo_percepcion,
    cerrar_modulo_percepcion,
    cargar_configuracion_json
)

# CONFIGURACIÓN GENERAL
CARPETA_SUMO = "intersection_av80_c65"
ARCHIVO_CONFIG = "intersection_av80_c65.sumocfg"
ID_SEMAFORO = "J0"

# Cambia a False si quieres correr sin interfaz gráfica
USAR_INTERFAZ_GRAFICA = True

# Tiempo total de simulación en segundos
TIEMPO_SIMULACION = 3600

# Fases del semáforo según el programa que definimos
FASE_AV80_VERDE = 0
FASE_PEATONAL = 1
FASE_CALLE65_VERDE = 2

# Duraciones base
DURACION_AV80_BASE = 52
DURACION_PEATONAL = 15
DURACION_CALLE65_BASE = 33

# Límites para control dinámico
VERDE_MINIMO = 25
VERDE_MAXIMO = 75

# Cada cuántos segundos se imprime el estado
INTERVALO_CONTROL = 5

# DEMANDA DESDE PERCEPCION
USAR_DEMANDA_PERCEPCION = False
MODO_PERCEPCION = "video"
FUENTES_PERCEPCION = {
    "N_in": "videos/norte.mp4",
    "S_in": "videos/sur.mp4",
    "E_in": "videos/oriente.mp4",
    "W_in": "videos/occidente.mp4"
}
CONFIG_JSON_PERCEPCION = None
INTERVALO_DEMANDA = 1.0
MOSTRAR_PERCEPCION = False
GUARDAR_DEBUG_PERCEPCION = False
SEMILLA_DEMANDA = 7

# DEMANDA SINTETICA (OPCIONAL)
USAR_DEMANDA_SINTETICA = True
INTERVALO_DEMANDA_SINTETICA = 1.0
SINT_FLOWS_VPH = {
    "NS": 600,
    "SN": 600,
    "EW": 400,
    "WE": 400
}
SINT_TURN_RATIO = {
    "E_N": 0.2,
    "W_S": 0.2
}
SINT_COMPOSICION = {
    "carros": 0.7,
    "motos": 0.2,
    "buses": 0.05,
    "camiones": 0.04,
    "bicicletas": 0.01
}
SINT_SPEEDS_KMH = {
    "NS": 38.0,
    "SN": 36.0,
    "EW": 30.0,
    "WE": 30.0
}
SINT_SPEED_DESV_KMH = 5.0
SINT_AMPLITUD = 0.0
SINT_PERIODO_S = 900.0

# CONTROL ADAPTATIVO
VEL_REF_KMH = 40.0
FACTOR_CONGESTION = 0.7
MAX_EDAD_DEMANDA = 20
INTERVALO_DEMANDA_ACTUAL = INTERVALO_DEMANDA

CONTROL_SEMAFORO = {
    "fase": None,
    "fin": 0,
    "proximo_verde": FASE_AV80_VERDE
}

ULTIMA_DEMANDA = None
TIEMPO_ULTIMA_DEMANDA = None

# FUNCIÓN PARA INICIAR SUMO

def iniciar_sumo():

    #Inicia SUMO con o sin interfaz gráfica.
    if USAR_INTERFAZ_GRAFICA:
        binario_sumo = "sumo-gui"
    else:
        binario_sumo = "sumo"

    ruta_config = os.path.join(CARPETA_SUMO, ARCHIVO_CONFIG)

    comando = [
        binario_sumo,
        "-c", ruta_config,
        "--start",
        "--quit-on-end"
    ]
    print("Iniciando SUMO...")
    print("Comando:", " ".join(comando))
    traci.start(comando)

# FUNCIONES PARA LEER DATOS DE SUMO

def obtener_vehiculos_en_arista(edge_id):

    #Retorna la cantidad de vehículos en una arista.
    return traci.edge.getLastStepVehicleNumber(edge_id)

 

def obtener_velocidad_promedio(edge_id):

    #Retorna la velocidad promedio en m/s en una arista.
    velocidad = traci.edge.getLastStepMeanSpeed(edge_id)

    if velocidad < 0:
        return 0

    return velocidad

def obtener_vehiculos_detenidos(edge_id):

    """
    Retorna el número de vehículos detenidos o casi detenidos.
    SUMO considera halting si la velocidad es menor a cierto umbral.
    """
    return traci.edge.getLastStepHaltingNumber(edge_id)

def obtener_datos_interseccion():

    """
    Lee datos básicos de la intersección desde SUMO.
    Aristas de entrada:
    N_in: Norte hacia Sur por Avenida 80
    S_in: Sur hacia Norte por Avenida 80
    E_in: Oriente hacia Occidente por Calle 65
    W_in: Occidente hacia Oriente por Calle 65
    """
    datos = {
        "vehiculos_N": obtener_vehiculos_en_arista("N_in"),
        "vehiculos_S": obtener_vehiculos_en_arista("S_in"),
        "vehiculos_E": obtener_vehiculos_en_arista("E_in"),
        "vehiculos_W": obtener_vehiculos_en_arista("W_in"),

        "cola_N": obtener_vehiculos_detenidos("N_in"),
        "cola_S": obtener_vehiculos_detenidos("S_in"),
        "cola_E": obtener_vehiculos_detenidos("E_in"),
        "cola_W": obtener_vehiculos_detenidos("W_in"),

        "velocidad_N": obtener_velocidad_promedio("N_in"),
        "velocidad_S": obtener_velocidad_promedio("S_in"),
        "velocidad_E": obtener_velocidad_promedio("E_in"),
        "velocidad_W": obtener_velocidad_promedio("W_in"),

    }

    datos["cola_av80"] = datos["cola_N"] + datos["cola_S"]
    datos["cola_calle65"] = datos["cola_E"] + datos["cola_W"]
 
    datos["vehiculos_av80"] = datos["vehiculos_N"] + datos["vehiculos_S"]
    datos["vehiculos_calle65"] = datos["vehiculos_E"] + datos["vehiculos_W"]

    return datos

# DATOS DE VISIÓN ARTIFICIAL

def obtener_datos_vision_artificial():

    """
    Esta función es un ejemplo.
    En el futuro se conectaría con un modelo de visión artificial.

    Por ejemplo:
    - YOLO
    - OpenCV
    - DeepSORT
    - ByteTrack
    - Cámara IP
    - Video local
    Por ahora retornamos valores de ejemplo.
    """

    datos_vision = {
        "peatones_esperando": 0,
        "peatones_cruzando": 0,
        "giro_derecha_E_N": 0,
        "giro_derecha_W_S": 0,
        "flujo_NS": 0,
        "flujo_SN": 0,
        "flujo_EW": 0,
        "flujo_WE": 0,

    }

    return datos_vision

# DEMANDA HACIA SUMO

CLASES_VTYPE = [
    ("carros", "car"),
    ("motos", "moto"),
    ("buses", "bus"),
    ("camiones", "truck"),
    ("bicicletas", "bicycle")
]

CONTADOR_VEHICULOS = 0

def _nuevo_id(route_id):
    global CONTADOR_VEHICULOS
    CONTADOR_VEHICULOS += 1
    return f"veh_{route_id}_{CONTADOR_VEHICULOS}"

def _distribucion_vtypes(demanda):
    conteos = []
    total = 0

    for clave, vtype_id in CLASES_VTYPE:
        valor = int(max(0, demanda.get(clave, 0)))
        conteos.append((vtype_id, valor))
        total += valor

    if total <= 0:
        return [("car", 1.0)]

    acumulada = []
    acumulado = 0.0

    for vtype_id, valor in conteos:
        if valor <= 0:
            continue
        acumulado += valor / total
        acumulada.append((vtype_id, acumulado))

    if not acumulada:
        return [("car", 1.0)]

    acumulada[-1] = (acumulada[-1][0], 1.0)
    return acumulada

def _elegir_vtype(distribucion, rng):
    r = rng.random()

    for vtype_id, limite in distribucion:
        if r <= limite:
            return vtype_id

    return distribucion[-1][0]

def _velocidad_depart(velocidad_kmh):
    if velocidad_kmh is None or velocidad_kmh <= 0:
        return "max"
    return round(float(velocidad_kmh) / 3.6, 2)

def _inyectar_demanda_sumo(demanda, tiempo_base, intervalo, rng):
    distribucion = _distribucion_vtypes(demanda)
    intervalo = max(0.0, float(intervalo))

    arribos_e_n = int(max(0, demanda.get("arribos_E_N", 0)))
    arribos_w_s = int(max(0, demanda.get("arribos_W_S", 0)))
    arribos_e_w = int(max(0, demanda.get("arribos_EW", 0)))
    arribos_w_e = int(max(0, demanda.get("arribos_WE", 0)))
    arribos_e_w = max(0, arribos_e_w - arribos_e_n)
    arribos_w_e = max(0, arribos_w_e - arribos_w_s)

    rutas = [
        ("route_N_S", int(max(0, demanda.get("arribos_NS", 0))), demanda.get("velocidad_NS_kmh", 0.0)),
        ("route_S_N", int(max(0, demanda.get("arribos_SN", 0))), demanda.get("velocidad_SN_kmh", 0.0)),
        ("route_E_W", arribos_e_w, demanda.get("velocidad_EW_kmh", 0.0)),
        ("route_W_E", arribos_w_e, demanda.get("velocidad_WE_kmh", 0.0)),
        ("route_E_N", arribos_e_n, demanda.get("velocidad_EW_kmh", 0.0)),
        ("route_W_S", arribos_w_s, demanda.get("velocidad_WE_kmh", 0.0))
    ]

    total_creados = 0

    for route_id, cantidad, velocidad_kmh in rutas:
        if cantidad <= 0:
            continue

        depart_speed = _velocidad_depart(velocidad_kmh)

        for _ in range(cantidad):
            vtype_id = _elegir_vtype(distribucion, rng)
            veh_id = _nuevo_id(route_id)
            if intervalo > 0:
                depart_time = tiempo_base + (rng.random() * intervalo)
            else:
                depart_time = tiempo_base

            try:
                traci.vehicle.add(
                    veh_id,
                    route_id,
                    typeID=vtype_id,
                    depart=round(depart_time, 2),
                    departLane="best",
                    departSpeed=depart_speed
                )
                total_creados += 1
            except Exception as exc:
                print(f"No se pudo insertar {veh_id} en {route_id}: {exc}")

    return total_creados

def _limitar(valor, minimo, maximo):
    return max(minimo, min(maximo, valor))

def _promedio_positivos(valores):
    validos = [v for v in valores if v is not None and v > 0]
    if not validos:
        return 0.0
    return float(sum(validos) / len(validos))

def _demanda_percepcion_valida(tiempo_actual):
    if ULTIMA_DEMANDA is None or TIEMPO_ULTIMA_DEMANDA is None:
        return None

    if tiempo_actual - TIEMPO_ULTIMA_DEMANDA > MAX_EDAD_DEMANDA:
        return None

    intervalo = max(0.001, float(INTERVALO_DEMANDA_ACTUAL))

    demanda_av80 = (
        float(ULTIMA_DEMANDA.get("arribos_NS", 0))
        + float(ULTIMA_DEMANDA.get("arribos_SN", 0))
    ) / intervalo
    demanda_calle65 = (
        float(ULTIMA_DEMANDA.get("arribos_EW", 0))
        + float(ULTIMA_DEMANDA.get("arribos_WE", 0))
    ) / intervalo

    vel_av80 = _promedio_positivos([
        ULTIMA_DEMANDA.get("velocidad_NS_kmh"),
        ULTIMA_DEMANDA.get("velocidad_SN_kmh")
    ])
    vel_calle65 = _promedio_positivos([
        ULTIMA_DEMANDA.get("velocidad_EW_kmh"),
        ULTIMA_DEMANDA.get("velocidad_WE_kmh")
    ])

    return demanda_av80, demanda_calle65, vel_av80, vel_calle65

def _demanda_para_control(tiempo_actual, datos_sumo):
    datos = _demanda_percepcion_valida(tiempo_actual)
    if datos is not None:
        return datos

    demanda_av80 = float(datos_sumo.get("cola_av80", 0))
    demanda_calle65 = float(datos_sumo.get("cola_calle65", 0))
    return demanda_av80, demanda_calle65, 0.0, 0.0

def _peso_demanda(demanda, velocidad_kmh):
    if demanda <= 0:
        return 0.0

    if velocidad_kmh and velocidad_kmh > 0:
        factor = (VEL_REF_KMH - velocidad_kmh) / VEL_REF_KMH
        factor = max(0.0, factor) * FACTOR_CONGESTION
        return demanda * (1.0 + factor)

    return demanda

def _calcular_duraciones_dinamicas(demanda_av80, demanda_calle65, vel_av80, vel_calle65):
    peso_av80 = _peso_demanda(demanda_av80, vel_av80)
    peso_calle65 = _peso_demanda(demanda_calle65, vel_calle65)
    total = peso_av80 + peso_calle65

    if total <= 0:
        return DURACION_AV80_BASE, DURACION_CALLE65_BASE

    total_verde = DURACION_AV80_BASE + DURACION_CALLE65_BASE
    dur_av80 = total_verde * (peso_av80 / total)
    dur_calle65 = total_verde - dur_av80

    dur_av80 = _limitar(dur_av80, VERDE_MINIMO, VERDE_MAXIMO)
    dur_calle65 = _limitar(dur_calle65, VERDE_MINIMO, VERDE_MAXIMO)

    return int(round(dur_av80)), int(round(dur_calle65))

def _factor_temporal_sintetico(tiempo_actual):
    if SINT_AMPLITUD <= 0 or SINT_PERIODO_S <= 0:
        return 1.0

    fase = (2 * math.pi * (tiempo_actual % SINT_PERIODO_S)) / SINT_PERIODO_S
    factor = 1.0 + (SINT_AMPLITUD * math.sin(fase))
    return max(0.0, factor)

def _poisson(lmbda, rng):
    if lmbda <= 0:
        return 0

    limite = math.exp(-lmbda)
    k = 0
    p = 1.0

    while p > limite:
        k += 1
        p *= rng.random()

    return max(0, k - 1)

def _distribucion_pesos(pesos):
    total = sum(max(0.0, float(valor)) for valor in pesos.values())

    if total <= 0:
        return [("carros", 1.0)]

    acumulada = []
    acumulado = 0.0

    for clave, valor in pesos.items():
        if valor <= 0:
            continue
        acumulado += float(valor) / total
        acumulada.append((clave, acumulado))

    acumulada[-1] = (acumulada[-1][0], 1.0)
    return acumulada

def _elegir_por_distribucion(distribucion, rng):
    r = rng.random()

    for clave, limite in distribucion:
        if r <= limite:
            return clave

    return distribucion[-1][0]

def _velocidad_sintetica(base_kmh, rng):
    if base_kmh is None or base_kmh <= 0:
        return 0.0

    velocidad = rng.gauss(base_kmh, SINT_SPEED_DESV_KMH)
    return float(_limitar(velocidad, 5.0, 80.0))

def _generar_demanda_sintetica(tiempo_actual, intervalo, rng):
    intervalo = max(0.001, float(intervalo))
    factor = _factor_temporal_sintetico(tiempo_actual)

    lambda_ns = SINT_FLOWS_VPH.get("NS", 0) * intervalo / 3600.0 * factor
    lambda_sn = SINT_FLOWS_VPH.get("SN", 0) * intervalo / 3600.0 * factor
    lambda_ew = SINT_FLOWS_VPH.get("EW", 0) * intervalo / 3600.0 * factor
    lambda_we = SINT_FLOWS_VPH.get("WE", 0) * intervalo / 3600.0 * factor

    arribos_ns = _poisson(lambda_ns, rng)
    arribos_sn = _poisson(lambda_sn, rng)
    arribos_ew = _poisson(lambda_ew, rng)
    arribos_we = _poisson(lambda_we, rng)

    ratio_en = _limitar(float(SINT_TURN_RATIO.get("E_N", 0.0)), 0.0, 1.0)
    ratio_ws = _limitar(float(SINT_TURN_RATIO.get("W_S", 0.0)), 0.0, 1.0)

    arribos_e_n = int(round(arribos_ew * ratio_en))
    arribos_w_s = int(round(arribos_we * ratio_ws))

    total_vehiculos = arribos_ns + arribos_sn + arribos_ew + arribos_we
    distribucion = _distribucion_pesos(SINT_COMPOSICION)
    conteos = {clave: 0 for clave, _ in CLASES_VTYPE}

    for _ in range(total_vehiculos):
        clave = _elegir_por_distribucion(distribucion, rng)
        if clave not in conteos:
            clave = "carros"
        conteos[clave] += 1

    vel_ns = _velocidad_sintetica(SINT_SPEEDS_KMH.get("NS", 0.0), rng)
    vel_sn = _velocidad_sintetica(SINT_SPEEDS_KMH.get("SN", 0.0), rng)
    vel_ew = _velocidad_sintetica(SINT_SPEEDS_KMH.get("EW", 0.0), rng)
    vel_we = _velocidad_sintetica(SINT_SPEEDS_KMH.get("WE", 0.0), rng)

    return {
        "tiempo": round(float(tiempo_actual), 3),
        "arribos_NS": int(arribos_ns),
        "arribos_SN": int(arribos_sn),
        "arribos_EW": int(arribos_ew),
        "arribos_WE": int(arribos_we),
        "arribos_E_N": int(arribos_e_n),
        "arribos_W_S": int(arribos_w_s),
        "carros": int(conteos.get("carros", 0)),
        "motos": int(conteos.get("motos", 0)),
        "buses": int(conteos.get("buses", 0)),
        "camiones": int(conteos.get("camiones", 0)),
        "bicicletas": int(conteos.get("bicicletas", 0)),
        "velocidad_NS_kmh": float(vel_ns),
        "velocidad_SN_kmh": float(vel_sn),
        "velocidad_EW_kmh": float(vel_ew),
        "velocidad_WE_kmh": float(vel_we)
    }

# CONTROL DINÁMICO DEL SEMÁFORO

def calcular_duracion_verde(cola_principal, cola_secundaria, duracion_base):

    """
    Calcula una duración dinámica para una fase verde.
    Si hay mucha cola en la vía que recibirá verde,
    se aumenta la duración.
    Si hay poca cola, se mantiene o reduce.
    """

    diferencia = cola_principal - cola_secundaria
    ajuste = diferencia * 2

    nueva_duracion = duracion_base + ajuste

    if nueva_duracion < VERDE_MINIMO:
        nueva_duracion = VERDE_MINIMO

    if nueva_duracion > VERDE_MAXIMO:
        nueva_duracion = VERDE_MAXIMO

    return int(nueva_duracion)

 

def cambiar_fase(fase, duracion):

    """
    Cambia la fase del semáforo y asigna una duración.
    """
    traci.trafficlight.setPhase(ID_SEMAFORO, fase)
    traci.trafficlight.setPhaseDuration(ID_SEMAFORO, duracion)

    if fase == FASE_AV80_VERDE:
        nombre = "Avenida 80 verde"
    elif fase == FASE_PEATONAL:
        nombre = "Peatonal - todos rojo"
    elif fase == FASE_CALLE65_VERDE:
        nombre = "Calle 65 verde"
    else:
        nombre = "Fase desconocida"

    print(f"Semáforo cambiado a: {nombre} durante {duracion} s")

 

def controlar_semaforo(datos_sumo, tiempo_actual):

    """
    Lógica principal del semáforo.
    Esta lógica hace:
    1. Alterna verdes entre Avenida 80 y Calle 65.
    2. Inserta una fase peatonal fija entre verdes.
    3. Ajusta duraciones usando la demanda de percepción si existe.
    """

    if CONTROL_SEMAFORO["fase"] is None:
        demanda_av80, demanda_calle65, vel_av80, vel_calle65 = _demanda_para_control(
            tiempo_actual,
            datos_sumo
        )
        dur_av80, dur_calle65 = _calcular_duraciones_dinamicas(
            demanda_av80,
            demanda_calle65,
            vel_av80,
            vel_calle65
        )

        cambiar_fase(FASE_AV80_VERDE, dur_av80)
        CONTROL_SEMAFORO["fase"] = FASE_AV80_VERDE
        CONTROL_SEMAFORO["fin"] = tiempo_actual + dur_av80
        CONTROL_SEMAFORO["proximo_verde"] = FASE_CALLE65_VERDE
        return

    if tiempo_actual < CONTROL_SEMAFORO["fin"]:
        return

    fase_actual = CONTROL_SEMAFORO["fase"]

    if fase_actual in (FASE_AV80_VERDE, FASE_CALLE65_VERDE):
        cambiar_fase(FASE_PEATONAL, DURACION_PEATONAL)
        CONTROL_SEMAFORO["fase"] = FASE_PEATONAL
        CONTROL_SEMAFORO["fin"] = tiempo_actual + DURACION_PEATONAL
        return

    demanda_av80, demanda_calle65, vel_av80, vel_calle65 = _demanda_para_control(
        tiempo_actual,
        datos_sumo
    )
    dur_av80, dur_calle65 = _calcular_duraciones_dinamicas(
        demanda_av80,
        demanda_calle65,
        vel_av80,
        vel_calle65
    )

    if CONTROL_SEMAFORO["proximo_verde"] == FASE_AV80_VERDE:
        cambiar_fase(FASE_AV80_VERDE, dur_av80)
        CONTROL_SEMAFORO["fase"] = FASE_AV80_VERDE
        CONTROL_SEMAFORO["fin"] = tiempo_actual + dur_av80
        CONTROL_SEMAFORO["proximo_verde"] = FASE_CALLE65_VERDE
    else:
        cambiar_fase(FASE_CALLE65_VERDE, dur_calle65)
        CONTROL_SEMAFORO["fase"] = FASE_CALLE65_VERDE
        CONTROL_SEMAFORO["fin"] = tiempo_actual + dur_calle65
        CONTROL_SEMAFORO["proximo_verde"] = FASE_AV80_VERDE

# FUNCIÓN PARA IMPRIMIR ESTADO
def imprimir_estado(tiempo_actual, datos_sumo, datos_vision):
    """
    Imprime datos importantes en consola.
    """
    fase_actual = traci.trafficlight.getPhase(ID_SEMAFORO)
    estado_luces = traci.trafficlight.getRedYellowGreenState(ID_SEMAFORO)

    print("-" * 70)
    print(f"Tiempo simulación: {tiempo_actual} s")
    print(f"Fase actual: {fase_actual}")
    print(f"Estado luces: {estado_luces}")

    print("Vehículos por acceso:")
    print(f"  N_in Avenida 80 N->S: {datos_sumo['vehiculos_N']}")
    print(f"  S_in Avenida 80 S->N: {datos_sumo['vehiculos_S']}")
    print(f"  E_in Calle 65 E->W:   {datos_sumo['vehiculos_E']}")
    print(f"  W_in Calle 65 W->E:   {datos_sumo['vehiculos_W']}")

    print("Colas:")
    print(f"  Cola Avenida 80: {datos_sumo['cola_av80']}")
    print(f"  Cola Calle 65:   {datos_sumo['cola_calle65']}")

    print("Velocidades promedio aproximadas:")
    print(f"  N_in: {datos_sumo['velocidad_N']:.2f} m/s")
    print(f"  S_in: {datos_sumo['velocidad_S']:.2f} m/s")
    print(f"  E_in: {datos_sumo['velocidad_E']:.2f} m/s")
    print(f"  W_in: {datos_sumo['velocidad_W']:.2f} m/s")

    print("Datos visión artificial:")
    print(f"  Peatones esperando: {datos_vision['peatones_esperando']}")
    print(f"  Peatones cruzando:  {datos_vision['peatones_cruzando']}")

# BUCLE PRINCIPAL DE SIMULACIÓN
def ejecutar_simulacion():
    
    # Ejecuta la simulación controlada con TraCI.
    global INTERVALO_DEMANDA_ACTUAL
    global ULTIMA_DEMANDA, TIEMPO_ULTIMA_DEMANDA

    iniciar_sumo()
    print("Simulación iniciada.")
    percepcion = None
    percepcion_activa = False
    frames_por_seg = 1
    intervalo_demanda = INTERVALO_DEMANDA
    intervalo_sintetico = max(0.1, float(INTERVALO_DEMANDA_SINTETICA))
    sintetico_activo = USAR_DEMANDA_SINTETICA
    siguiente_sintetico = 0.0
    rng = random.Random(SEMILLA_DEMANDA)

    if USAR_DEMANDA_PERCEPCION:
        if CONFIG_JSON_PERCEPCION is None:
            configuracion_camaras = None
        else:
            configuracion_camaras = cargar_configuracion_json(CONFIG_JSON_PERCEPCION)

        percepcion = inicializar_modulo_percepcion(
            fuentes=FUENTES_PERCEPCION,
            configuracion_camaras=configuracion_camaras,
            modo=MODO_PERCEPCION,
            intervalo_salida=INTERVALO_DEMANDA,
            mostrar=MOSTRAR_PERCEPCION,
            guardar_video_debug=GUARDAR_DEBUG_PERCEPCION
        )
        frames_por_seg = max(1, round(percepcion.fps_referencia))
        intervalo_demanda = percepcion.intervalo_salida
        INTERVALO_DEMANDA_ACTUAL = intervalo_demanda
        percepcion_activa = True
    elif sintetico_activo:
        INTERVALO_DEMANDA_ACTUAL = intervalo_sintetico

    try:

        for tiempo_actual in range(TIEMPO_SIMULACION):
            if percepcion_activa and percepcion is not None:
                for _ in range(frames_por_seg):
                    demanda = percepcion.procesar_paso()
                    if demanda is not None:
                        ULTIMA_DEMANDA = demanda
                        TIEMPO_ULTIMA_DEMANDA = tiempo_actual
                        _inyectar_demanda_sumo(
                            demanda=demanda,
                            tiempo_base=tiempo_actual,
                            intervalo=intervalo_demanda,
                            rng=rng
                        )

                    if percepcion.fin_video_detectado:
                        percepcion_activa = False
                        if sintetico_activo:
                            INTERVALO_DEMANDA_ACTUAL = intervalo_sintetico
                            siguiente_sintetico = float(tiempo_actual)
                        break

            if sintetico_activo and not percepcion_activa:
                while tiempo_actual >= siguiente_sintetico:
                    demanda = _generar_demanda_sintetica(
                        tiempo_actual=siguiente_sintetico,
                        intervalo=intervalo_sintetico,
                        rng=rng
                    )
                    ULTIMA_DEMANDA = demanda
                    TIEMPO_ULTIMA_DEMANDA = tiempo_actual
                    _inyectar_demanda_sumo(
                        demanda=demanda,
                        tiempo_base=siguiente_sintetico,
                        intervalo=intervalo_sintetico,
                        rng=rng
                    )
                    siguiente_sintetico += intervalo_sintetico

            # Avanza la simulación un segundo
            traci.simulationStep()

            # Lee datos de SUMO
            datos_sumo = obtener_datos_interseccion()

            # Sin cámaras en vivo: visión artificial en cero
            datos_vision = obtener_datos_vision_artificial()

            controlar_semaforo(
                datos_sumo=datos_sumo,
                tiempo_actual=tiempo_actual
            )

            if tiempo_actual % INTERVALO_CONTROL == 0:
                imprimir_estado(
                    tiempo_actual=tiempo_actual,
                    datos_sumo=datos_sumo,
                    datos_vision=datos_vision
                )

            # Opcional: ralentiza un poco para verlo mejor en GUI
            if USAR_INTERFAZ_GRAFICA:
                time.sleep(0.02)

    except KeyboardInterrupt:
        print("Simulación detenida manualmente.")

    finally:
        if percepcion is not None:
            cerrar_modulo_percepcion()
        traci.close()
        print("Simulación finalizada.")

# EJECUCION
if __name__ == "__main__":
    ejecutar_simulacion()