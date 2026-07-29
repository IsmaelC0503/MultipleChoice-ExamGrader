# Dataset

Hojas de respuestas rellenadas a mano para probar el calificador. Todo el
contenido es **ficticio**: los nombres y los códigos están inventados y las
hojas las rellené yo mismo. No hay datos de personas reales.

## Contenido

| Archivo | Qué es |
|---|---|
| `fotos/` | 10 hojas de respuestas rellenadas y fotografiadas |
| `clave.json` | clave de respuestas del examen |
| `alumnos.xlsx` | padrón de 20 alumnos ficticios (sección 2, grupo 5) |
| `FORMATO_EXAMEN.pdf` | el formato de hoja en blanco, para imprimir |

## La hoja de respuestas

Formato A4 diseñado específicamente para este sistema:

- 80 preguntas × 5 alternativas (A–E), repartidas en 4 bloques de 20.
- Tabla de código universitario de 10 dígitos × 10 valores.
- Marco rectangular en el borde, para recortar la hoja y corregir la perspectiva.
- 3 rombos y 30 guiones por margen, que delimitan las tablas y ubican las filas.
- Recuadro con las instrucciones de llenado correcto e incorrecto.

`FORMATO_EXAMEN.pdf` es ese formato en blanco. Imprímelo en A4 al 100 % (sin
"ajustar a la página") para que las proporciones se mantengan.

## La clave

Las 80 respuestas correctas son la alternativa **B**. Se eligió así para que
rellenar las hojas de prueba fuera rápido: se pinta la columna B de arriba abajo
y solo se cambian las preguntas que deben salir mal.

## Las fotos

Están tomadas con calidades distintas a propósito —unas con la cámara al máximo
y otras comprimidas por WhatsApp— para comprobar que la localización por Hough
aguanta tanto una imagen nítida como una degradada, que es el caso real.

Varias hojas llevan **marcas defectuosas puestas a propósito**: medias lunas,
aspas, puntos y dobles marcas. Sirven para verificar que la regla de llenado las
detecta y anula la pregunta en lugar de darlas por buenas.

## Cómo usarlo

Al abrir `app.py`, si `mis_datos/fotos/` está vacía la aplicación carga sola lo
que hay aquí. Basta con pulsar **CALIFICAR TODO**.

Desde la línea de comandos:

```bash
python main.py calificar --fotos dataset/fotos \
                         --clave dataset/clave.json \
                         --padron dataset/alumnos.xlsx \
                         --examen "Demostracion"
```

## Para usar tus propios exámenes

Pon tus fotos en `../mis_datos/fotos/`, tu padrón en `../mis_datos/alumnos.xlsx`
y cambia la carpeta del paso 1 en la aplicación. Esa carpeta está excluida por
`.gitignore` y no se sube al repositorio.

## Consejos para fotografiar

- La hoja **completa** dentro del encuadre, con el marco negro visible.
- Sobre una mesa de color distinto al papel.
- Luz difusa, **sin flash directo**: el grafito brilla y baja la medición.
- De frente. Algo de inclinación se corrige sola, pero no exageres.
