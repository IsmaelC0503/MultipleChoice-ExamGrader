"""Paso 5: medir cada burbuja con momentos espaciales (cv2.moments).

El momento de orden cero m00 de una imagen binaria ES el conteo de
pixeles encendidos: por eso "conteo de pixeles" y "momentos" son aqui
la misma operacion."""

import cv2
import numpy as np

from .config import Config


def binarizar_medida(hoja: np.ndarray, cfg: Config) -> np.ndarray:
    g = cv2.cvtColor(hoja, cv2.COLOR_BGR2GRAY)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (cfg.kernel_fondo, cfg.kernel_fondo))
    fondo = cv2.morphologyEx(g, cv2.MORPH_CLOSE, k)
    norm = cv2.divide(g, fondo, scale=255)
    _, b = cv2.threshold(norm, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return b


def _mascaras(radio, lado):
    m = lado // 2
    yy, xx = np.mgrid[0:lado, 0:lado]
    rad = np.hypot(xx - m, yy - m) / radio
    return {'m': m,
            'disco':  (rad <= 0.88).astype(np.uint8) * 255,
            'nucleo': (rad <= 0.45).astype(np.uint8) * 255,
            'afuera': ((rad >= 1.15) & (rad <= 1.60)).astype(np.uint8) * 255}


def medir_burbujas(binaria, rect, centros, radio, grupos, cfg: Config):
    """
    UNA sola pasada de medicion. Todo sale de cv2.moments.

      llenado  = m00 dentro del disco util / area del disco
                 -> el CONTEO DE PIXELES puro. Es lo que decide la lectura.
      nucleo   = m00 del residuo dentro del 45% central / area del nucleo
                 -> confirma que la tinta esta cerca del centro (marca real)
      centroide, momentos centrales y solidez -> solo para EXPLICAR el defecto

    El residuo (burbuja menos plantilla del grupo) ya no decide nada: se usa
    para nombrar el defecto y para el chequeo de nucleo. Asi las variaciones
    de plantilla no pueden cambiar una nota.
    """
    lado = int(round(radio * 1.9)) * 2 + 1
    K = _mascaras(radio, lado)
    m = K['m']
    aD = cv2.moments(K['disco'], binaryImage=True)['m00']
    aN = cv2.moments(K['nucleo'], binaryImage=True)['m00']
    aF = cv2.moments(K['afuera'], binaryImage=True)['m00']

    r_med = max(4, int(radio * cfg.r_medida))
    disco_med = np.zeros((2 * r_med + 1, 2 * r_med + 1), np.uint8)
    cv2.circle(disco_med, (r_med, r_med), r_med, 255, -1)
    aMed = float(cv2.countNonZero(disco_med))

    x0, y0 = rect[0], rect[1]
    H, W = binaria.shape[:2]
    nf, nc = centros.shape[:2]
    cubo = np.zeros((nf, nc, lado, lado), np.uint8)
    llenado = np.zeros((nf, nc), np.float32)

    for i in range(nf):
        for j in range(nc):
            cx, cy = centros[i, j]
            X, Y = int(round(x0 + cx)), int(round(y0 + cy))
            if m <= X < W - m and m <= Y < H - m:
                cubo[i, j] = binaria[Y - m:Y + m + 1, X - m:X + m + 1]
            if r_med <= X < W - r_med and r_med <= Y < H - r_med:
                parche = cv2.bitwise_and(
                    binaria[Y - r_med:Y + r_med + 1, X - r_med:X + r_med + 1], disco_med)
                llenado[i, j] = cv2.moments(parche, binaryImage=True)['m00'] / aMed

    # plantilla por grupo de burbujas con el mismo simbolo impreso
    grupos = np.asarray(grupos)
    plant = {}
    for g in sorted(set(int(v) for v in grupos.ravel())):
        plant[g] = (np.percentile(cubo[grupos == g].astype(np.float32), 30, axis=0)
                    > 127).astype(np.uint8) * 255

    ABRIR = np.ones((3, 3), np.uint8)
    forma = np.empty((nf, nc), dtype=object)
    for i in range(nf):
        for j in range(nc):
            g = int(grupos[i, j])
            p = cubo[i, j]
            residuo = cv2.morphologyEx(cv2.bitwise_and(p, cv2.bitwise_not(plant[g])),
                                       cv2.MORPH_OPEN, ABRIR)
            dentro = cv2.bitwise_and(residuo, K['disco'])
            n, lab, st, _ = cv2.connectedComponentsWithStats(dentro, 8)
            if n > 1:
                k = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
                marca = ((lab == k).astype(np.uint8)) * 255
            else:
                marca = np.zeros_like(dentro)

            M = cv2.moments(marca, binaryImage=True)
            a = M['m00']
            d = {'llenado': float(llenado[i, j]),
                 'nucleo': cv2.moments(cv2.bitwise_and(marca, K['nucleo']),
                                       binaryImage=True)['m00'] / aN,
                 'desborde': cv2.moments(cv2.bitwise_and(residuo, K['afuera']),
                                         binaryImage=True)['m00'] / aF,
                 'area': a / aD}
            if a > 0:
                gx, gy = M['m10'] / a, M['m01'] / a
                d['desplazamiento'] = float(np.hypot(gx - m, gy - m) / radio)
                mu20, mu02, mu11 = M['mu20'] / a, M['mu02'] / a, M['mu11'] / a
                rz = np.sqrt(max((mu20 - mu02) ** 2 + 4 * mu11 ** 2, 0.0))
                l1, l2 = (mu20 + mu02 + rz) / 2, (mu20 + mu02 - rz) / 2
                d['elongacion'] = float(np.sqrt(l1 / max(l2, 1e-9)))
                d['dispersion'] = float(np.sqrt(mu20 + mu02) / radio)
                d['hu1'] = float(cv2.HuMoments(M).ravel()[0])
                cs, _ = cv2.findContours(marca, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                if cs:
                    ac = cv2.contourArea(cs[0])
                    ah = cv2.contourArea(cv2.convexHull(cs[0]))
                    d['solidez'] = float(ac / ah) if ah > 0 else 0.0
                else:
                    d['solidez'] = 0.0
            else:
                d.update(desplazamiento=0.0, elongacion=0.0, dispersion=0.0,
                         hu1=0.0, solidez=0.0)
            forma[i, j] = d
    return llenado, forma
