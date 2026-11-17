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

# Permite cambiar la carpeta de datos (por ejemplo, para las pruebas) sin modificar el código
DIR_DATOS = os.environ.get("SWEETSECURE_DATOS", "data")
MAX_INTENTOS = 3

usuarios = GestorUsuarios(DIR_DATOS)
pedidos = GestorPedidos(DIR_DATOS)


def configurar(dir_datos):
    global usuarios, pedidos
    usuarios, pedidos = GestorUsuarios(dir_datos), GestorPedidos(dir_datos)


# El modo demostración muestra operaciones y parámetros públicos, nunca claves secretas
def activar_demo(activo):
    cripto.DEBUG = activo
    cripto.salida_log = ui.log_tecnico


# Los fallos de firma e integridad se muestran como rechazos, no como operaciones correctas.
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
    # Ejecuta una operación y traduce cualquier error a un mensaje comprensible.
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

# getpass evita mostrar la contraseña mientras se escribe; después se valida su robustez
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


# El primer arranque crea la cuenta administradora y sus pares de claves protegidas
def configuracion_inicial():
    ui.cabecera("Configuración inicial de la pastelería")
    ui.texto("Todavía no hay administrador/a. Se creará ahora junto con las claves de cifrado "
             "y de firma de la pastelería. Su contraseña protege también las claves privadas.")
    while True:
        username = ui.pedir("Usuario de administrador/a:")
        password = pedir_password_nueva()
        try:
            usuarios.registrar(username, password, rol=ROL_ADMIN)
            ui.ok(f"Administrador/a '{username}' creado/a y claves generadas")
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


# Los intentos de inicio de sesión se limitan a tres por ejecución de este flujo
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
    # Recorre los pasos del pedido. V vuelve al anterior; 0 cancela (lanza Cancelado)
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


# No se cifra ni guarda el pedido hasta que el cliente confirma el resumen final
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


# ---------- Listados y selección de pedidos ----------

NOMBRE_ESTADO = {PENDIENTE: "PENDIENTE", CONFIRMADO: "CONFIRMADO", MANIPULADO: "JUSTIFICANTE MANIPULADO"}


def _estado(item):
    estado = item["estado"]
    return ui.color_estado(estado) + NOMBRE_ESTADO.get(estado, estado) + ui.FIN


def describir(item, con_cliente=False):
    producto = nombre_corto(item["pedido"]) if item["pedido"] else "Contenido no disponible"
    cliente = f" · {item['cliente']}" if con_cliente else ""
    return f"{item['id']}{cliente} · {producto} · {_estado(item)}"


def mostrar_pedidos(lista, con_cliente=False):
    if not lista:
        ui.aviso("No hay pedidos todavía.")
    for n, item in enumerate(lista, 1):
        ui.seccion(f"{n}. Pedido nº {item['id']}")
        if con_cliente:
            ui.campo("Cliente", item["cliente"])
        if item["pedido"] is None:
            ui.campo("Estado", "RECHAZADO: información manipulada", ui.color_estado(MANIPULADO))
            ui.texto(ui.ERROR + item["error"] + ui.FIN)
            continue
        ui.campo("Producto", resumen(item["pedido"]))
        ui.campo("Fecha de recogida", fecha_es(item["pedido"]["fecha_recogida"]))
        ui.campo("Total", euros(item["pedido"]["precio"]))
        ui.campo("Estado", NOMBRE_ESTADO.get(item["estado"], item["estado"]), ui.color_estado(item["estado"]))


def elegir_pedido(lista, etiqueta, con_cliente=False, vacio="No hay pedidos disponibles para esta operación."):
    if not lista:
        ui.aviso(vacio)
        return None
    item = ui.elegir_de_lista(etiqueta, lista, lambda p: describir(p, con_cliente))
    return item["id"] if item else None


def agrupar(huella):
    return " ".join(huella[i:i + 4] for i in range(0, len(huella), 4))


# Esta pantalla solo debe recibir justificantes cuya firma ya se haya verificado
def mostrar_justificante(contenido):
    ui.seccion("JUSTIFICANTE DE COMPRA — SWEETSECURE")
    ui.campo("Número de pedido", contenido["pedido_id"])
    ui.campo("Cliente", contenido["cliente"])
    ui.campo("Producto", contenido["resumen"])
    ui.campo("Importe total", euros(contenido["total_eur"]))
    ui.campo("Fecha de recogida", fecha_es(contenido["fecha_recogida"]))
    ui.campo("Estado", contenido["estado"], ui.color_estado(CONFIRMADO))
    ui.campo("Fecha de emisión", fecha_hora_es(contenido["emitida"]))
    ui.campo("Firma digital", "VÁLIDA (ECDSA P-256 + SHA-256)", ui.color_estado(CONFIRMADO))
    ui.campo("Huella de la clave", agrupar(pedidos.info_firma()["huella_firma"]))


