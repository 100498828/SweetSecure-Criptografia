"""Presentación en terminal: colores, cabeceras, menús y lectura de datos"""

import os
import textwrap

try:
    from colorama import Fore, Style, just_fix_windows_console
    just_fix_windows_console()
    TITULO, OK, AVISO, ERROR = Fore.LIGHTMAGENTA_EX, Fore.LIGHTGREEN_EX, Fore.LIGHTYELLOW_EX, Fore.LIGHTRED_EX
    TECNICO, SUAVE, NEGRITA, FIN = Fore.CYAN, Style.DIM, Style.BRIGHT, Style.RESET_ALL
except ImportError:
    # Colorama permite mostrar colores también en Windows.
    # Sin colorama la aplicación funciona igual, solo que sin colores
    TITULO = OK = AVISO = ERROR = TECNICO = SUAVE = NEGRITA = FIN = ""

ANCHO = 64
CANCELAR = "0"
VOLVER = "V"


class Cancelado(Exception):
    pass


class Volver(Exception):
    pass


def limpiar():
    os.system("cls" if os.name == "nt" else "clear")


def linea(caracter="─"):
    print(TITULO + caracter * ANCHO + FIN)


# Se limpia la pantalla al cambiar de sección para evitar que se acumulen los menús y resultados anteriores
def cabecera(subtitulo, detalle=""):
    limpiar()
    linea("═")
    print(TITULO + NEGRITA + "  SweetSecure · Pastelería de tartas personalizadas".ljust(ANCHO) + FIN)
    linea("═")
    print(NEGRITA + f"  {subtitulo}" + FIN + (SUAVE + f"   {detalle}" + FIN if detalle else ""))
    print()


def seccion(texto):
    print()
    print(TITULO + NEGRITA + f"  {texto}" + FIN)
    linea()


def ok(texto):
    print(OK + NEGRITA + f"  ✔ {texto}" + FIN)


def aviso(texto):
    print(AVISO + f"  ⚠ {texto}" + FIN)


def error(texto):
    print(ERROR + NEGRITA + f"  ✖ {texto}" + FIN)


def texto(contenido, sangria=2):
    for parrafo in str(contenido).split("\n"):
        print(textwrap.fill(parrafo, ANCHO, initial_indent=" " * sangria, subsequent_indent=" " * sangria))


def campo(etiqueta, valor, color=""):
    prefijo = f"  {etiqueta + ':':<20}"
    lineas = textwrap.wrap(str(valor), ANCHO - len(prefijo)) or [""]
    print(prefijo + color + lineas[0] + (FIN if color else ""))
    for resto in lineas[1:]:
        print(" " * len(prefijo) + color + resto + (FIN if color else ""))


def log_tecnico(mensaje):
    print(TECNICO + "    " + mensaje + FIN)

