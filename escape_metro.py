"""El Escape de los Coleccionistas en el Metro de París
Modelación de Sistemas en Redes - UNIMET - Trimestre 2627-1

Uso:
    python escape_metro.py [input.txt] [output.txt]

Flujo:
    1. LectorEntrada         lee input.txt y crea el grafo, la misión y las restricciones.
    2. PlanificadorEscape    busca las rutas sincronizadas de Pierre y Amélie.
    3. GeneradorReporte      arma el texto con el plan y lo guarda en output.txt.

Clases (en orden de dependencia):
    GrafoMetro          red del metro (lista de adyacencias)
    Restricciones       disponibilidad y penalización de líneas
    Mision              orígenes y compuertas de la misión
    LectorEntrada       lectura y validación de input.txt
    Dijkstra            caminos mínimos (cota para la búsqueda)
    Personaje           estados y movimientos de Pierre / Amélie
    DetectorColisiones  reglas de no-colisión
    PlanificadorEscape  búsqueda sincronizada en el tiempo
    InfoRuta            resumen de la ruta de un personaje
    AnalizadorRuta      convierte estados en eventos legibles
    GeneradorReporte    texto final de output.txt

Solo se usa la biblioteca estándar de Python.
"""

import os
import sys


# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------
# Valor que representa "no se puede llegar". Se usa como distancia inicial en
# Dijkstra y como señal de que una estación es inalcanzable. Cualquier suma con
# infinito sigue siendo infinito, lo que simplifica las comparaciones.
INFINITO = float("inf")


# ---------------------------------------------------------------------------
# GrafoMetro
# ---------------------------------------------------------------------------
class GrafoMetro:
    """Red del metro representada como LISTA DE ADYACENCIAS.

    Se eligió esta representación porque el metro es un grafo disperso (cada
    estación se conecta con muy pocas otras). Una lista de adyacencias ocupa
    memoria proporcional a V + E y permite recorrer los vecinos de una
    estación sin revisar las que no están conectadas, que es justo lo que hace
    Dijkstra y la búsqueda de movimientos.

    Atributos:
        adyacencias: dict  estación -> lista de (vecino, tiempo_viaje, línea).
        transbordo:  dict  estación -> tiempo de transbordo interno (minutos).
    """

    def __init__(self):
        """Crea un grafo vacío, sin estaciones ni túneles."""
        self.adyacencias = {}
        self.transbordo = {}

    def agregar_estacion(self, estacion, tiempo_transbordo):
        """Agrega un vértice (estación) con su tiempo de transbordo interno.

        Lanza ValueError si la estación ya fue agregada antes.
        """
        if estacion in self.adyacencias:
            raise ValueError(f"La estación {estacion} está repetida en el archivo.")
        self.adyacencias[estacion] = []
        self.transbordo[estacion] = tiempo_transbordo

    def agregar_tunel(self, u, v, tiempo, linea):
        """Agrega un túnel entre las estaciones u y v, en AMBOS sentidos.

        El archivo de entrada lista cada túnel una sola vez, pero los trenes
        circulan en las dos direcciones, por eso se guardan dos arcos
        (u -> v y v -> u) con el mismo tiempo y la misma línea.

        Lanza ValueError si alguna estación no existe o el tiempo no es positivo.
        """
        for estacion in (u, v):
            if estacion not in self.adyacencias:
                raise ValueError(f"El túnel {u}-{v} usa la estación {estacion}, que no existe.")
        if tiempo <= 0:
            raise ValueError(f"El túnel {u}-{v} debe tener un tiempo de viaje positivo.")
        self.adyacencias[u].append((v, tiempo, linea))
        self.adyacencias[v].append((u, tiempo, linea))

    def estaciones(self):
        """Devuelve la lista de todos los identificadores de estación."""
        return list(self.adyacencias.keys())

    def existe_estacion(self, estacion):
        """Indica si la estación existe en la red."""
        return estacion in self.adyacencias

    def vecinos(self, u):
        """Devuelve los arcos que salen de u como lista de (vecino, tiempo, línea)."""
        return self.adyacencias[u]

    def lineas_de(self, u):
        """Devuelve el conjunto de líneas que pasan por la estación u."""
        return {linea for (_, _, linea) in self.adyacencias[u]}

    def lineas(self):
        """Devuelve la lista ordenada de todas las líneas de la red."""
        return sorted({linea for arcos in self.adyacencias.values() for (_, _, linea) in arcos})

    def tiempo_transbordo(self, u):
        """Devuelve el tiempo de transbordo interno de la estación u."""
        return self.transbordo[u]


