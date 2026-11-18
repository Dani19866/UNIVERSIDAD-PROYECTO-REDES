"""
El Escape de los Coleccionistas en el Metro de París
Modelación de Sistemas en Redes - UNIMET - Trimestre 2627-1

Uso:
    python3 escape_metro.py [input.txt] [output.txt]

Modelo:
  * El metro es un grafo ponderado almacenado como LISTA DE ADYACENCIAS.
    Cada túnel del archivo de entrada se recorre en ambos sentidos, por lo que
    se agregan dos arcos (u -> v y v -> u) con el mismo tiempo y la misma línea.
  * Cambiar de línea en una estación cuesta su Tiempo de Transbordo Interno. El
    transbordo es una acción propia: se puede cambiar de andén y luego esperar ahí.
  * Restricciones de colisión (en cada minuto exacto):
      - Pierre y Amélie no pueden estar en la misma estación (nodo "restringido").
      - Mientras uno viaja por un túnel de la línea L, toda la línea L queda
        "ocupada": el otro no puede estar viajando por ningún túnel de L.
  * Disponibilidad: una línea puede prohibir transbordos (hacia o desde ella)
    en un intervalo de minutos [inicio, fin].
  * Penalización: factor que multiplica el tiempo de viaje de una línea (por defecto 1).
  * Riesgo: cada minuto que un personaje pasa esperando (en el origen, en una
    estación intermedia o en su compuerta) suma 1 punto de riesgo.

Objetivo (en orden de prioridad):
  1. Minimizar el tiempo total de la operación Tmax (llegada de ambos).
  2. Minimizar el costo de ruta: minutos en movimiento (viaje + transbordos) de
     ambos personajes. Así nadie da vueltas innecesarias para no esperar.
  3. A igual costo, preferir esperar en el origen (desfase de salida).
  Los puntos de riesgo se calculan y se reportan, pero no se optimizan.

Solo se usa la biblioteca estándar de Python.
"""

import os
import sys

INFINITO = float("inf")


# ---------------------------------------------------------------------------
# 1. Representación del grafo: Lista de Adyacencias
# ---------------------------------------------------------------------------
class GrafoMetro:
    """Red del metro almacenada como lista de adyacencias.

    adyacencias[u] = [(v, tiempo_viaje, linea), ...]
    transbordo[u]  = tiempo de transbordo interno de la estación u
    """

    def __init__(self):
        self.adyacencias = {}
        self.transbordo = {}

    def agregar_estacion(self, estacion, tiempo_transbordo):
        if estacion in self.adyacencias:
            raise ValueError(f"La estación {estacion} está repetida en el archivo.")
        self.adyacencias[estacion] = []
        self.transbordo[estacion] = tiempo_transbordo

    def agregar_tunel(self, u, v, tiempo, linea):
        """Agrega el túnel en ambos sentidos (u -> v y v -> u)."""
        for estacion in (u, v):
            if estacion not in self.adyacencias:
                raise ValueError(f"El túnel {u}-{v} usa la estación {estacion}, que no existe.")
        if tiempo <= 0:
            raise ValueError(f"El túnel {u}-{v} debe tener un tiempo de viaje positivo.")
        self.adyacencias[u].append((v, tiempo, linea))
        self.adyacencias[v].append((u, tiempo, linea))

    def estaciones(self):
        return list(self.adyacencias.keys())

    def vecinos(self, u):
        return self.adyacencias[u]

    def lineas_de(self, u):
        """Líneas que pasan por la estación u."""
        return {linea for (_, _, linea) in self.adyacencias[u]}

    def lineas(self):
        return sorted({linea for arcos in self.adyacencias.values() for (_, _, linea) in arcos})


# ---------------------------------------------------------------------------
# 2. Estados de "disponibilidad" y "penalización" de las líneas
# ---------------------------------------------------------------------------
class Restricciones:
    def __init__(self):
        self.disponibilidad = {}   # linea -> [(min_inicio, min_fin), ...]
        self.penalizacion = {}     # linea -> factor (entero >= 1)

    def factor(self, linea):
        """Factor de penalización de la línea; por defecto 1 (sin cambios)."""
        return self.penalizacion.get(linea, 1)

    def tiempo_viaje(self, tiempo_base, linea):
        return tiempo_base * self.factor(linea)

    def transbordo_permitido(self, linea_actual, linea_nueva, inicio, fin):
        """Un transbordo que ocupa los minutos [inicio, fin] está prohibido si se
        solapa con un intervalo de no-disponibilidad de la línea de origen o de
        la línea de destino."""
        for linea in (linea_actual, linea_nueva):
            for (a, b) in self.disponibilidad.get(linea, []):
                if inicio <= b and a <= fin:
                    return False
        return True


