# Calificador de Exámenes de Opción Múltiple

Sistema automático de calificación de exámenes de opción múltiple usando la
Transformada de Hough para detectar los círculos de respuesta y conteo de
píxeles (momentos) para identificar la opción marcada.

Proyecto final del curso **Procesamiento Digital de Señales 2**
Escuela de Ingeniería de Telecomunicaciones — Universidad Nacional de Piura

## 👥 Integrantes

| # | Apellidos y Nombres |
|---|---------------------|
| 1 | Cordova Malca Ismael Osmar |
| 2 | Guerrero Guerrero Erick Jair |
| 3 | Lizana Huancas Franzel |
| 4 | Peña Ipanaque Joel |
| 5 | Sosa Troncos Daniel Alexander |
| 6 | Tuesta Peña Kurt Brian |
| 7 | Yañez Manrique Rigoberto David |

---

## El problema

Corregir a mano un examen de opción múltiple es trabajo mecánico y largo. Un
curso de 40 alumnos con 80 preguntas son **3 200 burbujas** que revisar, más la
transcripción de las notas y el cruce con la lista de la clase. Se va media
tarde y basta un despiste para poner una nota que no corresponde.

Existen lectoras comerciales, pero piden hojas preimpresas propias, escáner
dedicado o licencia de pago. Lo realista en la universidad es una **foto tomada
con el celular**, que llega torcida, con sombras y comprimida por WhatsApp.

Y hay un detalle que se suele pasar por alto: los alumnos no siempre rellenan
bien. Pintan media luna, ponen un punto en el centro, dibujan un aspa o se salen
del círculo. Un programa que solo mire "cuál tiene más tinta" les califica algo
que no marcaron.

## Objetivos

**General.** Calificar automáticamente exámenes de opción múltiple a partir de
fotografías, usando la Transformada de Hough para localizar los círculos de
respuesta y operaciones de conteo de píxeles (momentos) para determinar cuál
opción fue marcada.

**Específicos:**

- Localizar la hoja dentro de la foto y corregir su perspectiva, para que el
  resto del proceso trabaje siempre sobre una imagen normalizada.
- Detectar las 500 burbujas de la hoja (400 de respuestas y 100 del código) con
  `cv2.HoughCircles`, sin depender de coordenadas fijas.
- Medir el llenado de cada burbuja con `cv2.moments` y definir un criterio
  objetivo para aceptar o anular una marca.
- Detectar y anular las marcas defectuosas: medias lunas, puntos, aspas y dobles
  marcas.
- Leer el código universitario y cruzarlo con el padrón del curso para generar
  notas y actas.
- Validar el sistema sobre fotos reales y medir su precisión con números
  verificables.

## Qué hace

Le das una carpeta con fotos y te devuelve las notas. Por el camino localiza
cada hoja, la endereza, encuentra las burbujas, mide cuánta tinta puso el alumno
en cada una, decide qué marcó, lo compara con la clave y cruza el código
universitario con la lista de la clase.

Se puede usar de tres formas, todas sobre el mismo código:

- `app.py` — aplicación de escritorio con ventana.
- `main.py` — línea de comandos, más práctico para lotes grandes.
- `notebooks/interfaz.ipynb` — la misma interfaz en Google Colab.

Genera un CSV con las notas, un Excel con cuatro hojas (notas, detalle pregunta
por pregunta, índice de dificultad y hojas sin identificar), el acta del curso y
una imagen de cada examen con la lectura marcada encima.

---

## Cómo funciona

| Paso | Qué hace | Con qué |
|---|---|---|
| 1 | Encuentra la hoja y corrige la perspectiva | `adaptiveThreshold`, `approxPolyDP`, `warpPerspective` |
| 2 | Decide si la foto está al derecho | densidad de tinta comparada por bandas |
| 3 | Localiza las burbujas | **`cv2.HoughCircles`** |
| 4 | Arma la malla de 400 nodos | picos del histograma de X e Y, ajuste lineal por fila |
| 5 | Mide cada burbuja | **`cv2.moments`** |
| 6 | Decide la respuesta | regla de llenado |
| 7 | Califica y exporta | pandas + openpyxl |

