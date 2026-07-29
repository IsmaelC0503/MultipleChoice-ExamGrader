"""Paso 1: localizar el marco impreso y corregir la perspectiva.

Convierte la foto de celular en un "escaneo virtual" de 1700x2404 px,
siempre igual sin importar el angulo desde el que se tomo."""

import cv2
import numpy as np

from .config import Config


def ordenar_puntos(p) -> np.ndarray:
    p = np.asarray(p, np.float32).reshape(4, 2)
    s, d = p.sum(1), np.diff(p, axis=1).ravel()
    return np.array([p[np.argmin(s)], p[np.argmin(d)],
                     p[np.argmax(s)], p[np.argmax(d)]], np.float32)


def detectar_marco(img: np.ndarray, cfg: Config) -> np.ndarray:
    """Devuelve las 4 esquinas del marco impreso de la hoja."""
    h, w = img.shape[:2]
    esc = 1000.0 / max(h, w)
    ch = cv2.resize(img, None, fx=esc, fy=esc, interpolation=cv2.INTER_AREA)
    g = cv2.GaussianBlur(cv2.cvtColor(ch, cv2.COLOR_BGR2GRAY), (5, 5), 0)

    th = cv2.adaptiveThreshold(g, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY_INV, 51, 15)
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))

    contornos, _ = cv2.findContours(th, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    area_img = ch.shape[0] * ch.shape[1]
    mejor, mejor_area = None, -1.0

    for c in contornos:
        a = cv2.contourArea(c)
        if a < 0.15 * area_img or a > 0.95 * area_img:
            continue
        per = cv2.arcLength(c, True)
        for eps in (0.01, 0.02, 0.03, 0.04):
            ap = cv2.approxPolyDP(c, eps * per, True)
            if len(ap) != 4 or not cv2.isContourConvex(ap):
                continue
            q = ordenar_puntos(ap.reshape(4, 2))
            lw = max(np.linalg.norm(q[1] - q[0]), np.linalg.norm(q[2] - q[3]))
            lh = max(np.linalg.norm(q[3] - q[0]), np.linalg.norm(q[2] - q[1]))
            asp = max(lw, lh) / max(1.0, min(lw, lh))
            if abs(asp - cfg.aspecto) < cfg.tol_aspecto and a > mejor_area:
                mejor, mejor_area = q, a
                break          # CORREGIDO: solo se corta si el candidato sirve

    if mejor is None:
        raise RuntimeError('No se encontro el marco de la hoja. '
                           'Revisa que salga completa y con buena luz.')
    return mejor / esc


def enderezar(img: np.ndarray, quad: np.ndarray, cfg: Config) -> np.ndarray:
    destino = np.float32([[0, 0], [cfg.ancho - 1, 0],
                          [cfg.ancho - 1, cfg.alto - 1], [0, cfg.alto - 1]])
    M = cv2.getPerspectiveTransform(ordenar_puntos(quad), destino)
    return cv2.warpPerspective(img, M, (cfg.ancho, cfg.alto), flags=cv2.INTER_CUBIC)
