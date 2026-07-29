"""
Calificador automatico de examenes de opcion multiple — linea de comandos.

Universidad Nacional de Piura · Procesamiento Digital de Senales 2

Ejemplos
--------
    # 1. sacar la clave de la hoja resuelta por el profesor
    python main.py clave --hoja dataset/maestra.jpg --salida dataset/clave.json

    # 2. revisar que las fotos sirvan ANTES de calificar
    python main.py diagnostico --fotos dataset/fotos

    # 3. calificar todo el lote
    python main.py calificar --fotos dataset/fotos --clave dataset/clave.json \
                             --padron dataset/alumnos.xlsx --examen "Final 2026"
"""

import argparse
import csv
import glob
import json
import os
import sys
from datetime import date

import cv2
import pandas as pd

from omr import (OPCIONES, cfg, clave_desde_hoja, dibujar, diagnosticar_carpeta,
                 procesar)
from omr.basedatos import cargar_padron, guardar_en_bd, acta

PATRONES = ('*.jpg', '*.jpeg', '*.png', '*.JPG', '*.JPEG', '*.PNG')


def listar_fotos(carpeta):
    """Lista las imagenes de una carpeta, sin repetidos.

    En Windows '*.jpeg' y '*.JPEG' encuentran los mismos archivos, asi que hay
    que filtrar o cada foto sale dos veces.
    """
    vistos, fotos = set(), []
    for patron in PATRONES:
        for ruta in glob.glob(os.path.join(carpeta, patron)):
            clave = os.path.normcase(os.path.abspath(ruta))
            if clave not in vistos:
                vistos.add(clave)
                fotos.append(ruta)
    if not fotos:
        sys.exit(f'No hay fotos en {carpeta}')
    return sorted(fotos)


def cargar_clave(ruta):
    with open(ruta, encoding='utf-8') as f:
        datos = json.load(f)
    clave = {int(k): str(v).strip().upper() for k, v in datos.items()}
    malas = [k for k, v in clave.items() if v not in OPCIONES]
    if malas:
        sys.exit(f'Alternativas invalidas en las preguntas: {malas}')
    return clave


# --------------------------------------------------------------- subcomandos
def cmd_clave(args):
    clave, faltan, _ = clave_desde_hoja(args.hoja, cfg)
    with open(args.salida, 'w', encoding='utf-8') as f:
        json.dump({str(k): v for k, v in sorted(clave.items())}, f,
                  indent=2, ensure_ascii=False)
    print(f'Clave con {len(clave)} respuestas guardada en {args.salida}')
    if faltan:
        print(f'ATENCION: sin resolver {faltan}. Completalas a mano en el JSON.')


def cmd_diagnostico(args):
    df = diagnosticar_carpeta(args.fotos, cfg)
    pd.set_option('display.width', 220)
    pd.set_option('display.max_colwidth', 30)
    print(df[['archivo', 'resolucion', 'hoja_ocupa_%', 'radio_px',
              'enganche', 'metodo', 'codigo', 'estado']].to_string(index=False))
    print()
    for a, v in zip(df['archivo'], df['veredicto']):
        print(f'{a}:')
        print(f'   {v}')
    malas = (df['estado'] != 'OK').sum()
    print(f'\n{len(df) - malas} de {len(df)} fotos utilizables.')
    return 0 if malas == 0 else 1