# ---------------------------------------------------------------------------
# Restricciones
# ---------------------------------------------------------------------------
class Restricciones:
    """Guarda las dos restricciones opcionales que puede traer el archivo de entrada.

    * DISPONIBILIDAD: una línea no permite transbordos (ni hacia ella ni desde
      ella) durante un intervalo de minutos [inicio, fin]. Representa
      mantenimientos imprevistos.
    * PENALIZACIÓN: un factor entero que multiplica el tiempo de viaje de una
      línea (retrasos técnicos). Por defecto vale 1, es decir, sin cambios.

    Atributos:
        disponibilidad: dict  línea -> lista de (minuto_inicio, minuto_fin).
        penalizacion:   dict  línea -> factor entero >= 1.
    """

    def __init__(self):
        """Crea el objeto sin ninguna restricción activa."""
        self.disponibilidad = {}
        self.penalizacion = {}

    def agregar_disponibilidad(self, linea, inicio, fin):
        """Registra que `linea` no permite transbordos entre los minutos inicio y fin."""
        self.disponibilidad.setdefault(linea, []).append((inicio, fin))

    def agregar_penalizacion(self, linea, factor):
        """Registra que el tiempo de viaje de `linea` se multiplica por `factor`."""
        self.penalizacion[linea] = factor

    def hay_restricciones(self):
        """Indica si hay al menos una restricción registrada (para el reporte)."""
        return bool(self.disponibilidad or self.penalizacion)

    def factor(self, linea):
        """Factor de penalización de la línea; 1 si no tiene penalización."""
        return self.penalizacion.get(linea, 1)

    def tiempo_viaje(self, tiempo_base, linea):
        """Tiempo real de un túnel: el tiempo del archivo por el factor de su línea."""
        return tiempo_base * self.factor(linea)

    def fin_ultima_ventana(self):
        """Último minuto en que alguna línea tiene una restricción de disponibilidad.

        Pasado ese minuto las reglas dejan de depender del reloj. El planificador
        usa este dato para saber desde cuándo puede detectar ciclos en su búsqueda.
        """
        return max([fin for ventanas in self.disponibilidad.values()
                    for (_, fin) in ventanas] + [0])

    def transbordo_permitido(self, linea_actual, linea_nueva, inicio, fin):
        """Indica si un transbordo que ocupa los minutos [inicio, fin] es válido.

        Está prohibido si ese intervalo se solapa con una ventana de
        no-disponibilidad de la línea de origen O de la línea de destino.
        """
        for linea in (linea_actual, linea_nueva):
            for (a, b) in self.disponibilidad.get(linea, []):
                if inicio <= b and a <= fin:
                    return False
        return True


# ---------------------------------------------------------------------------
# Mision
# ---------------------------------------------------------------------------
class Mision:
    """Datos de la misión leídos del archivo de entrada.

    Atributos:
        origen_pierre:  estación donde inicia Pierre.
        origen_amelie:  estación donde inicia Amélie.
        destino_pierre: estación de la compuerta D1 del búnker (por donde entra Pierre).
        destino_amelie: estación de la compuerta D2 del búnker (por donde entra Amélie).
    """

    def __init__(self, origen_pierre, origen_amelie, destino_pierre, destino_amelie):
        """Guarda los cuatro identificadores de estación de la misión."""
        self.origen_pierre = origen_pierre
        self.origen_amelie = origen_amelie
        self.destino_pierre = destino_pierre
        self.destino_amelie = destino_amelie

    def estaciones(self):
        """Devuelve las cuatro estaciones involucradas (para validar que existen)."""
        return [self.origen_pierre, self.origen_amelie,
                self.destino_pierre, self.destino_amelie]