# ---------------------------------------------------------------------------
# 3. Lectura del archivo de entrada
# ---------------------------------------------------------------------------
def leer_entrada(ruta):
    with open(ruta, encoding="utf-8") as archivo:
        datos = []
        for numero, linea in enumerate(archivo, start=1):
            texto = linea.split("#", 1)[0].strip()
            if texto:
                datos.append((numero, texto.split()))

    if not datos:
        raise ValueError("El archivo de entrada está vacío.")

    def enteros(numero, campos, cantidad, descripcion):
        if len(campos) != cantidad:
            raise ValueError(f"Línea {numero}: se esperaban {cantidad} valores ({descripcion}).")
        try:
            return [int(c) for c in campos]
        except ValueError:
            raise ValueError(f"Línea {numero}: valores no numéricos en {descripcion}.")

    pos = 0
    num_estaciones, num_tuneles = enteros(*datos[pos], 2, "estaciones y túneles")
    pos += 1

    grafo = GrafoMetro()
    for _ in range(num_estaciones):
        if pos >= len(datos):
            raise ValueError("Faltan estaciones en el archivo de entrada.")
        estacion, transbordo = enteros(*datos[pos], 2, "estación y transbordo")
        if transbordo < 0:
            raise ValueError(f"Línea {datos[pos][0]}: el transbordo no puede ser negativo.")
        grafo.agregar_estacion(estacion, transbordo)
        pos += 1

    for _ in range(num_tuneles):
        if pos >= len(datos):
            raise ValueError("Faltan túneles en el archivo de entrada.")
        numero, campos = datos[pos]
        if len(campos) != 4:
            raise ValueError(f"Línea {numero}: un túnel necesita origen, destino, tiempo y línea.")
        u, v, tiempo = enteros(numero, campos[:3], 3, "túnel")
        grafo.agregar_tunel(u, v, tiempo, campos[3])
        pos += 1

    if pos >= len(datos):
        raise ValueError("Faltan los datos de la misión.")
    mision = enteros(*datos[pos], 4, "datos de la misión")
    for estacion in mision:
        if estacion not in grafo.adyacencias:
            raise ValueError(f"La estación {estacion} de la misión no existe.")
    pos += 1

    restricciones = Restricciones()
    lineas_validas = set(grafo.lineas())
    while pos < len(datos):
        numero, campos = datos[pos]
        tipo = campos[0].upper()
        if tipo == "DISPONIBILIDAD" and len(campos) == 4:
            linea = campos[1]
            inicio, fin = enteros(numero, campos[2:], 2, "intervalo de disponibilidad")
            if inicio > fin:
                raise ValueError(f"Línea {numero}: el minuto inicial es mayor que el final.")
            restricciones.disponibilidad.setdefault(linea, []).append((inicio, fin))
        elif tipo == "PENALIZACION" and len(campos) == 3:
            linea = campos[1]
            (factor,) = enteros(numero, campos[2:], 1, "factor de penalización")
            if factor < 1:
                raise ValueError(f"Línea {numero}: el factor de penalización debe ser >= 1.")
            restricciones.penalizacion[linea] = factor
        else:
            raise ValueError(f"Línea {numero}: restricción no reconocida: {' '.join(campos)}")
        if linea not in lineas_validas:
            raise ValueError(f"Línea {numero}: la línea {linea} no existe en la red.")
        pos += 1

    return grafo, mision, restricciones