def cmd_calificar(args):
    os.makedirs(args.salida, exist_ok=True)
    clave = cargar_clave(args.clave) if args.clave else None
    padron = cargar_padron(args.padron) if args.padron else pd.DataFrame()
    if args.nota_maxima:
        cfg.nota_maxima = args.nota_maxima
    if args.penalidad:
        cfg.penalidad = args.penalidad
    cfg.anular_defectuosas = not args.no_anular

    fotos = listar_fotos(args.fotos)
    resultados, fallos = {}, []
    for i, ruta in enumerate(fotos, 1):
        nombre = os.path.basename(ruta)
        try:
            r = procesar(ruta, clave, cfg)
            resultados[ruta] = r
            cv2.imwrite(os.path.join(args.salida,
                                     os.path.splitext(nombre)[0] + '_calificado.png'),
                        dibujar(r, cfg))
            nota = f"{r['resumen']['nota']:>5}" if r['resumen'] else '  -  '
            print(f'[{i:>3}/{len(fotos)}] {nombre:45} cod={r["codigo_leido"]} '
                  f'nota={nota}  revisar={len(r["incidencias"])}')
        except Exception as e:
            fallos.append((nombre, str(e)))
            print(f'[{i:>3}/{len(fotos)}] {nombre:45} ERROR: {e}')

    if not resultados:
        sys.exit('No se pudo calificar ninguna hoja. Corre "diagnostico" para ver por que.')

    # CSV siempre
    destino = os.path.join(args.salida, 'notas.csv')
    with open(destino, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f, delimiter=';')
        w.writerow(['archivo', 'codigo', 'aciertos', 'errores', 'blancos',
                    'anuladas', 'nota', 'a_revisar', 'respuestas'])
        for ruta in sorted(resultados):
            r = resultados[ruta]
            s = r.get('resumen') or {}
            w.writerow([r['archivo'], r['codigo_leido'], s.get('aciertos', ''),
                        s.get('errores', ''), s.get('blancos', ''),
                        s.get('anuladas', ''), s.get('nota', ''),
                        len(r['incidencias']), r['cadena']])
    print(f'\nCSV: {destino}')

    # Excel solo si hay padron
    if not padron.empty:
        ruta_xlsx = os.path.join(args.salida, 'notas.xlsx')
        hojas = guardar_en_bd(resultados, padron, clave or {}, args.examen,
                              args.fecha, cfg, ruta=ruta_xlsx)
        print(f'Excel: {ruta_xlsx}  (' +
              ', '.join(f'{k}: {len(v)}' for k, v in hojas.items()) + ')')
        ruta_acta = os.path.join(args.salida, 'acta.xlsx')
        acta(resultados, padron, args.examen, args.fecha, cfg).to_excel(
            ruta_acta, index=False)
        print(f'Acta:  {ruta_acta}')

    total_rev = sum(len(r['incidencias']) for r in resultados.values())
    print(f'\n{len(resultados)} hoja(s) calificadas, {len(fallos)} con error, '
          f'{total_rev} marca(s) para revisar a ojo.')
    return 0 if not fallos else 1


# --------------------------------------------------------------------- main
def main(argv=None):
    p = argparse.ArgumentParser(
        prog='main.py',
        description='Calificador de examenes de opcion multiple '
                    '(Hough + momentos)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    sub = p.add_subparsers(dest='comando', required=True)

    c = sub.add_parser('calificar', help='califica todas las fotos de una carpeta')
    c.add_argument('--fotos', required=True, help='carpeta con las fotos')
    c.add_argument('--clave', help='JSON con la clave de respuestas')
    c.add_argument('--padron', help='alumnos.xlsx (para cruzar codigo con nombre)')
    c.add_argument('--salida', default='resultados', help='carpeta de salida')
    c.add_argument('--examen', default='Examen', help='nombre del examen')
    c.add_argument('--fecha', default=date.today().isoformat())
    c.add_argument('--nota-maxima', type=float, dest='nota_maxima')
    c.add_argument('--penalidad', type=float)
    c.add_argument('--no-anular', action='store_true',
                   help='no anular las marcas defectuosas, solo avisar')
    c.set_defaults(func=cmd_calificar)

    d = sub.add_parser('diagnostico', help='revisa si las fotos sirven')
    d.add_argument('--fotos', required=True)
    d.set_defaults(func=cmd_diagnostico)

    k = sub.add_parser('clave', help='saca la clave de una hoja resuelta')
    k.add_argument('--hoja', required=True, help='foto de la hoja maestra')
    k.add_argument('--salida', default='clave.json')
    k.set_defaults(func=cmd_clave)

    args = p.parse_args(argv)
    return args.func(args) or 0


if __name__ == '__main__':
    sys.exit(main())
