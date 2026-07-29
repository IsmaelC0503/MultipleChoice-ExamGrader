"""Une todos los pasos: de la foto a la nota."""

import os
import cv2
import numpy as np
from typing import Dict, Optional

from .config import Config, OPCIONES, DEFECTOS
from .perspectiva import detectar_marco, enderezar
from .marcadores import orientar
from .grilla import (banda_rect, circulos_hough, construir_centros,
                     filas_desde_guiones, malla_desde_circulos,
                     paso_filas, region_tabla)
from .medicion import binarizar_medida, medir_burbujas
from .decision import calificar, leer_codigo, leer_respuestas


def _tabla_desde_hough(hoja, gris, cfg, nombre, nf, nc, info):
    """
    Localiza una tabla y devuelve (rect, circulos, radio, centros, enganche,
    metodo). Primero prueba la malla derivada de los propios circulos; si
    engancha poco, cae al metodo antiguo basado en los guiones del margen.
    """
    banda = cfg.banda_codigo if nombre == 'codigo' else cfg.banda_respuestas
    rect = banda_rect(hoja, cfg, banda)
    circulos, radio = circulos_hough(gris, rect, nf, nc, cfg)
    centros, enganche = malla_desde_circulos(circulos, nf, nc, radio)
    metodo = 'hough'

    if centros is None or enganche < cfg.enganche_minimo * nf * nc:
        if info is not None:                      # respaldo: guiones del margen
            try:
                fijo = (nombre == 'respuestas')
                r2 = region_tabla(hoja, None, info[nombre], cfg, ancho_fijo=fijo)
                paso = paso_filas(info[nombre]) if fijo else None
                c2, rad2 = circulos_hough(gris, r2, nf, nc, cfg, paso)
                cen2, eng2 = construir_centros(c2, r2, info[nombre], nf, nc, rad2)
                if centros is None or eng2 > enganche:
                    return r2, c2, rad2, cen2, eng2, 'guiones'
            except Exception:
                pass
        if centros is None:
            raise RuntimeError(f'No se pudo armar la malla de {nombre}.')
    return rect, circulos, radio, centros, enganche, metodo


def procesar(ruta, clave, cfg: Config, anular=None) -> dict:
    if anular is None:
        anular = cfg.anular_defectuosas
    img = cv2.imread(ruta) if isinstance(ruta, str) else ruta
    if img is None:
        raise RuntimeError(f'No se pudo abrir la imagen: {ruta}')

    hoja = enderezar(img, detectar_marco(img, cfg), cfg)
    hoja, marcadores, girada, dudosa = orientar(hoja, cfg)

    # los guiones ya no mandan: solo sirven de respaldo y de diagnostico
    try:
        info = filas_desde_guiones(marcadores, cfg)
        calidad = dict(info['calidad'])
    except Exception as e:
        info, calidad = None, {'guiones': f'no utilizables ({e})'}

    gris = cv2.cvtColor(hoja, cv2.COLOR_BGR2GRAY)
    binaria = binarizar_medida(hoja, cfg)

    r = {'archivo': os.path.basename(ruta) if isinstance(ruta, str) else 'imagen',
         'ruta': ruta if isinstance(ruta, str) else None,
         'girada': girada, 'orientacion_dudosa': dudosa,
         'marcadores': marcadores, 'hoja': hoja, 'calidad': calidad}

    for nombre, nf, nc, grupos in (
            ('codigo', cfg.n_valores, cfg.n_digitos,
             np.tile(np.arange(10).reshape(-1, 1), (1, 10))),
            ('respuestas', cfg.por_bloque, cfg.n_bloques * cfg.n_opciones,
             np.tile(np.arange(20) % 5, (20, 1)))):
        rect, circ, radio, centros, enganche, metodo = _tabla_desde_hough(
            hoja, gris, cfg, nombre, nf, nc, info)
        llenado, formas = medir_burbujas(binaria, rect, centros, radio, grupos, cfg)
        r[nombre] = {'rect': rect, 'centros': centros, 'radio': radio,
                     'llenado': llenado, 'formas': formas,
                     'n_circulos': len(circ), 'enganche': enganche,
                     'total_nodos': nf * nc, 'metodo': metodo}

    r['codigo_leido'], r['avisos'], r['codigo_estados'] = leer_codigo(
        r['codigo']['llenado'], r['codigo']['formas'], cfg)
    r['lectura'] = leer_respuestas(r['respuestas']['llenado'],
                                   r['respuestas']['formas'], cfg)
    r['cadena'] = ''.join(i['marcada'] or '-' for i in r['lectura'])
    r['incidencias'] = [i for i in r['lectura']
                        if i['estado'] in ('doble',) + DEFECTOS or i['avisos']]
    r['revisar'] = [i['pregunta'] for i in r['incidencias']]
    r['resumen'] = calificar(r['lectura'], clave, cfg, anular) if clave else None
    return r


