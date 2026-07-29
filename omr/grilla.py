"""Pasos 3 y 4: localizar las burbujas.

Metodo principal: Transformada de Hough (cv2.HoughCircles) y malla
derivada de los propios circulos. Metodo de respaldo: filas a partir
de los guiones del margen."""

import cv2
import numpy as np
from typing import Dict, Optional, Tuple

from .config import Config
from .marcadores import binarizar_tinta


def eje_regular(ys, n, tol_rel=0.25):
    """
    Reconstruye n posiciones equiespaciadas a partir de detecciones
    incompletas o contaminadas. OPTIMIZADO: sale en cuanto una rejilla
    explica TODAS las detecciones (caso normal), en vez de recorrer
    siempre el espacio completo.
    """
    ys = np.array(sorted(float(y) for y in ys))
    if len(ys) < 2:
        return None, 0
    lo, hi = ys.min(), ys.max()
    mejor, mejor_pts, listo = None, -1, False
    for i in range(len(ys)):
        if listo:
            break
        for j in range(i + 1, len(ys)):
            if listo:
                break
            for dk in range(1, n):
                paso = (ys[j] - ys[i]) / dk
                if paso <= 1:
                    continue
                tol = paso * tol_rel
                for o in range(n):
                    base = ys[i] - o * paso
                    if base < lo - paso or base + (n - 1) * paso > hi + paso:
                        continue
                    rej = base + np.arange(n) * paso
                    pts = int(np.count_nonzero(
                        np.abs(ys[:, None] - rej[None, :]).min(axis=1) <= tol))
                    if pts > mejor_pts:
                        mejor_pts, mejor = pts, rej
                        if pts == len(ys):
                            listo = True
                            break
    if mejor is None:
        return None, 0
    paso = mejor[1] - mejor[0]
    idx, val = [], []
    for y in ys:
        k = int(round((y - mejor[0]) / paso))
        if 0 <= k < n and abs(y - mejor[k]) <= paso * tol_rel:
            idx.append(k); val.append(y)
    if len(idx) >= 2:
        b, a = np.polyfit(idx, val, 1)
        mejor = np.array([a + b * k for k in range(n)])
    return list(mejor), mejor_pts


def filas_desde_guiones(marc: dict, cfg: Config) -> Dict[str, dict]:
    ys_izq = [p[1] for p in marc["guion"]["izq"]]
    ys_der = [p[1] for p in marc["guion"]["der"]]
    if len(ys_izq) < 6:
        raise RuntimeError("Casi no se ven los guiones del margen izquierdo.")

    res_der, pts_der = eje_regular(ys_der, cfg.por_bloque) if len(ys_der) >= 4 else (None, 0)

    if res_der is not None:
        paso = res_der[1] - res_der[0]
        y_ini = res_der[0] - paso * 0.6
        det_resp = [y for y in ys_izq if y >= y_ini]
        det_cod = [y for y in ys_izq if y < y_ini]
    else:
        grupos = _grupos_por_salto(ys_izq)
        if len(grupos) < 2:
            raise RuntimeError("No se distinguen los dos bloques de guiones.")
        det_cod, det_resp = grupos[0], grupos[-1]

    res_izq, pts_izq = eje_regular(det_resp, cfg.por_bloque)
    cod, pts_cod = eje_regular(det_cod, cfg.n_valores)
    if res_izq is None or cod is None:
        raise RuntimeError("No se pudieron reconstruir las filas.")
    if pts_izq < 0.5 * cfg.por_bloque or pts_cod < 0.5 * cfg.n_valores:
        raise RuntimeError("Demasiados guiones ilegibles para fiarse.")
    if res_der is None:
        res_der = res_izq

    x_izq = float(np.median([p[0] for p in marc["guion"]["izq"]]))
    x_der = float(np.median([p[0] for p in marc["guion"]["der"]])) if ys_der else x_izq
    return {
        "codigo": {"y": cod, "y_der": cod, "x_izq": x_izq, "x_der": x_der},
        "respuestas": {"y": res_izq, "y_der": res_der, "x_izq": x_izq, "x_der": x_der},
        "calidad": {"guiones_codigo": pts_cod, "guiones_respuestas": pts_izq,
                    "guiones_derecha": pts_der},
    }


def y_de_fila(info: dict, i: int, x: float) -> float:
    y1, y2 = info["y"][i], info["y_der"][i]
    x1, x2 = info["x_izq"], info["x_der"]
    if abs(x2 - x1) < 1e-6:
        return y1
    return y1 + (y2 - y1) * (x - x1) / (x2 - x1)


def paso_filas(info: dict) -> float:
    ys = info["y"]
    return (max(ys) - min(ys)) / max(len(ys) - 1, 1)