# ---------------------------------------------------------------------------
# 4. Algoritmo de Dijkstra (versión de clase: etiquetado permanente)
# ---------------------------------------------------------------------------
def dijkstra(grafo, origen, restricciones):
    """Distancia mínima desde `origen` a todas las estaciones, usando el tiempo
    de viaje penalizado y sin considerar transbordos ni colisiones.

    Como los transbordos y las esperas solo pueden AUMENTAR el tiempo, este
    valor es una cota inferior del tiempo real que falta para llegar.
    Como los túneles son bidireccionales, la distancia desde el destino es igual
    a la distancia hacia el destino.
    """
    d = {x: INFINITO for x in grafo.estaciones()}
    previo = {x: None for x in grafo.estaciones()}
    etiquetado = set()
    d[origen] = 0

    while True:
        # Paso 2: elegir el vértice no etiquetado con menor d(x)
        y, menor = None, INFINITO
        for x in grafo.estaciones():
            if x not in etiquetado and d[x] < menor:
                y, menor = x, d[x]
        if y is None:          # todos etiquetados o los restantes con d = infinito
            break
        etiquetado.add(y)
        # Actualizar solo los adyacentes de y (lista de adyacencias)
        for (x, tiempo, linea) in grafo.vecinos(y):
            if x not in etiquetado:
                alternativa = d[y] + restricciones.tiempo_viaje(tiempo, linea)
                if alternativa < d[x]:
                    d[x] = alternativa
                    previo[x] = y
    return d, previo


# ---------------------------------------------------------------------------
# 5. Estados individuales de un personaje
# ---------------------------------------------------------------------------
# ("E", estacion, linea)              -> En el andén de `linea` de una estación
#                                        (None si aún no ha salido de su origen)
# ("T", estacion, linea_nueva, fin)   -> Transbordando hacia el andén de `linea_nueva`
#                                        hasta el minuto `fin`
# ("V", origen, destino, linea, fin)  -> Viajando por un túnel; llega en `fin`
#
# El transbordo es una acción propia: el personaje puede cambiarse de andén y luego
# esperar allí el tren de la nueva línea. El tiempo de transbordo se paga siempre.

def estacion_actual(estado):
    """Estación que ocupa el personaje en un instante, o None si está en un túnel."""
    if estado[0] in ("E", "T"):
        return estado[1]
    return None


def sucesores(estado, t, grafo, restricciones, destino):
    """Movimientos posibles de un personaje entre el minuto t y t+1.

    Devuelve tuplas (nuevo_estado, linea_en_tunel, espera) donde:
      linea_en_tunel = línea que ocupa durante (t, t+1], o None
      espera         = True si el personaje estuvo quieto ese minuto (suma riesgo)
    """
    tipo = estado[0]

    if tipo == "V":
        _, u, v, linea, fin = estado
        nuevo = ("E", v, linea) if fin == t + 1 else estado
        return [(nuevo, linea, False)]

    if tipo == "T":
        _, u, linea_nueva, fin = estado
        nuevo = ("E", u, linea_nueva) if fin == t + 1 else estado
        return [(nuevo, None, False)]

    # tipo == "E"
    _, u, linea_actual = estado
    opciones = [(estado, None, True)]                 # esperar un minuto
    if u == destino:                                  # ya está en su compuerta
        return opciones

    # Salir por un túnel de la línea en cuyo andén está (al inicio puede tomar cualquiera)
    for (v, tiempo, linea) in grafo.vecinos(u):
        if linea_actual is None or linea_actual == linea:
            duracion = restricciones.tiempo_viaje(tiempo, linea)
            opciones.append((partir(u, v, linea, duracion, t), linea, False))

    # Transbordar a otra línea de la estación (penalizado con su tiempo de transbordo)
    if linea_actual is not None:
        duracion_transbordo = grafo.transbordo[u]
        fin = t + duracion_transbordo
        for linea_nueva in sorted(grafo.lineas_de(u) - {linea_actual}):
            if not restricciones.transbordo_permitido(linea_actual, linea_nueva, t, fin):
                continue
            if duracion_transbordo == 0:          # transbordo instantáneo: sale de una vez
                for (v, tiempo, linea) in grafo.vecinos(u):
                    if linea == linea_nueva:
                        duracion = restricciones.tiempo_viaje(tiempo, linea)
                        opciones.append((partir(u, v, linea, duracion, t), linea, False))
            elif fin == t + 1:
                opciones.append((("E", u, linea_nueva), None, False))
            else:
                opciones.append((("T", u, linea_nueva, fin), None, False))
    return opciones


