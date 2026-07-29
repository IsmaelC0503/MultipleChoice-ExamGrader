"""Diagnostico: por que falla una foto y que hacer al respecto."""

import glob
import os
import cv2
import numpy as np
import pandas as pd

from .config import Config, cfg
from .perspectiva import detectar_marco, enderezar
from .marcadores import orientacion_correcta, orientar
from .grilla import circulos_hough, filas_desde_guiones
from .pipeline import _tabla_desde_hough, procesar


ETAPAS = ['marco', 'orientacion', 'guiones', 'hough_codigo', 'malla_codigo',
          'hough_respuestas', 'malla_respuestas', 'lectura']


def diagnosticar(ruta, cfg: Config, verbose=True) -> dict:
    """
    Recorre el proceso etapa por etapa y dice exactamente donde se rompe.
    No lanza excepciones: devuelve un informe.
    """
    d = {'archivo': os.path.basename(ruta) if isinstance(ruta, str) else 'imagen',
         'fallo_en': None}
    img = cv2.imread(ruta) if isinstance(ruta, str) else ruta
    if img is None:
        d['fallo_en'] = 'lectura del archivo'
        d['veredicto'] = 'No se pudo abrir el archivo. Revisa la ruta y el formato.'
        return d
    d['resolucion'] = f'{img.shape[1]}x{img.shape[0]}'
    d['megapixeles'] = round(img.shape[0] * img.shape[1] / 1e6, 1)

    # --- marco --------------------------------------------------------
    try:
        quad = detectar_marco(img, cfg)
        w = np.linalg.norm(quad[1] - quad[0])
        h = np.linalg.norm(quad[3] - quad[0])
        d['marco'] = 'OK'
        d['marco_px'] = f'{w:.0f}x{h:.0f}'
        d['marco_aspecto'] = round(max(w, h) / max(min(w, h), 1), 3)
        d['hoja_ocupa_%'] = round(100 * (w * h) / (img.shape[0] * img.shape[1]), 1)
    except Exception as e:
        d['marco'] = f'FALLA: {e}'
        d['fallo_en'] = 'marco'
        d['veredicto'] = _veredicto(d)
        if verbose:
            for k, v in d.items():
                print(f'  {k:24} {v}')
        return d

    hoja = enderezar(img, quad, cfg)

    # --- orientacion --------------------------------------------------
    hoja, marc, girada, dudosa = orientar(hoja, cfg)
    _, razon = orientacion_correcta(hoja, cfg)
    d['orientacion'] = 'DUDOSA' if dudosa else ('girada 180' if girada else 'OK')
    d['orientacion_razon'] = round(razon, 2)

    # --- guiones (ya solo son respaldo) --------------------------------
    d['guiones_izq'] = len(marc['guion']['izq'])
    d['guiones_der'] = len(marc['guion']['der'])
    d['rombos'] = len(marc['rombo']['izq']) + len(marc['rombo']['der'])
    try:
        info = filas_desde_guiones(marc, cfg)
        d['guiones'] = 'utilizables'
    except Exception as e:
        info = None
        d['guiones'] = f'no utilizables ({e})'

    # --- las dos tablas -----------------------------------------------
    gris = cv2.cvtColor(hoja, cv2.COLOR_BGR2GRAY)
    for nombre, nf, nc in (('codigo', cfg.n_valores, cfg.n_digitos),
                           ('respuestas', cfg.por_bloque,
                            cfg.n_bloques * cfg.n_opciones)):
        try:
            rect, circ, radio, cen, eng, met = _tabla_desde_hough(
                hoja, gris, cfg, nombre, nf, nc, info)
            d[f'{nombre}_circulos'] = f'{len(circ)} (se esperan {nf*nc})'
            d[f'{nombre}_radio_px'] = round(radio, 1)
            d[f'{nombre}_enganche'] = f'{eng}/{nf*nc} = {100*eng//(nf*nc)}%'
            d[f'{nombre}_metodo'] = met
            d[f'{nombre}_ok'] = eng >= cfg.enganche_minimo * nf * nc
        except Exception as e:
            d[f'{nombre}_enganche'] = f'FALLA: {e}'
            d[f'{nombre}_ok'] = False
            d['fallo_en'] = nombre

    if d.get('fallo_en') is None:
        try:
            r = procesar(img, None, cfg)
            d['codigo_leido'] = r['codigo_leido']
            d['respuestas_leidas'] = sum(1 for i in r['lectura'] if i['marcada'])
            d['en_blanco'] = sum(1 for i in r['lectura'] if not i['marcada'])
            d['a_revisar'] = len(r['incidencias'])
            d['lectura'] = 'OK'
        except Exception as e:
            d['lectura'] = f'FALLA: {e}'
            d['fallo_en'] = 'lectura'

    d['veredicto'] = _veredicto(d)
    if verbose:
        for k, v in d.items():
            print(f'  {k:24} {v}')
    return d