def region_tabla(hoja, marc, info, cfg: Config, ancho_fijo=False):
    """Solo se usa como respaldo, cuando la malla por Hough no alcanza."""
    H, W = hoja.shape[:2]
    margen = int(paso_filas(info) * 0.45)
    y0 = max(0, int(min(info["y"][0], info["y_der"][0]) - margen))
    y1 = min(H, int(max(info["y"][-1], info["y_der"][-1]) + margen))
    if ancho_fijo:
        x0 = int(W * cfg.franja * 0.75)
        return x0, y0, W - 2 * x0, y1 - y0
    b = binarizar_tinta(hoja)[y0:y1, :]
    cs, _ = cv2.findContours(b, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    mejor = None
    for c in cs:
        x, y, w, h = cv2.boundingRect(c)
        if w * h < 0.15 * (y1 - y0) * W or w > 0.95 * W:
            continue
        if mejor is None or w * h > mejor[2] * mejor[3]:
            mejor = (x, y, w, h)
    if mejor is None:
        x0 = int(W * cfg.franja * 1.6)
        return x0, y0, W - 2 * x0, y1 - y0
    x, y, w, h = mejor
    return x, y0 + y, w, h


def circulos_hough(gris, rect, n_filas, n_cols, cfg: Config, paso=None):
    x, y, w, h = rect
    if paso is None:
        paso = min(w / n_cols, h / n_filas)
    roi = cv2.GaussianBlur(gris[y:y + h, x:x + w], (5, 5), 1.4)
    objetivo = n_filas * n_cols
    mejor, dif = None, 10 ** 9
    for p2 in cfg.hough_param2:
        c = cv2.HoughCircles(roi, cv2.HOUGH_GRADIENT, dp=1,
                             minDist=int(paso * cfg.dist_min),
                             param1=cfg.hough_param1, param2=p2,
                             minRadius=int(paso * cfg.r_min),
                             maxRadius=int(paso * cfg.r_max))
        if c is None:
            continue
        k = len(c[0])
        if abs(k - objetivo) < dif:
            dif, mejor = abs(k - objetivo), c[0]
        if k == objetivo:
            break
    if mejor is None:
        raise RuntimeError("Hough no encontro circulos en la tabla.")
    return mejor, float(np.median(mejor[:, 2]))


def eje_por_picos(vals: np.ndarray, n: int, sigma: float = 3.0):
    if len(vals) < n:
        return None
    v0, v1 = float(np.min(vals)), float(np.max(vals))
    rango = v1 - v0
    if rango < n:
        return None
    largo = int(np.ceil(rango)) + 1
    hist = np.zeros(largo, np.float32)
    for v in vals:
        hist[int(round(v - v0))] += 1.0
    k = max(3, int(sigma * 6) | 1)
    hist = cv2.GaussianBlur(hist.reshape(-1, 1), (1, k), sigma).ravel()
    sep = max(3, int(rango / (n - 1) * 0.5))
    ext = np.concatenate([[0.0], hist, [0.0]])
    cand = [i - 1 for i in range(1, len(ext) - 1)
            if ext[i] >= ext[i - 1] and ext[i] > ext[i + 1]]
    cand.sort(key=lambda i: hist[i], reverse=True)
    picos = []
    for i in cand:
        if all(abs(i - p) >= sep for p in picos):
            picos.append(i)
        if len(picos) == n:
            break
    if len(picos) != n:
        return None
    ejes = []
    for p in sorted(picos):
        a, b = max(0, p - sep // 2), min(largo, p + sep // 2 + 1)
        wgt = hist[a:b]
        ejes.append(v0 + a + float(np.dot(np.arange(len(wgt)), wgt) / max(wgt.sum(), 1e-6)))
    return ejes


def banda_rect(hoja: np.ndarray, cfg: Config, banda: Tuple[float, float]):
    """Rectangulo de busqueda de una tabla, por posicion fija en la hoja."""
    H, W = hoja.shape[:2]
    x0 = int(W * cfg.franja * 0.75)
    a, b = banda
    return (x0, int(H * a), W - 2 * x0, int(H * (b - a)))


def malla_desde_circulos(circulos, n_filas, n_cols, radio):
    """
    Construye la malla usando SOLO los circulos que encontro Hough: las
    columnas de los picos del histograma de X y las filas de los picos de Y.

    Es el metodo principal porque no depende de los guiones del margen, que
    son marcas de 70-260 px y se pierden en fotos comprimidas de celular.

    Cada fila se ajusta ademas con una recta y = a + b*x sobre los circulos
    que le tocaron, asi absorbe cualquier inclinacion que quede tras enderezar.
    """
    xs = eje_por_picos(circulos[:, 0], n_cols)
    ys = eje_por_picos(circulos[:, 1], n_filas)
    if xs is None or ys is None:
        return None, 0
    xs, ys = np.asarray(xs, float), np.asarray(ys, float)
    idx = np.abs(circulos[:, 1][:, None] - ys[None, :]).argmin(1)
    tol = (ys[1] - ys[0]) * 0.45 if n_filas > 1 else 1e9

    centros = np.zeros((n_filas, n_cols, 2), np.float32)
    enganchados = 0
    for i in range(n_filas):
        sel = circulos[(idx == i) & (np.abs(circulos[:, 1] - ys[i]) <= tol)]
        if len(sel) >= 4:
            b, a = np.polyfit(sel[:, 0], sel[:, 1], 1)
            recta = lambda x, _a=a, _b=b: _a + _b * x
        else:
            recta = lambda x, _y=ys[i]: _y
        for j, cx in enumerate(xs):
            cy = recta(cx)
            centros[i, j] = (cx, cy)
            d = np.hypot(circulos[:, 0] - cx, circulos[:, 1] - cy)
            k = int(np.argmin(d))
            if d[k] <= radio * 0.6:
                centros[i, j] = circulos[k, :2]
                enganchados += 1
    return centros, enganchados


def construir_centros(circulos, rect, info, n_filas, n_cols, radio):
    x0, y0 = rect[0], rect[1]
    xs = eje_por_picos(circulos[:, 0], n_cols)
    if xs is None:
        raise RuntimeError(f"No se pudieron ubicar las {n_cols} columnas.")
    centros = np.zeros((n_filas, n_cols, 2), np.float32)
    enganchados = 0
    tope = radio * 0.6
    for i in range(n_filas):
        for j, cx in enumerate(xs):
            cy = y_de_fila(info, i, x0 + cx) - y0
            centros[i, j] = (cx, cy)
            d = np.hypot(circulos[:, 0] - cx, circulos[:, 1] - cy)
            k = int(np.argmin(d))
            if d[k] <= tope:
                centros[i, j] = circulos[k, :2]
                enganchados += 1
    return centros, enganchados