# ---------- Cliente ----------

def consultar_justificante(sesion):
    ui.cabecera("Consultar justificante de compra")
    lista = [p for p in pedidos.mis_pedidos(sesion) if p["estado"] in (CONFIRMADO, MANIPULADO)]
    pedido_id = elegir_pedido(lista, "Pedidos con justificante", vacio="Todavía no tienes pedidos confirmados.")
    if pedido_id:
        # La firma se verifica siempre antes de mostrar el justificante como válido
        contenido = ejecutar(pedidos.verificar_guardada, sesion, pedido_id)
        if contenido:
            mostrar_justificante(contenido)
    ui.pausa()


def descargar_justificante(sesion):
    ui.cabecera("Descargar justificante")
    pedido_id = elegir_pedido(pedidos.mis_pedidos(sesion, CONFIRMADO), "Pedidos confirmados",
                              vacio="Todavía no tienes pedidos confirmados.")
    if pedido_id:
        ruta = ejecutar(pedidos.exportar, sesion, pedido_id)
        if ruta:
            ui.ok("Justificante descargado")
            ui.campo("Guardado en", ruta)
            ui.texto("Es un fichero JSON con el contenido y su firma digital. Puedes comprobar su "
                     "autenticidad más tarde con la opción 6.")
    ui.pausa()


# Se verifica tanto la firma del fichero exportado como su asociación al pedido seleccionado
def comprobar_autenticidad(sesion):
    ui.cabecera("Comprobar autenticidad de un justificante")
    ui.texto(f"Los justificantes descargados están en la carpeta: {os.path.abspath(pedidos.dir_justificantes)}")
    ficheros = sorted(f for f in os.listdir(pedidos.dir_justificantes) if f.endswith(".json")) \
        if os.path.isdir(pedidos.dir_justificantes) else []
    opciones = ficheros + ["Escribir otra ruta"]
    eleccion = ui.elegir_de_lista("Elige el justificante", opciones, str, "Selecciona el número de fichero:")
    if eleccion is None:
        return
    ruta = ui.pedir("Ruta del fichero:") if eleccion == "Escribir otra ruta" \
        else os.path.join(pedidos.dir_justificantes, eleccion)
    pedido_id = elegir_pedido(pedidos.mis_pedidos(sesion), "¿A qué pedido corresponde este justificante?")
    if pedido_id:
        contenido = ejecutar(pedidos.verificar_fichero, sesion, ruta, pedido_id)
        if contenido:
            ui.ok("Justificante AUTÉNTICO: firmado por SweetSecure y sin modificaciones")
            mostrar_justificante(contenido)
    ui.pausa()


def ver_mis_pedidos(sesion):
    ui.cabecera("Mis pedidos")
    mostrar_pedidos(pedidos.mis_pedidos(sesion))
    ui.pausa()


def menu_cliente(sesion):
    acciones = [("Ver catálogo", ver_catalogo), ("Realizar nuevo pedido", nuevo_pedido),
                ("Mis pedidos", ver_mis_pedidos), ("Consultar justificante de compra", consultar_justificante),
                ("Descargar justificante", descargar_justificante),
                ("Comprobar autenticidad de un justificante", comprobar_autenticidad), ("Cerrar sesión", None)]
    while True:
        ui.cabecera(f"Área de cliente · {sesion.username}", modo_actual())
        nombre, accion = acciones[ui.menu([a[0] for a in acciones])]
        if accion is None:
            return
        pantalla(accion, sesion)


# ---------- Administrador/a ----------

def ver_pedidos_clientes(sesion):
    ui.cabecera("Pedidos de clientes")
    lista = pedidos.todos(sesion)
    pendientes = [p for p in lista if p["estado"] == PENDIENTE]
    resto = [p for p in lista if p["estado"] != PENDIENTE]
    if pendientes:
        ui.aviso(f"{len(pendientes)} pedido(s) pendiente(s) de confirmar (se muestran primero)")
    mostrar_pedidos(pendientes + resto, con_cliente=True)
    ui.pausa()


# Solo el administrador confirma: el gestor descifra y verifica el pedido antes de firmarlo
def confirmar_pedido(sesion):
    ui.cabecera("Confirmar pedido")
    pedido_id = elegir_pedido(pedidos.todos(sesion, PENDIENTE), "Pedidos pendientes", con_cliente=True,
                              vacio="No hay pedidos pendientes de confirmar.")
    if pedido_id and ejecutar(pedidos.confirmar, sesion, pedido_id):
        ui.ok("Pedido confirmado y justificante firmado")
        ui.texto("El cliente ya puede consultar y verificar su justificante.")
    ui.pausa()