def _veredicto(d) -> str:
    """Traduce el informe a una recomendacion concreta."""
    if d.get('fallo_en') == 'marco':
        return ('No encuentro el marco impreso. Causas tipicas: la hoja sale '
                'cortada, hay poco contraste con la mesa, o la foto esta muy '
                'borrosa. Repite la foto con la hoja COMPLETA y sobre un fondo '
                'de color distinto al papel.')
    if d.get('marco_aspecto') and abs(d['marco_aspecto'] - cfg.aspecto) > 0.15:
        return (f"El marco detectado tiene aspecto {d['marco_aspecto']} y una A4 "
                f"es 1.414: probablemente agarro otra cosa (una mesa, un cuaderno). "
                f"Aisla la hoja del resto.")
    if d.get('hoja_ocupa_%', 100) < 25:
        return (f"La hoja ocupa solo el {d['hoja_ocupa_%']}% de la foto. Acercate: "
                f"con tan pocos pixeles por burbuja la medicion pierde precision.")
    if d.get('orientacion') == 'DUDOSA':
        return 'No puedo decidir la orientacion. Revisa que la foto no este de lado (90 grados).'
    malas = [n for n in ('codigo', 'respuestas') if not d.get(f'{n}_ok', True)]
    if malas:
        return (f"La malla de {' y '.join(malas)} no engancha con los circulos. "
                f"Suele ser foto borrosa o resolucion baja. Radio de burbuja "
                f"detectado: {d.get('respuestas_radio_px')} px (por debajo de 12 px "
                f"la lectura ya no es fiable).")
    if d.get('lectura', '').startswith('FALLA'):
        return 'Todo se localizo bien pero fallo la medicion. Revisa el mensaje.'
    return f"OK. Enganche {d.get('respuestas_enganche')}, metodo '{d.get('respuestas_metodo')}'."


def diagnosticar_carpeta(carpeta, cfg: Config) -> pd.DataFrame:
    """Diagnostico de TODAS las fotos de una carpeta, en una tabla."""
    pats = ('*.jpg', '*.jpeg', '*.png', '*.JPG', '*.JPEG', '*.PNG')
    fotos = sorted(sum([glob.glob(os.path.join(carpeta, p)) for p in pats], []))
    filas = []
    for f in fotos:
        d = diagnosticar(f, cfg, verbose=False)
        filas.append({'archivo': d['archivo'], 'resolucion': d.get('resolucion'),
                      'hoja_ocupa_%': d.get('hoja_ocupa_%'),
                      'radio_px': d.get('respuestas_radio_px'),
                      'enganche': d.get('respuestas_enganche'),
                      'metodo': d.get('respuestas_metodo'),
                      'guiones': f"{d.get('guiones_izq')}/{d.get('guiones_der')}",
                      'codigo': d.get('codigo_leido', '-'),
                      'estado': 'OK' if d['fallo_en'] is None else f"falla en {d['fallo_en']}",
                      'veredicto': d['veredicto']})
    return pd.DataFrame(filas)


def imagen_malla(ruta, cfg: Config, tabla='respuestas'):
    """
    Dibuja la malla sobre la hoja: en VERDE los nodos que engancharon con un
    circulo real de Hough y en ROJO los que se quedaron en su sitio teorico.
    Si ves rojo, la malla esta desalineada ahi.
    """
    r = procesar(ruta, None, cfg)
    img = r['hoja'].copy()
    x0, y0 = r[tabla]['rect'][0], r[tabla]['rect'][1]
    C = r[tabla]['centros']
    rad = int(r[tabla]['radio'])
    cv2.rectangle(img, (x0, y0), (x0 + r[tabla]['rect'][2], y0 + r[tabla]['rect'][3]),
                  (255, 0, 255), 3)
    gris = cv2.cvtColor(r['hoja'], cv2.COLOR_BGR2GRAY)
    circ, _ = circulos_hough(gris, r[tabla]['rect'],
                             C.shape[0], C.shape[1], cfg)
    for i in range(C.shape[0]):
        for j in range(C.shape[1]):
            cx, cy = C[i, j]
            d = np.hypot(circ[:, 0] - cx, circ[:, 1] - cy).min()
            col = (0, 180, 0) if d <= rad * 0.6 else (0, 0, 255)
            cv2.circle(img, (int(x0 + cx), int(y0 + cy)), rad, col, 2)
    return img