def partir(u, v, linea, duracion, t):
    """Estado al minuto t+1 de alguien que sale de u hacia v en el minuto t."""
    if duracion == 1:
        return ("E", v, linea)
    return ("V", u, v, linea, t + duracion)


def cota_restante(estado, t, distancia):
    """Cota inferior del tiempo que le falta a un personaje (usa Dijkstra)."""
    tipo = estado[0]
    if tipo == "E":
        return distancia[estado[1]]
    if tipo == "T":
        _, u, linea_nueva, fin = estado
        return (fin - t) + distancia[u]
    _, u, v, linea, fin = estado
    return (fin - t) + distancia[v]


# ---------------------------------------------------------------------------
# 6. Condición de colisión
# ---------------------------------------------------------------------------
def hay_colision(estado_p, estado_a, linea_tunel_p, linea_tunel_a):
    """Indica si Pierre y Amélie chocan en un paso de la simulación.

    estado_p, estado_a: estados de cada uno en el instante t+1
    linea_tunel_p, linea_tunel_a: línea por la que viajó cada uno durante (t, t+1],
                                  o None si no estuvo en un túnel.
    Usa estacion_actual(estado) para saber en qué estación está cada uno.
    """
    # Condición de No-Colisión Temporal: misma estación en el mismo minuto exacto.
    # (Dos personajes dentro de túneles tienen estación None: eso no es coincidir.)
    estacion_p = estacion_actual(estado_p)
    estacion_a = estacion_actual(estado_a)
    if estacion_p is not None and estacion_p == estacion_a:
        return True
    # Condición de No-Colisión Espacial: la línea por la que uno viaja queda ocupada
    # completa; esto cubre "mismo tren" y "cruzarse en sentidos opuestos".
    return linea_tunel_p is not None and linea_tunel_p == linea_tunel_a


# ---------------------------------------------------------------------------
# 7. Búsqueda sincronizada en la red expandida en el tiempo
# ---------------------------------------------------------------------------
def planificar_escape(grafo, mision, restricciones):
    """Busca, minuto a minuto, los planes conjuntos de Pierre y Amélie.

    Cada capa t contiene los estados conjuntos (estado_P, estado_A) alcanzables
    en el minuto t sin colisiones, con su mejor costo (costo_ruta, esperas_fuera_origen).
    La primera capa donde ambos están en su compuerta da el Tmax mínimo, y dentro
    de esa capa se elige el estado de menor costo.
    """
    origen_p, origen_a, destino_p, destino_a = mision
    dist_p, _ = dijkstra(grafo, destino_p, restricciones)
    dist_a, _ = dijkstra(grafo, destino_a, restricciones)

    if dist_p[origen_p] == INFINITO or dist_a[origen_a] == INFINITO:
        return None, "No existe camino desde el origen hasta la compuerta asignada."
    inicial = (("E", origen_p, None), ("E", origen_a, None))
    if hay_colision(inicial[0], inicial[1], None, None):
        return None, "Pierre y Amélie comienzan en la misma estación."
    if origen_p == destino_p and origen_a == destino_a:
        return ([inicial[0]], [inicial[1]]), None     # ya están en sus compuertas

    # Después del último minuto con restricción de disponibilidad, las reglas ya no
    # dependen del reloj. Si una capa (con los tiempos medidos relativos al minuto
    # actual) repite una capa anterior, la búsqueda entró en un ciclo: no hay plan.
    fin_ventanas = max([b for ventanas in restricciones.disponibilidad.values()
                        for (_, b) in ventanas] + [0])
    capas_vistas = set()

    # capas[t][estado_conjunto] = (costo, estado_conjunto_previo)
    capas = [{inicial: ((0, 0), None)}]
    t = 0
    while capas[t]:
        if t > fin_ventanas:
            firma = frozenset((relativo(p, t), relativo(a, t)) for (p, a) in capas[t])
            if firma in capas_vistas:
                break
            capas_vistas.add(firma)

        siguiente = {}
        for (estado_p, estado_a), (costo, _) in capas[t].items():
            mov_p = sucesores(estado_p, t, grafo, restricciones, destino_p)
            mov_a = sucesores(estado_a, t, grafo, restricciones, destino_a)
            for (nuevo_p, tunel_p, espera_p) in mov_p:
                if cota_restante(nuevo_p, t + 1, dist_p) == INFINITO:
                    continue                      # ya no puede llegar a su compuerta
                for (nuevo_a, tunel_a, espera_a) in mov_a:
                    if cota_restante(nuevo_a, t + 1, dist_a) == INFINITO:
                        continue
                    if hay_colision(nuevo_p, nuevo_a, tunel_p, tunel_a):
                        continue
                    # Costo de ruta = minutos en movimiento (viaje o transbordo)
                    costo_ruta = costo[0] + (not espera_p) + (not espera_a)
                    fuera_origen = costo[1]
                    if espera_p and estado_p[2] is not None:
                        fuera_origen += 1
                    if espera_a and estado_a[2] is not None:
                        fuera_origen += 1
                    nuevo_costo = (costo_ruta, fuera_origen)
                    clave = (nuevo_p, nuevo_a)
                    if clave not in siguiente or nuevo_costo < siguiente[clave][0]:
                        siguiente[clave] = (nuevo_costo, (estado_p, estado_a))
        capas.append(siguiente)
        t += 1

        metas = [(c, clave) for clave, (c, _) in siguiente.items()
                 if clave[0] == ("E", destino_p, clave[0][2])
                 and clave[1] == ("E", destino_a, clave[1][2])]
        if metas:
            _, mejor = min(metas)
            return reconstruir(capas, t, mejor), None

    return None, "No existe ningún plan que evite las colisiones."


