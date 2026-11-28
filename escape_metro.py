# Proyecto: El Escape de los Coleccionistas en el Metro de París
# Modelación de Sistemas en Redes - UNIMET (Trimestre 2627-1)

import os
import sys

INFINITO = float("inf")


class GrafoMetro:
    """Grafo dirigido y ponderado implementado con LISTA DE ADYACENCIA.
    Ideal para redes dispersas como el metro: usa memoria O(V + E) y recorre
    únicamente los túneles salientes de cada estación.
    """

    def __init__(self):
        self.adyacencia = {}   # estacion -> [(destino, tiempo_viaje, linea), ...]
        self.transbordos = {}  # estacion -> tiempo de transbordo interno

    def agregar_estacion(self, id_est, t_transbordo):
        self.adyacencia[id_est] = []
        self.transbordos[id_est] = t_transbordo

    def agregar_tunel(self, origen, destino, tiempo, linea):
        # Grafo dirigido: solo se registra el sentido origen -> destino
        self.adyacencia[origen].append((destino, tiempo, linea))


def leer_archivo(ruta):
    """Lee input.txt ignorando comentarios (#) y retorna grafo, misión y restricciones."""
    datos = []
    with open(ruta, "r", encoding="utf-8") as f:
        for linea in f:
            limpio = linea.split("#")[0].strip()
            if limpio:
                datos.append(limpio.split())

    n_est, n_tun = map(int, datos[0])
    grafo = GrafoMetro()
    idx = 1

    for _ in range(n_est):
        est, t_trans = map(int, datos[idx])
        grafo.agregar_estacion(est, t_trans)
        idx += 1

    for _ in range(n_tun):
        u, v, tiempo = map(int, datos[idx][:3])
        grafo.agregar_tunel(u, v, tiempo, datos[idx][3])
        idx += 1

    op, oa, dp, da = map(int, datos[idx])
    mision = {"origen_p": op, "origen_a": oa, "destino_p": dp, "destino_a": da}
    idx += 1

    clausuras = []
    retrasos = {}
    while idx < len(datos):
        campos = datos[idx]
        tipo = campos[0].upper()
        if tipo in ("CLAUSURA", "DISPONIBILIDAD"):
            clausuras.append((campos[1], int(campos[2]), int(campos[3])))
        elif tipo in ("RETRASO", "PENALIZACION"):
            retrasos[campos[1]] = int(campos[2]) if len(campos) > 2 else 2
        idx += 1

    return grafo, mision, clausuras, retrasos


def dijkstra_inverso(grafo, destino, retrasos):
    """Calcula la distancia mínima hacia 'destino' invirtiendo los arcos dirigidos."""
    entrantes = {est: [] for est in grafo.adyacencia}
    for u in grafo.adyacencia:
        for v, t_base, linea in grafo.adyacencia[u]:
            entrantes[v].append((u, t_base * retrasos.get(linea, 1)))

    dist = {est: INFINITO for est in grafo.adyacencia}
    dist[destino] = 0
    visitados = set()

    while len(visitados) < len(dist):
        actual, menor = None, INFINITO
        for est in dist:
            if est not in visitados and dist[est] < menor:
                actual, menor = est, dist[est]
        if actual is None:
            break
        visitados.add(actual)
        for vecino, peso in entrantes[actual]:
            if vecino not in visitados and dist[actual] + peso < dist[vecino]:
                dist[vecino] = dist[actual] + peso
    return dist