La hoja lleva marcadores impresos: un marco rectangular en el borde, rombos y
guiones en los márgenes. El marco es el que permite recortar y enderezar.

Los guiones estaban pensados para ubicar las filas, pero resultó que no sirven
en todas las fotos: son marcas de 70–260 px y al comprimir la imagen se pierden.
En una de nuestras pruebas solo se detectaron 5 de los 20 del margen derecho, y
la malla salía descuadrada. Por eso ahora las filas y las columnas se sacan de
los propios círculos que encuentra Hough, que son mucho más grandes. Los guiones
quedaron como respaldo.

### Conteo de píxeles y momentos son lo mismo

En una imagen binaria, el momento de orden cero

```
m00 = ΣΣ I(x,y)
```

es literalmente el número de píxeles encendidos. Es decir, contar píxeles y
calcular `m00` es la misma operación. Los momentos de orden superior (`m10`,
`m01`, `mu20`, `mu02`, `mu11`) y los invariantes de Hu se usan además para
describir la *forma* de la marca y así poder decir qué tipo de defecto tiene.

### La regla de llenado

Para cada burbuja se calcula `pintado = m00 − línea base del grupo`, que es la
fracción del círculo que puso el alumno. La línea base es el percentil 30 de las
5 alternativas de esa pregunta: representa cómo se ve una burbuja vacía *en esa
zona concreta* de la hoja, con su iluminación.

| `pintado` | Diagnóstico | Qué pasa |
|---|---|---|
| ≥ 60 % | pintó más de lo que dejó en blanco | se acepta |
| 40 – 60 % | quedó a la mitad | se anula |
| 18 – 40 % | dejó en blanco más de lo que pintó | se anula |
| < 18 % | no hay marca | burbuja vacía |

Si hay dos o más alternativas marcadas, la pregunta se anula sin mirar la
calidad de ninguna.

Los cortes no los elegimos a ojo. Medimos las 1 500 burbujas de las primeras
fotos y el histograma sale claramente partido en dos: por debajo de 0.511 están
las marcas defectuosas y por encima de 0.711 los rellenos sólidos, sin nada en
medio. El umbral de 0.60 cae justo en ese hueco, con margen por los dos lados.

---

## Instalación

```bash
git clone https://github.com/IsmaelC0503/MultipleChoice-ExamGrader.git
cd MultipleChoice-ExamGrader
pip install -r requirements.txt
```

Necesita Python 3.9 o superior. En Linux, si falta Tkinter:
`sudo apt install python3-tk`.

## Uso

**Con la aplicación:**

```bash
python app.py
```

La primera pestaña tiene cuatro pasos numerados: carpeta de fotos, clave de
respuestas, padrón de alumnos y opciones. Cada uno avisa a la derecha si ya está
listo. Después, `CALIFICAR TODO`.

![Pasos numerados](docs/captura_pasos.png)

En la pestaña de Revisión están la lista de las 80 preguntas, la hoja calificada
y la lupa de cada pregunta con el porcentaje pintado de cada alternativa. Doble
clic en cualquier imagen abre un visor con zoom.

![Revisión hoja por hoja](docs/captura_revision.png)

**Por terminal:**

```bash
# sacar la clave de la hoja que resolvió el profesor
python main.py clave --hoja mis_datos/maestra.jpg --salida mis_datos/clave.json

# comprobar que las fotos sirven, antes de calificar
python main.py diagnostico --fotos mis_datos/fotos

# calificar el lote
python main.py calificar --fotos mis_datos/fotos \
                         --clave mis_datos/clave.json \
                         --padron mis_datos/alumnos.xlsx \
                         --examen "Final 2026"
```

**Desde Python:**