# ---------------------------------------------------------------------------
# LectorEntrada
# ---------------------------------------------------------------------------
class LectorEntrada:
    """Lee y valida el archivo de entrada.

    Formato esperado (las líneas que empiezan con # son comentarios):
        1. Número de estaciones y número de túneles.
        2. Una línea por estación: id y tiempo de transbordo.
        3. Una línea por túnel: origen, destino, tiempo y línea.
        4. Datos de la misión: origen de Pierre, de Amélie y las dos compuertas.
        5. (Opcional) restricciones:
             DISPONIBILIDAD <línea> <minuto_inicio> <minuto_fin>
             PENALIZACION   <línea> <factor>

    Uso:
        grafo, mision, restricciones = LectorEntrada(ruta).leer()
    """

    def __init__(self, ruta):
        """Guarda la ruta del archivo a leer."""
        self.ruta = ruta
        self.datos = []      # lista de (número_de_línea, [campos]) ya sin comentarios
        self.pos = 0         # índice de la próxima línea de `datos` por procesar

    def leer(self):
        """Lee el archivo completo y devuelve (grafo, mision, restricciones).

        Lanza ValueError si el contenido es inválido y OSError si no se puede abrir.
        """
        self._cargar_lineas()
        num_estaciones, num_tuneles = self._siguiente_entero(2, "estaciones y túneles")

        grafo = GrafoMetro()
        self._leer_estaciones(grafo, num_estaciones)
        self._leer_tuneles(grafo, num_tuneles)
        mision = self._leer_mision(grafo)
        restricciones = self._leer_restricciones(grafo)
        return grafo, mision, restricciones

    # ------------------------------------------------------------------
    # Pasos internos de la lectura
    # ------------------------------------------------------------------
    def _cargar_lineas(self):
        """Carga el archivo descartando comentarios (#) y líneas en blanco.

        Se conserva el número original de cada línea para poder dar mensajes de
        error que indiquen exactamente dónde está el problema.
        """
        self.datos = []
        self.pos = 0
        with open(self.ruta, encoding="utf-8") as archivo:
            for numero, linea in enumerate(archivo, start=1):
                texto = linea.split("#", 1)[0].strip()
                if texto:
                    self.datos.append((numero, texto.split()))
        if not self.datos:
            raise ValueError("El archivo de entrada está vacío.")

    @staticmethod
    def _enteros(numero, campos, cantidad, descripcion):
        """Convierte `campos` a enteros verificando que haya exactamente `cantidad`."""
        if len(campos) != cantidad:
            raise ValueError(f"Línea {numero}: se esperaban {cantidad} valores ({descripcion}).")
        try:
            return [int(c) for c in campos]
        except ValueError:
            raise ValueError(f"Línea {numero}: valores no numéricos en {descripcion}.")

    def _siguiente_entero(self, cantidad, descripcion):
        """Consume la próxima línea y la devuelve como lista de `cantidad` enteros."""
        numero, campos = self.datos[self.pos]
        self.pos += 1
        return self._enteros(numero, campos, cantidad, descripcion)

    def _leer_estaciones(self, grafo, cantidad):
        """Lee las `cantidad` líneas de estaciones y las agrega al grafo."""
        for _ in range(cantidad):
            if self.pos >= len(self.datos):
                raise ValueError("Faltan estaciones en el archivo de entrada.")
            numero = self.datos[self.pos][0]
            estacion, transbordo = self._siguiente_entero(2, "estación y transbordo")
            if transbordo < 0:
                raise ValueError(f"Línea {numero}: el transbordo no puede ser negativo.")
            grafo.agregar_estacion(estacion, transbordo)

    def _leer_tuneles(self, grafo, cantidad):
        """Lee las `cantidad` líneas de túneles y las agrega al grafo."""
        for _ in range(cantidad):
            if self.pos >= len(self.datos):
                raise ValueError("Faltan túneles en el archivo de entrada.")
            numero, campos = self.datos[self.pos]
            if len(campos) != 4:
                raise ValueError(f"Línea {numero}: un túnel necesita origen, destino, tiempo y línea.")
            u, v, tiempo = self._enteros(numero, campos[:3], 3, "túnel")
            grafo.agregar_tunel(u, v, tiempo, campos[3])    # la línea es texto (ej. "L1")
            self.pos += 1

    def _leer_mision(self, grafo):
        """Lee la línea de la misión y verifica que las 4 estaciones existan."""
        if self.pos >= len(self.datos):
            raise ValueError("Faltan los datos de la misión.")
        valores = self._siguiente_entero(4, "datos de la misión")
        mision = Mision(*valores)
        for estacion in mision.estaciones():
            if not grafo.existe_estacion(estacion):
                raise ValueError(f"La estación {estacion} de la misión no existe.")
        return mision

    def _leer_restricciones(self, grafo):
        """Lee las líneas opcionales DISPONIBILIDAD / PENALIZACION hasta el final."""
        restricciones = Restricciones()
        lineas_validas = set(grafo.lineas())
        while self.pos < len(self.datos):
            numero, campos = self.datos[self.pos]
            tipo = campos[0].upper()
            if tipo == "DISPONIBILIDAD" and len(campos) == 4:
                linea = campos[1]
                inicio, fin = self._enteros(numero, campos[2:], 2, "intervalo de disponibilidad")
                if inicio > fin:
                    raise ValueError(f"Línea {numero}: el minuto inicial es mayor que el final.")
                restricciones.agregar_disponibilidad(linea, inicio, fin)
            elif tipo == "PENALIZACION" and len(campos) == 3:
                linea = campos[1]
                (factor,) = self._enteros(numero, campos[2:], 1, "factor de penalización")
                if factor < 1:
                    raise ValueError(f"Línea {numero}: el factor de penalización debe ser >= 1.")
                restricciones.agregar_penalizacion(linea, factor)
            else:
                raise ValueError(f"Línea {numero}: restricción no reconocida: {' '.join(campos)}")
            if linea not in lineas_validas:
                raise ValueError(f"Línea {numero}: la línea {linea} no existe en la red.")
            self.pos += 1
        return restricciones


# ---------------------------------------------------------------------------
# Dijkstra
# ---------------------------------------------------------------------------
class Dijkstra:
    """Algoritmo de Dijkstra (versión de clase: etiquetado permanente).

    Calcula la distancia mínima desde una estación a todas las demás usando el
    tiempo de viaje penalizado y SIN considerar transbordos ni colisiones.

    ¿Para qué sirve entonces? Como los transbordos y las esperas solo pueden
    AUMENTAR el tiempo, esta distancia es una COTA INFERIOR de lo que falta
    para llegar. El planificador la usa para descartar estados desde los que
    ya es imposible alcanzar la compuerta.

    Como los túneles son bidireccionales, la distancia calculada desde el
    destino hacia todas las estaciones es igual a la distancia de cada
    estación hacia el destino.
    """

    def __init__(self, grafo, restricciones):
        """Guarda el grafo y las restricciones (para aplicar las penalizaciones)."""
        self.grafo = grafo
        self.restricciones = restricciones

    def calcular(self, origen):
        """Ejecuta Dijkstra desde `origen`.

        Devuelve (d, previo):
            d[x]      = distancia mínima de origen a x (INFINITO si no hay camino).
            previo[x] = estación anterior a x en el camino mínimo (None si no hay).
        """
        estaciones = self.grafo.estaciones()
        d = {x: INFINITO for x in estaciones}
        previo = {x: None for x in estaciones}
        etiquetado = set()      # vértices con distancia ya definitiva
        d[origen] = 0

        while True:
            # Elegir el vértice no etiquetado con menor distancia provisional.
            y, menor = None, INFINITO
            for x in estaciones:
                if x not in etiquetado and d[x] < menor:
                    y, menor = x, d[x]
            if y is None:       # todos etiquetados, o los restantes son inalcanzables
                break
            etiquetado.add(y)
            # Actualizar solo los adyacentes de y (ventaja de la lista de adyacencias).
            for (x, tiempo, linea) in self.grafo.vecinos(y):
                if x not in etiquetado:
                    alternativa = d[y] + self.restricciones.tiempo_viaje(tiempo, linea)
                    if alternativa < d[x]:
                        d[x] = alternativa
                        previo[x] = y
        return d, previo