def obtener_movimientos(grafo, estado, t, meta, dist_meta, clausuras, retrasos):
    """Genera las transiciones válidas (nuevo_estado, tunel_usado, es_espera) de t a t+1."""
    tipo = estado[0]
    if tipo == "VIAJE":
        _, u, v, linea, fin = estado
        nuevo = ("ESTACION", v, linea) if t + 1 == fin else estado
        return [(nuevo, (u, v, linea), False)]

    if tipo == "TRANSBORDO":
        _, est, linea_nueva, fin = estado
        nuevo = ("ESTACION", est, linea_nueva) if t + 1 == fin else estado
        return [(nuevo, None, False)]

    _, est, linea_act = estado
    opciones = [(estado, None, True)]  # Esperar 1 minuto en la estación
    if est == meta:
        return opciones

    # Abordar tren de la línea actual (o cualquiera si recién arranca desde el origen)
    for vecino, t_base, linea in grafo.adyacencia[est]:
        if dist_meta[vecino] != INFINITO and (linea_act is None or linea == linea_act):
            dur = t_base * retrasos.get(linea, 1)
            nuevo = ("ESTACION", vecino, linea) if dur == 1 else ("VIAJE", est, vecino, linea, t + dur)
            opciones.append((nuevo, (est, vecino, linea), False))

    # Hacer transbordo interno hacia otra línea disponible en esta estación
    if linea_act is not None:
        t_trans = grafo.transbordos[est]
        fin = t + t_trans
        lineas_est = {lin for _, _, lin in grafo.adyacencia[est] if lin != linea_act}
        for lin_nueva in sorted(lineas_est):
            bloqueado = False
            for lin_bloq, ini_b, fin_b in clausuras:
                if lin_bloq in (linea_act, lin_nueva) and t <= fin_b and ini_b <= fin:
                    bloqueado = True
                    break
            if bloqueado:
                continue
            if t_trans == 0:
                for vecino, t_base, linea in grafo.adyacencia[est]:
                    if linea == lin_nueva and dist_meta[vecino] != INFINITO:
                        dur = t_base * retrasos.get(linea, 1)
                        nuevo = ("ESTACION", vecino, linea) if dur == 1 else ("VIAJE", est, vecino, linea, t + dur)
                        opciones.append((nuevo, (est, vecino, linea), False))
            elif t_trans == 1:
                opciones.append((("ESTACION", est, lin_nueva), None, False))
            else:
                opciones.append((("TRANSBORDO", est, lin_nueva, fin), None, False))

    return opciones


def hay_colision(est_p, est_a, tunel_p, tunel_a, dest_p, dest_a):
    """Verifica no-colisión temporal (misma estación) y espacial (mismo túnel)."""
    pos_p = est_p[1] if est_p[0] != "VIAJE" else None
    pos_a = est_a[1] if est_a[0] != "VIAJE" else None

    if pos_p is not None and pos_p == pos_a:
        if not (dest_p == dest_a and pos_p == dest_p and est_p[0] == "ESTACION" and est_a[0] == "ESTACION"):
            return True

    if tunel_p is not None and tunel_a is not None:
        u1, v1, _ = tunel_p
        u2, v2, _ = tunel_a
        if (u1 == u2 and v1 == v2) or (u1 == v2 and v1 == u2):
            return True
    return False


def cota_restante(estado, t_act, dist_meta):
    """Minutos mínimos restantes desde el estado actual hasta la compuerta."""
    if estado[0] == "ESTACION":
        return dist_meta[estado[1]]
    if estado[0] == "TRANSBORDO":
        return (estado[3] - t_act) + dist_meta[estado[1]]
    return (estado[4] - t_act) + dist_meta[estado[2]]


