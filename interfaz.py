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


# Los estados de los pedidos se distinguen por colores:
# amarillo para pendientes, verde para confirmados y rojo para errores
def color_estado(estado):
    return {"PENDIENTE": AVISO, "CONFIRMADO": OK}.get(estado, ERROR) + NEGRITA


def pedir(etiqueta):
    return input(f"\n  {etiqueta}\n  " + TITULO + NEGRITA + "› " + FIN).strip()


def pausa():
    input("\n  " + SUAVE + "Pulsa Enter para continuar..." + FIN)


def menu(opciones):
    # Muestra opciones numeradas y devuelve el índice elegido (empezando en 0)
    print()
    for i, opcion in enumerate(opciones, 1):
        print(f"   {TITULO}{NEGRITA}{i}{FIN}  {opcion}")
    while True:
        valor = pedir("Elige una opción:")
        if valor.isdigit() and 1 <= int(valor) <= len(opciones):
            return int(valor) - 1
        error(f"Escribe un número del 1 al {len(opciones)}")


def ayuda_navegacion(volver=True):
    extra = f"   {NEGRITA}V{FIN} volver atrás" if volver else ""
    print(SUAVE + f"  {NEGRITA}0{FIN}{SUAVE} cancelar el pedido" + FIN + extra)


def elegir(etiqueta, opciones, volver=True):
    # Elige una opción numerada: 0 cancela y V vuelve atrás
    seccion(etiqueta)
    for i, opcion in enumerate(opciones, 1):
        print(f"   {TITULO}{NEGRITA}{i:>2}{FIN}  {opcion}")
    print()
    ayuda_navegacion(volver)
    while True:
        valor = pedir("Elige una opción:").upper()
        if valor == CANCELAR:
            raise Cancelado()
        if valor == VOLVER and volver:
            raise Volver()
        if valor.isdigit() and 1 <= int(valor) <= len(opciones):
            return opciones[int(valor) - 1]
        error(f"Escribe un número del 1 al {len(opciones)}")


def preguntar(etiqueta, validar, explicacion="", volver=True):
    # Pide un dato y lo repite hasta que la función validar lo acepte, sin perder lo anterior
    seccion(etiqueta)
    if explicacion:
        texto(explicacion)
    ayuda_navegacion(volver)
    while True:
        valor = pedir("Escribe tu respuesta:")
        if valor == CANCELAR:
            raise Cancelado()
        if valor.upper() == VOLVER and volver:
            raise Volver()
        try:
            return validar(valor)
        except ValueError as e:
            error(str(e))


def elegir_de_lista(etiqueta, elementos, describir, pregunta="Selecciona el número de pedido:"):
    # Lista numerada de elementos; devuelve el elegido o None si se pulsa 0
    seccion(etiqueta)
    for i, elemento in enumerate(elementos, 1):
        print(f"   {TITULO}{NEGRITA}{i:>2}{FIN}  {describir(elemento)}")
    print(SUAVE + f"\n  {NEGRITA}0{FIN}{SUAVE} volver al menú" + FIN)
    while True:
        valor = pedir(pregunta)
        if valor == "0":
            return None
        if valor.isdigit() and 1 <= int(valor) <= len(elementos):
            return elementos[int(valor) - 1]
        error(f"Escribe un número del 1 al {len(elementos)}, o 0 para volver")