# ---------------------------------------------------------------------------
# Personaje
# ---------------------------------------------------------------------------
class Personaje:
    """Un personaje (Pierre o Amélie) que debe llegar a su compuerta del búnker.

    ESTADOS INDIVIDUALES
    --------------------
    En cada minuto el personaje está en uno de estos tres estados. Se guardan
    como tuplas (y no como objetos) porque el planificador los usa como claves
    de diccionario y los compara millones de veces; las tuplas son mucho más
    rápidas de hashear.

      ("E", estacion, linea)             En el ANDÉN de `linea` de una estación.
                                         `linea` es None si aún no ha salido de
                                         su origen (puede tomar cualquier línea).
      ("T", estacion, linea_nueva, fin)  TRANSBORDANDO hacia el andén de
                                         `linea_nueva`; termina en el minuto `fin`.
      ("V", origen, destino, linea, fin) VIAJANDO por un túnel de `linea`;
                                         llega a `destino` en el minuto `fin`.

    El transbordo es una acción propia: el personaje puede cambiarse de andén y
    luego esperar allí el tren de la nueva línea. El tiempo de transbordo se
    paga siempre.

    Atributos:
        nombre:     "Pierre" o "Amélie".
        origen:     estación de partida.
        destino:    estación de su compuerta en el búnker.
        compuerta:  nombre de la compuerta ("D1" o "D2"), solo para el reporte.
        distancia:  dict estación -> distancia mínima a `destino` (Dijkstra).
    """

    def __init__(self, nombre, origen, destino, compuerta, grafo, restricciones):
        """Crea el personaje y precalcula las distancias mínimas a su compuerta.

        Dijkstra se ejecuta UNA vez desde el destino; como los túneles son
        bidireccionales, esa distancia vale para cualquier estación del mapa.
        """
        self.nombre = nombre
        self.origen = origen
        self.destino = destino
        self.compuerta = compuerta
        self.grafo = grafo
        self.restricciones = restricciones
        self.distancia, _ = Dijkstra(grafo, restricciones).calcular(destino)

    # ------------------------------------------------------------------
    # Consultas sobre el personaje y sus estados
    # ------------------------------------------------------------------
    def estado_inicial(self):
        """Estado en el minuto 0: en su origen, sin línea elegida todavía."""
        return ("E", self.origen, None)

    def puede_llegar(self):
        """Indica si existe algún camino de su origen a su compuerta."""
        return self.distancia[self.origen] != INFINITO

    def ya_esta_en_compuerta(self):
        """Indica si el origen ya es su compuerta (no necesita moverse)."""
        return self.origen == self.destino

    def esta_en_compuerta(self, estado):
        """Indica si `estado` es estar parado en el andén de su compuerta."""
        return estado[0] == "E" and estado[1] == self.destino

    @staticmethod
    def estacion_actual(estado):
        """Estación que ocupa el personaje en un instante, o None si está en un túnel."""
        if estado[0] in ("E", "T"):
            return estado[1]
        return None

    @staticmethod
    def relativo(estado, t):
        """Devuelve el estado con su minuto de fin expresado RELATIVO a t.

        Sirve para comparar situaciones iguales ocurridas en distintos minutos
        (por ejemplo "me faltan 3 minutos de viaje") y así detectar ciclos.
        """
        if estado[0] == "E":
            return estado
        return estado[:-1] + (estado[-1] - t,)

    # ------------------------------------------------------------------
    # Movimientos
    # ------------------------------------------------------------------
    def sucesores(self, estado, t):
        """Movimientos posibles del personaje entre el minuto t y el t+1.

        Devuelve una lista de tuplas (nuevo_estado, linea_en_tunel, espera):
          nuevo_estado   = estado del personaje en el minuto t+1.
          linea_en_tunel = línea que ocupa durante (t, t+1], o None si no viaja.
          espera         = True si estuvo quieto ese minuto (suma 1 punto de riesgo).
        """
        tipo = estado[0]

        # Viajando: no tiene opciones, el tren sigue hasta llegar.
        if tipo == "V":
            _, _, v, linea, fin = estado
            nuevo = ("E", v, linea) if fin == t + 1 else estado
            return [(nuevo, linea, False)]

        # Transbordando: tampoco decide, camina hasta el otro andén.
        if tipo == "T":
            _, u, linea_nueva, fin = estado
            nuevo = ("E", u, linea_nueva) if fin == t + 1 else estado
            return [(nuevo, None, False)]

        # Está en un andén: aquí sí puede elegir.
        _, u, linea_actual = estado
        opciones = [(estado, None, True)]                 # opción 1: esperar un minuto
        if u == self.destino:                             # ya está en su compuerta
            return opciones

        # Opción 2: salir por un túnel de la línea de su andén
        # (al inicio, sin línea elegida, puede tomar cualquiera).
        for (v, tiempo, linea) in self.grafo.vecinos(u):
            if linea_actual is None or linea_actual == linea:
                duracion = self.restricciones.tiempo_viaje(tiempo, linea)
                opciones.append((self._partir(u, v, linea, duracion, t), linea, False))

        # Opción 3: transbordar a otra línea de la estación (cuesta su tiempo de transbordo).
        if linea_actual is not None:
            duracion_transbordo = self.grafo.tiempo_transbordo(u)
            fin = t + duracion_transbordo
            for linea_nueva in sorted(self.grafo.lineas_de(u) - {linea_actual}):
                # Respeta las ventanas de DISPONIBILIDAD (línea en mantenimiento).
                if not self.restricciones.transbordo_permitido(linea_actual, linea_nueva, t, fin):
                    continue
                if duracion_transbordo == 0:              # transbordo instantáneo: sale de una vez
                    for (v, tiempo, linea) in self.grafo.vecinos(u):
                        if linea == linea_nueva:
                            duracion = self.restricciones.tiempo_viaje(tiempo, linea)
                            opciones.append((self._partir(u, v, linea, duracion, t), linea, False))
                elif fin == t + 1:                        # el transbordo dura un solo minuto
                    opciones.append((("E", u, linea_nueva), None, False))
                else:
                    opciones.append((("T", u, linea_nueva, fin), None, False))
        return opciones

    @staticmethod
    def _partir(u, v, linea, duracion, t):
        """Estado en el minuto t+1 de quien sale de u hacia v en el minuto t.

        Si el túnel dura 1 minuto ya llegó; si no, queda "viajando" hasta t + duracion.
        """
        if duracion == 1:
            return ("E", v, linea)
        return ("V", u, v, linea, t + duracion)

    def cota_restante(self, estado, t):
        """Cota inferior del tiempo que le falta para llegar a su compuerta.

        Usa las distancias de Dijkstra (que ignoran transbordos y esperas, por
        lo tanto nunca sobreestiman). Devuelve INFINITO si ya es imposible llegar.
        """
        tipo = estado[0]
        if tipo == "E":
            return self.distancia[estado[1]]
        if tipo == "T":
            _, u, _, fin = estado
            return (fin - t) + self.distancia[u]
        _, _, v, _, fin = estado
        return (fin - t) + self.distancia[v]


