# Semaforos - Descripcion del proyecto

## Idea general y funcionamiento
Este proyecto simula un sistema de semaforos inteligentes para Medellin
usando SUMO y TraCI con Python. La idea es medir la demanda por acceso,
inyectar vehiculos en la simulacion y ajustar los tiempos de verde de
forma adaptativa. La demanda se obtiene de dos fuentes: (1) percepcion
por vision artificial con YOLOv8 y (2) demanda sintetica definida por
parametros. El orquestador lee estados de SUMO (colas, velocidades y
vehiculos), calcula duraciones dinamicas con reglas heuristicas y aplica
los cambios de fase del semaforo.

MARL-DQN es el enfoque optimo para control por aprendizaje por refuerzo,
pero en esta iteracion se prioriza el control heuristico para evaluar
resultados y construir una linea base. En una iteracion adicional seria
ideal comparar con MARL-DQN para comprobar si la mejora es significativa.

## 2.3. Proceso de diseno de la solucion
El sistema de semaforos inteligentes para Medellin se diseno en cinco
fases iterativas: analisis del problema, seleccion tecnologica, diseno
de arquitectura, simulacion y refinamiento. La trazabilidad entre
requerimientos y decisiones de diseno se garantizo documentando cada
fase (Tabla 5). El enfoque considero las restricciones urbanas de
Medellin (topografia, trafico heterogeneo, clima, integracion con el
SIMM) y los requerimientos definidos en la seccion anterior. La
arquitectura se detalla en la Seccion 2.7, la simulacion en la Seccion
2.6, y el refinamiento se aplica mediante iteraciones de parametros de
control y validacion de metricas.

Tabla 5. Fases del proceso de diseno de la solucion.

| Fase | Decision clave | Resultado |
| --- | --- | --- |
| 1. Analisis del problema | Alcance: interseccion unica | Problema delimitado con benchmarking internacional (Pittsburgh, Lima, Google Green Light). |
| 2. Seleccion tecnologica | YOLOv8 para vision, MARL-DQN para decision | Decisiones documentadas con tabla de criterios ponderados. |
| 3. Diseno de arquitectura | Pipeline percepcion -> SUMO -> TraCI -> Python | Arquitectura modular exportable al SIMM de Medellin. |
| 4. Validacion | SUMO + TraCI + Python | Comparacion contra tiempos fijos y control actuado. |
| 5. Refinamiento iterativo | Ajuste de hiperparametros (RL) | Mejora progresiva documentada en cada iteracion. |

En cada fase se consideraron las restricciones del contexto urbano de
Medellin (topografia, trafico heterogeneo, clima e integracion con el
SIMM), asi como los requerimientos definidos en la seccion anterior.
Durante la fase inicial se evaluo implementar el PMV en dos
intersecciones conectadas. No obstante, por disponibilidad de datos
calibrados y alcance del proyecto, se decidio concentrar el piloto en una
sola interseccion, priorizando una validacion mas profunda. La seleccion
se sustento en la evaluacion comparativa presentada en la Tabla 8 del
Anexo 1, mientras que la coordinacion multi-interseccion se abordara
posteriormente en un escenario de red 2x2 en SUMO (Seccion 2.6).

La seleccion tecnologica se fundamento en la evaluacion comparativa de la
Tabla 3 del Anexo 2 con criterios ponderados (Tabla 2, Anexo 2). La
combinacion YOLOv8 + Python obtuvo la mayor calificacion global (8.4/10)
frente a YOLOv3 (6.8/10), SSD MobileNet (5.9/10) y sensores inductivos
(4.2/10), evidenciando un mejor balance entre precision, latencia e
integracion. En la capa de control, MARL-DQN es el enfoque optimo en la
literatura, pero en esta iteracion se usan reglas heuristicas para
establecer la linea base y evaluar resultados; una iteracion adicional
idealmente contrastara con MARL-DQN.

El flujo de la arquitectura presentada se puede seguir a traves del
Anexo 7.