```python
from omr import procesar, cfg

r = procesar('foto.jpg', clave={1: 'B', 2: 'B'}, cfg=cfg)
print(r['codigo_leido'], r['resumen']['nota'])
```

---

## Dataset

No usamos ningún dataset público: la hoja de respuestas la diseñamos nosotros y
las fotos las rellenamos y tomamos nosotros. Todo está en `dataset/`.

| Archivo | Qué es |
|---|---|
| `fotos/` | 10 hojas rellenadas y fotografiadas |
| `clave.json` | la clave del examen |
| `alumnos.xlsx` | padrón de 20 alumnos ficticios |
| `FORMATO_EXAMEN.pdf` | la hoja en blanco, para imprimir |

La hoja es A4 y lleva 80 preguntas × 5 alternativas repartidas en 4 bloques de
20, la tabla del código universitario de 10 dígitos, el marco del borde, 3
rombos y 30 guiones por margen, y el recuadro de instrucciones de llenado.
`FORMATO_EXAMEN.pdf` es esa hoja en blanco: hay que imprimirla en A4 al 100 %,
sin "ajustar a la página", para que las proporciones se mantengan.

Los nombres y los códigos del padrón son **inventados**, y las hojas las
rellenamos nosotros. No hay datos de ningún alumno real.

Las fotos están tomadas con calidades distintas a propósito, unas con la cámara
al máximo y otras enviadas por WhatsApp, porque queríamos comprobar que la
detección aguanta las dos. Varias hojas llevan además marcas mal hechas puestas
adrede —medias lunas, aspas, puntos y dobles marcas— para verificar que la regla
de llenado las caza y anula la pregunta.

---

## Entorno de trabajo

| | |
|---|---|
| Sistema operativo | Windows 10 (64 bits) |
| Python | 3.12 |
| Editor | Visual Studio Code, con las extensiones Python y Jupyter |
| Tkinter | 8.6 (viene con Python) |
| Control de versiones | Git / GitHub |

También lo probamos en Ubuntu 24.04 y en Google Colab.

### Versiones de los paquetes

| Paquete | Versión | Para qué |
|---|---|---|
| `opencv-python-headless` | 4.13.0 | Hough, momentos, morfología, perspectiva |
| `numpy` | 2.4.4 | cálculo numérico |
| `pandas` | 3.0.2 | tablas de notas y lectura/escritura de Excel |
| `openpyxl` | 3.1.5 | motor de archivos `.xlsx` |
| `pillow` | 12.1.1 | mostrar las imágenes en la ventana |
| `matplotlib` | 3.10.8 | gráficos en el cuaderno de Colab |

Hay un script que imprime estas dos tablas con los valores de tu propia máquina:

```bash
python entorno.py
```

---

## Estructura del repositorio

```
MultipleChoice-ExamGrader/
│
├── app.py                    aplicación de escritorio
├── main.py                   línea de comandos
├── entorno.py                imprime las versiones instaladas
├── requirements.txt
│
├── omr/                      el algoritmo, un archivo por etapa
│   ├── config.py               parámetros del formato y de la regla
│   ├── perspectiva.py          encontrar la hoja y enderezarla
│   ├── marcadores.py           marcadores del margen y orientación
│   ├── grilla.py               Hough y construcción de la malla
│   ├── medicion.py             momentos (cv2.moments)
│   ├── decision.py             la regla de llenado
│   ├── pipeline.py             une todo: de la foto a la nota
│   ├── diagnostico.py          por qué falla una foto
│   └── basedatos.py            padrón y notas en Excel
│
├── tests/test_omr.py         pruebas automáticas
├── notebooks/                la misma interfaz, para Colab
├── docs/                     capturas de pantalla
├── dataset/                  las hojas de muestra y la clave
└── mis_datos/                exámenes reales (no se sube)
```

Cada módulo de `omr/` hace una sola cosa y se puede reutilizar por separado:
`perspectiva.py` sirve para enderezar cualquier documento, `grilla.py` para
localizar cualquier matriz de círculos, `medicion.py` para medir el llenado de
formas.