# ---------------------------------------------------------------------------
# DetectorColisiones
# ---------------------------------------------------------------------------
class DetectorColisiones:
    """Decide si dos personajes chocan en un paso de la simulación.

    Implementa las dos condiciones del enunciado:

      1. No-Colisión TEMPORAL: no pueden estar en la misma estación en el mismo
         minuto exacto.
      2. No-Colisión ESPACIAL: no pueden viajar en el mismo tren ni cruzarse en
         el mismo túnel en sentidos opuestos. Para cubrir ambos casos a la vez,
         mientras uno viaja por una línea, TODA la línea queda "ocupada" y el
         otro no puede viajar por ella.

    Es una clase sin estado: solo agrupa la regla para que esté en un único lugar.
    """

    @staticmethod
    def hay_colision(estado_p, estado_a, linea_tunel_p, linea_tunel_a):
        """Indica si Pierre y Amélie chocan en un paso de la simulación.

        Parámetros:
            estado_p, estado_a: estados de Pierre y Amélie en el minuto t+1.
            linea_tunel_p, linea_tunel_a: línea por la que viajó cada uno durante
                (t, t+1], o None si no estuvo en un túnel.
        """
        # Condición temporal: misma estación en el mismo minuto.
        # (Dos personajes dentro de túneles tienen estación None: eso no es coincidir.)
        estacion_p = Personaje.estacion_actual(estado_p)
        estacion_a = Personaje.estacion_actual(estado_a)
        if estacion_p is not None and estacion_p == estacion_a:
            return True
        # Condición espacial: la misma línea ocupada por ambos a la vez.
        return linea_tunel_p is not None and linea_tunel_p == linea_tunel_a


