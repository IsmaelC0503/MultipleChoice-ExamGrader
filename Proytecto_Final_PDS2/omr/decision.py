"""Paso 6: decidir que alternativa marco el alumno y si la marca vale.

Regla: pintado = m00 - linea base del grupo.
  >= 0.60  se acepta   (pinto mas de lo que dejo en blanco)
  0.40-0.60 se anula   (quedo a la mitad)
  <  0.40  se anula    (dejo en blanco mas de lo que pinto)"""

import numpy as np
from typing import Dict, List

from .config import Config, OPCIONES, ETIQUETAS, DEFECTOS


def clasificar_marca(rel: float, d: dict, cfg: Config) -> str:
    """
    REGLA PEDIDA: se compara lo pintado contra lo no pintado.

        rel >= umbral_acepta (0.60)  ->  'valida'   (pintado > no pintado)
        umbral_mitad <= rel < 0.60   ->  'mitad'    (mitad y mitad) -> ANULA
        rel <  umbral_mitad (0.40)   ->  no pintado > pintado       -> ANULA

    Debajo del umbral de mitad se nombra el defecto con los momentos
    (punto, aspa grande, media luna) solo para el informe.
    """
    if rel >= cfg.umbral_acepta:
        return 'valida'
    if rel >= cfg.umbral_mitad:
        return 'mitad'
    if (rel < 0.25
            and d['solidez'] >= cfg.punto_solidez
            and d['desplazamiento'] < cfg.punto_desplaz
            and d['dispersion'] < cfg.punto_dispersion):
        return 'punto'
    if d['dispersion'] >= cfg.aspa_dispersion:
        return 'aspa'
    if d['desplazamiento'] >= cfg.luna_desplaz:
        return 'media_luna'
    return 'insuficiente'


def evaluar_grupo(llenado_grupo, formas_grupo, cfg: Config, etiquetas=OPCIONES):
    """
    Decide un grupo (las 5 alternativas de una pregunta, o los 10 digitos
    de una columna del codigo).

    Devuelve (indice, estado, detalle, relativos) con estado en
    'ok' | 'blanco' | 'doble' | <nombre del defecto>
    """
    v = np.asarray(llenado_grupo, np.float64)
    base = float(np.percentile(v, cfg.base_pct))
    rel = v - base                      # proporcion realmente pintada

    marcadas = [k for k in range(len(v))
                if rel[k] >= cfg.umbral_marca
                and formas_grupo[k]['nucleo'] > cfg.umbral_nucleo]

    if not marcadas:
        return -1, 'blanco', [], rel

    if len(marcadas) > 1:
        k = max(marcadas, key=lambda z: rel[z])
        det = ', '.join(f"{etiquetas[z]} ({rel[z]:.0%} pintado)" for z in marcadas)
        return k, 'doble', [f'{len(marcadas)} alternativas marcadas: {det}'], rel

    k = marcadas[0]
    forma = clasificar_marca(float(rel[k]), formas_grupo[k], cfg)
    if forma == 'valida':
        avisos = []
        if formas_grupo[k]['desborde'] > cfg.desborde_aviso:
            avisos.append('el relleno se sale del circulo (aceptada igual)')
        return k, 'ok', avisos, rel
    return k, forma, [f'{ETIQUETAS[forma]} ({rel[k]:.0%} del circulo pintado)'], rel


def leer_codigo(llenado, formas, cfg: Config):
    """
    Misma regla que en las respuestas. Como un '?' en un codigo de alumno
    no sirve de nada, si la marca existe pero es defectuosa se devuelve el
    digito Y se avisa, en vez de perderlo.
    """
    digitos, avisos, estados = [], [], []
    for c in range(cfg.n_digitos):
        k, estado, det, rel = evaluar_grupo(llenado[:, c], [formas[i, c] for i in range(cfg.n_valores)],
                                            cfg, etiquetas='0123456789')
        estados.append(estado)
        if estado == 'blanco':
            digitos.append('?'); avisos.append(f'digito {c+1}: sin marcar')
        elif estado == 'doble':
            digitos.append('?'); avisos.append(f'digito {c+1}: {det[0] if det else "doble marca"}')
        else:
            digitos.append(str(k))
            if estado != 'ok':
                avisos.append(f'digito {c+1}: {det[0] if det else estado} '
                              f'-> se leyo {k}, conviene verificar')
    return ''.join(digitos), avisos, estados


def leer_respuestas(llenado, formas, cfg: Config) -> List[dict]:
    salida = []
    for bloque in range(cfg.n_bloques):
        for fila in range(cfg.por_bloque):
            cols = [bloque * cfg.n_opciones + k for k in range(cfg.n_opciones)]
            lg = [llenado[fila, c] for c in cols]
            fg = [formas[fila, c] for c in cols]
            k, estado, avisos, rel = evaluar_grupo(lg, fg, cfg)
            salida.append({
                'pregunta': bloque * cfg.por_bloque + fila + 1,
                'marcada': OPCIONES[k] if k >= 0 else None,
                'estado': estado,
                'avisos': avisos,
                'pintado': [round(float(x), 3) for x in rel],
                'pct': round(float(rel[k]), 3) if k >= 0 else 0.0,
            })
    salida.sort(key=lambda z: z['pregunta'])
    return salida


def calificar(lectura, clave: Dict[int, str], cfg: Config, anular=True) -> dict:
    aciertos = errores = blancos = anuladas = 0
    for it in lectura:
        correcta = clave.get(it['pregunta'])
        it['correcta'] = correcta
        if correcta is None:
            it['resultado'] = 'sin_clave'
            continue
        if it['estado'] == 'blanco':
            it['resultado'] = 'blanco'; blancos += 1
        elif it['estado'] == 'doble':
            it['resultado'] = 'anulada'; anuladas += 1
        elif anular and it['estado'] in DEFECTOS:
            it['resultado'] = 'anulada'; anuladas += 1
        elif it['marcada'] == correcta:
            it['resultado'] = 'correcta'; aciertos += 1
        else:
            it['resultado'] = 'incorrecta'; errores += 1
    total = len(clave)
    puntos = max(0.0, aciertos * cfg.puntos - errores * cfg.penalidad)
    nota = (puntos / (total * cfg.puntos)) * cfg.nota_maxima if total else 0.0
    return {'total': total, 'aciertos': aciertos, 'errores': errores,
            'blancos': blancos, 'anuladas': anuladas,
            'puntos': round(puntos, 2), 'nota': round(nota, 2)}