def relativo(estado, t):
    """Estado con su minuto de fin expresado relativo a t (para detectar ciclos)."""
    if estado[0] == "E":
        return estado
    return estado[:-1] + (estado[-1] - t,)


def reconstruir(capas, t_final, estado_final):
    """Recorre los punteros hacia atrás y devuelve la línea de tiempo de cada uno."""
    linea_p, linea_a = [], []
    estado = estado_final
    for t in range(t_final, -1, -1):
        linea_p.append(estado[0])
        linea_a.append(estado[1])
        estado = capas[t][estado][1]
    linea_p.reverse()
    linea_a.reverse()
    return linea_p, linea_a


# ---------------------------------------------------------------------------
# 8. Reporte
# ---------------------------------------------------------------------------
def analizar_ruta(estados, origen, destino, compuerta):
    """Convierte la línea de tiempo de un personaje en eventos legibles."""
    t_final = len(estados) - 1
    salida = 0
    while salida < t_final and estados[salida + 1] == ("E", origen, None):
        salida += 1

    eventos = []
    riesgo = {"origen": salida, "intermedia": 0, "destino": 0}
    if salida > 0:
        eventos.append((salida, f"Estación {origen} (Origen - Inicia Movimiento)"))
    else:
        eventos.append((0, f"Estación {origen} (Origen)"))

    llegada = None
    espera_inicio = None
    for t in range(salida + 1, t_final + 1):
        previo, actual = estados[t - 1], estados[t]
        # Fin de una espera intermedia: el último minuto quieto fue t-1
        if espera_inicio is not None and actual != previo:
            eventos.append((t - 1, f"Estación {previo[1]} (Fin de espera de "
                                   f"{t - 1 - espera_inicio} min)"))
            espera_inicio = None
        llego = actual[0] == "E" and (
            previo[0] == "V" or (previo[0] == "E" and actual[1] != previo[1]))
        transbordo = actual[0] == "E" and actual[1] == previo[1] and (
            previo[0] == "T" or (previo[0] == "E" and actual[2] != previo[2]))
        if llego:
            # Llegada a una estación tras un viaje
            if actual[1] == destino:
                llegada = t
                eventos.append((t, f"Estación {destino} (Destino Compuerta {compuerta})"))
            else:
                eventos.append((t, f"Estación {actual[1]} (Viaje {actual[2]})"))
        elif transbordo:
            eventos.append((t, f"Estación {actual[1]} (Termina Transbordo a {actual[2]})"))
        elif actual[0] == "E" and previo == actual:
            if actual[1] == destino:
                riesgo["destino"] += 1
            else:
                riesgo["intermedia"] += 1
                if espera_inicio is None:
                    espera_inicio = t - 1
    if llegada is None:            # salió y llegó en el minuto 0 (origen == destino)
        llegada = salida
    if llegada < t_final:
        eventos.append((t_final, f"Estación {destino} (Acceso al búnker por "
                                 f"{compuerta} tras esperar {t_final - llegada} min)"))
    return {"salida": salida, "llegada": llegada, "eventos": eventos, "riesgo": riesgo}


