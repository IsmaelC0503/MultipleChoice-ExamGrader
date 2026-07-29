"""
Interfaz de escritorio del calificador.

    python app.py

Toda la vision por computador esta en el paquete omr/. Aqui solo hay ventana:
elegir las carpetas, lanzar la calificacion, revisar hoja por hoja y exportar.

UNP - Procesamiento Digital de Senales 2
"""

import csv
import glob
import json
import os
import queue
import sys
import threading
import traceback
from datetime import date

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import cv2
import numpy as np
import pandas as pd
from PIL import Image, ImageTk

from omr import (DEFECTOS, OPCIONES, cfg, clave_desde_hoja, diagnosticar_carpeta,
                 dibujar, procesar, recorte_pregunta)
from omr.basedatos import (_escribir_excel, _norm_codigo, acta, buscar_alumno,
                           cargar_padron, guardar_en_bd, tabla_notas)
from omr.decision import calificar, leer_respuestas

PATRONES = ('*.jpg', '*.jpeg', '*.png', '*.JPG', '*.JPEG', '*.PNG')


def listar_fotos(carpeta):
    """Lista las imagenes de una carpeta, sin repetidos.

    En Windows '*.jpeg' y '*.JPEG' encuentran los mismos archivos, asi que hay
    que filtrar o cada foto sale dos veces.
    """
    vistos, salida = set(), []
    for patron in PATRONES:
        for ruta in glob.glob(os.path.join(carpeta, patron)):
            clave = os.path.normcase(os.path.abspath(ruta))
            if clave not in vistos:
                vistos.add(clave)
                salida.append(ruta)
    return sorted(salida)

AZUL = '#16324f'
AZUL_CLARO = '#2f7fb8'
VERDE = '#2c9e5d'
AMBAR = '#e0a02c'
ROJO = '#cf4257'
GRIS = '#f4f6f8'


def cv2_a_tk(img, ancho_max=900, alto_max=700):
    """Pasa una imagen de OpenCV al formato que entiende Tkinter."""
    h, w = img.shape[:2]
    esc = min(ancho_max / w, alto_max / h, 1.0)
    if esc < 1.0:
        img = cv2.resize(img, (int(w * esc), int(h * esc)),
                         interpolation=cv2.INTER_AREA)
    return ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)))


class MarcoScroll(ttk.Frame):
    """Marco con barra de desplazamiento. En pantallas de portatil el paso a
    paso no cabe entero y sin esto no habia forma de bajar."""

    def __init__(self, padre, **kw):
        super().__init__(padre, **kw)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        self.barra = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.barra.set)
        self.barra.pack(side='right', fill='y')
        self.canvas.pack(side='left', fill='both', expand=True)

        self.interior = ttk.Frame(self.canvas)
        self._ventana = self.canvas.create_window((0, 0), window=self.interior,
                                                  anchor='nw')
        self.interior.bind('<Configure>', self._al_cambiar_contenido)
        self.canvas.bind('<Configure>', self._al_cambiar_canvas)
        for w in (self.canvas, self.interior):
            w.bind('<Enter>', lambda e: self._rueda(True))
            w.bind('<Leave>', lambda e: self._rueda(False))

    def _al_cambiar_contenido(self, _=None):
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    def _al_cambiar_canvas(self, ev):
        self.canvas.itemconfigure(self._ventana, width=ev.width)

    def _rueda(self, activar):
        if activar:
            self.canvas.bind_all('<MouseWheel>', self._mover)
            self.canvas.bind_all('<Button-4>', self._mover)
            self.canvas.bind_all('<Button-5>', self._mover)
        else:
            for ev in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
                self.canvas.unbind_all(ev)

    def _mover(self, ev):
        if getattr(ev, 'num', None) == 4:
            paso = -1
        elif getattr(ev, 'num', None) == 5:
            paso = 1
        else:
            paso = -1 if ev.delta > 0 else 1
        self.canvas.yview_scroll(paso, 'units')


class VisorImagen(tk.Toplevel):
    """Ventana para ver una imagen en grande, con zoom y arrastre."""

    def __init__(self, padre, imagen_cv2, titulo='Imagen'):
        super().__init__(padre)
        self.title(titulo)
        self.geometry('1050x780')
        self.original = imagen_cv2
        self.zoom = 1.0
        self._tkimg = None

        bar = ttk.Frame(self, padding=6)
        bar.pack(fill='x')
        ttk.Button(bar, text='  −  ', command=lambda: self._zoom(1 / 1.25)).pack(side='left')
        ttk.Button(bar, text='  +  ', command=lambda: self._zoom(1.25)).pack(side='left', padx=4)
        ttk.Button(bar, text='Ajustar a la ventana', command=self._ajustar).pack(side='left', padx=8)
        ttk.Button(bar, text='Tamano real (100%)',
                   command=lambda: self._poner(1.0)).pack(side='left')
        self.lbl_zoom = ttk.Label(bar, text='100%')
        self.lbl_zoom.pack(side='left', padx=12)
        ttk.Label(bar, text='Arrastra con el raton para moverte  ·  '
                            'rueda del raton para acercar').pack(side='right')

        cont = ttk.Frame(self)
        cont.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(cont, background='#3a3a3a', highlightthickness=0)
        vs = ttk.Scrollbar(cont, orient='vertical', command=self.canvas.yview)
        hs = ttk.Scrollbar(cont, orient='horizontal', command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        vs.pack(side='right', fill='y')
        hs.pack(side='bottom', fill='x')
        self.canvas.pack(side='left', fill='both', expand=True)

        self.canvas.bind('<ButtonPress-1>', lambda e: self.canvas.scan_mark(e.x, e.y))
        self.canvas.bind('<B1-Motion>', lambda e: self.canvas.scan_dragto(e.x, e.y, gain=1))
        self.canvas.bind('<MouseWheel>',
                         lambda e: self._zoom(1.15 if e.delta > 0 else 1 / 1.15))
        self.canvas.bind('<Button-4>', lambda e: self._zoom(1.15))     # Linux
        self.canvas.bind('<Button-5>', lambda e: self._zoom(1 / 1.15))
        self.bind('<Escape>', lambda e: self.destroy())

        self.after(60, self._ajustar)

    def _ajustar(self):
        self.update_idletasks()
        h, w = self.original.shape[:2]
        cw = max(self.canvas.winfo_width(), 200)
        chh = max(self.canvas.winfo_height(), 200)
        self._poner(min(cw / w, chh / h))

    def _zoom(self, factor):
        self._poner(self.zoom * factor)

    def _poner(self, z):
        self.zoom = max(0.08, min(6.0, z))
        h, w = self.original.shape[:2]
        nw, nh = max(1, int(w * self.zoom)), max(1, int(h * self.zoom))
        interp = cv2.INTER_AREA if self.zoom < 1 else cv2.INTER_LINEAR
        img = cv2.resize(self.original, (nw, nh), interpolation=interp)
        self._tkimg = ImageTk.PhotoImage(
            Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)))
        self.canvas.delete('all')
        self.canvas.create_image(0, 0, anchor='nw', image=self._tkimg)
        self.canvas.configure(scrollregion=(0, 0, nw, nh))
        self.lbl_zoom.configure(text=f'{self.zoom:.0%}')