# ---------------------------------------------------------------------------
# PlanificadorEscape
# ---------------------------------------------------------------------------
class PlanificadorEscape:
    """Busca, minuto a minuto, los planes conjuntos de Pierre y Amélie.

    IDEA GENERAL
    ------------
    El problema no se puede resolver con un Dijkstra normal porque lo que
    importa no es solo DÓNDE está cada uno, sino CUÁNDO (para no chocar).
    Por eso se hace una búsqueda sobre la red EXPANDIDA EN EL TIEMPO:

      * Una "capa" t contiene todos los estados conjuntos (estado_P, estado_A)
        alcanzables en el minuto t sin colisiones.
      * De cada estado de la capa t se generan los de la capa t+1 combinando
        todos los movimientos de Pierre con todos los de Amélie y descartando
        los que chocan (DetectorColisiones) o que ya no pueden llegar.
      * La PRIMERA capa donde ambos están en su compuerta da el Tmax mínimo
        (porque se avanza de a un minuto, la primera que aparece es la más corta).

    CRITERIO DE DESEMPATE (en orden de prioridad)
      1. Menor tiempo total de la operación (Tmax).
      2. Menor costo de ruta: minutos en movimiento (viaje + transbordos) de ambos.
      3. A igual costo, preferir esperar en el origen (que sea desfase de salida)
         antes que esperar en estaciones intermedias.

    Atributos:
        grafo, mision, restricciones: los datos de entrada.
        pierre, amelie: los dos objetos Personaje.
    """

    def __init__(self, grafo, mision, restricciones):
        """Crea al planificador y a los dos personajes de la misión."""
        self.grafo = grafo
        self.mision = mision
        self.restricciones = restricciones
        self.pierre = Personaje("Pierre", mision.origen_pierre, mision.destino_pierre,
                                "D1", grafo, restricciones)
        self.amelie = Personaje("Amélie", mision.origen_amelie, mision.destino_amelie,
                                "D2", grafo, restricciones)

    def planificar(self):
        """Calcula el plan de escape.

        Devuelve (plan, error):
          * Éxito: plan = (estados_pierre, estados_amelie), dos listas con el
            estado de cada uno en cada minuto 0..Tmax; error = None.
          * Fracaso: plan = None; error = texto que explica la causa.
        """
        pierre, amelie = self.pierre, self.amelie

        if not pierre.puede_llegar() or not amelie.puede_llegar():
            return None, "No existe camino desde el origen hasta la compuerta asignada."

        inicial = (pierre.estado_inicial(), amelie.estado_inicial())
        if DetectorColisiones.hay_colision(inicial[0], inicial[1], None, None):
            return None, "Pierre y Amélie comienzan en la misma estación."
        if pierre.ya_esta_en_compuerta() and amelie.ya_esta_en_compuerta():
            return ([inicial[0]], [inicial[1]]), None     # ya están en sus compuertas

        # Detección de ciclos: después del último minuto con restricción de
        # disponibilidad, las reglas ya no dependen del reloj. Si una capa (con
        # los tiempos medidos relativos al minuto actual) repite una capa
        # anterior, la búsqueda entró en un ciclo: no existe plan.
        fin_ventanas = self.restricciones.fin_ultima_ventana()
        capas_vistas = set()

        # capas[t][estado_conjunto] = (costo, estado_conjunto_previo)
        capas = [{inicial: ((0, 0), None)}]
        t = 0
        while capas[t]:
            if t > fin_ventanas:
                firma = frozenset((Personaje.relativo(p, t), Personaje.relativo(a, t))
                                  for (p, a) in capas[t])
                if firma in capas_vistas:
                    break
                capas_vistas.add(firma)

            capas.append(self._expandir_capa(capas[t], t))
            t += 1

            mejor = self._mejor_estado_meta(capas[t])
            if mejor is not None:
                return self._reconstruir(capas, t, mejor), None

        return None, "No existe ningún plan que evite las colisiones."

    # ------------------------------------------------------------------
    # Pasos internos
    # ------------------------------------------------------------------
    def _expandir_capa(self, capa, t):
        """Genera la capa t+1 a partir de la capa t.

        Para cada estado conjunto combina todos los movimientos de Pierre con
        todos los de Amélie. Si un mismo estado conjunto se alcanza por varios
        caminos, se conserva el de menor costo.

        El costo es una tupla (costo_ruta, esperas_fuera_del_origen):
          * costo_ruta: minutos en movimiento (viaje o transbordo) de ambos.
          * esperas_fuera_del_origen: minutos quietos DESPUÉS de haber salido del
            origen; se minimiza para preferir el desfase de salida.
        """
        pierre, amelie = self.pierre, self.amelie
        siguiente = {}
        for (estado_p, estado_a), (costo, _) in capa.items():
            mov_p = pierre.sucesores(estado_p, t)
            mov_a = amelie.sucesores(estado_a, t)
            for (nuevo_p, tunel_p, espera_p) in mov_p:
                if pierre.cota_restante(nuevo_p, t + 1) == INFINITO:
                    continue                      # ya no puede llegar a su compuerta
                for (nuevo_a, tunel_a, espera_a) in mov_a:
                    if amelie.cota_restante(nuevo_a, t + 1) == INFINITO:
                        continue
                    if DetectorColisiones.hay_colision(nuevo_p, nuevo_a, tunel_p, tunel_a):
                        continue
                    costo_ruta = costo[0] + (not espera_p) + (not espera_a)
                    fuera_origen = costo[1]
                    if espera_p and estado_p[2] is not None:    # esperó, y ya había salido
                        fuera_origen += 1
                    if espera_a and estado_a[2] is not None:
                        fuera_origen += 1
                    nuevo_costo = (costo_ruta, fuera_origen)
                    clave = (nuevo_p, nuevo_a)
                    if clave not in siguiente or nuevo_costo < siguiente[clave][0]:
                        siguiente[clave] = (nuevo_costo, (estado_p, estado_a))
        return siguiente

    def _mejor_estado_meta(self, capa):
        """Devuelve el estado conjunto de menor costo donde AMBOS están en su compuerta.

        Devuelve None si en esta capa ninguno cumple (todavía no terminan).
        """
        metas = [(costo, clave) for clave, (costo, _) in capa.items()
                 if self.pierre.esta_en_compuerta(clave[0])
                 and self.amelie.esta_en_compuerta(clave[1])]
        if not metas:
            return None
        return min(metas)[1]

    @staticmethod
    def _reconstruir(capas, t_final, estado_final):
        """Recorre los punteros hacia atrás y devuelve la línea de tiempo de cada uno.

        Devuelve (estados_pierre, estados_amelie): listas con el estado en cada
        minuto desde 0 hasta t_final.
        """
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
# InfoRuta
# ---------------------------------------------------------------------------
class InfoRuta:
    """Resultado de analizar la línea de tiempo de un personaje.

    Atributos:
        salida:  minuto en que el personaje empieza a moverse (el desfase de salida).
        llegada: minuto en que llega por primera vez a su compuerta.
        eventos: lista de (minuto, texto) con los hitos del recorrido, en orden.
        riesgo:  dict con los minutos de espera (1 minuto = 1 punto de riesgo):
                   "origen"     -> esperando antes de salir,
                   "intermedia" -> esperando en estaciones del camino,
                   "destino"    -> esperando en su compuerta a que llegue el otro.
    """

    def __init__(self, salida, llegada, eventos, riesgo):
        """Guarda los datos ya calculados por AnalizadorRuta."""
        self.salida = salida
        self.llegada = llegada
        self.eventos = eventos
        self.riesgo = riesgo

    def puntos_riesgo(self):
        """Total de puntos de riesgo del personaje (suma de todas sus esperas)."""
        return sum(self.riesgo.values())


