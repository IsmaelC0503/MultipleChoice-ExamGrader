"""Base de datos en Excel: padron de alumnos y notas acumuladas."""

import os
import numpy as np
import pandas as pd
from typing import Dict

from .config import Config, OPCIONES, cfg


NOMBRE_ALUMNOS = 'alumnos.xlsx'
NOMBRE_NOTAS = 'notas.xlsx'

COLS_ALUMNOS = ['codigo', 'apellidos_y_nombres', 'escuela', 'seccion', 'correo']


def _norm_codigo(c) -> str:
    """Deja el codigo como 10 caracteres. Excel se come los ceros a la
    izquierda si la celda es numerica, asi que se rellenan aqui."""
    s = str(c).strip().replace('.0', '') if c is not None else ''
    s = ''.join(ch for ch in s if ch.isdigit() or ch == '?')
    return s.rjust(cfg.n_digitos, '0') if s and len(s) < cfg.n_digitos else s


def crear_padron_ejemplo(ruta: str) -> pd.DataFrame:
    """Crea un alumnos.xlsx vacio con las columnas correctas y un ejemplo."""
    df = pd.DataFrame([{'codigo': '0000000000',
                        'apellidos_y_nombres': 'BORRA ESTA FILA Y PON A TUS ALUMNOS',
                        'escuela': 'Ing. de Telecomunicaciones',
                        'seccion': 'A', 'correo': ''}], columns=COLS_ALUMNOS)
    _escribir_excel(ruta, {'alumnos': df})
    return df


def cargar_padron(ruta: str) -> pd.DataFrame:
    """Lee el padron. Si no existe, crea la plantilla y devuelve vacio."""
    if not os.path.exists(ruta):
        crear_padron_ejemplo(ruta)
        print(f'No habia padron. Se creo la plantilla en:\n  {ruta}')
        print('Abrelo, pon a tus alumnos y vuelve a ejecutar esta celda.')
        return pd.DataFrame(columns=COLS_ALUMNOS)

    df = pd.read_excel(ruta, dtype=str).fillna('')
    df.columns = [str(c).strip().lower().replace(' ', '_') for c in df.columns]
    for c in COLS_ALUMNOS:
        if c not in df.columns:
            df[c] = ''
    df['codigo'] = df['codigo'].map(_norm_codigo)
    df = df[df['codigo'].str.len() == cfg.n_digitos].copy()
    df = df[~df['codigo'].str.startswith('0000000000')]
    dup = df['codigo'][df['codigo'].duplicated()].tolist()
    if dup:
        print(f'AVISO: codigos repetidos en el padron: {sorted(set(dup))}')
    return df[COLS_ALUMNOS].reset_index(drop=True)


def buscar_alumno(padron: pd.DataFrame, codigo: str):
    """
    Busca el codigo leido en el padron.

    Devuelve (fila, estado, sugerencias) con estado:
      'exacto'        el codigo esta tal cual en el padron
      'aproximado'    tenia digitos ilegibles (?) y solo un alumno encaja
      'ambiguo'       tenia ? y encajan varios
      'parecido'      no esta, pero hay alumnos a 1 digito de distancia
      'no_encontrado' ni eso
    """
    if padron.empty:
        return None, 'sin_padron', []
    cod = _norm_codigo(codigo)

    exacto = padron[padron['codigo'] == cod]
    if len(exacto) == 1:
        return exacto.iloc[0], 'exacto', []
    if len(exacto) > 1:
        return exacto.iloc[0], 'ambiguo', exacto['codigo'].tolist()

    if '?' in cod:                       # hay digitos que no se pudieron leer
        pos = [i for i, ch in enumerate(cod) if ch != '?']
        encajan = padron[padron['codigo'].map(
            lambda c: len(c) == len(cod) and all(c[i] == cod[i] for i in pos))]
        if len(encajan) == 1:
            return encajan.iloc[0], 'aproximado', []
        if len(encajan) > 1:
            return None, 'ambiguo', encajan['codigo'].tolist()[:6]

    # ni exacto ni con comodines: buscar a distancia de 1 digito
    def dist(c):
        return sum(1 for a, b in zip(c, cod) if a != b) if len(c) == len(cod) else 99
    d = padron['codigo'].map(dist)
    cerca = padron[d <= 1]
    if len(cerca):
        return None, 'parecido', cerca['codigo'].tolist()[:6]
    return None, 'no_encontrado', []


def _escribir_excel(ruta: str, hojas: Dict[str, pd.DataFrame]) -> None:
    """Escribe varias hojas y ajusta el ancho de las columnas."""
    with pd.ExcelWriter(ruta, engine='openpyxl') as xl:
        for nombre, df in hojas.items():
            df.to_excel(xl, sheet_name=nombre[:31], index=False)
            ws = xl.sheets[nombre[:31]]
            for i, col in enumerate(df.columns, start=1):
                ancho = max(len(str(col)),
                            *(len(str(v)) for v in df[col].head(300))) if len(df) else len(str(col))
                ws.column_dimensions[ws.cell(row=1, column=i).column_letter].width = min(ancho + 3, 60)
            ws.freeze_panes = 'A2'