def verificar_justificante_admin(sesion):
    ui.cabecera("Verificar justificante de compra")
    lista = [p for p in pedidos.todos(sesion) if p["estado"] in (CONFIRMADO, MANIPULADO)]
    pedido_id = elegir_pedido(lista, "Pedidos con justificante", con_cliente=True,
                              vacio="Todavía no hay pedidos confirmados.")
    if pedido_id:
        contenido = ejecutar(pedidos.verificar_guardada, sesion, pedido_id)
        if contenido:
            mostrar_justificante(contenido)
    ui.pausa()


# Las huellas permiten comparar claves públicas, pero no sustituyen a un certificado digital
def info_firma(sesion):
    ui.cabecera("Información de firma digital")
    info = pedidos.info_firma()
    ui.seccion("CLAVE DE FIRMA (justificantes)")
    ui.campo("Algoritmo", info["algoritmo_firma"])
    ui.campo("Tamaño", f"{info['bits_firma']} bits")
    ui.campo("Huella SHA-256", agrupar(info["huella_firma"]))
    ui.seccion("CLAVE DE CIFRADO (claves de los pedidos)")
    ui.campo("Algoritmo", info["algoritmo_cifrado"])
    ui.campo("Tamaño", f"{info['bits_cifrado']} bits")
    ui.campo("Huella SHA-256", agrupar(info["huella_cifrado"]))
    ui.seccion("COMPROBACIÓN")
    if pedidos.claves_coherentes(sesion):
        ui.ok("Las claves públicas del disco corresponden a las claves privadas de la pastelería")
    else:
        ui.error("Las claves públicas del disco NO corresponden a las privadas: han sido sustituidas")
    print()
    ui.texto("Las claves privadas están cifradas con la contraseña de la cuenta administradora (PKCS#8) y nunca se "
             "muestran. La huella permite a los clientes comparar la clave pública con la que publica la "
             "pastelería, pero no es un certificado: no hay una autoridad que la vincule con su identidad.")
    ui.pausa()


def menu_admin(sesion):
    acciones = [("Ver pedidos de clientes", ver_pedidos_clientes), ("Confirmar pedido", confirmar_pedido),
                ("Verificar justificante de compra", verificar_justificante_admin),
                ("Consultar información de firma digital", info_firma), ("Cerrar sesión", None)]
    while True:
        ui.cabecera(f"Área de administración · {sesion.username}", modo_actual())
        pendientes = len(pedidos.todos(sesion, PENDIENTE))
        if pendientes:
            ui.aviso(f"Tienes {pendientes} pedido{'s' if pendientes > 1 else ''} pendiente"
                     f"{'s' if pendientes > 1 else ''} de confirmar")
        nombre, accion = acciones[ui.menu([a[0] for a in acciones])]
        if accion is None:
            return
        pantalla(accion, sesion)


# Antes de continuar se comprueba si las claves públicas guardadas coinciden con las privadas
def entrar_admin(sesion):
    if not pedidos.claves_coherentes(sesion):
        ui.cabecera("Alerta de seguridad")
        ui.error("Las claves públicas guardadas no corresponden a las claves privadas de la pastelería.")
        ui.texto("Alguien podría haberlas sustituido. Restaura las claves públicas antes de seguir trabajando.")
        ui.pausa()
        return
    
    menu_admin(sesion)
    


# ---------- Menú principal ----------

def modo_actual():
    return "[MODO DEMOSTRACIÓN CRIPTOGRÁFICA]" if cripto.DEBUG else ""


# Punto de entrada: inicialización, autenticación y acceso a menús según el rol
def main():
    activar_demo(os.environ.get("SWEETSECURE_DEMO") == "1")
    try:
        if not usuarios.existe_admin():
            configuracion_inicial()
        while True:
            ui.cabecera("Bienvenido/a", modo_actual())
            demo = "ACTIVADO" if cripto.DEBUG else "DESACTIVADO"
            opcion = ui.menu(["Registrarse", "Iniciar sesión", f"Modo demostración criptográfica: {demo}", "Salir"])
            if opcion == 0:
                registrarse()
            elif opcion == 1:
                sesion = iniciar_sesion()
                if sesion:
                    pantalla(entrar_admin if sesion.rol == ROL_ADMIN else menu_cliente, sesion)
                    # Se descarta la sesión al salir para no mantener claves en memoria más de lo necesario
                    del sesion
            elif opcion == 2:
                activar_demo(not cripto.DEBUG)
            else:
                ui.limpiar()
                print("\n  ¡Gracias por confiar en SweetSecure! Hasta pronto.\n")
                return
    except ErrorAlmacen as e:
        ui.error(f"Error de datos: {e}")
    except (KeyboardInterrupt, EOFError):
        print("\n\n  Saliendo de SweetSecure.\n")


if __name__ == "__main__":
    main()
