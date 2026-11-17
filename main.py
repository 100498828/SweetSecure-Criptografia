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


# ---------- Catálogo ----------

def ver_catalogo(sesion=None):
    ui.cabecera("Nuestra carta")
    tarta = CATALOGO["tarta"]
    ui.seccion("TARTAS PERSONALIZADAS")
    for pisos, precio in tarta["precio_pisos"].items():
        ui.campo(f"{pisos} piso{'s' if pisos > 1 else ''}", euros(precio))
    ui.campo("Mensaje opcional", f"+ {euros(tarta['precio_mensaje'])} (máx. {MAX_MENSAJE} caracteres)")
    print()
    ui.campo("Bizcochos", " · ".join(tarta["bizcocho"]))
    ui.campo("Coberturas", " · ".join(tarta["cobertura"]))
    ui.campo("Rellenos", " · ".join(tarta["relleno"]))
    for producto in ("cupcakes", "galletas"):
        datos = CATALOGO[producto]
        ui.seccion(producto.upper())
        ui.campo("Precio", f"{euros(datos['precio_unidad'])} la unidad")
        ui.campo("Cajas de", " | ".join(map(str, CANTIDADES)) + " unidades")
        ui.campo("Sabores", " · ".join(datos["sabor"]))
    print()
    ui.texto(f"Los pedidos se recogen en tienda, entre {DIAS_MIN_RECOGIDA} y {DIAS_MAX_RECOGIDA} días después de encargarlos.")
    ui.pausa()


# ---------- Asistente de nuevo pedido ----------

ETIQUETAS = {"producto": "Producto", "bizcocho": "Bizcocho", "cobertura": "Cobertura", "relleno": "Relleno",
             "pisos": "Pisos", "mensaje": "Mensaje", "sabor": "Sabor", "cantidad": "Cantidad",
             "fecha": "Fecha de recogida"}


def _paso_producto(datos):
    eleccion = ui.elegir("¿Qué quieres encargar?", ["Tarta personalizada", "Cupcakes", "Galletas"], volver=False)
    return {"Tarta personalizada": "tarta", "Cupcakes": "cupcakes", "Galletas": "galletas"}[eleccion]


def _paso_opcion(campo):
    def paso(datos):
        return ui.elegir(f"Elige {ETIQUETAS[campo].lower()}", CATALOGO["tarta"][campo])
    return paso


def _paso_pisos(datos):
    precios = CATALOGO["tarta"]["precio_pisos"]
    opciones = [f"{p} piso{'s' if p > 1 else ''} · {euros(v)}" for p, v in precios.items()]
    return list(precios)[opciones.index(ui.elegir("¿Cuántos pisos?", opciones))]


def _paso_mensaje(datos):
    return ui.preguntar("Mensaje personalizado (opcional)", validar_mensaje,
                        f"Escribe el texto de la tarta (máx. {MAX_MENSAJE} caracteres) o pulsa Enter para "
                        f"no poner mensaje. Con mensaje: + {euros(CATALOGO['tarta']['precio_mensaje'])}.")


def _paso_sabor(datos):
    return ui.elegir("Elige el sabor", CATALOGO[datos["producto"]]["sabor"])


def _paso_cantidad(datos):
    return ui.preguntar("¿Cuántas unidades quieres?", parsear_cantidad,
                        "Cantidades disponibles: " + " | ".join(map(str, CANTIDADES)) + ". Introduce la cantidad.")


def _validar_fecha_texto(valor):
    parsear_fecha(valor)
    return valor.strip()


def _paso_fecha(datos):
    return ui.preguntar("Fecha de recogida", _validar_fecha_texto,
                        f"Formato DD/MM/AAAA (por ejemplo 20/11/2026). Debe estar entre "
                        f"{DIAS_MIN_RECOGIDA} y {DIAS_MAX_RECOGIDA} días desde hoy.")


PASOS_TARTA = [("bizcocho", _paso_opcion("bizcocho")), ("cobertura", _paso_opcion("cobertura")),
               ("relleno", _paso_opcion("relleno")), ("pisos", _paso_pisos), ("mensaje", _paso_mensaje),
               ("fecha", _paso_fecha)]