## 2.5. Criterios de evaluacion y analisis de alternativas
Los criterios de evaluacion se definieron con una ponderacion tecnica,
destacando la precision de deteccion y la latencia como factores clave
para garantizar el desempeno en tiempo real. Tambien se consideraron la
capacidad de deteccion de motocicletas, la madurez tecnologica, el costo
de implementacion, el rendimiento en condiciones adversas, la facilidad
de integracion y la escalabilidad del sistema. El detalle de los criterios
y su ponderacion se presenta en la Tabla 2 del Anexo 2.

El analisis de alternativas evidencia que YOLOv8 + Python obtuvo la mayor
puntuacion (8.4/10), destacandose por su equilibrio entre precision, baja
latencia y madurez tecnologica. Aunque versiones mas recientes presentan
ligeras mejoras en precision, fueron descartadas por su menor madurez al
momento del diseno. Alternativas como YOLOv3 y SSD MobileNet mostraron
limitaciones en precision, especialmente en la deteccion de motocicletas,
mientras que los sensores inductivos fueron descartados por su alto costo
y baja capacidad de clasificacion vehicular. El analisis detallado se
presenta en la Tabla 3 del Anexo 2.

## 2.6. Validacion mediante simulacion
Antes de cualquier implementacion fisica, es necesario verificar que las
decisiones de diseno produzcan el comportamiento esperado. La simulacion
permite hacerlo de forma segura, repetible y a bajo costo, probando
escenarios extremos que serian imposibles de recrear en la vida real. Se
usa SUMO (Simulation of Urban Mobility) y TraCI con Python en tres
escenarios de complejidad creciente. Las metricas de evaluacion se
comparan con la linea base de control por tiempos fijos y corresponden a
los indicadores de la Tabla 2 del Anexo 1: tiempo promedio de espera,
longitud maxima de cola, throughput vehicular y numero de cambios de fase
por ciclo.

Escenario 1 - Interseccion simple (estado: completado): flujo calibrado
con datos TomTom 2025: 900 - 1,200 veh/h por acceso en hora pico matutina
(congestion del 80.7%) y 1,100 - 1,500 veh/h en vespertina (139.2%).
Resultados preliminares: tiempo promedio de espera con reduccion del 19%
(93 s -> ~75 s), longitud maxima de cola de 14 a 9 vehiculos en el acceso
con mayor demanda, throughput vehicular con mejora del 11% y emisiones de
CO2 relativas con reduccion estimada del 12% al 15%.

Escenario 2 - Red 2x2 / cuatro intersecciones (estado: en desarrollo):
evaluacion de coordinacion multi-interseccion y metricas de red. Permitira
evidenciar el efecto rebote entre intersecciones y la capacidad de
coordinacion a nivel de corredor. En una iteracion posterior se planea
comparar con MARL-DQN.

Escenario 3 - Condiciones adversas (estado: planificado): ruido gaussiano
sobre fotogramas para simular lluvia y baja iluminacion (excluidas del PMV
segun la Tabla 3, Anexo 1). Prueba de robustez del modo fallback y del
preprocesamiento CLAHE.

## 2.7. Arquitectura funcional del sistema
La arquitectura de diseno, modular y de cuatro capas, define la operacion
del sistema.

Tabla 6. Operacion del sistema.

| Capa | Componente | Funcion |
| --- | --- | --- |
| Percepcion | Camaras IP + YOLOv8 + CLAHE (opcional) / demanda sintetica | Deteccion y clasificacion vehicular; estimacion de densidad, colas y velocidades por acceso. |
| Comunicacion | Orquestador + TraCI (intercambio interno en Python) | Flujo de datos entre percepcion, simulacion y control; sin capa MQTT/WebSocket en esta iteracion. |
| Decision | Control heuristico (linea base) | Genera orden de control (extender, mantener o adelantar fase verde); prepara comparacion futura con MARL-DQN. |
| Actuacion | Controlador semaforico en SUMO | Ejecuta cambio de fase respetando tiempos minimos/maximos definidos en la configuracion. |