class App(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title('Calificador automático de exámenes de opción múltiple — UNP')
        # la ventana se ajusta al tamano de la pantalla
        pw, ph = self.winfo_screenwidth(), self.winfo_screenheight()
        ancho = min(1180, pw - 40)
        alto = min(820, ph - 90)
        self.geometry(f'{ancho}x{alto}+{max(0, (pw - ancho) // 2)}+10')
        self.minsize(900, 520)

        # ---- estado ----
        self.resultados = {}
        self.clave = {}
        self.padron = pd.DataFrame()
        self.cola = queue.Queue()
        self._ultimo_conteo = 0
        self._img_ref = None          # evita que el recolector borre la imagen
        self._img_ref2 = None

        # rutas relativas a este archivo, no al directorio desde donde se ejecuta
        raiz = os.path.dirname(os.path.abspath(__file__))
        self.var_fotos = tk.StringVar(value=os.path.join(raiz, 'dataset', 'fotos'))
        self.var_salida = tk.StringVar(value=os.path.join(raiz, 'resultados'))
        self.var_padron = tk.StringVar(value=os.path.join(raiz, 'dataset', 'alumnos.xlsx'))
        self.var_examen = tk.StringVar(value='Examen Final')
        self.var_fecha = tk.StringVar(value=date.today().isoformat())
        self.var_nota_max = tk.DoubleVar(value=cfg.nota_maxima)
        self.var_penalidad = tk.DoubleVar(value=cfg.penalidad)
        self.var_anular = tk.BooleanVar(value=cfg.anular_defectuosas)
        self.var_umbral = tk.DoubleVar(value=cfg.umbral_acepta)
        self.var_estado = tk.StringVar(value='Listo.')
        self.var_resumen_pasos = tk.StringVar(value='')
        self.var_clave_txt = tk.StringVar(value='')

        self._estilos()
        self._cabecera()
        self._barra_estado()
        self._barra_accion()
        self._pestanas()
        self.after(120, self._revisar_cola)

    # ------------------------------------------------------------- apariencia
    def _estilos(self):
        s = ttk.Style(self)
        try:
            s.theme_use('clam')
        except tk.TclError:
            pass
        s.configure('TNotebook.Tab', padding=(16, 8))
        s.configure('Treeview', rowheight=24)
        s.configure('Treeview.Heading', font=('TkDefaultFont', 9, 'bold'))
        s.configure('Titulo.TLabel', background=AZUL, foreground='white',
                    font=('TkDefaultFont', 14, 'bold'), padding=(14, 10))
        s.configure('Sub.TLabel', background=AZUL, foreground='#cfe0ee',
                    padding=(14, 0, 14, 10))
        s.configure('Accion.TButton', font=('TkDefaultFont', 10, 'bold'))

    def _cabecera(self):
        cab = tk.Frame(self, bg=AZUL)
        cab.pack(fill='x')
        ttk.Label(cab, text='Calificador automático de exámenes de opción múltiple',
          style='Titulo.TLabel').pack(anchor='w')
        ttk.Label(cab, text='Universidad Nacional de Piura   |   80 preguntas   |   '
                            'Hough para localizar + momentos para medir',
                  style='Sub.TLabel').pack(anchor='w')

    def _barra_estado(self):
        b = tk.Frame(self, bg=GRIS, height=26)
        b.pack(fill='x', side='bottom')
        tk.Label(b, textvariable=self.var_estado, bg=GRIS, anchor='w').pack(
            fill='x', padx=10, pady=3)

    def _barra_accion(self):
        """Barra de abajo. Va fija para que el boton de calificar no se pierda
        si la ventana queda corta."""
        b = tk.Frame(self, bg='#e8edf2')
        b.pack(fill='x', side='bottom')
        self.btn_calificar = ttk.Button(b, text='CALIFICAR TODO',
                                        style='Accion.TButton',
                                        command=self.procesar_lote)
        self.btn_calificar.pack(side='left', padx=12, pady=8, ipadx=14, ipady=3)
        self.barra = ttk.Progressbar(b, length=320, mode='determinate')
        self.barra.pack(side='left', padx=6)
        tk.Label(b, textvariable=self.var_resumen_pasos, bg='#e8edf2',
                 anchor='e').pack(side='right', padx=14)

    def _pestanas(self):
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill='both', expand=True, padx=10, pady=8)
        self.tab_inicio = ttk.Frame(self.nb)
        self.tab_result = ttk.Frame(self.nb)
        self.tab_revis = ttk.Frame(self.nb)
        self.tab_bd = ttk.Frame(self.nb)
        self.tab_diag = ttk.Frame(self.nb)
        for t, n in ((self.tab_inicio, '  1 · Preparar y calificar  '),
                     (self.tab_result, '  2 · Resultados  '),
                     (self.tab_revis, '  3 · Revision  '),
                     (self.tab_bd, '  4 · Base de datos  '),
                     (self.tab_diag, '  5 · Diagnostico  ')):
            self.nb.add(t, text=n)
        self._pest_inicio()
        self._pest_resultados()
        self._pest_revision()
        self._pest_bd()
        self._pest_diagnostico()

    # ------------------------------------------------------- 1. calificar
    def _paso(self, padre, num, titulo, ayuda=None):
        """Recuadro numerado de cada paso, con su indicador a la derecha."""
        caja = ttk.Frame(padre, padding=(0, 0, 0, 10))
        caja.pack(fill='x')
        cab = tk.Frame(caja, bg=GRIS)
        cab.pack(fill='x')
        tk.Label(cab, text=f' {num} ', bg=AZUL_CLARO, fg='white',
                 font=('TkDefaultFont', 11, 'bold')).pack(side='left', padx=(0, 8), pady=4)
        tk.Label(cab, text=titulo, bg=GRIS, font=('TkDefaultFont', 10, 'bold'),
                 anchor='w').pack(side='left', pady=4)
        estado = tk.Label(cab, text='', bg=GRIS, anchor='e')
        estado.pack(side='right', padx=8)
        cuerpo = ttk.Frame(caja, padding=(28, 8, 8, 4))
        cuerpo.pack(fill='x')
        if ayuda:
            ttk.Label(cuerpo, text=ayuda, foreground='#5b6b7a',
                      wraplength=980, justify='left').pack(anchor='w', pady=(0, 6))
        return cuerpo, estado

    def _pest_inicio(self):
        scroll = MarcoScroll(self.tab_inicio)
        scroll.pack(fill='both', expand=True)
        cont = ttk.Frame(scroll.interior, padding=14)
        cont.pack(fill='both', expand=True)

        # ---------------- paso 1: fotos
        c1, self.est_fotos = self._paso(
            cont, 1, 'Carpeta con las fotos de los examenes',
            'Todas las hojas del mismo examen en una sola carpeta.')
        f1 = ttk.Frame(c1); f1.pack(fill='x')
        ttk.Entry(f1, textvariable=self.var_fotos).pack(
            side='left', fill='x', expand=True)
        ttk.Button(f1, text='Elegir carpeta...', command=self._elegir_fotos).pack(
            side='left', padx=6)
        ttk.Button(f1, text='Contar fotos', command=self.contar_fotos).pack(side='left')

        # ---------------- paso 2: clave
        c2, self.est_clave = self._paso(
            cont, 2, 'Clave de respuestas',
            'Sin clave se leen las hojas pero no hay notas. Elige UNA de las tres formas.')
        f2 = ttk.Frame(c2); f2.pack(fill='x')
        ttk.Label(f2, text='Escribe las 80 letras seguidas (usa "-" para anular '
                           'una pregunta):').pack(anchor='w')
        self.txt_clave = tk.Text(f2, height=3, wrap='char', font=('TkFixedFont', 10))
        self.txt_clave.pack(fill='x', pady=4)
        b2 = ttk.Frame(f2); b2.pack(fill='x')
        ttk.Button(b2, text='Aplicar lo escrito', command=self.aplicar_clave).pack(side='left')
        ttk.Separator(b2, orient='vertical').pack(side='left', fill='y', padx=10)
        ttk.Button(b2, text='...o leerla de la hoja resuelta',
                   command=self.leer_clave_de_hoja).pack(side='left')
        ttk.Button(b2, text='...o cargar clave.json',
                   command=self.cargar_clave_json).pack(side='left', padx=6)
        ttk.Button(b2, text='Guardar clave.json',
                   command=self.guardar_clave_json).pack(side='right')

        # ---------------- paso 3: padron
        c3, self.est_padron = self._paso(
            cont, 3, 'Padron de alumnos  (opcional)',
            'Un alumnos.xlsx con las columnas codigo y apellidos_y_nombres. '
            'Sirve para poner nombre a cada codigo y generar el acta.')
        f3 = ttk.Frame(c3); f3.pack(fill='x')
        ttk.Entry(f3, textvariable=self.var_padron).pack(
            side='left', fill='x', expand=True)
        ttk.Button(f3, text='Elegir archivo...', command=self._elegir_padron).pack(
            side='left', padx=6)
        ttk.Button(f3, text='Cargar', command=self.cargar_padron).pack(side='left')

        # ---------------- paso 4: opciones y calificar
        c4, self.est_calif = self._paso(
            cont, 4, 'Opciones y calificacion')
        f4 = ttk.Frame(c4); f4.pack(fill='x')
        ttk.Label(f4, text='Guardar en:').grid(row=0, column=0, sticky='w')
        ttk.Entry(f4, textvariable=self.var_salida, width=58).grid(
            row=0, column=1, columnspan=4, sticky='we', padx=6)
        ttk.Button(f4, text='Elegir...', command=self._elegir_salida).grid(row=0, column=5)

        ttk.Label(f4, text='Nota maxima:').grid(row=1, column=0, sticky='w', pady=(8, 0))
        ttk.Spinbox(f4, from_=1, to=100, increment=1, width=7,
                    textvariable=self.var_nota_max).grid(row=1, column=1, sticky='w',
                                                         padx=6, pady=(8, 0))
        ttk.Label(f4, text='Penalidad por error:').grid(row=1, column=2, sticky='e',
                                                        pady=(8, 0))
        ttk.Spinbox(f4, from_=0, to=1, increment=0.05, width=7,
                    textvariable=self.var_penalidad).grid(row=1, column=3, sticky='w',
                                                          padx=6, pady=(8, 0))
        ttk.Checkbutton(f4, text='Anular marcas defectuosas',
                        variable=self.var_anular).grid(row=1, column=4, columnspan=2,
                                                       sticky='w', pady=(8, 0))

        ttk.Label(f4, text='Aceptar la marca desde:').grid(row=2, column=0, sticky='w',
                                                           pady=(8, 0))
        self.lbl_umbral = ttk.Label(f4, text=f'{cfg.umbral_acepta:.0%} pintado',
                                    width=12)
        self.lbl_umbral.grid(row=2, column=1, sticky='w', padx=6, pady=(8, 0))
        ttk.Scale(f4, from_=0.45, to=0.80, variable=self.var_umbral,
                  command=self._mover_umbral, length=240).grid(
            row=2, column=2, columnspan=3, sticky='we', pady=(8, 0))
        ttk.Button(f4, text='Recalcular', command=self.recalcular).grid(
            row=2, column=5, pady=(8, 0))
        f4.columnconfigure(4, weight=1)

        # ---------------- registro
        reg = ttk.LabelFrame(cont, text=' Registro ', padding=6)
        reg.pack(fill='both', expand=True, pady=(10, 0))
        self.txt_log = tk.Text(reg, height=7, wrap='none', font=('TkFixedFont', 9))
        sb = ttk.Scrollbar(reg, command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        self.txt_log.pack(fill='both', expand=True)
        self.txt_log.tag_configure('ok', foreground=VERDE)
        self.txt_log.tag_configure('mal', foreground=ROJO)
        self.txt_log.tag_configure('avi', foreground='#8f6109')

    def contar_fotos(self):
        n = len(listar_fotos(self.var_fotos.get()))
        self._ultimo_conteo = n
        self.est_fotos.configure(text=(f'{n} foto(s) encontradas' if n
                                       else 'no encuentro imagenes ahi'),
                                 fg=VERDE if n else ROJO)
        return n

    def _refrescar_pasos(self):
        self.contar_fotos()
        n = len(self.clave)
        self.est_clave.configure(
            text=(f'{n} de {cfg.n_preguntas} respuestas' if n else 'sin clave'),
            fg=VERDE if n == cfg.n_preguntas else (AMBAR if n else ROJO))
        m = len(self.padron)
        self.est_padron.configure(text=(f'{m} alumno(s)' if m else 'sin padron'),
                                  fg=VERDE if m else '#8a97a3')
        self.est_calif.configure(
            text=(f'{len(self.resultados)} hoja(s) calificadas'
                  if self.resultados else 'sin calificar'),
            fg=VERDE if self.resultados else '#8a97a3')
        self.var_resumen_pasos.set(
            f'{self._ultimo_conteo} foto(s)   ·   '
            f'clave {n}/{cfg.n_preguntas}   ·   padron {m}')

    def _mover_umbral(self, _=None):
        self.lbl_umbral.config(text=f'{self.var_umbral.get():.0%} pintado')

    def _elegir_fotos(self):
        d = filedialog.askdirectory(title='Carpeta con las fotos')
        if d:
            self.var_fotos.set(d)
            self.contar_fotos()

    def _elegir_salida(self):
        d = filedialog.askdirectory(title='Carpeta de resultados')
        if d:
            self.var_salida.set(d)

    def _elegir_padron(self):
        d = filedialog.askopenfilename(title='Padron de alumnos',
                                       filetypes=[('Excel', '*.xlsx')])
        if d:
            self.var_padron.set(d)
            self.cargar_padron()

    def log(self, txt, tag=None):
        self.txt_log.insert('end', txt + '\n', tag or '')
        self.txt_log.see('end')

    # -------------------------------------------------------- procesamiento
    def procesar_lote(self):
        fotos = listar_fotos(self.var_fotos.get())
        if not fotos:
            messagebox.showwarning('Sin fotos',
                                   f'No hay imagenes en:\n{self.var_fotos.get()}')
            return
        if not self.clave:
            if not messagebox.askyesno(
                    'Sin clave',
                    'No has cargado la clave de respuestas.\n\n'
                    'Puedo leer las hojas igual, pero no habra notas.\n'
                    '(La clave se pone en la pestana 4.)\n\n¿Continuar?'):
                return
        cfg.nota_maxima = float(self.var_nota_max.get())
        cfg.penalidad = float(self.var_penalidad.get())
        cfg.umbral_acepta = float(self.var_umbral.get())

        self.resultados.clear()
        self.txt_log.delete('1.0', 'end')
        self.barra['maximum'] = len(fotos)
        self.barra['value'] = 0
        self.var_estado.set(f'Procesando {len(fotos)} hoja(s)...')
        # las variables de Tkinter solo se leen desde el hilo principal, asi que
        # se resuelven antes de lanzar el hilo
        salida = self.var_salida.get()
        anular = bool(self.var_anular.get())
        clave = dict(self.clave) if self.clave else None
        threading.Thread(target=self._hilo_procesar,
                         args=(fotos, salida, anular, clave), daemon=True).start()

    def _hilo_procesar(self, fotos, salida, anular, clave):
        os.makedirs(salida, exist_ok=True)
        for i, ruta in enumerate(fotos, 1):
            nombre = os.path.basename(ruta)
            try:
                r = procesar(ruta, clave, cfg, anular)
                cv2.imwrite(os.path.join(salida,
                                         os.path.splitext(nombre)[0] + '_calificado.png'),
                            dibujar(r, cfg))
                self.cola.put(('hoja', ruta, r, i, nombre))
            except Exception as e:
                self.cola.put(('error', ruta, str(e), i, nombre))
        self.cola.put(('fin', None, None, len(fotos), None))

    def _revisar_cola(self):
        try:
            while True:
                tipo, ruta, dato, i, nombre = self.cola.get_nowait()
                if tipo == 'hoja':
                    self.resultados[ruta] = dato
                    nota = (f"{dato['resumen']['nota']:>6}" if dato['resumen'] else '   -  ')
                    rev = len(dato['incidencias'])
                    tag = 'ok' if rev == 0 else ('avi' if rev <= 3 else 'mal')
                    self.log(f"[{i:>3}] {nombre[:44]:46} cod={dato['codigo_leido']} "
                             f"nota={nota}  revisar={rev}", tag)
                elif tipo == 'error':
                    self.log(f'[{i:>3}] {nombre[:44]:46} ERROR: {dato}', 'mal')
                elif tipo == 'fin':
                    self.barra['value'] = i
                    n = len(self.resultados)
                    self.var_estado.set(f'{n} de {i} hoja(s) calificadas.')
                    self.log(f'\nListo: {n} de {i} hoja(s).',
                             'ok' if n == i else 'avi')
                    self.refrescar_todo()
                    if n:
                        self.nb.select(self.tab_result)
                    continue
                self.barra['value'] = i
        except queue.Empty:
            pass
        self.after(120, self._revisar_cola)

    def recalcular(self):
        if not self.resultados:
            return
        cfg.nota_maxima = float(self.var_nota_max.get())
        cfg.penalidad = float(self.var_penalidad.get())
        cfg.umbral_acepta = float(self.var_umbral.get())
        for r in self.resultados.values():
            r['lectura'] = leer_respuestas(r['respuestas']['llenado'],
                                           r['respuestas']['formas'], cfg)
            r['cadena'] = ''.join(i['marcada'] or '-' for i in r['lectura'])
            r['incidencias'] = [i for i in r['lectura']
                                if i['estado'] in ('doble',) + DEFECTOS or i['avisos']]
            r['resumen'] = (calificar(r['lectura'], self.clave, cfg,
                                      bool(self.var_anular.get()))
                            if self.clave else None)
        self.refrescar_todo()
        self.var_estado.set(f'Recalculado con umbral {cfg.umbral_acepta:.0%}.')

    # ----------------------------------------------------- 2. resultados
    def _pest_resultados(self):
        f = self.tab_result
        cols = ('archivo', 'codigo', 'alumno', 'nota', 'bien', 'mal',
                'blanco', 'anuladas', 'revisar')
        anchos = (250, 100, 250, 60, 55, 55, 60, 75, 70)
        self.tv_res = ttk.Treeview(f, columns=cols, show='headings')
        for c, a in zip(cols, anchos):
            self.tv_res.heading(c, text=c.upper())
            self.tv_res.column(c, width=a, anchor='w' if a > 90 else 'center')
        sb = ttk.Scrollbar(f, command=self.tv_res.yview)
        self.tv_res.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y', pady=10)
        self.tv_res.pack(fill='both', expand=True, padx=(12, 0), pady=10)
        self.tv_res.tag_configure('bien', background='#e9f6ee')
        self.tv_res.tag_configure('avi', background='#fdf5e3')
        self.tv_res.tag_configure('mal', background='#fce9ec')
        self.tv_res.bind('<Double-1>', self._abrir_en_revision)

        bar = ttk.Frame(f, padding=(12, 0, 12, 12))
        bar.pack(fill='x')
        ttk.Button(bar, text='Exportar CSV', command=self.exportar_csv).pack(side='left')
        ttk.Button(bar, text='Exportar Excel', command=self.exportar_excel).pack(
            side='left', padx=8)
        ttk.Button(bar, text='Exportar acta', command=self.exportar_acta).pack(side='left')
        ttk.Button(bar, text='Abrir carpeta de resultados',
                   command=self.abrir_salida).pack(side='right')
        ttk.Button(bar, text='Ver la hoja seleccionada en grande',
                   command=self._ver_seleccionada).pack(side='right', padx=8)

    def refrescar_resultados(self):
        self.tv_res.delete(*self.tv_res.get_children())
        for ruta in sorted(self.resultados):
            r = self.resultados[ruta]
            s = r.get('resumen') or {}
            alu, est, _ = buscar_alumno(self.padron, r['codigo_leido'])
            nombre = alu['apellidos_y_nombres'] if alu is not None else f'<{est}>'
            rev = len(r['incidencias'])
            tag = 'bien' if rev == 0 else ('avi' if rev <= 3 else 'mal')
            self.tv_res.insert('', 'end', iid=ruta, tags=(tag,), values=(
                r['archivo'], r['codigo_leido'], nombre, s.get('nota', ''),
                s.get('aciertos', ''), s.get('errores', ''), s.get('blancos', ''),
                s.get('anuladas', ''), rev))

    def _ver_seleccionada(self):
        sel = self.tv_res.selection()
        if not sel:
            messagebox.showinfo('Zoom', 'Elige una fila de la tabla primero.')
            return
        r = self.resultados[sel[0]]
        VisorImagen(self, dibujar(r, cfg),
                    f"{r['archivo']}  —  codigo {r['codigo_leido']}")

    def _abrir_en_revision(self, _=None):
        sel = self.tv_res.selection()
        if sel:
            self.cmb_hoja.set(self.resultados[sel[0]]['archivo'])
            self.nb.select(self.tab_revis)
            self._cambiar_hoja()

    # ------------------------------------------------------- 3. revision
    def _pest_revision(self):
        f = self.tab_revis
        top = ttk.Frame(f, padding=(12, 10, 12, 4))
        top.pack(fill='x')
        ttk.Label(top, text='Hoja:').pack(side='left')
        self.cmb_hoja = ttk.Combobox(top, state='readonly', width=44)
        self.cmb_hoja.pack(side='left', padx=6)
        self.cmb_hoja.bind('<<ComboboxSelected>>', self._cambiar_hoja)
        ttk.Label(top, text='   Pregunta:').pack(side='left')
        self.spin_preg = ttk.Spinbox(top, from_=1, to=cfg.n_preguntas, width=6,
                                     command=self._ver_pregunta)
        self.spin_preg.set(1)
        self.spin_preg.pack(side='left', padx=4)
        ttk.Button(top, text='Ver de cerca', command=self._ver_pregunta).pack(side='left')
        ttk.Label(top, text='   Corregir a:').pack(side='left')
        self.cmb_alt = ttk.Combobox(top, state='readonly', width=10,
                                    values=list(OPCIONES) + ['en blanco'])
        self.cmb_alt.set('A')
        self.cmb_alt.pack(side='left', padx=4)
        ttk.Button(top, text='Aplicar', command=self._corregir).pack(side='left')
        ttk.Button(top, text='Solo incidencias >>',
                   command=self._siguiente_incidencia).pack(side='right')

        cuerpo = ttk.Frame(f)
        cuerpo.pack(fill='both', expand=True, padx=12, pady=6)

        izq = ttk.LabelFrame(cuerpo, text=' Preguntas ', padding=6)
        izq.pack(side='left', fill='both', expand=False)
        cols = ('preg', 'leida', 'clave', 'pintado', 'estado')
        self.tv_preg = ttk.Treeview(izq, columns=cols, show='headings',
                                    height=22, selectmode='browse')
        for c, a in zip(cols, (50, 55, 55, 70, 110)):
            self.tv_preg.heading(c, text=c.upper())
            self.tv_preg.column(c, width=a, anchor='center')
        sb = ttk.Scrollbar(izq, command=self.tv_preg.yview)
        self.tv_preg.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        self.tv_preg.pack(fill='both', expand=True)
        self.tv_preg.tag_configure('mal', background='#fce9ec')
        self.tv_preg.tag_configure('avi', background='#fdf5e3')
        self.tv_preg.bind('<<TreeviewSelect>>', self._sel_pregunta)

        der = ttk.Frame(cuerpo)
        der.pack(side='left', fill='both', expand=True, padx=(10, 0))
        self.lbl_lupa = ttk.Label(der, text='Elige una pregunta para verla ampliada',
                                  anchor='center', background='white', relief='solid')
        self.lbl_lupa.pack(fill='x', pady=(0, 6), ipady=20)

        zb = ttk.Frame(der)
        zb.pack(fill='x', pady=(0, 4))
        ttk.Button(zb, text='Ver la hoja en grande (zoom)',
                   command=self.ver_hoja_grande).pack(side='left')
        ttk.Button(zb, text='Ver esta pregunta en grande',
                   command=self.ver_pregunta_grande).pack(side='left', padx=6)
        ttk.Label(zb, text='(o haz doble clic sobre la imagen)',
                  foreground='#5b6b7a').pack(side='left', padx=6)

        self.lbl_hoja_img = ttk.Label(der, anchor='center', background='white',
                                      relief='solid', cursor='hand2')
        self.lbl_hoja_img.pack(fill='both', expand=True)
        self.lbl_hoja_img.bind('<Double-1>', lambda e: self.ver_hoja_grande())
        self.lbl_lupa.bind('<Double-1>', lambda e: self.ver_pregunta_grande())

    def refrescar_revision(self):
        nombres = [self.resultados[k]['archivo'] for k in sorted(self.resultados)]
        self.cmb_hoja['values'] = nombres
        if nombres and self.cmb_hoja.get() not in nombres:
            self.cmb_hoja.set(nombres[0])
        self._cambiar_hoja()

    def _hoja_actual(self):
        nom = self.cmb_hoja.get()
        for k in sorted(self.resultados):
            if self.resultados[k]['archivo'] == nom:
                return k, self.resultados[k]
        return None, None

    def _cambiar_hoja(self, _=None):
        ruta, r = self._hoja_actual()
        if r is None:
            return
        self.tv_preg.delete(*self.tv_preg.get_children())
        for it in r['lectura']:
            tag = ('mal' if it['estado'] == 'doble' else
                   'avi' if it['estado'] in DEFECTOS or it['avisos'] else '')
            self.tv_preg.insert('', 'end', iid=str(it['pregunta']), tags=(tag,),
                                values=(it['pregunta'], it['marcada'] or '-',
                                        it.get('correcta') or '-',
                                        f"{it['pct']:.0%}", it['estado']))
        img = dibujar(r, cfg)
        self._img_ref2 = cv2_a_tk(img, 620, 520)
        self.lbl_hoja_img.configure(image=self._img_ref2, text='')
        avisos = []
        if r['orientacion_dudosa']:
            avisos.append('ORIENTACION DUDOSA')
        if r['avisos']:
            avisos.append('codigo: ' + '; '.join(r['avisos']))
        self.var_estado.set(f"{r['archivo']} | codigo {r['codigo_leido']} | "
                            f"enganche {r['respuestas']['enganche']}/"
                            f"{r['respuestas']['total_nodos']}"
                            + ('  |  ' + ' | '.join(avisos) if avisos else ''))

    def _sel_pregunta(self, _=None):
        sel = self.tv_preg.selection()
        if sel:
            self.spin_preg.set(sel[0])
            self._ver_pregunta()

    def _ver_pregunta(self):
        ruta, r = self._hoja_actual()
        if r is None:
            return
        try:
            p = int(self.spin_preg.get())
        except ValueError:
            return
        it = r['lectura'][p - 1]
        try:
            crop = recorte_pregunta(r, p, cfg, escala=2.2)
            self._img_ref = cv2_a_tk(crop, 620, 130)
            barras = '  '.join(f'{OPCIONES[k]}:{v:.0%}' for k, v in enumerate(it['pintado']))
            self.lbl_lupa.configure(
                image=self._img_ref,
                text=f"P{p}  leida={it['marcada'] or '-'}  ({it['estado']})\n{barras}",
                compound='top')
        except Exception as e:
            self.lbl_lupa.configure(image='', text=f'No se pudo ampliar: {e}')

    def ver_hoja_grande(self):
        ruta, r = self._hoja_actual()
        if r is None:
            messagebox.showinfo('Sin hoja', 'Primero califica y elige una hoja.')
            return
        VisorImagen(self, dibujar(r, cfg),
                    f"{r['archivo']}  —  codigo {r['codigo_leido']}")

    def ver_pregunta_grande(self):
        ruta, r = self._hoja_actual()
        if r is None:
            return
        try:
            p = int(self.spin_preg.get())
        except ValueError:
            return
        it = r['lectura'][p - 1]
        try:
            crop = recorte_pregunta(r, p, cfg, escala=5.0)
        except Exception as e:
            messagebox.showerror('Zoom', str(e))
            return
        VisorImagen(self, crop,
                    f"{r['archivo']} — P{p}  leida={it['marcada'] or '-'} "
                    f"({it['estado']}, {it['pct']:.0%} pintado)")

    def _siguiente_incidencia(self):
        ruta, r = self._hoja_actual()
        if r is None or not r['incidencias']:
            messagebox.showinfo('Sin incidencias', 'Esta hoja no tiene marcas dudosas.')
            return
        try:
            actual = int(self.spin_preg.get())
        except ValueError:
            actual = 0
        pend = [i['pregunta'] for i in r['incidencias'] if i['pregunta'] > actual]
        p = pend[0] if pend else r['incidencias'][0]['pregunta']
        self.spin_preg.set(p)
        self.tv_preg.selection_set(str(p))
        self.tv_preg.see(str(p))
        self._ver_pregunta()

    def _corregir(self):
        ruta, r = self._hoja_actual()
        if r is None:
            return
        p = int(self.spin_preg.get())
        it = r['lectura'][p - 1]
        it['marcada'] = None if self.cmb_alt.get() == 'en blanco' else self.cmb_alt.get()
        it['estado'] = 'blanco' if it['marcada'] is None else 'ok'
        it['avisos'] = ['corregido a mano']
        r['incidencias'] = [i for i in r['lectura']
                            if i['estado'] in ('doble',) + DEFECTOS or i['avisos']]
        r['cadena'] = ''.join(i['marcada'] or '-' for i in r['lectura'])
        if self.clave:
            r['resumen'] = calificar(r['lectura'], self.clave, cfg,
                                     bool(self.var_anular.get()))
        self.refrescar_todo()
        self.spin_preg.set(p)
        self.var_estado.set(f"P{p} corregida a {it['marcada'] or 'en blanco'}.")

    # ---------------------------------------------------------- 4. clave
    def _texto_clave(self):
        return ''.join(self.clave.get(i, '-') for i in range(1, cfg.n_preguntas + 1))

    def _pintar_clave(self):
        self.txt_clave.delete('1.0', 'end')
        self.txt_clave.insert('1.0', self._texto_clave())
        self._refrescar_pasos()

    def aplicar_clave(self):
        txt = ''.join(c for c in self.txt_clave.get('1.0', 'end').upper()
                      if c in OPCIONES + '-')
        if len(txt) != cfg.n_preguntas:
            messagebox.showerror('Clave incorrecta',
                                 f'Has escrito {len(txt)} letras y deben ser '
                                 f'{cfg.n_preguntas}.')
            return
        self.clave = {i + 1: c for i, c in enumerate(txt) if c in OPCIONES}
        self._pintar_clave()
        if self.resultados:
            self.recalcular()
        self.var_estado.set(f'Clave aplicada: {len(self.clave)} preguntas.')

    def leer_clave_de_hoja(self):
        ruta = filedialog.askopenfilename(title='Foto de la hoja resuelta',
                                          filetypes=[('Imagenes', '*.jpg *.jpeg *.png')])
        if not ruta:
            return
        try:
            clave, faltan, _ = clave_desde_hoja(ruta, cfg)
        except Exception as e:
            messagebox.showerror('No se pudo leer', str(e))
            return
        self.clave = clave
        self._pintar_clave()
        msg = f'Leidas {len(clave)} respuestas.'
        if faltan:
            msg += (f'\n\nSin resolver: {faltan}\n'
                    'Completalas a mano en el recuadro y pulsa "Aplicar clave".')
        messagebox.showinfo('Clave leida', msg)
        if self.resultados:
            self.recalcular()

    def cargar_clave_json(self):
        ruta = filedialog.askopenfilename(filetypes=[('JSON', '*.json')])
        if not ruta:
            return
        try:
            with open(ruta, encoding='utf-8') as fh:
                datos = json.load(fh)
            self.clave = {int(k): str(v).strip().upper() for k, v in datos.items()}
        except Exception as e:
            messagebox.showerror('Error', str(e))
            return
        self._pintar_clave()
        if self.resultados:
            self.recalcular()

    def guardar_clave_json(self):
        if not self.clave:
            messagebox.showwarning('Sin clave', 'No hay clave que guardar.')
            return
        ruta = filedialog.asksaveasfilename(defaultextension='.json',
                                            initialfile='clave.json',
                                            filetypes=[('JSON', '*.json')])
        if not ruta:
            return
        with open(ruta, 'w', encoding='utf-8') as fh:
            json.dump({str(k): v for k, v in sorted(self.clave.items())}, fh,
                      indent=2, ensure_ascii=False)
        self.var_estado.set(f'Clave guardada en {ruta}')

    # ---------------------------------------------------- 5. base de datos
    def _pest_bd(self):
        f = self.tab_bd
        top = ttk.Frame(f, padding=(12, 12, 12, 4))
        top.pack(fill='x')
        ttk.Label(top, text='Examen:').pack(side='left')
        ttk.Entry(top, textvariable=self.var_examen, width=30).pack(side='left', padx=6)
        ttk.Label(top, text='Fecha:').pack(side='left')
        ttk.Entry(top, textvariable=self.var_fecha, width=14).pack(side='left', padx=6)
        ttk.Button(top, text='Recargar padron', command=self.cargar_padron).pack(
            side='left', padx=12)
        self.lbl_padron = ttk.Label(top, text='Padron sin cargar.', foreground=ROJO)
        self.lbl_padron.pack(side='left')

        med = ttk.Frame(f, padding=(12, 4))
        med.pack(fill='x')
        ttk.Label(med, text='Hoja sin identificar? asignale el codigo a mano:').pack(
            side='left')
        self.cmb_hoja_cod = ttk.Combobox(med, state='readonly', width=34)
        self.cmb_hoja_cod.pack(side='left', padx=6)
        self.ent_cod = ttk.Entry(med, width=14)
        self.ent_cod.pack(side='left', padx=4)
        ttk.Button(med, text='Asignar', command=self.asignar_codigo).pack(side='left')

        cols = ('codigo', 'alumno', 'seccion', 'identificacion', 'nota', 'sugerencias')
        self.tv_bd = ttk.Treeview(f, columns=cols, show='headings', height=16)
        for c, a in zip(cols, (110, 270, 70, 110, 60, 220)):
            self.tv_bd.heading(c, text=c.upper())
            self.tv_bd.column(c, width=a, anchor='w' if a > 90 else 'center')
        self.tv_bd.pack(fill='both', expand=True, padx=12, pady=8)
        self.tv_bd.tag_configure('mal', background='#fce9ec')

        bar = ttk.Frame(f, padding=(12, 0, 12, 12))
        bar.pack(fill='x')
        ttk.Button(bar, text='Guardar en notas.xlsx',
                   command=self.exportar_excel).pack(side='left')
        ttk.Button(bar, text='Exportar acta del curso',
                   command=self.exportar_acta).pack(side='left', padx=8)

    def cargar_padron(self):
        ruta = self.var_padron.get()
        if not os.path.exists(ruta):
            self.lbl_padron.configure(text='No encuentro el archivo.', foreground=ROJO)
            return
        try:
            self.padron = cargar_padron(ruta)
        except Exception as e:
            messagebox.showerror('Padron', str(e))
            return
        n = len(self.padron)
        self.lbl_padron.configure(text=f'{n} alumno(s) en el padron.',
                                  foreground=VERDE if n else ROJO)
        self.refrescar_todo()
        self.var_estado.set(f'Padron cargado: {n} alumno(s).')

    def refrescar_bd(self):
        self.tv_bd.delete(*self.tv_bd.get_children())
        self.cmb_hoja_cod['values'] = [self.resultados[k]['archivo']
                                       for k in sorted(self.resultados)]
        if not self.resultados:
            return
        df = tabla_notas(self.resultados, self.padron, self.var_examen.get(),
                         self.var_fecha.get(), cfg)
        for _, fila in df.iterrows():
            tag = '' if fila['identificacion'] == 'exacto' else 'mal'
            self.tv_bd.insert('', 'end', tags=(tag,), values=(
                fila['codigo'], fila['apellidos_y_nombres'], fila['seccion'],
                fila['identificacion'], fila['nota'], fila['sugerencias_codigo']))

    def asignar_codigo(self):
        nom = self.cmb_hoja_cod.get()
        cod = _norm_codigo(self.ent_cod.get())
        if len(cod) != cfg.n_digitos or '?' in cod:
            messagebox.showerror('Codigo', f'Escribe los {cfg.n_digitos} digitos.')
            return
        for k in self.resultados:
            if self.resultados[k]['archivo'] == nom:
                self.resultados[k]['codigo_leido'] = cod
                self.resultados[k]['avisos'] = ['codigo asignado a mano']
                self.refrescar_todo()
                self.var_estado.set(f'{nom}: codigo {cod}')
                return

    # ------------------------------------------------------ 6. diagnostico
    def _pest_diagnostico(self):
        f = self.tab_diag
        top = ttk.Frame(f, padding=(12, 12, 12, 4))
        top.pack(fill='x')
        ttk.Button(top, text='Analizar la carpeta de fotos',
                   command=self.correr_diagnostico).pack(side='left')
        ttk.Button(top, text='Ver la malla de la hoja seleccionada',
                   command=self.ver_malla).pack(side='left', padx=8)
        ttk.Label(top, text='   (verde = nodo enganchado, rojo = desalineado; '
                            'doble clic en la imagen para el zoom)').pack(side='left')

        cols = ('archivo', 'resolucion', 'ocupa_%', 'radio_px', 'enganche',
                'metodo', 'codigo', 'estado')
        self.tv_diag = ttk.Treeview(f, columns=cols, show='headings', height=10)
        for c, a in zip(cols, (240, 95, 70, 75, 115, 75, 100, 130)):
            self.tv_diag.heading(c, text=c.upper())
            self.tv_diag.column(c, width=a, anchor='w' if a > 120 else 'center')
        self.tv_diag.pack(fill='x', padx=12, pady=8)
        self.tv_diag.tag_configure('mal', background='#fce9ec')
        self.tv_diag.bind('<<TreeviewSelect>>', self._ver_veredicto)

        self.txt_diag = tk.Text(f, height=6, wrap='word', font=('TkDefaultFont', 9))
        self.txt_diag.pack(fill='x', padx=12)
        self.lbl_malla = ttk.Label(f, anchor='center', background='white',
                                   relief='solid')
        self.lbl_malla.pack(fill='both', expand=True, padx=12, pady=10)
        self._veredictos = {}

    def correr_diagnostico(self):
        carpeta = self.var_fotos.get()
        self.var_estado.set('Analizando la carpeta...')
        self.update_idletasks()
        try:
            df = diagnosticar_carpeta(carpeta, cfg)
        except Exception as e:
            messagebox.showerror('Diagnostico', str(e))
            return
        self.tv_diag.delete(*self.tv_diag.get_children())
        self._veredictos.clear()
        for _, r in df.iterrows():
            tag = '' if r['estado'] == 'OK' else 'mal'
            iid = self.tv_diag.insert('', 'end', tags=(tag,), values=(
                r['archivo'], r['resolucion'], r['hoja_ocupa_%'], r['radio_px'],
                r['enganche'], r['metodo'], r['codigo'], r['estado']))
            self._veredictos[iid] = (r['archivo'], r['veredicto'])
        malas = (df['estado'] != 'OK').sum()
        self.var_estado.set(f'{len(df) - malas} de {len(df)} fotos utilizables.')

    def _ver_veredicto(self, _=None):
        sel = self.tv_diag.selection()
        if not sel:
            return
        nombre, ver = self._veredictos.get(sel[0], ('', ''))
        self.txt_diag.delete('1.0', 'end')
        self.txt_diag.insert('1.0', f'{nombre}\n\n{ver}')

    def ver_malla(self):
        sel = self.tv_diag.selection()
        if not sel:
            messagebox.showinfo('Malla', 'Elige una fila de la tabla primero.')
            return
        nombre = self._veredictos[sel[0]][0]
        ruta = os.path.join(self.var_fotos.get(), nombre)
        try:
            from omr import imagen_malla
            img = imagen_malla(ruta, cfg)
        except Exception as e:
            messagebox.showerror('Malla', str(e))
            return
        self._img_malla = cv2_a_tk(img, 700, 420)
        self.lbl_malla.configure(image=self._img_malla)
        self._malla_cv2 = img
        self.lbl_malla.bind('<Double-1>', lambda e: VisorImagen(
            self, self._malla_cv2, f'Malla — {nombre}'))

    # --------------------------------------------------------- exportar
    def _hay_datos(self):
        if not self.resultados:
            messagebox.showwarning('Sin datos', 'Primero califica alguna hoja.')
            return False
        return True

    def exportar_csv(self):
        if not self._hay_datos():
            return
        os.makedirs(self.var_salida.get(), exist_ok=True)
        destino = os.path.join(self.var_salida.get(), 'notas.csv')
        with open(destino, 'w', newline='', encoding='utf-8-sig') as fh:
            w = csv.writer(fh, delimiter=';')
            w.writerow(['archivo', 'codigo', 'alumno', 'aciertos', 'errores',
                        'blancos', 'anuladas', 'nota', 'a_revisar', 'respuestas'])
            for ruta in sorted(self.resultados):
                r = self.resultados[ruta]
                s = r.get('resumen') or {}
                alu, _e, _ = buscar_alumno(self.padron, r['codigo_leido'])
                w.writerow([r['archivo'], r['codigo_leido'],
                            alu['apellidos_y_nombres'] if alu is not None else '',
                            s.get('aciertos', ''), s.get('errores', ''),
                            s.get('blancos', ''), s.get('anuladas', ''),
                            s.get('nota', ''), len(r['incidencias']), r['cadena']])
        self.var_estado.set(f'CSV guardado: {destino}')
        messagebox.showinfo('Exportado', destino)

    def exportar_excel(self):
        if not self._hay_datos():
            return
        if self.padron.empty:
            messagebox.showwarning('Sin padron',
                                   'Carga el padron para cruzar codigos con nombres.')
        os.makedirs(self.var_salida.get(), exist_ok=True)
        destino = os.path.join(self.var_salida.get(), 'notas.xlsx')
        try:
            hojas = guardar_en_bd(self.resultados, self.padron, self.clave,
                                  self.var_examen.get(), self.var_fecha.get(),
                                  cfg, ruta=destino)
        except PermissionError:
            messagebox.showerror('Archivo abierto',
                                 'notas.xlsx esta abierto en Excel. Cierralo.')
            return
        self.var_estado.set('Excel guardado: ' + destino)
        messagebox.showinfo('Exportado', destino + '\n\n'
                            + '\n'.join(f'{k}: {len(v)} filas' for k, v in hojas.items()))

    def exportar_acta(self):
        if not self._hay_datos():
            return
        if self.padron.empty:
            messagebox.showerror('Sin padron', 'El acta necesita el padron de alumnos.')
            return
        os.makedirs(self.var_salida.get(), exist_ok=True)
        destino = os.path.join(self.var_salida.get(), 'acta.xlsx')
        df = acta(self.resultados, self.padron, self.var_examen.get(),
                  self.var_fecha.get(), cfg)
        _escribir_excel(destino, {'acta': df})
        self.var_estado.set('Acta guardada: ' + destino)
        messagebox.showinfo('Exportado', destino)

    def abrir_salida(self):
        d = self.var_salida.get()
        os.makedirs(d, exist_ok=True)
        try:
            if sys.platform.startswith('win'):
                os.startfile(d)
            elif sys.platform == 'darwin':
                os.system(f'open "{d}"')
            else:
                os.system(f'xdg-open "{d}"')
        except Exception:
            messagebox.showinfo('Carpeta', d)

    # ------------------------------------------------------------ comun
    def refrescar_todo(self):
        self.refrescar_resultados()
        self.refrescar_revision()
        self.refrescar_bd()
        self._refrescar_pasos()


def main():
    app = App()
    if os.path.exists(app.var_padron.get()):
        app.cargar_padron()
    app._pintar_clave()
    app._refrescar_pasos()
    app.mainloop()


if __name__ == '__main__':
    main()