---

## Qué tan bien funciona

La métrica que usamos para saber si la localización sirve es el **enganche**:
cuántos de los 400 nodos de la malla caen encima de un círculo que Hough
realmente detectó. Si ese número es alto, la lectura está bien alineada.

| Origen de la foto | Resolución | Enganche | Código leído |
|---|---|---|---|
| Escáner / cámara 12 Mpx | 3072 × 4096 | 399/400 | correcto |
| Foto de celular por WhatsApp | 900 × 1600 | 400/400 | correcto |

Para comprobar que la decisión también es correcta, la comparamos contra una
segunda ruta independiente: elegir a secas la alternativa con mayor `m00`, sin
regla de calidad ni análisis de forma. **Coinciden en 80/80 preguntas** en todas
las hojas probadas.

Deformando las fotos a propósito, las diferencias respecto a la lectura original
(sobre 80 preguntas):

| Perturbación | Diferencias |
|---|---|
| Rotación +8°, −12° | 0–1 |
| Perspectiva fuerte | 0 |
| Foto oscura (×0.6) o clara (×1.35) | 0–1 |
| Desenfoque gaussiano de 13 px | 0 |
| Resolución al 40–60 % | 0 |
| Contraste muy bajo o desenfoque fuerte | falla con excepción |

Ese último caso es a propósito: cuando el programa no puede leer bien, lanza un
error en vez de inventar una nota. Preferimos repetir la foto a poner una
calificación mal.

Las pruebas se corren con:

```bash
python tests/test_omr.py
```

Verifican la regla de llenado, la clasificación de puntos y aspas, los ceros a
la izquierda de los códigos (Excel se los come), la búsqueda en el padrón cuando
un dígito sale ilegible, el procesamiento de las fotos, que girar la hoja 180° no
cambie el resultado, la verificación cruzada, y que el diagnóstico informe en
lugar de reventar ante una imagen inválida.

---

## Limitaciones

**El formato de hoja es fijo.** Las bandas donde se buscan las tablas están
medidas sobre nuestro diseño. Con otra hoja hay que reajustar `banda_codigo` y
`banda_respuestas` en `omr/config.py`.

**Resolución mínima.** Por debajo de unos 12 px de radio de burbuja la medición
deja de ser fiable. El diagnóstico avisa cuando eso pasa.

**El aspa no siempre se etiqueta como aspa.** Si una X cubre casi la mitad del
círculo, el programa la clasifica como "mitad". Anula igual, así que la decisión
es correcta, pero el motivo que reporta es menos preciso. El problema es que la
componente conexa mayor de un aspa es un trazo fino y sus descriptores se
solapan con los de una media luna.

**Fotos muy lavadas o muy movidas no se procesan.** Es la excepción que
mencionamos arriba.

**El brillo del grafito baja la medición.** Si la luz pega directa sobre el
lápiz, el reflejo hace que la burbuja parezca menos rellena de lo que está. Se
evita con luz difusa y sin flash.

**Una clave por lote.** Todas las fotos de una carpeta se califican contra la
misma clave, así que exámenes distintos van en carpetas separadas.

**No corrige fotos giradas 90°.** El giro de 180° sí lo detecta y lo arregla
solo, pero una foto tomada de lado no.

## Ideas pendientes

- Detectar el aspa por sus dos diagonales cruzadas, en vez de por la componente
  conexa mayor, para que el motivo del defecto se reporte bien.
- Corregir automáticamente las fotos giradas 90°.
- Un archivo de configuración para soportar varios formatos de hoja.
- Enviar las notas por correo usando la columna del padrón.

---

## Nota sobre privacidad

La carpeta `mis_datos/` está excluida en el `.gitignore` porque ahí van los
exámenes reales. No subimos al repositorio fotos de exámenes ni notas de
compañeros: los nombres y códigos que aparecen en `dataset/` son inventados y
las hojas las rellenamos nosotros.