def tabla_notas(resultados: dict, padron: pd.DataFrame, examen: str,
                fecha: str, cfg: Config) -> pd.DataFrame:
    """Una fila por hoja calificada, con el nombre del alumno pegado."""
    filas = []
    for ruta in sorted(resultados):
        r = resultados[ruta]
        s = r.get('resumen') or {}
        alu, estado, sug = buscar_alumno(padron, r['codigo_leido'])
        filas.append({
            'examen': examen, 'fecha': fecha,
            'codigo': _norm_codigo(r['codigo_leido']),
            'apellidos_y_nombres': (alu['apellidos_y_nombres'] if alu is not None else ''),
            'seccion': (alu['seccion'] if alu is not None else ''),
            'identificacion': estado,
            'nota': s.get('nota', ''), 'puntos': s.get('puntos', ''),
            'aciertos': s.get('aciertos', ''), 'errores': s.get('errores', ''),
            'blancos': s.get('blancos', ''), 'anuladas': s.get('anuladas', ''),
            'a_revisar': len(r['incidencias']),
            'preguntas_revisar': ', '.join(str(i['pregunta']) for i in r['incidencias']),
            'sugerencias_codigo': ', '.join(sug),
            'archivo': r['archivo'],
            'respuestas': r['cadena'],
        })
    return pd.DataFrame(filas)


def tabla_detalle(resultados: dict, examen: str, cfg: Config) -> pd.DataFrame:
    """Una fila por alumno y pregunta. Sirve para revisar caso por caso."""
    filas = []
    for ruta in sorted(resultados):
        r = resultados[ruta]
        for it in r['lectura']:
            filas.append({'examen': examen, 'codigo': _norm_codigo(r['codigo_leido']),
                          'pregunta': it['pregunta'], 'marcada': it['marcada'] or '',
                          'correcta': it.get('correcta') or '',
                          'resultado': it.get('resultado', ''),
                          'estado': it['estado'],
                          'pintado_%': round(it['pct'] * 100, 1),
                          'observacion': '; '.join(it['avisos'])})
    return pd.DataFrame(filas)


def analisis_preguntas(resultados: dict, clave: Dict[int, str],
                       examen: str, cfg: Config) -> pd.DataFrame:
    """
    Indice de dificultad por pregunta: que porcentaje de alumnos la acerto.
    Sirve para detectar preguntas mal formuladas o mal impresas.
    """
    if not resultados or not clave:
        return pd.DataFrame()
    filas = []
    n = len(resultados)
    for p in sorted(clave):
        bien = mal = blanco = anul = 0
        reparto = {k: 0 for k in OPCIONES}
        for r in resultados.values():
            it = r['lectura'][p - 1]
            if it['marcada']:
                reparto[it['marcada']] += 1
            res = it.get('resultado')
            bien += res == 'correcta'
            mal += res == 'incorrecta'
            blanco += res == 'blanco'
            anul += res == 'anulada'
        filas.append({'examen': examen, 'pregunta': p, 'clave': clave[p],
                      'aciertos': bien, 'errores': mal, 'blancos': blanco,
                      'anuladas': anul,
                      'dificultad_%': round(100 * bien / n, 1),
                      **{f'marcaron_{k}': reparto[k] for k in OPCIONES}})
    return pd.DataFrame(filas)


def guardar_en_bd(resultados: dict, padron: pd.DataFrame, clave: Dict[int, str],
                  examen: str, fecha: str, cfg: Config,
                  ruta: str = None) -> Dict[str, pd.DataFrame]:
    """
    Vuelca todo a notas.xlsx. Si el archivo ya existe, ACUMULA: conserva los
    examenes anteriores y reemplaza solo las filas de este mismo examen, para
    poder recalificar sin duplicar.
    """
    ruta = ruta or NOMBRE_NOTAS
    nuevas = {
        'Notas': tabla_notas(resultados, padron, examen, fecha, cfg),
        'Detalle': tabla_detalle(resultados, examen, cfg),
        'Preguntas': analisis_preguntas(resultados, clave, examen, cfg),
    }
    if os.path.exists(ruta):
        try:
            viejas = pd.read_excel(ruta, sheet_name=None, dtype=str)
        except Exception:
            viejas = {}
        for hoja, df in nuevas.items():
            ant = viejas.get(hoja)
            if ant is not None and not ant.empty and 'examen' in ant.columns:
                ant = ant[ant['examen'].astype(str) != str(examen)]
                nuevas[hoja] = pd.concat([ant, df.astype(str)], ignore_index=True)

    sin_id = nuevas['Notas']
    sin_id = sin_id[sin_id['identificacion'].astype(str) != 'exacto']
    nuevas['Sin_identificar'] = sin_id

    _escribir_excel(ruta, nuevas)
    return nuevas


def acta(resultados: dict, padron: pd.DataFrame, examen: str, fecha: str,
         cfg: Config) -> pd.DataFrame:
    """
    Acta del curso: TODOS los alumnos del padron, ordenados por apellido,
    con su nota o 'NO SE PRESENTO'. Es lo que se entrega firmado.
    """
    notas = tabla_notas(resultados, padron, examen, fecha, cfg)
    por_cod = {r['codigo']: r for _, r in notas.iterrows()}
    filas = []
    for _, a in padron.sort_values('apellidos_y_nombres').iterrows():
        r = por_cod.get(a['codigo'])
        filas.append({'codigo': a['codigo'],
                      'apellidos_y_nombres': a['apellidos_y_nombres'],
                      'seccion': a['seccion'],
                      'nota': (r['nota'] if r is not None else ''),
                      'observacion': ('' if r is not None else 'NO SE PRESENTO')})
    return pd.DataFrame(filas)