# ---------------------------------------------------------------------------
# AnalizadorRuta
# ---------------------------------------------------------------------------
class AnalizadorRuta:
    """Convierte la línea de tiempo de un personaje en un InfoRuta.

    El planificador entrega, para cada personaje, una lista con su estado en
    cada minuto (ver Personaje). Esa lista es difícil de leer; esta clase
    detecta cuándo sale, dónde llega, dónde transborda y cuánto espera.
    """

    def __init__(self, personaje):
        """Recibe el Personaje cuya ruta se va a analizar (origen, destino y compuerta)."""
        self.personaje = personaje

    def analizar(self, estados):
        """Analiza la lista de estados (uno por minuto) y devuelve un InfoRuta."""
        origen = self.personaje.origen
        destino = self.personaje.destino
        compuerta = self.personaje.compuerta

        t_final = len(estados) - 1
        salida = self._minuto_de_salida(estados, origen)

        eventos = []
        riesgo = {"origen": salida, "intermedia": 0, "destino": 0}
        if salida > 0:
            eventos.append((salida, f"Estación {origen} (Origen - Inicia Movimiento)"))
        else:
            eventos.append((0, f"Estación {origen} (Origen)"))

        llegada = None
        espera_inicio = None        # minuto en que empezó una espera en estación intermedia
        for t in range(salida + 1, t_final + 1):
            previo, actual = estados[t - 1], estados[t]

            # Fin de una espera intermedia: el último minuto quieto fue t-1.
            if espera_inicio is not None and actual != previo:
                eventos.append((t - 1, f"Estación {previo[1]} (Fin de espera de "
                                       f"{t - 1 - espera_inicio} min)"))
                espera_inicio = None

            # "Llegó": terminó un viaje (o cambió de estación en un solo minuto).
            llego = actual[0] == "E" and (
                previo[0] == "V" or (previo[0] == "E" and actual[1] != previo[1]))
            # "Transbordó": sigue en la misma estación pero cambió de línea/andén.
            transbordo = actual[0] == "E" and actual[1] == previo[1] and (
                previo[0] == "T" or (previo[0] == "E" and actual[2] != previo[2]))

            if llego:
                if actual[1] == destino:
                    llegada = t
                    eventos.append((t, f"Estación {destino} (Destino Compuerta {compuerta})"))
                else:
                    eventos.append((t, f"Estación {actual[1]} (Viaje {actual[2]})"))
            elif transbordo:
                eventos.append((t, f"Estación {actual[1]} (Termina Transbordo a {actual[2]})"))
            elif actual[0] == "E" and previo == actual:
                # Se quedó quieto este minuto: suma un punto de riesgo.
                if actual[1] == destino:
                    riesgo["destino"] += 1
                else:
                    riesgo["intermedia"] += 1
                    if espera_inicio is None:
                        espera_inicio = t - 1

        if llegada is None:         # salió y llegó en el minuto 0 (origen == destino)
            llegada = salida
        if llegada < t_final:       # llegó antes que el otro y tuvo que esperar
            eventos.append((t_final, f"Estación {destino} (Acceso al búnker por "
                                     f"{compuerta} tras esperar {t_final - llegada} min)"))
        return InfoRuta(salida, llegada, eventos, riesgo)

    @staticmethod
    def _minuto_de_salida(estados, origen):
        """Primer minuto en que el personaje deja de estar quieto en su origen.

        Ese valor es el DESFASE DE SALIDA: cuántos minutos se retrasa respecto
        al inicio de la operación.
        """
        t_final = len(estados) - 1
        salida = 0
        while salida < t_final and estados[salida + 1] == ("E", origen, None):
            salida += 1
        return salida