def planificar_rutas(grafo, mision, clausuras, retrasos):
    """Busca minuto a minuto el plan conjunto que minimiza T_max sin colisiones."""
    op, oa = mision["origen_p"], mision["origen_a"]
    dp, da = mision["destino_p"], mision["destino_a"]

    dist_p = dijkstra_inverso(grafo, dp, retrasos)
    dist_a = dijkstra_inverso(grafo, da, retrasos)
    if dist_p[op] == INFINITO or dist_a[oa] == INFINITO:
        return None, "No existe camino dirigido hasta el búnker."

    ini_p, ini_a = ("ESTACION", op, None), ("ESTACION", oa, None)
    if hay_colision(ini_p, ini_a, None, None, dp, da):
        return None, "Pierre y Amélie inician en la misma estación."
    if op == dp and oa == da:
        return ([ini_p], [ini_a]), None

    suma_pesos = sum(grafo.transbordos.values()) + sum(
        tb * retrasos.get(lin, 1) for u in grafo.adyacencia for _, tb, lin in grafo.adyacencia[u]
    )
    max_clausura = max([fin for _, _, fin in clausuras], default=0)
    tiempo_limite = max_clausura + (suma_pesos * 2) + 60

    capas = [{(ini_p, ini_a): (0, 0, 0, None)}]
    t = 0
    while t < tiempo_limite and capas[t]:
        siguiente = {}
        for (ep, ea), (mov, riesgo, esp_int, _) in capas[t].items():
            movs_p = obtener_movimientos(grafo, ep, t, dp, dist_p, clausuras, retrasos)
            movs_a = obtener_movimientos(grafo, ea, t, da, dist_a, clausuras, retrasos)

            for np, tp, espera_p in movs_p:
                if (t + 1) + cota_restante(np, t + 1, dist_p) > tiempo_limite:
                    continue
                for na, ta, espera_a in movs_a:
                    if (t + 1) + cota_restante(na, t + 1, dist_a) > tiempo_limite:
                        continue
                    if hay_colision(np, na, tp, ta, dp, da):
                        continue

                    n_mov = mov + (0 if espera_p else 1) + (0 if espera_a else 1)
                    n_riesgo, n_int = riesgo, esp_int

                    if espera_p and (ep[2] is not None or op == dp):
                        if ep[1] == dp:
                            n_riesgo += 1
                        else:
                            n_int += 1
                    if espera_a and (ea[2] is not None or oa == da):
                        if ea[1] == da:
                            n_riesgo += 1
                        else:
                            n_int += 1

                    clave = (np, na)
                    criterio = (n_mov, n_riesgo, n_int)
                    if clave not in siguiente or criterio < siguiente[clave][:3]:
                        siguiente[clave] = (n_mov, n_riesgo, n_int, (ep, ea))

        capas.append(siguiente)
        t += 1

        metas = [
            (datos[:3], par) for par, datos in siguiente.items()
            if par[0][0] == "ESTACION" and par[0][1] == dp and par[1][0] == "ESTACION" and par[1][1] == da
        ]
        if metas:
            _, actual = min(metas)
            hist_p, hist_a = [], []
            for m in range(t, -1, -1):
                hist_p.append(actual[0])
                hist_a.append(actual[1])
                actual = capas[m][actual][3]
            return (hist_p[::-1], hist_a[::-1]), None

    return None, "No existe plan sincronizado libre de colisiones."


