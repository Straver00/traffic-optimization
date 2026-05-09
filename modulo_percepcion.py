import os
import cv2
import json
import time
import argparse
import numpy as np
import pandas as pd
from ultralytics import YOLO

# CLASES COCO PARA YOLOv8
CLASE_BICICLETA = 1
CLASE_CARRO = 2
CLASE_MOTO = 3
CLASE_BUS = 5
CLASE_CAMION = 7

CLASES_VEHICULOS = {
    CLASE_BICICLETA: "bicicleta",
    CLASE_CARRO: "carro",
    CLASE_MOTO: "moto",
    CLASE_BUS: "bus",
    CLASE_CAMION: "camion"
}

CLASES_VALIDAS = [
    CLASE_BICICLETA,
    CLASE_CARRO,
    CLASE_MOTO,
    CLASE_BUS,
    CLASE_CAMION
]

# FUNCIONES AUXILIARES

def centro_bbox(x1, y1, x2, y2):

    #Calcula el centro de una caja delimitadora.
    return int((x1 + x2) / 2), int((y1 + y2) / 2)

def distancia(p1, p2):

    #Distancia euclidiana entre dos puntos.
    return float(np.linalg.norm(np.array(p1) - np.array(p2)))

def lado_linea(punto, linea):

    """
    Retorna el lado de un punto respecto a una línea.
    punto:
        (x, y)

    linea:
        [[x1, y1], [x2, y2]]

    retorno:
        1, -1 o 0

    """
    x, y = punto
    (x1, y1), (x2, y2) = linea

    valor = (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)

    if valor > 0:
        return 1

    if valor < 0:
        return -1
    return 0

 

def cruzo_linea(punto_anterior, punto_actual, linea, direccion=None):

    """
    Detecta si un objeto cruzó una línea.
    direccion opcional:
        None          -> cuenta ambos sentidos
        "pos_to_neg" -> solo cuenta si pasa de lado positivo a negativo
        "neg_to_pos" -> solo cuenta si pasa de lado negativo a positivo
    """

    if punto_anterior is None or punto_actual is None or linea is None:
        return False

    lado_anterior = lado_linea(punto_anterior, linea)
    lado_actual = lado_linea(punto_actual, linea)

    if lado_anterior == 0 or lado_actual == 0:
        return False

    if lado_anterior == lado_actual:
        return False

    if direccion is None:
        return True

    if direccion == "pos_to_neg":
        return lado_anterior > 0 and lado_actual < 0

    if direccion == "neg_to_pos":
        return lado_anterior < 0 and lado_actual > 0

    return True

def convertir_fuente(fuente):

    """
    Convierte fuentes tipo '0', '1', '2' en enteros para cámaras USB.
    Si no es número, retorna el valor original.
    """
    if isinstance(fuente, str) and fuente.isdigit():
        return int(fuente)

    return fuente

def cargar_configuracion_json(ruta_json):
    """
    Carga configuración de cámaras desde un archivo JSON.
    """
    with open(ruta_json, "r", encoding="utf-8") as archivo:
        return json.load(archivo)

