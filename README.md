# El Escape de los Coleccionistas en el Metro de París

Proyecto de Modelación de Sistemas en Redes (UNIMET, trimestre 2627-1).

El programa lee la red del metro desde `input.txt` y calcula las rutas de Pierre y Amélie
hasta el búnker. Las dos rutas no chocan entre sí, minimizan el tiempo total de la
operación (T_max = max(T_P, T_A)) y dicen cuántos minutos debe esperar cada uno antes de
salir para que lleguen al mismo tiempo. El reporte se guarda en `output.txt`.

Solo usa la biblioteca estándar de Python (no hace falta instalar nada).

## Cómo ejecutarlo

Desde la carpeta del proyecto:

```
python escape_metro.py
```

Por defecto lee `input.txt` y escribe `output.txt`. También se pueden indicar otros archivos:

```
python escape_metro.py pruebas/bunker_compartido.txt salida.txt
```

En Windows, si los acentos se ven mal en la consola, antes ejecutar:

```
$env:PYTHONIOENCODING='utf-8'
```

## Formato de `input.txt`

Las líneas que empiezan con `#` son comentarios y se ignoran.

```
# Número de estaciones, número de túneles
15 22
# Estación | Tiempo de Transbordo
1 2
...
# Túneles: Estación_Origen | Estación_Destino | Tiempo_Viaje | Línea
1 2 4 L1
...
# Datos de la Misión: Origen_Pierre | Origen_Amélie | Destino_Búnker_P | Destino_Búnker_A
1 12 7 8
# Restricciones (opcionales)
DISPONIBILIDAD L4 10 20   # la línea L4 no permite transbordos entre el minuto 10 y el 20
PENALIZACION L7 2         # la línea L7 multiplica su tiempo de viaje por 2
```

Si el archivo tiene un error (una estación que no existe, un valor que no es número,
faltan líneas, una restricción con una línea de metro inexistente, etc.), el programa
indica **en qué línea del archivo** está el problema en lugar de fallar.

## Representación del grafo: lista de adyacencia

El metro se guarda como un **grafo dirigido y ponderado** con **lista de adyacencia**
(clase `GrafoMetro`): cada estación tiene la lista de túneles que salen de ella, con su
destino, tiempo de viaje y línea.

¿Por qué lista de adyacencia y no matriz de adyacencia (u otra representación)?

- **El metro es una red dispersa:** cada estación se conecta con muy pocas otras. Una
  matriz de V×V tendría casi todas sus casillas vacías; la lista usa memoria O(V + E).
- **El algoritmo necesita recorrer los túneles que salen de una estación**, y con la lista
  eso cuesta solo lo que tenga esa estación, no recorrer una fila completa de V casillas.
- **Entre dos estaciones puede haber túneles de distintas líneas**, y cada túnel tiene
  varios datos (tiempo y línea). En la lista cada túnel es un elemento propio; en una
  matriz habría que meter varios valores en una misma casilla.

## Cómo funciona (resumen de las funciones)

| Función | Qué hace |
|---|---|
| `leer_archivo` | Lee y valida `input.txt`; arma el grafo, la misión y las restricciones. |
| `dijkstra_inverso` | Dijkstra desde el búnker con los arcos invertidos: da la distancia mínima de cada estación al destino. Sirve para descartar rutas que ya no pueden ser óptimas. |
| `obtener_movimientos` | Desde el estado de un personaje en un minuto, genera lo que puede hacer en el minuto siguiente: esperar, viajar por un túnel o hacer transbordo (respetando las clausuras). |
| `hay_colision` | Revisa que Pierre y Amélie no estén en la misma estación ni en el mismo túnel al mismo tiempo. |
| `planificar_rutas` | Avanza minuto a minuto con los dos personajes a la vez y se queda con el primer minuto en que ambos llegan juntos (así minimiza T_max). |
| `extraer_eventos` / `armar_reporte` | Convierten las rutas en el texto de `output.txt`. |

## Casos de prueba (`pruebas/`)

| Archivo | Qué prueba | Resultado esperado |
|---|---|---|
| `bunker_compartido.txt` | Los dos van a la misma estación búnker (por D1 y D2). | ÉXITO en el minuto 19 |
| `sin_restricciones.txt` | La red original sin clausuras ni penalizaciones. | ÉXITO en el minuto 21 |
| `sin_camino.txt` | Por ser un grafo dirigido, Amélie no tiene cómo llegar. | FRACASO: no existe camino |
| `error_estacion_inexistente.txt` | Un túnel usa una estación no declarada. | Mensaje de error en la línea 8 |
