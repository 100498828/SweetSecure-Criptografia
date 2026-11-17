"""SweetSecure: gestión segura de pedidos de una pastelería (menú por terminal)"""

import os
from getpass import getpass

import cripto
import interfaz as ui
from almacen import ErrorAlmacen
from pedidos import (CANTIDADES, CATALOGO, CONFIRMADO, DIAS_MAX_RECOGIDA, DIAS_MIN_RECOGIDA, MANIPULADO,
                     MAX_MENSAJE, PENDIENTE, ErrorPedido, ErrorPermisos, GestorPedidos, construir_caja,
                     construir_tarta, euros, fecha_es, fecha_hora_es, nombre_corto, parsear_cantidad,
                     parsear_fecha, resumen, validar_mensaje)
from usuarios import ROL_ADMIN, ErrorAutenticacion, ErrorUsuario, GestorUsuarios, errores_password

DIR_DATOS = os.environ.get("SWEETSECURE_DATOS", "data")
MAX_INTENTOS = 3

usuarios = GestorUsuarios(DIR_DATOS)
pedidos = GestorPedidos(DIR_DATOS)


def configurar(dir_datos):
    global usuarios, pedidos
    usuarios, pedidos = GestorUsuarios(dir_datos), GestorPedidos(dir_datos)


def activar_demo(activo):
    cripto.DEBUG = activo
    cripto.salida_log = ui.log_tecnico


def mostrar_error(e):
    if isinstance(e, cripto.FirmaInvalida):
        ui.error("Firma digital inválida. El justificante ha sido rechazado.")
        ui.texto(f"Motivo: {e}")
    elif isinstance(e, cripto.ErrorIntegridad):
        ui.error("Los datos han sido manipulados: no superan la verificación de integridad.")
        ui.texto("La información se ha rechazado y no se ha procesado.")
    else:
        ui.error(str(e))


ERRORES = (cripto.FirmaInvalida, cripto.ErrorIntegridad, cripto.ErrorClave, ErrorPermisos, ErrorPedido, ErrorAlmacen)


def ejecutar(accion, *args):
    """Ejecuta una operación y traduce cualquier error a un mensaje comprensible."""
    try:
        return accion(*args)
    except ERRORES as e:
        mostrar_error(e)
    return None


def pantalla(accion, *args):
    # Si una pantalla falla, se informa y se espera a que el usuario lo lea antes de volver al menú
    try:
        accion(*args)
    except ERRORES as e:
        mostrar_error(e)
        ui.pausa()


# ---------- Inicio, registro y login ----------

def pedir_password_nueva():
    while True:
        password = getpass("\n  Contraseña (no se muestra al escribir)\n  › ")
        errores = errores_password(password)
        if errores:
            ui.error("Contraseña poco robusta: " + ", ".join(errores))
            continue
        if getpass("  Repite la contraseña\n  › ") != password:
            ui.error("Las contraseñas no coinciden")
            continue
        return password


def configuracion_inicial():
    ui.cabecera("Configuración inicial de la pastelería")
    ui.texto("Todavía no hay administradora. Se creará ahora junto con las claves de cifrado "
             "y de firma de la pastelería. Su contraseña protege también las claves privadas.")
    while True:
        username = ui.pedir("Usuario de la administradora:")
        password = pedir_password_nueva()
        try:
            usuarios.registrar(username, password, rol=ROL_ADMIN)
            ui.ok(f"Administradora '{username}' creada y claves generadas")
            ui.campo("Huella de firma", agrupar(pedidos.info_firma()["huella_firma"]))
            ui.texto("Anota esta huella: los clientes pueden compararla con la que publique la pastelería.")
            ui.pausa()
            return
        except ErrorUsuario as e:
            ui.error(str(e))


def registrarse():
    ui.cabecera("Registro de cliente")
    ui.texto("Usuario: de 3 a 20 letras, números o _. Contraseña: mínimo 8 caracteres con "
             "mayúscula, minúscula, número y símbolo.")
    username = ui.pedir("Nombre de usuario:")
    if usuarios.existe(username):
        ui.error("Ese nombre de usuario no está disponible")
        ui.pausa()
        return
    password = pedir_password_nueva()
    try:
        usuarios.registrar(username, password)
        ui.ok(f"Usuario '{username}' registrado. Ya puedes iniciar sesión")
    except ErrorUsuario as e:
        ui.error(str(e))
    ui.pausa()


def iniciar_sesion():
    ui.cabecera("Iniciar sesión")
    for intento in range(1, MAX_INTENTOS + 1):
        username = ui.pedir("Usuario:")
        password = getpass("\n  Contraseña\n  › ")
        try:
            return usuarios.autenticar(username, password)
        except ErrorAutenticacion as e:
            # Mismo mensaje si el usuario no existe o la contraseña falla: no se revela qué usuarios existen
            ui.error(f"{e} (intento {intento} de {MAX_INTENTOS})")
    ui.aviso("Demasiados intentos fallidos. Vuelve a intentarlo más tarde.")
    ui.pausa()
    return None

