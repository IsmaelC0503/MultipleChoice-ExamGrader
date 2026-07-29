"""Parametros del formato de hoja y de la regla de llenado."""

from dataclasses import dataclass
from typing import Tuple


OPCIONES = 'ABCDE'


@dataclass
class Config:
    # lienzo al que se endereza la hoja (proporcion A4)
    ancho: int = 1700
    alto: int = 2404
    aspecto: float = 1.414
    tol_aspecto: float = 0.25

    # estructura de la hoja
    n_preguntas: int = 80
    n_opciones: int = 5
    n_bloques: int = 4
    por_bloque: int = 20
    n_digitos: int = 10
    n_valores: int = 10

    # marcadores impresos
    franja: float = 0.045
    rombo_area: Tuple[int, int] = (400, 1400)
    rombo_ext: Tuple[float, float] = (0.38, 0.68)
    guion_area: Tuple[int, int] = (70, 260)
    guion_rel: Tuple[float, float] = (1.4, 3.2)

    # bandas donde vive cada tabla, en fraccion de la altura de la hoja ya
    # enderezada. Medido sobre 6 fotos: el codigo ocupa 0.188-0.391 y las
    # respuestas 0.457-0.938, con un hueco vacio entre las dos.
    banda_codigo: Tuple[float, float] = (0.15, 0.42)
    banda_respuestas: Tuple[float, float] = (0.43, 0.98)
    enganche_minimo: float = 0.85     # por debajo se prueba el metodo de guiones

    # transformada de Hough (fracciones del paso de la grilla)
    hough_param1: int = 100
    hough_param2: Tuple[int, ...] = (22, 24, 20, 26, 18, 28, 30)
    r_min: float = 0.24
    r_max: float = 0.48
    dist_min: float = 0.70

    # medicion
    kernel_fondo: int = 81
    r_medida: float = 0.72

    # ---------------- REGLA DE LLENADO (lo que se pinta vs lo que no) -------
    # 'relleno' = m00 de la burbuja menos la linea base del grupo.
    # Calibrado sobre 1500 burbujas de 3 hojas reales: hueco natural
    # entre 0.511 (peor marca defectuosa) y 0.711 (mejor relleno solido).
    umbral_marca: float = 0.18     # por debajo no hay marca del alumno
    umbral_nucleo: float = 0.03    # ademas debe haber tinta cerca del centro
    umbral_acepta: float = 0.60    # pintado claramente > no pintado -> VALIDA
    umbral_mitad: float = 0.40     # entre 0.40 y 0.60 -> esta a la mitad -> ANULA
    base_pct: float = 30.0         # percentil que define "burbuja vacia"

    # subtipos de marca defectuosa (solo para explicar el motivo)
    punto_solidez: float = 0.80
    punto_desplaz: float = 0.20
    punto_dispersion: float = 0.30
    aspa_dispersion: float = 0.35
    luna_desplaz: float = 0.25
    desborde_aviso: float = 0.55

    # puntaje
    puntos: float = 1.0
    penalidad: float = 0.0
    nota_maxima: float = 20.0
    anular_defectuosas: bool = True


cfg = Config()


ETIQUETAS = {
    'valida':       'relleno correcto',
    'mitad':        'pintado aproximadamente la mitad',
    'punto':        'solo un punto, sin rellenar',
    'aspa':         'aspa (X) en vez de relleno',
    'media_luna':   'pintado solo de un lado',
    'insuficiente': 'relleno insuficiente',
    'vacia':        '',
}


DEFECTOS = ('mitad', 'punto', 'aspa', 'media_luna', 'insuficiente')