def extraer_eventos(historial, origen, destino, compuerta):
    """Convierte los estados por minuto de un personaje en los eventos del reporte."""
    t_max = len(historial) - 1
    if origen == destino:
        eventos = [(0, f"Estación {origen} (Origen - Destino Compuerta {compuerta})")]
        if t_max > 0:
            eventos.append((t_max, f"Estación {destino} (Espera en {compuerta}: {t_max} min - {t_max} pts de riesgo)"))
        return 0, 0, t_max, eventos

    salida = 0
    while salida < t_max and historial[salida + 1] == ("ESTACION", origen, None):
        salida += 1

    texto_ini = "Origen - Inicia Movimiento" if salida > 0 else "Origen"
    eventos = [(salida, f"Estación {origen} ({texto_ini})")]
    llegada, espera_ini, riesgo = None, None, 0

    for t in range(salida + 1, t_max + 1):
        ant, act = historial[t - 1], historial[t]
        if espera_ini is not None and act != ant:
            eventos.append((t - 1, f"Estación {ant[1]} (Fin de espera de {t - 1 - espera_ini} min)"))
            espera_ini = None

        llego = act[0] == "ESTACION" and (ant[0] == "VIAJE" or (ant[0] == "ESTACION" and act[1] != ant[1]))
        transbordo = act[0] == "ESTACION" and act[1] == ant[1] and (ant[0] == "TRANSBORDO" or act[2] != ant[2])

        if llego:
            if act[1] == destino and llegada is None:
                llegada = t
                eventos.append((t, f"Estación {destino} (Destino Compuerta {compuerta})"))
            else:
                eventos.append((t, f"Estación {act[1]} (Viaje {act[2]})"))
        elif transbordo:
            eventos.append((t, f"Estación {act[1]} (Termina Transbordo a {act[2]})"))
        elif act[0] == "ESTACION" and act == ant:
            if act[1] == destino:
                riesgo += 1
            elif espera_ini is None:
                espera_ini = t - 1

    if riesgo > 0:
        eventos.append((t_max, f"Estación {destino} (Espera en {compuerta}: {riesgo} min - {riesgo} pts de riesgo)"))
    return salida, (llegada or salida) - salida, riesgo, eventos


def armar_reporte(resultado, error, mision):
    """Genera el texto final con el formato de output.txt pedido en el enunciado."""
    if resultado is None:
        return f"=== PLAN DE ESCAPE CONFIGURADO ===\n\nResultado de Sincronización: FRACASO. {error}\n"

    hist_p, hist_a = resultado
    t_max = len(hist_p) - 1
    sal_p, viaje_p, riesgo_p, ev_p = extraer_eventos(hist_p, mision["origen_p"], mision["destino_p"], "D1")
    sal_a, viaje_a, riesgo_a, ev_a = extraer_eventos(hist_a, mision["origen_a"], mision["destino_a"], "D2")

    lineas = [
        "=== PLAN DE ESCAPE CONFIGURADO ===",
        f"Tiempo Total de la Operación: {t_max} minutos",
        "",
        "[PROGRAMACIÓN DE SALIDAS]",
    ]
    for nombre, sal in (("Pierre", sal_p), ("Amélie", sal_a)):
        extra = f" (Debe esperar {sal} minutos en su estación de origen)" if sal > 0 else ""
        lineas.append(f"* {nombre} arranca en el minuto: {sal}{extra}")

    for nombre, viaje, eventos in (("PIERRE", viaje_p, ev_p), ("AMÉLIE", viaje_a, ev_a)):
        lineas.append("")
        lineas.append(f"[RUTA DE {nombre} (Tiempo total de viaje: {viaje} min)]")
        for minuto, desc in eventos:
            lineas.append(f"Minuto {minuto}: {desc}")

    lineas.append("")
    riesgo_tot = riesgo_p + riesgo_a
    if riesgo_tot == 0:
        lineas.append(f"Resultado de Sincronización: ÉXITO. Llegada simultánea en el minuto {t_max}.")
    else:
        lineas.append(f"Resultado de Sincronización: ÉXITO. Acceso simultáneo en el minuto {t_max} (Puntos de riesgo: {riesgo_tot}).")
    return "\n".join(lineas) + "\n"


def main():
    base = os.path.dirname(os.path.abspath(__file__))
    entrada = sys.argv[1] if len(sys.argv) > 1 else os.path.join(base, "input.txt")
    salida = sys.argv[2] if len(sys.argv) > 2 else os.path.join(base, "output.txt")

    try:
        grafo, mision, clausuras, retrasos = leer_archivo(entrada)
    except Exception as e:
        print(f"Error en archivo de entrada: {e}")
        return

    resultado, error = planificar_rutas(grafo, mision, clausuras, retrasos)
    reporte = armar_reporte(resultado, error, mision)
    with open(salida, "w", encoding="utf-8") as f:
        f.write(reporte)
    print(reporte)


if __name__ == "__main__":
    main()
