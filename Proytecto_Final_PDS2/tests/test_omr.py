"""
Pruebas del calificador.

Se ejecutan con:      python -m pytest tests/ -v
o sin pytest:         python tests/test_omr.py

Necesitan al menos una foto en tests/fixtures/ (o en datos/fotos/).
"""

import glob
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from omr import cfg, procesar, diagnosticar
from omr.basedatos import _norm_codigo, buscar_alumno
from omr.decision import clasificar_marca

CARPETAS = ['tests/fixtures', 'datos/fotos']
FOTOS = sorted(sum([glob.glob(os.path.join(c, '*.jpg')) +
                    glob.glob(os.path.join(c, '*.jpeg')) for c in CARPETAS], []))


# ------------------------------------------------- pruebas que no usan fotos
def test_regla_de_llenado():
    """La regla: pintado > no pintado se acepta, a la mitad se anula."""
    forma = dict(solidez=0.7, desplazamiento=0.1, dispersion=0.5,
                 elongacion=1.2, desborde=0.0)
    assert clasificar_marca(0.85, forma, cfg) == 'valida'
    assert clasificar_marca(0.62, forma, cfg) == 'valida'
    assert clasificar_marca(0.50, forma, cfg) == 'mitad'
    assert clasificar_marca(0.42, forma, cfg) == 'mitad'
    assert clasificar_marca(0.30, forma, cfg) not in ('valida', 'mitad')
    print('  regla de llenado: OK')


def test_punto_y_aspa():
    punto = dict(solidez=0.95, desplazamiento=0.04, dispersion=0.16,
                 elongacion=1.3, desborde=0.0)
    aspa = dict(solidez=0.55, desplazamiento=0.30, dispersion=0.55,
                elongacion=2.0, desborde=0.1)
    assert clasificar_marca(0.19, punto, cfg) == 'punto'
    assert clasificar_marca(0.30, aspa, cfg) == 'aspa'
    print('  punto y aspa: OK')


def test_codigo_con_ceros_a_la_izquierda():
    """Excel guarda 0032022153 como numero y se come los ceros."""
    assert _norm_codigo(32022153) == '0032022153'
    assert _norm_codigo('0032022153') == '0032022153'
    assert _norm_codigo('32022153.0') == '0032022153'
    print('  ceros a la izquierda: OK')


def test_busqueda_en_padron():
    import pandas as pd
    padron = pd.DataFrame([
        {'codigo': '1332022038', 'apellidos_y_nombres': 'CASTILLO SULLON, ELMER',
         'escuela': '', 'seccion': '2', 'correo': ''},
        {'codigo': '1332022039', 'apellidos_y_nombres': 'CORDOVA MALCA, ISMAEL',
         'escuela': '', 'seccion': '2', 'correo': ''}])
    assert buscar_alumno(padron, '1332022038')[1] == 'exacto'
    assert buscar_alumno(padron, '1332022?38')[1] == 'aproximado'
    assert buscar_alumno(padron, '133202203?')[1] == 'ambiguo'   # encajan los dos
    assert buscar_alumno(padron, '9999999999')[1] == 'no_encontrado'
    print('  busqueda en padron: OK')


# ------------------------------------------------------ pruebas sobre fotos
def test_se_procesan_las_fotos():
    if not FOTOS:
        print('  (sin fotos de prueba, se omite)'); return
    for f in FOTOS:
        r = procesar(f, None, cfg)
        n = os.path.basename(f)
        assert len(r['codigo_leido']) == cfg.n_digitos, f'{n}: codigo raro'
        assert len(r['lectura']) == cfg.n_preguntas, f'{n}: faltan preguntas'
        enganche = r['respuestas']['enganche'] / r['respuestas']['total_nodos']
        assert enganche >= 0.95, f'{n}: enganche bajo ({enganche:.0%})'
        print(f"  {n[:40]:42} cod={r['codigo_leido']} enganche={enganche:.0%}")


def test_girar_180_no_cambia_la_lectura():
    if not FOTOS:
        print('  (sin fotos de prueba, se omite)'); return
    for f in FOTOS[:3]:
        img = cv2.imread(f)
        a = procesar(img, None, cfg)
        b = procesar(cv2.rotate(img, cv2.ROTATE_180), None, cfg)
        assert a['codigo_leido'] == b['codigo_leido'], f'{f}: codigo distinto al girar'
        dif = sum(1 for x, y in zip(a['cadena'], b['cadena']) if x != y)
        assert dif <= 1, f'{f}: {dif} diferencias al girar 180'
        print(f'  {os.path.basename(f)[:40]:42} girada 180 -> {dif} diferencia(s)')


def test_verificacion_cruzada():
    """La regla completa debe coincidir con elegir el maximo m00 a secas."""
    if not FOTOS:
        print('  (sin fotos de prueba, se omite)'); return
    from omr import OPCIONES
    for f in FOTOS:
        r = procesar(f, None, cfg)
        L = r['respuestas']['llenado']
        malos = []
        for it in r['lectura']:
            n = it['pregunta'] - 1
            b, fi = n // cfg.por_bloque, n % cfg.por_bloque
            v = L[fi, b * cfg.n_opciones:(b + 1) * cfg.n_opciones]
            k = int(np.argmax(v))
            simple = (OPCIONES[k]
                      if v[k] - np.percentile(v, cfg.base_pct) >= cfg.umbral_marca
                      else None)
            if simple != it['marcada'] and it['estado'] != 'doble':
                malos.append(it['pregunta'])
        assert not malos, f'{os.path.basename(f)}: discrepan {malos}'
        print(f'  {os.path.basename(f)[:40]:42} 80/80 coinciden')


def test_diagnostico_no_lanza_excepciones():
    """Ante una imagen basura debe informar, no reventar."""
    basura = np.full((600, 400, 3), 200, np.uint8)
    d = diagnosticar(basura, cfg, verbose=False)
    assert d['fallo_en'] is not None
    assert 'veredicto' in d
    print(f"  imagen invalida -> falla en '{d['fallo_en']}': OK")


if __name__ == '__main__':
    pruebas = [v for k, v in sorted(globals().items()) if k.startswith('test_')]
    print(f'{len(pruebas)} pruebas, {len(FOTOS)} foto(s) disponibles\n')
    fallos = 0
    for p in pruebas:
        print(f'{p.__name__}:')
        try:
            p()
        except AssertionError as e:
            fallos += 1
            print(f'  FALLO: {e}')
        print()
    print(f'{len(pruebas) - fallos}/{len(pruebas)} pruebas OK')
    sys.exit(1 if fallos else 0)