Esta arquitectura responde a los requisitos funcionales: monitoreo,
deteccion y clasificacion, estimacion de congestion, control adaptativo,
procesamiento en tiempo real y escalabilidad. El flujo operativo es:
percepcion (YOLOv8 o demanda sintetica) -> preprocesamiento -> control
heuristico -> actuacion por TraCI -> registro de metricas. Un diagrama de
flujo debe mostrar el procesamiento de la senal, el envio de informacion,
los datos utilizados y los supuestos de control.

## 2.8. Evaluacion tecnica de la solucion (viabilidad)
La arquitectura combina un enfoque modular de cajas blancas para el
procesamiento y una capa de control basada en reglas. El sistema debe
integrarse con el SIMM, responsable de la red semaforica y el monitoreo en
Medellin. A diferencia de soluciones existentes, se plantea un enfoque que
considera multiples variables del entorno, como la composicion del
trafico, las condiciones climaticas y la interaccion entre
intersecciones.

Entre las alternativas evaluadas se encuentran Q-learning, DQN, MARL y
ACO (Agrahari et al., 2024). Con base en la literatura, MARL-DQN es el
enfoque optimo a futuro; sin embargo, en esta etapa se prioriza el control
heuristico para validar la viabilidad y generar la linea base. La
iteracion adicional con MARL-DQN permitira comparar si existen mejoras
consistentes (ver Figuras 1 y 2 del Anexo 2).

## 2.9. Riesgos de operacion
Uno de los riesgos mas criticos es la latencia del sistema frente a la
 dinamica del trafico. Si el tiempo entre la deteccion con YOLOv8 y la
 decision supera los umbrales de tiempo real, la respuesta semaforica
 puede ejecutarse con informacion desactualizada, generando ineficiencias
 o nuevos puntos de congestion (Wei et al., 2019). Adicionalmente,
 factores ambientales como lluvias intensas o baja iluminacion degradan la
 calidad de la imagen, introduciendo ruido en los datos de entrada. Esto
 puede afectar la precision de la deteccion y provocar decisiones
 erraticas, comprometiendo la operacion segura del sistema. La alta
 variabilidad del entorno urbano tambien representa un reto, ya que la
 presencia de actores no convencionales y comportamientos atipicos puede
 generar errores de interpretacion. Finalmente, existe el riesgo de
 incompatibilidad entre la velocidad de procesamiento y las restricciones
 de operacion de los semaforos tradicionales, lo que podria ocasionar
 fallos de sincronizacion o afectar la vida util de los componentes del
 sistema (Haydari & Yilmaz, 2020).

Los riesgos de operacion se gestionan mediante analisis cuantitativo
combinado FMEA y SWIFT (seccion 6.1 y Tablas 1 y 2, Anexo 4). Exposicion
inicial alta (13 riesgos FMEA: 12 criticos, 1 alto). Tras controles:
reduccion promedio del NPR del 76.8%: 1 alto, 9 moderados, 3 bajos. Los
cuatro riesgos operacionales prioritarios son:

- Error en vision por clima (FMEA n. 1 - NPR inicial 384, Critico -> NPR
  residual 120, Alto): lluvia intensa o baja iluminacion degrada la
  precision de YOLOv8 por debajo del umbral aceptable. Mitigacion: dataset
  local + preprocesamiento HDR/CLAHE. Fallback automatico ante caida de
  precision.
- Rechazo social (SWIFT n. 11 - Pxl 16, Critico -> Residual I=3, P=2):
  percepcion de vigilancia indebida genera oposicion ciudadana y riesgo de
  suspension. Mitigacion: comunicacion, transparencia, senalizacion
  obligatoria y anonimizacion en tiempo real.
- Sesgo en reglas heuristicas (FMEA n. 3 - NPR inicial 288, Critico -> NPR
  residual 96, Moderado): umbrales mal definidos generan efecto rebote en
  vias secundarias. Mitigacion: redisenar reglas con restricciones de
  equidad y validacion en red 2x2 SUMO; en la iteracion con MARL-DQN se
  ajustara la funcion de recompensa.
- Latencia de integracion (FMEA n. 6 - NPR inicial 240, Alto -> NPR
  residual 80, Moderado): desfase entre percepcion, control y actuacion.
  Mitigacion: monitoreo de tiempos de ciclo, buffers y degradacion a modo
  fijo seguro.
