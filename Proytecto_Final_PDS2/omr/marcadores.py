"""Paso 2: marcadores impresos del margen y orientacion de la hoja.

Desde la v5 los guiones son solo respaldo: en fotos comprimidas de
celular se pierden. La orientacion se decide por densidad de tinta."""

import cv2
import numpy as np
from typing import List, Sequence

from .config import Config


def binarizar_tinta(hoja: np.ndarray) -> np.ndarray:
    g = cv2.cvtColor(hoja, cv2.COLOR_BGR2GRAY)
    return cv2.adaptiveThreshold(cv2.GaussianBlur(g, (5, 5), 0), 255,
                                 cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                 cv2.THRESH_BINARY_INV, 41, 12)


def detectar_marcadores(hoja: np.ndarray, cfg: Config) -> dict:
    H, W = hoja.shape[:2]
    b = binarizar_tinta(hoja)
    ancho = int(W * cfg.franja)
    res = {'rombo': {'izq': [], 'der': []}, 'guion': {'izq': [], 'der': []}}

    for lado, x0 in (('izq', 0), ('der', W - ancho)):
        contornos, _ = cv2.findContours(b[:, x0:x0 + ancho],
                                        cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in contornos:
            x, y, w, h = cv2.boundingRect(c)
            if w == 0 or h == 0:
                continue
            a = cv2.contourArea(c)
            extension = a / (w * h)
            relacion = w / h
            cx, cy = x0 + x + w / 2.0, y + h / 2.0
            if (cfg.rombo_area[0] < a < cfg.rombo_area[1]
                    and cfg.rombo_ext[0] < extension < cfg.rombo_ext[1]
                    and 0.7 < relacion < 1.4):
                res['rombo'][lado].append((cx, cy))
            elif (cfg.guion_area[0] < a < cfg.guion_area[1]
                    and extension > 0.6
                    and cfg.guion_rel[0] < relacion < cfg.guion_rel[1]):
                res['guion'][lado].append((cx, cy))

    for tipo in res:
        for lado in res[tipo]:
            res[tipo][lado].sort(key=lambda p: p[1])
    return res


def _grupos_por_salto(ys: Sequence[float]) -> List[List[float]]:
    if len(ys) < 2:
        return [list(ys)]
    d = np.diff(ys)
    cortes = [i for i, v in enumerate(d) if v > 1.6 * np.median(d)]
    return [list(g) for g in np.split(np.asarray(ys), [c + 1 for c in cortes])]


def orientacion_correcta(hoja: np.ndarray, cfg: Config):
    """
    Test de orientacion sin depender de los guiones del margen.

    La tabla de respuestas (20x20 burbujas, ancho completo) tiene bastante
    mas tinta por unidad de area que la del codigo (10x10, media hoja). Se
    compara la densidad de las dos bandas: si la de abajo no gana, la foto
    esta al reves.

    Medido sobre 6 fotos y sus versiones giradas 180: la razon vale entre
    1.42 y 1.55 bien orientada, y entre 0.64 y 0.69 al reves. El corte en
    1.0 queda en medio del hueco. Al ser un cociente, no le afecta que la
    foto salga clara u oscura.

    Devuelve (correcta, razon).
    """
    b = binarizar_tinta(hoja)
    H, W = b.shape[:2]
    m = int(W * 0.06)

    def densidad(y0, y1):
        tira = b[int(H * y0):int(H * y1), m:W - m]
        return np.count_nonzero(tira) / max(tira.size, 1)

    d_cod = densidad(*cfg.banda_codigo)
    d_resp = densidad(*cfg.banda_respuestas)
    razon = d_resp / max(d_cod, 1e-6)
    return razon > 1.0, float(razon)


def orientar(hoja: np.ndarray, cfg: Config):
    """Gira 180 si hace falta. Devuelve (hoja, marcadores, girada, dudosa)."""
    ok, r1 = orientacion_correcta(hoja, cfg)
    if ok:
        return hoja, detectar_marcadores(hoja, cfg), False, False
    girada = cv2.rotate(hoja, cv2.ROTATE_180)
    ok2, r2 = orientacion_correcta(girada, cfg)
    if ok2:
        return girada, detectar_marcadores(girada, cfg), True, False
    # ninguna convence: se queda la que tenga mas tinta arriba, y se avisa
    if r2 > r1:
        return girada, detectar_marcadores(girada, cfg), True, True
    return hoja, detectar_marcadores(hoja, cfg), False, True