def generar_reporte(grafo, mision, restricciones, plan, error):
    origen_p, origen_a, destino_p, destino_a = mision
    lineas = ["=== PLAN DE ESCAPE CONFIGURADO ==="]

    if plan is None:
        lineas.append("")
        lineas.append(f"Resultado de Sincronización: FRACASO. {error}")
        return "\n".join(lineas) + "\n"

    ruta_p, ruta_a = plan
    t_max = len(ruta_p) - 1
    info_p = analizar_ruta(ruta_p, origen_p, destino_p, "D1")
    info_a = analizar_ruta(ruta_a, origen_a, destino_a, "D2")

    lineas.append(f"Tiempo Total de la Operación: {t_max} minutos")
    lineas.append("")
    lineas.append("[PROGRAMACIÓN DE SALIDAS]")
    for nombre, info in (("Pierre", info_p), ("Amélie", info_a)):
        texto = f"* {nombre} arranca en el minuto: {info['salida']}"
        if info["salida"] > 0:
            texto += f" (Debe esperar {info['salida']} minutos en su estación de origen)"
        lineas.append(texto)

    for nombre, info in (("PIERRE", info_p), ("AMÉLIE", info_a)):
        lineas.append("")
        lineas.append(f"[RUTA DE {nombre} (Tiempo total de viaje: "
                      f"{t_max - info['salida']} min)]")
        for minuto, texto in info["eventos"]:
            lineas.append(f"Minuto {minuto}: {texto}")

    lineas.append("")
    lineas.append("[PUNTOS DE RIESGO (1 punto por minuto de espera)]")
    total = 0
    for nombre, info in (("Pierre", info_p), ("Amélie", info_a)):
        r = info["riesgo"]
        suma = r["origen"] + r["intermedia"] + r["destino"]
        total += suma
        lineas.append(f"* {nombre}: {suma} (origen: {r['origen']}, "
                      f"intermedias: {r['intermedia']}, compuerta: {r['destino']})")
    lineas.append(f"* Total: {total}")

    if restricciones.disponibilidad or restricciones.penalizacion:
        lineas.append("")
        lineas.append("[RESTRICCIONES APLICADAS]")
        for linea, ventanas in sorted(restricciones.disponibilidad.items()):
            for (a, b) in ventanas:
                lineas.append(f"* Disponibilidad: {linea} sin transbordos entre "
                              f"los minutos {a} y {b}")
        for linea, factor in sorted(restricciones.penalizacion.items()):
            lineas.append(f"* Penalización: {linea} multiplica su tiempo de viaje x{factor}")

    lineas.append("")
    if info_p["llegada"] == info_a["llegada"] == t_max:
        lineas.append(f"Resultado de Sincronización: ÉXITO. Llegada simultánea en el "
                      f"minuto {t_max}.")
    else:
        lineas.append(f"Resultado de Sincronización: ÉXITO. Acceso simultáneo al búnker "
                      f"en el minuto {t_max}.")
    return "\n".join(lineas) + "\n"


# ---------------------------------------------------------------------------
# 9. Programa principal
# ---------------------------------------------------------------------------
def main():
    carpeta = os.path.dirname(os.path.abspath(__file__))
    ruta_entrada = sys.argv[1] if len(sys.argv) > 1 else os.path.join(carpeta, "input.txt")
    ruta_salida = sys.argv[2] if len(sys.argv) > 2 else os.path.join(carpeta, "output.txt")

    try:
        grafo, mision, restricciones = leer_entrada(ruta_entrada)
    except (OSError, ValueError) as error:
        print(f"Error al leer la entrada: {error}")
        sys.exit(1)

    plan, error = planificar_escape(grafo, mision, restricciones)
    reporte = generar_reporte(grafo, mision, restricciones, plan, error)

    with open(ruta_salida, "w", encoding="utf-8") as archivo:
        archivo.write(reporte)
    print(reporte)
    print(f"Reporte guardado en: {ruta_salida}")


if __name__ == "__main__":
    main()
