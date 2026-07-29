"""
Calificador automatico de examenes de opcion multiple
=====================================================

Transformada de Hough para localizar los circulos de respuesta y momentos
espaciales (conteo de pixeles) para determinar cual opcion fue marcada.

Universidad Nacional de Piura - Procesamiento Digital de Senales 2

Uso rapido
----------
    from omr import procesar, cfg

    r = procesar('foto.jpg', clave={1: 'A', 2: 'C'}, cfg=cfg)
    print(r['codigo_leido'], r['resumen']['nota'])
"""

__version__ = '5.0.0'

from .config import Config, cfg, OPCIONES, ETIQUETAS, DEFECTOS
from .pipeline import procesar, clave_desde_hoja, dibujar, recorte_pregunta
from .diagnostico import diagnosticar, diagnosticar_carpeta, imagen_malla
from .basedatos import (cargar_padron, buscar_alumno, guardar_en_bd, acta,
                        tabla_notas, analisis_preguntas)

__all__ = [
    'Config', 'cfg', 'OPCIONES', 'ETIQUETAS', 'DEFECTOS',
    'procesar', 'clave_desde_hoja', 'dibujar', 'recorte_pregunta',
    'diagnosticar', 'diagnosticar_carpeta', 'imagen_malla',
    'cargar_padron', 'buscar_alumno', 'guardar_en_bd', 'acta',
    'tabla_notas', 'analisis_preguntas',
]