# MÓDULO PRINCIPAL
class ModuloPercepcionDemanda:
    """
    Módulo de percepción vehicular para generar demanda desde 4 cámaras.
    Accesos esperados:
        N_in: cámara acceso norte, Avenida 80 Norte -> Sur
        S_in: cámara acceso sur, Avenida 80 Sur -> Norte
        E_in: cámara acceso oriente, Calle 65 Oriente -> Occidente
        W_in: cámara acceso occidente, Calle 65 Occidente -> Oriente

    Salidas por intervalo:
        tiempo
        arribos_NS
        arribos_SN
        arribos_EW
        arribos_WE
        arribos_E_N
        arribos_W_S
        carros
        motos
        buses
        camiones
        bicicletas
        velocidad_NS_kmh
        velocidad_SN_kmh
        velocidad_EW_kmh
        velocidad_WE_kmh
    """

    def __init__(
        self,
        fuentes,
        configuracion_camaras,
        modo="video",
        modelo_yolo="yolov8n.pt",
        usar_gpu=False,
        confianza=0.35,
        imgsz=640,
        intervalo_salida=1.0,
        mostrar=True,
        guardar_video_debug=False,
        carpeta_debug="debug_percepcion",
        limpiar_tracks_segundos=10.0
    ):
        self.fuentes = fuentes
        self.configuracion_camaras = configuracion_camaras
        self.modo = modo
 
        if self.modo not in ["video", "stream"]:
            raise ValueError("modo debe ser 'video' o 'stream'")

        self.modelo_yolo = modelo_yolo
        self.usar_gpu = usar_gpu
        self.device = 0 if usar_gpu else "cpu"
        self.confianza = confianza
        self.imgsz = imgsz

        self.intervalo_salida = float(intervalo_salida)
        self.mostrar = mostrar
        self.guardar_video_debug = guardar_video_debug
        self.carpeta_debug = carpeta_debug
        self.limpiar_tracks_segundos = limpiar_tracks_segundos
        self.accesos = ["N_in", "S_in", "E_in", "W_in"]
        self.modelos = {}
        self.capturas = {}
        self.video_writers = {}


        self.fps_referencia = 30.0
        self.frame_actual = 0
        self.tiempo_simulado = 0.0
        self.tiempo_inicio_real = time.monotonic()
        self.ultimo_intervalo = 0.0
        self.fin_video_detectado = False
        self.historial_centros = {acceso: {} for acceso in self.accesos}
        self.ids_contados_arribo = {
            "N_in": set(),
            "S_in": set(),
            "E_in": set(),
            "W_in": set()
        }

        self.ids_contados_giro = {
            "E_in": set(),
            "W_in": set()
        }

        self.demanda_intervalo = self._crear_demanda_vacia()
        self.registros_demanda = []
        self._validar_entradas()
        self._inicializar_modelos()
        self._inicializar_capturas()
 
        if self.guardar_video_debug:
            os.makedirs(self.carpeta_debug, exist_ok=True)
            self._inicializar_writers_debug()

    # INICIALIZACIÓN
 
    def _validar_entradas(self):
        for acceso in self.accesos:
            if acceso not in self.fuentes:
                raise ValueError(f"Falta fuente para {acceso}")
            if acceso not in self.configuracion_camaras:
                raise ValueError(f"Falta configuración para {acceso}")

 

    def _inicializar_modelos(self):
        """
        Se usa un modelo YOLO por cámara para no mezclar el estado
        interno del tracker entre cámaras distintas.
        """
        for acceso in self.accesos:
            self.modelos[acceso] = YOLO(self.modelo_yolo)

    def _inicializar_capturas(self):
        fps_list = []

        for acceso in self.accesos:
            fuente = convertir_fuente(self.fuentes[acceso])
            cap = cv2.VideoCapture(fuente)

            if not cap.isOpened():
                raise RuntimeError(
                    f"No se pudo abrir la fuente de {acceso}: {self.fuentes[acceso]}"
                )

            self.capturas[acceso] = cap
            fps = cap.get(cv2.CAP_PROP_FPS)

            if fps and fps > 0:
                fps_list.append(fps)

        self.fps_referencia = min(fps_list) if fps_list else 30.0

    def _inicializar_writers_debug(self):

        for acceso, cap in self.capturas.items():
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS)

            if fps <= 0:
                fps = 30.0

            ruta_salida = os.path.join(self.carpeta_debug, f"debug_{acceso}.mp4")
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")

            writer = cv2.VideoWriter(
                ruta_salida,
                fourcc,
                fps,
                (width, height)
            )
            self.video_writers[acceso] = writer

    # DEMANDA
    def _crear_demanda_vacia(self):
        return {
            "tiempo": 0.0,
            "arribos_NS": 0,
            "arribos_SN": 0,
            "arribos_EW": 0,
            "arribos_WE": 0,
            "arribos_E_N": 0,
            "arribos_W_S": 0,
 
            "carros": 0,
            "motos": 0,
            "buses": 0,
            "camiones": 0,
            "bicicletas": 0,
 
            "velocidad_NS_kmh": 0.0,
            "velocidad_SN_kmh": 0.0,
            "velocidad_EW_kmh": 0.0,
            "velocidad_WE_kmh": 0.0,

            "_vel_NS": [],
            "_vel_SN": [],
            "_vel_EW": [],
            "_vel_WE": []
        }

    def _finalizar_demanda_intervalo(self):
        demanda = self.demanda_intervalo.copy()
        demanda["tiempo"] = round(self.ultimo_intervalo, 3)
        demanda["velocidad_NS_kmh"] = self._promedio_o_cero(demanda["_vel_NS"])
        demanda["velocidad_SN_kmh"] = self._promedio_o_cero(demanda["_vel_SN"])
        demanda["velocidad_EW_kmh"] = self._promedio_o_cero(demanda["_vel_EW"])
        demanda["velocidad_WE_kmh"] = self._promedio_o_cero(demanda["_vel_WE"])

        demanda.pop("_vel_NS", None)
        demanda.pop("_vel_SN", None)
        demanda.pop("_vel_EW", None)
        demanda.pop("_vel_WE", None)

        self.registros_demanda.append(demanda)
        self.demanda_intervalo = self._crear_demanda_vacia()
        self.ultimo_intervalo += self.intervalo_salida

        return demanda

    @staticmethod
    def _promedio_o_cero(lista):
        if not lista:
            return 0.0
        return float(np.mean(lista))

    # PROCESAMIENTO GENERAL

    def procesar_paso(self):

        """
        Procesa un frame de cada cámara.
        Retorna:
            None si aún no se completa el intervalo.
            dict con demanda si se completó el intervalo.
        """
        self._actualizar_tiempo_inicio_paso()

        frames = {}

        for acceso, cap in self.capturas.items():
            ret, frame = cap.read()
            if not ret:
                if self.modo == "video":
                    self.fin_video_detectado = True
                    return None
                frames[acceso] = None
                continue

            frames[acceso] = frame

        for acceso, frame in frames.items():
            if frame is not None:
                self._procesar_frame(acceso, frame)

        self._actualizar_tiempo_fin_paso()
        self._limpiar_historial_antiguo()

        if self.tiempo_simulado >= self.ultimo_intervalo + self.intervalo_salida:
            return self._finalizar_demanda_intervalo()

        return None

    def _actualizar_tiempo_inicio_paso(self):
        if self.modo == "video":
            self.tiempo_simulado = self.frame_actual / self.fps_referencia
        else:
            self.tiempo_simulado = time.monotonic() - self.tiempo_inicio_real

    def _actualizar_tiempo_fin_paso(self):
        if self.modo == "video":
            self.frame_actual += 1
            self.tiempo_simulado = self.frame_actual / self.fps_referencia
        else:
            self.tiempo_simulado = time.monotonic() - self.tiempo_inicio_real

    def _procesar_frame(self, acceso, frame):
        config = self.configuracion_camaras[acceso]
        linea_arribo = config.get("linea_arribo")
        linea_giro_derecha = config.get("linea_giro_derecha")
        direccion_arribo = config.get("direccion_arribo", None)
        direccion_giro_derecha = config.get("direccion_giro_derecha", None)
        pixeles_por_metro = config.get("pixeles_por_metro", None)

        modelo = self.modelos[acceso]

        resultado = modelo.track(
            source=frame,
            persist=True,
            verbose=False,
            conf=self.confianza,
            imgsz=self.imgsz,
            classes=CLASES_VALIDAS,
            device=self.device,
            tracker="bytetrack.yaml"
        )[0]

        if resultado.boxes is None or len(resultado.boxes) == 0:
            self._visualizar(acceso, frame, config)
            return

        boxes = resultado.boxes

        xyxy = boxes.xyxy.cpu().numpy()
        clases = boxes.cls.cpu().numpy().astype(int)

        if boxes.id is not None:
            ids = boxes.id.cpu().numpy().astype(int)

        else:
            ids = np.arange(len(xyxy))

        for bbox, clase, track_id in zip(xyxy, clases, ids):
            x1, y1, x2, y2 = bbox.astype(int)
            centro_actual = centro_bbox(x1, y1, x2, y2)
            centro_anterior = None

            if track_id in self.historial_centros[acceso]:
                centro_anterior = self.historial_centros[acceso][track_id]["centro"]

            velocidad_kmh = self._estimar_velocidad_kmh(
                acceso=acceso,
                track_id=track_id,
                centro_actual=centro_actual,
                pixeles_por_metro=pixeles_por_metro
            )

            self._procesar_vehiculo(
                acceso=acceso,
                clase=clase,
                track_id=track_id,
                centro_actual=centro_actual,
                centro_anterior=centro_anterior,
                linea_arribo=linea_arribo,
                linea_giro_derecha=linea_giro_derecha,
                direccion_arribo=direccion_arribo,
                direccion_giro_derecha=direccion_giro_derecha,
                velocidad_kmh=velocidad_kmh
            )

            self.historial_centros[acceso][track_id] = {
                "centro": centro_actual,
                "tiempo": self.tiempo_simulado
            }

            if self.mostrar or self.guardar_video_debug:
                self._dibujar_bbox(frame, x1, y1, x2, y2, clase, track_id)

        self._visualizar(acceso, frame, config)


    # PROCESAMIENTO VEHICULAR

    def _procesar_vehiculo(
        self,
        acceso,
        clase,
        track_id,
        centro_actual,
        centro_anterior,
        linea_arribo,
        linea_giro_derecha,
        direccion_arribo,
        direccion_giro_derecha,
        velocidad_kmh
    ):
        if centro_anterior is None:
            return

        cruzo_arribo = cruzo_linea(
            punto_anterior=centro_anterior,
            punto_actual=centro_actual,
            linea=linea_arribo,
            direccion=direccion_arribo
        )

        if cruzo_arribo and track_id not in self.ids_contados_arribo[acceso]:
            self.ids_contados_arribo[acceso].add(track_id)
            self._sumar_arribo_por_acceso(acceso)
            self._sumar_clase_vehiculo(clase)
            self._guardar_velocidad_por_acceso(acceso, velocidad_kmh)

        if acceso in ["E_in", "W_in"] and linea_giro_derecha is not None:
            cruzo_giro = cruzo_linea(
                punto_anterior=centro_anterior,
                punto_actual=centro_actual,
                linea=linea_giro_derecha,
                direccion=direccion_giro_derecha
            )

 

            if cruzo_giro and track_id not in self.ids_contados_giro[acceso]:
                self.ids_contados_giro[acceso].add(track_id)

                if acceso == "E_in":
                    self.demanda_intervalo["arribos_E_N"] += 1

                elif acceso == "W_in":
                    self.demanda_intervalo["arribos_W_S"] += 1

                self._sumar_clase_vehiculo(clase)
                self._guardar_velocidad_por_acceso(acceso, velocidad_kmh)


    def _sumar_arribo_por_acceso(self, acceso):
        if acceso == "N_in":
            self.demanda_intervalo["arribos_NS"] += 1

        elif acceso == "S_in":
            self.demanda_intervalo["arribos_SN"] += 1


        elif acceso == "E_in":
            self.demanda_intervalo["arribos_EW"] += 1

        elif acceso == "W_in":
            self.demanda_intervalo["arribos_WE"] += 1

    def _sumar_clase_vehiculo(self, clase):
        if clase == CLASE_CARRO:
            self.demanda_intervalo["carros"] += 1

        elif clase == CLASE_MOTO:
            self.demanda_intervalo["motos"] += 1

        elif clase == CLASE_BUS:
            self.demanda_intervalo["buses"] += 1

        elif clase == CLASE_CAMION:
            self.demanda_intervalo["camiones"] += 1

        elif clase == CLASE_BICICLETA:
            self.demanda_intervalo["bicicletas"] += 1

    def _guardar_velocidad_por_acceso(self, acceso, velocidad_kmh):
        if velocidad_kmh is None:
            return

        if acceso == "N_in":
            self.demanda_intervalo["_vel_NS"].append(velocidad_kmh)

        elif acceso == "S_in":
            self.demanda_intervalo["_vel_SN"].append(velocidad_kmh)

        elif acceso == "E_in":
            self.demanda_intervalo["_vel_EW"].append(velocidad_kmh)

        elif acceso == "W_in":
            self.demanda_intervalo["_vel_WE"].append(velocidad_kmh)

    # VELOCIDAD
    def _estimar_velocidad_kmh(
        self,
        acceso,
        track_id,
        centro_actual,
        pixeles_por_metro
    ):

        if pixeles_por_metro is None or pixeles_por_metro <= 0:

            return None

        anterior = self.historial_centros[acceso].get(track_id)

        if anterior is None:

            return None

        dt = self.tiempo_simulado - anterior["tiempo"]

        if dt <= 0:

            return None

        d_px = distancia(anterior["centro"], centro_actual)
        velocidad_px_s = d_px / dt
        velocidad_m_s = velocidad_px_s / pixeles_por_metro
        velocidad_kmh = velocidad_m_s * 3.6

        if velocidad_kmh < 0 or velocidad_kmh > 140:
            return None

        return float(velocidad_kmh)

    # LIMPIEZA DE TRACKS
    def _limpiar_historial_antiguo(self):
        for acceso in self.accesos:
            ids_a_eliminar = []

            for track_id, info in self.historial_centros[acceso].items():
                edad = self.tiempo_simulado - info["tiempo"]

                if edad > self.limpiar_tracks_segundos:
                    ids_a_eliminar.append(track_id)

            for track_id in ids_a_eliminar:
                self.historial_centros[acceso].pop(track_id, None)

    # VISUALIZACIÓN

    def _dibujar_bbox(self, frame, x1, y1, x2, y2, clase, track_id):
        etiqueta = CLASES_VEHICULOS.get(clase, "vehiculo")
        color = (0, 255, 0)
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        texto = f"{etiqueta} ID:{track_id}"

        cv2.putText(
            frame,
            texto,
            (x1, max(20, y1 - 5)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            color,
            1
        )

    def _visualizar(self, acceso, frame, config):
        self._dibujar_config(frame, config)

        texto_1 = f"{acceso} | t={self.tiempo_simulado:.1f}s"
        texto_2 = (
            f"NS:{self.demanda_intervalo['arribos_NS']} "
            f"SN:{self.demanda_intervalo['arribos_SN']} "
            f"EW:{self.demanda_intervalo['arribos_EW']} "
            f"WE:{self.demanda_intervalo['arribos_WE']} "
            f"EN:{self.demanda_intervalo['arribos_E_N']} "
            f"WS:{self.demanda_intervalo['arribos_W_S']}"
        )

        cv2.putText(
            frame,
            texto_1,
            (20, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2
        )

        cv2.putText(
            frame,
            texto_2,
            (20, 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2
        )

        if self.mostrar:
            cv2.imshow(f"Percepcion {acceso}", frame)
            cv2.waitKey(1)

        if self.guardar_video_debug and acceso in self.video_writers:
            self.video_writers[acceso].write(frame)

    def _dibujar_config(self, frame, config):
        linea_arribo = config.get("linea_arribo")
        linea_giro_derecha = config.get("linea_giro_derecha")

        if linea_arribo is not None:
            p1 = tuple(linea_arribo[0])
            p2 = tuple(linea_arribo[1])
            cv2.line(frame, p1, p2, (0, 255, 255), 2)

            cv2.putText(
                frame,
                "arribo",
                p1,
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 255),
                1
            )

        if linea_giro_derecha is not None:
            p1 = tuple(linea_giro_derecha[0])
            p2 = tuple(linea_giro_derecha[1])
            cv2.line(frame, p1, p2, (255, 255, 0), 2)

            cv2.putText(
                frame,
                "giro der",
                p1,
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (255, 255, 0),
                1
            )

    # PROCESAMIENTO DE VIDEO COMPLETO

    def procesar_video_completo(self, salida_csv="demanda_generada.csv"):
        print("Procesando videos para generar demanda vehicular...")

        while True:
            demanda = self.procesar_paso()

            if demanda is not None:
                print(demanda)

            if self._videos_terminados():
                break

            if self.mostrar:
                key = cv2.waitKey(1)

                if key == 27:
                    print("Procesamiento detenido con ESC.")
                    break

        self.guardar_csv(salida_csv)
        self.cerrar()

        print(f"CSV generado: {salida_csv}")

    def _videos_terminados(self):

        if self.modo != "video":
            return False

        if self.fin_video_detectado:
            return True

        for cap in self.capturas.values():
            frame_pos = cap.get(cv2.CAP_PROP_POS_FRAMES)
            frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)

            if frame_count > 0 and frame_pos >= frame_count:
                return True

        return False

    # STREAM

    def obtener_demanda_stream(self):
        return self.procesar_paso()

    # EXPORTACIÓN Y CIERRE
    def guardar_csv(self, salida_csv):

        if len(self.registros_demanda) == 0:
            print("No hay registros para guardar.")
            return

        df = pd.DataFrame(self.registros_demanda)
        df.to_csv(salida_csv, index=False, encoding="utf-8")

    def cerrar(self):
        for cap in self.capturas.values():
            cap.release()

        for writer in self.video_writers.values():
            writer.release()

        if self.mostrar:
            cv2.destroyAllWindows()

# CONFIGURACIÓN DE EJEMPLO
def configuracion_ejemplo():

    """
    Coordenadas de ejemplo.
    Deben ajustarse manualmente según cada cámara.
    linea_arribo:
        línea para contar vehículos de llegada.

    linea_giro_derecha:
        línea para contar giros derechos.
        Solo aplica en E_in y W_in.

    direccion_arribo:
        None, "pos_to_neg" o "neg_to_pos".

    direccion_giro_derecha:
        None, "pos_to_neg" o "neg_to_pos".

    pixeles_por_metro:
        calibración aproximada para velocidad.
    """

    return {
        "N_in": {
            "linea_arribo": [[250, 520], [950, 520]],
            "linea_giro_derecha": None,
            "direccion_arribo": None,
            "direccion_giro_derecha": None,
            "pixeles_por_metro": 18
        },

        "S_in": {
            "linea_arribo": [[250, 520], [950, 520]],
            "linea_giro_derecha": None,
            "direccion_arribo": None,
            "direccion_giro_derecha": None,
            "pixeles_por_metro": 18
        },

        "E_in": {
            "linea_arribo": [[250, 520], [750, 520]],
            "linea_giro_derecha": [[760, 300], [1050, 620]],
            "direccion_arribo": None,
            "direccion_giro_derecha": None,
            "pixeles_por_metro": 18
        },

        "W_in": {
            "linea_arribo": [[250, 520], [750, 520]],
            "linea_giro_derecha": [[760, 300], [1050, 620]],
            "direccion_arribo": None,
            "direccion_giro_derecha": None,
            "pixeles_por_metro": 18
        }
    }

# FUNCIONES DE ALTO NIVEL PARA IMPORTAR DESDE OTROS MÓDULOS
percepcion_global = None

def inicializar_modulo_percepcion(
    fuentes,
    configuracion_camaras=None,
    modo="video",
    modelo_yolo="yolov8n.pt",
    usar_gpu=False,
    confianza=0.35,
    imgsz=640,
    intervalo_salida=1.0,
    mostrar=True,
    guardar_video_debug=False
):
    global percepcion_global

    if configuracion_camaras is None:
        configuracion_camaras = configuracion_ejemplo()

    percepcion_global = ModuloPercepcionDemanda(
        fuentes=fuentes,
        configuracion_camaras=configuracion_camaras,
        modo=modo,
        modelo_yolo=modelo_yolo,
        usar_gpu=usar_gpu,
        confianza=confianza,
        imgsz=imgsz,
        intervalo_salida=intervalo_salida,
        mostrar=mostrar,
        guardar_video_debug=guardar_video_debug
    )

    return percepcion_global

def obtener_demanda_percepcion():

    global percepcion_global

    if percepcion_global is None:
        raise RuntimeError(
            "Primero debes llamar inicializar_modulo_percepcion(...)"
        )

    return percepcion_global.obtener_demanda_stream()

def cerrar_modulo_percepcion():
    global percepcion_global

    if percepcion_global is not None:
        percepcion_global.cerrar()
        percepcion_global = None

# MAIN

def main():
    parser = argparse.ArgumentParser(
        description="Módulo de percepción vehicular para generar demanda desde 4 cámaras."
    )

    parser.add_argument(
        "--modo",
        type=str,
        default="video",
        choices=["video", "stream"],
        help="Modo de operación: video o stream."
    )

    parser.add_argument(
        "--norte",
        type=str,
        required=True,
        help="Video, stream o cámara USB para N_in."
    )

    parser.add_argument(
        "--sur",
        type=str,
        required=True,
        help="Video, stream o cámara USB para S_in."
    )

    parser.add_argument(
        "--oriente",
        type=str,
        required=True,
        help="Video, stream o cámara USB para E_in."
    )

    parser.add_argument(
        "--occidente",
        type=str,
        required=True,
        help="Video, stream o cámara USB para W_in."
    )

    parser.add_argument(
        "--salida_csv",
        type=str,
        default="demanda_generada.csv",
        help="Ruta del CSV de salida."
    )

    parser.add_argument(
        "--config_json",
        type=str,
        default=None,
        help="Archivo JSON opcional con configuración de líneas."
    )

    parser.add_argument(
        "--modelo",
        type=str,
        default="yolov8n.pt",
        help="Modelo YOLO. Ejemplo: yolov8n.pt, yolov8s.pt."
    )

    parser.add_argument(
        "--usar_gpu",
        action="store_true",
        help="Usar GPU si está disponible."
    )

    parser.add_argument(
        "--mostrar",
        action="store_true",
        help="Mostrar ventanas con detecciones."
    )

    parser.add_argument(
        "--guardar_debug",
        action="store_true",
        help="Guardar videos de depuración."
    )

    parser.add_argument(
        "--intervalo",
        type=float,
        default=1.0,
        help="Intervalo de agregación de demanda en segundos."
    )

    parser.add_argument(
        "--confianza",
        type=float,
        default=0.35,
        help="Umbral de confianza de YOLO."

    )

    parser.add_argument(
        "--imgsz",
        type=int,
        default=640,
        help="Tamaño de imagen para YOLO."
    )

    args = parser.parse_args()

    fuentes = {
        "N_in": convertir_fuente(args.norte),
        "S_in": convertir_fuente(args.sur),
        "E_in": convertir_fuente(args.oriente),
        "W_in": convertir_fuente(args.occidente)
    }

    if args.config_json is not None:
        configuracion = cargar_configuracion_json(args.config_json)
    else:
        configuracion = configuracion_ejemplo()

    modulo = ModuloPercepcionDemanda(
        fuentes=fuentes,
        configuracion_camaras=configuracion,
        modo=args.modo,
        modelo_yolo=args.modelo,
        usar_gpu=args.usar_gpu,
        confianza=args.confianza,
        imgsz=args.imgsz,
        intervalo_salida=args.intervalo,
        mostrar=args.mostrar,
        guardar_video_debug=args.guardar_debug
    )

    if args.modo == "video":

        modulo.procesar_video_completo(args.salida_csv)

    elif args.modo == "stream":
        print("Procesando stream. Presiona Ctrl+C para detener.")

        try:
            while True:
                demanda = modulo.obtener_demanda_stream()

                if demanda is not None:
                    print(demanda)
                    modulo.guardar_csv(args.salida_csv)

        except KeyboardInterrupt:
            print("Stream detenido por usuario.")

        finally:
            modulo.guardar_csv(args.salida_csv)
            modulo.cerrar()
            print(f"CSV generado: {args.salida_csv}")

if __name__ == "__main__":
    main()