def clave_desde_hoja(ruta, cfg: Config) -> Dict[int, str]:
    """Lee una hoja MAESTRA (resuelta por el profesor) y la convierte en clave."""
    r = procesar(ruta, None, cfg, anular=False)
    clave, faltan = {}, []
    for it in r['lectura']:
        if it['marcada'] is None or it['estado'] == 'doble':
            faltan.append(it['pregunta'])
        else:
            clave[it['pregunta']] = it['marcada']
    return clave, faltan, r


def dibujar(r: dict, cfg: Config) -> np.ndarray:
    img = r['hoja'].copy()
    VERDE, ROJO, AMARILLO, AZUL = (0,170,0), (0,0,235), (0,190,235), (235,120,0)
    for lado in ('izq', 'der'):
        for cx, cy in r['marcadores']['guion'][lado]:
            cv2.circle(img, (int(cx), int(cy)), 7, (255, 0, 255), -1)
        for cx, cy in r['marcadores']['rombo'][lado]:
            cv2.circle(img, (int(cx), int(cy)), 15, (255, 0, 255), 3)

    x0, y0 = r['codigo']['rect'][0], r['codigo']['rect'][1]
    C, rad = r['codigo']['centros'], int(r['codigo']['radio'])
    for col, dig in enumerate(r['codigo_leido']):
        if dig.isdigit():
            cx, cy = C[int(dig), col]
            col_c = AZUL if r['codigo_estados'][col] == 'ok' else AMARILLO
            cv2.circle(img, (int(x0+cx), int(y0+cy)), rad, col_c, 3)

    x0, y0 = r['respuestas']['rect'][0], r['respuestas']['rect'][1]
    C, rad = r['respuestas']['centros'], int(r['respuestas']['radio'])
    for it in r['lectura']:
        n = it['pregunta'] - 1
        bloque, fila = n // cfg.por_bloque, n % cfg.por_bloque
        if it['marcada'] is None:
            cx, cy = C[fila, bloque * cfg.n_opciones]
            cv2.line(img, (int(x0+cx)-32, int(y0+cy)-14),
                          (int(x0+cx)-14, int(y0+cy)+14), (150,150,150), 3)
            continue
        col = bloque * cfg.n_opciones + OPCIONES.index(it['marcada'])
        cx, cy = C[fila, col]
        res = it.get('resultado')
        color = (VERDE if res == 'correcta' else ROJO if res == 'incorrecta'
                 else AMARILLO if it['estado'] != 'ok' else AZUL)
        cv2.circle(img, (int(x0+cx), int(y0+cy)), rad + 2, color, 3)
        if res == 'incorrecta' and it.get('correcta'):
            ccol = bloque * cfg.n_opciones + OPCIONES.index(it['correcta'])
            gx, gy = C[fila, ccol]
            cv2.circle(img, (int(x0+gx), int(y0+gy)), rad + 6, VERDE, 2)

    texto = f"CODIGO: {r['codigo_leido']}"
    if r.get('resumen'):
        s = r['resumen']
        texto += (f"   NOTA: {s['nota']:.2f}/{cfg.nota_maxima:.0f}"
                  f"   ({s['aciertos']} bien / {s['errores']} mal"
                  f" / {s['blancos']} blanco / {s['anuladas']} anuladas)")
    cv2.rectangle(img, (0, 0), (img.shape[1], 70), (255, 255, 255), -1)
    cv2.putText(img, texto, (25, 48), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0,0,0), 2, cv2.LINE_AA)
    return img


def recorte_pregunta(r, pregunta, cfg: Config, escala=3.0):
    """Recorte ampliado de una pregunta, para revisarla a ojo."""
    n = pregunta - 1
    b, fi = n // cfg.por_bloque, n % cfg.por_bloque
    C = r['respuestas']['centros']; rad = int(r['respuestas']['radio'])
    x0, y0 = r['respuestas']['rect'][0], r['respuestas']['rect'][1]
    cx1, _ = C[fi, b*cfg.n_opciones]; cx2, cy = C[fi, b*cfg.n_opciones+cfg.n_opciones-1]
    X1 = max(0, int(x0+cx1) - rad*3); X2 = min(r['hoja'].shape[1], int(x0+cx2) + rad*2)
    Y = int(y0+cy)
    crop = r['hoja'][max(0, Y-rad-8):Y+rad+8, X1:X2].copy()
    return cv2.resize(crop, None, fx=escala, fy=escala, interpolation=cv2.INTER_CUBIC)