# ---------------------------------------------------------------------------
# GeneradorReporte
# ---------------------------------------------------------------------------
class GeneradorReporte:
    """Construye el reporte final del plan de escape.

    Secciones del reporte (según el formato pedido en el enunciado):
      * Tiempo total de la operación.
      * Programación de salidas (el desfase de cada personaje).
      * Ruta detallada de Pierre y de Amélie.
      * Puntos de riesgo.
      * Restricciones aplicadas (si el archivo de entrada las traía).
      * Resultado de la sincronización.
    """

    def __init__(self, planificador, restricciones):
        """Recibe el planificador (de él se toman los personajes) y las restricciones."""
        self.pierre = planificador.pierre
        self.amelie = planificador.amelie
        self.restricciones = restricciones

    def generar(self, plan, error):
        """Devuelve el reporte completo como un solo texto.

        Si `plan` es None se reporta el fracaso y su causa (`error`).
        """
        lineas = ["=== PLAN DE ESCAPE CONFIGURADO ==="]

        if plan is None:
            lineas.append("")
            lineas.append(f"Resultado de Sincronización: FRACASO. {error}")
            return "\n".join(lineas) + "\n"

        ruta_p, ruta_a = plan
        t_max = len(ruta_p) - 1
        info_p = AnalizadorRuta(self.pierre).analizar(ruta_p)
        info_a = AnalizadorRuta(self.amelie).analizar(ruta_a)
        personajes = ((self.pierre.nombre, info_p), (self.amelie.nombre, info_a))

        lineas.append(f"Tiempo Total de la Operación: {t_max} minutos")
        lineas.append("")
        lineas += self._seccion_salidas(personajes)
        for nombre, info in personajes:
            lineas.append("")
            lineas += self._seccion_ruta(nombre, info, t_max)
        lineas.append("")
        lineas += self._seccion_riesgo(personajes)
        lineas += self._seccion_restricciones()
        lineas.append("")
        lineas.append(self._resultado(info_p, info_a, t_max))
        return "\n".join(lineas) + "\n"

    # ------------------------------------------------------------------
    # Secciones del reporte
    # ------------------------------------------------------------------
    @staticmethod
    def _seccion_salidas(personajes):
        """Sección con el minuto de arranque (desfase) de cada personaje."""
        lineas = ["[PROGRAMACIÓN DE SALIDAS]"]
        for nombre, info in personajes:
            texto = f"* {nombre} arranca en el minuto: {info.salida}"
            if info.salida > 0:
                texto += f" (Debe esperar {info.salida} minutos en su estación de origen)"
            lineas.append(texto)
        return lineas

    @staticmethod
    def _seccion_ruta(nombre, info, t_max):
        """Sección con la ruta detallada de un personaje."""
        lineas = [f"[RUTA DE {nombre.upper()} (Tiempo total de viaje: "
                  f"{t_max - info.salida} min)]"]
        for minuto, texto in info.eventos:
            lineas.append(f"Minuto {minuto}: {texto}")
        return lineas

    @staticmethod
    def _seccion_riesgo(personajes):
        """Sección con los puntos de riesgo (1 punto por minuto de espera)."""
        lineas = ["[PUNTOS DE RIESGO (1 punto por minuto de espera)]"]
        total = 0
        for nombre, info in personajes:
            r = info.riesgo
            total += info.puntos_riesgo()
            lineas.append(f"* {nombre}: {info.puntos_riesgo()} (origen: {r['origen']}, "
                          f"intermedias: {r['intermedia']}, compuerta: {r['destino']})")
        lineas.append(f"* Total: {total}")
        return lineas

    def _seccion_restricciones(self):
        """Sección con las restricciones del archivo de entrada (vacía si no hay)."""
        if not self.restricciones.hay_restricciones():
            return []
        lineas = ["", "[RESTRICCIONES APLICADAS]"]
        for linea, ventanas in sorted(self.restricciones.disponibilidad.items()):
            for (a, b) in ventanas:
                lineas.append(f"* Disponibilidad: {linea} sin transbordos entre "
                              f"los minutos {a} y {b}")
        for linea, factor in sorted(self.restricciones.penalizacion.items()):
            lineas.append(f"* Penalización: {linea} multiplica su tiempo de viaje x{factor}")
        return lineas

    @staticmethod
    def _resultado(info_p, info_a, t_max):
        """Línea final: indica si la llegada fue simultánea o hubo que esperar en la compuerta."""
        if info_p.llegada == info_a.llegada == t_max:
            return f"Resultado de Sincronización: ÉXITO. Llegada simultánea en el minuto {t_max}."
        return (f"Resultado de Sincronización: ÉXITO. Acceso simultáneo al búnker "
                f"en el minuto {t_max}.")


# ---------------------------------------------------------------------------
# Programa principal
# ---------------------------------------------------------------------------
def main():
    """Lee la entrada, calcula el plan, muestra el reporte y lo guarda en un archivo."""
    carpeta = os.path.dirname(os.path.abspath(__file__))
    ruta_entrada = sys.argv[1] if len(sys.argv) > 1 else os.path.join(carpeta, "input.txt")
    ruta_salida = sys.argv[2] if len(sys.argv) > 2 else os.path.join(carpeta, "output.txt")

    try:
        grafo, mision, restricciones = LectorEntrada(ruta_entrada).leer()
    except (OSError, ValueError) as error:
        print(f"Error al leer la entrada: {error}")
        sys.exit(1)

    planificador = PlanificadorEscape(grafo, mision, restricciones)
    plan, error = planificador.planificar()
    reporte = GeneradorReporte(planificador, restricciones).generar(plan, error)

    with open(ruta_salida, "w", encoding="utf-8") as archivo:
        archivo.write(reporte)
    print(reporte)
    print(f"Reporte guardado en: {ruta_salida}")


if __name__ == "__main__":
    main()