PASOS_CAJA = [("sabor", _paso_sabor), ("cantidad", _paso_cantidad), ("fecha", _paso_fecha)]


def _pasos(datos):
    resto = {"tarta": PASOS_TARTA, "cupcakes": PASOS_CAJA, "galletas": PASOS_CAJA}.get(datos.get("producto"), [])
    return [("producto", _paso_producto)] + resto


def _mostrar_borrador(datos):
    for clave, _ in _pasos(datos):
        if clave in datos:
            valor = datos[clave]
            if clave == "producto":
                valor = {"tarta": "Tarta personalizada"}.get(valor, valor.capitalize())
            ui.campo(ETIQUETAS[clave], valor if valor != "" else "(sin mensaje)")


def _asistente(datos, desde=0):
    """Recorre los pasos del pedido. V vuelve al anterior; 0 cancela (lanza Cancelado)."""
    i = desde
    while i < len(_pasos(datos)):
        pasos = _pasos(datos)
        clave, paso = pasos[i]
        ui.cabecera("Nuevo pedido", f"Paso {i + 1} de {len(pasos)}")
        if datos:
            ui.texto(ui.SUAVE + "Tu pedido hasta ahora:" + ui.FIN)
            _mostrar_borrador(datos)
        try:
            datos[clave] = paso(datos)
            i += 1
        except ui.Volver:
            i = max(0, i - 1)
    return datos


def _construir(datos):
    if datos["producto"] == "tarta":
        return construir_tarta(datos["bizcocho"], datos["cobertura"], datos["relleno"], datos["pisos"],
                               datos["mensaje"], datos["fecha"])
    return construir_caja(datos["producto"], datos["sabor"], datos["cantidad"], datos["fecha"])


def nuevo_pedido(sesion):
    datos = {}
    try:
        _asistente(datos)
        while True:
            pedido = _construir(datos)
            ui.cabecera("Nuevo pedido", "Resumen")
            ui.seccion("REVISA TU PEDIDO")
            ui.campo("Producto", resumen(pedido))
            ui.campo("Fecha de recogida", fecha_es(pedido["fecha_recogida"]))
            ui.campo("Total", euros(pedido["precio"]), ui.NEGRITA)
            opcion = ui.menu(["Confirmar y guardar el pedido", "Modificar un dato", "Cancelar el pedido"])
            if opcion == 0:
                break
            if opcion == 2:
                raise ui.Cancelado()
            pasos = _pasos(datos)
            nombres = [ETIQUETAS[c] + (" (empezar de nuevo)" if c == "producto" else "") for c, _ in pasos]
            try:
                elegido = nombres.index(ui.elegir("¿Qué dato quieres cambiar?", nombres))
            except ui.Volver:
                continue
            if elegido == 0:
                datos.clear()
                _asistente(datos)
            else:
                # Se edita solo ese campo; V o un error no pierden el resto del pedido
                clave, paso = pasos[elegido]
                ui.cabecera("Nuevo pedido", f"Modificar {ETIQUETAS[clave].lower()}")
                try:
                    datos[clave] = paso(datos)
                except ui.Volver:
                    pass
    except ui.Cancelado:
        ui.cabecera("Nuevo pedido")
        ui.aviso("Pedido cancelado. No se ha guardado nada.")
        ui.pausa()
        return None

    ui.cabecera("Nuevo pedido")
    pedido_id = ejecutar(pedidos.crear, sesion, pedido)
    if pedido_id:
        ui.ok("PEDIDO REALIZADO CORRECTAMENTE")
        ui.texto("Pedido protegido y guardado correctamente.")
        print()
        ui.campo("Número de pedido", pedido_id)
        ui.campo("Producto", resumen(pedido))
        ui.campo("Fecha de recogida", fecha_es(pedido["fecha_recogida"]))
        ui.campo("Total", euros(pedido["precio"]))
        ui.campo("Estado", "PENDIENTE DE CONFIRMACIÓN", ui.color_estado(PENDIENTE))
        print()
        ui.texto("La pastelería todavía debe revisar tu pedido. Puedes consultar su estado en «Mis pedidos».")
    ui.pausa()
    return pedido_id

