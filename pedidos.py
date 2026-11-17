"""Catálogo, pedidos cifrados y justificantes firmados"""

import json
import os
import secrets
from datetime import date, datetime, timedelta, timezone

import cripto
from almacen import guardar_json, leer_json

# Opciones y precios centralizados: se validan los pedidos usando este catálogo
CATALOGO = {
    "tarta": {
        "bizcocho": ["Vainilla", "Chocolate oscuro", "Chocolate con leche", "Canela", "Naranja", "Zanahoria"],
        "cobertura": ["Ganache de chocolate", "Buttercream suizo", "Fondant", "Crema de queso"],
        "relleno": ["Caramelo", "Caramelo salado", "Crema de cacao y avellanas", "Dulce de leche",
                    "Crema de Kinder Bueno", "Mermelada de fresa", "Mermelada de frutos rojos",
                    "Mermelada de melocotón"],
        "precio_pisos": {1: 30.0, 2: 55.0, 3: 80.0},
        "precio_mensaje": 3.0,
    },
    "cupcakes": {
        "sabor": ["Vainilla", "Chocolate", "Red velvet", "Limón"],
        "precio_unidad": 2.5,
    },
    "galletas": {
        "sabor": ["Pepitas de chocolate", "Mantequilla", "Avena y pasas"],
        "precio_unidad": 1.5,
    },
}
CANTIDADES = [6, 12, 24]
MAX_MENSAJE = 60
DIAS_MIN_RECOGIDA = 2
DIAS_MAX_RECOGIDA = 90

PENDIENTE = "PENDIENTE"
CONFIRMADO = "CONFIRMADO"
MANIPULADO = "MANIPULADO"
ERROR_INTEGRIDAD = "ERROR DE INTEGRIDAD"


class ErrorPedido(ValueError):
    # Dato del pedido no válido (hereda de ValueError para poder pedirlo de nuevo)


class ErrorPermisos(Exception):
    pass


# ---------- Formato ----------

def euros(cantidad):
    return f"{cantidad:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def fecha_es(iso):
    return date.fromisoformat(iso).strftime("%d/%m/%Y")


def fecha_hora_es(iso):
    # Las fechas de emisión se guardan en UTC y se muestran en la hora local del equipo
    return datetime.fromisoformat(iso).astimezone().strftime("%d/%m/%Y %H:%M")


# ---------- Validación de cada campo por separado ----------

def _elegir(valor, opciones, campo):
    if valor not in opciones:
        raise ErrorPedido(f"Opción no válida para {campo}")
    return valor


def limites_fecha():
    hoy = date.today()
    return hoy + timedelta(days=DIAS_MIN_RECOGIDA), hoy + timedelta(days=DIAS_MAX_RECOGIDA)


def parsear_fecha(texto):
    # Convierte DD/MM/AAAA en una fecha ISO (AAAA-MM-DD) dentro del intervalo permitido
    texto = (texto or "").strip()
    partes = texto.split("/")
    if len(partes) != 3 or not all(p.isdigit() for p in partes) or len(partes[2]) != 4:
        raise ErrorPedido("Formato incorrecto. Escribe la fecha como DD/MM/AAAA (por ejemplo 03/12/2026)")
    dia, mes, anio = (int(p) for p in partes)
    try:
        fecha = date(anio, mes, dia)
    except ValueError:
        raise ErrorPedido(f"La fecha {texto} no existe")
    minima, maxima = limites_fecha()
    if not minima <= fecha <= maxima:
        raise ErrorPedido(f"Fecha no válida. Introduce una fecha entre el {minima:%d/%m/%Y} "
                          f"y el {maxima:%d/%m/%Y}")
    return fecha.isoformat()


def validar_mensaje(texto):
    mensaje = (texto or "").strip()
    if len(mensaje) > MAX_MENSAJE:
        raise ErrorPedido(f"El mensaje es demasiado largo ({len(mensaje)} caracteres, máximo {MAX_MENSAJE})")
    # Se rechazan caracteres de control para que el mensaje no altere la terminal al mostrarse
    if not mensaje.isprintable():
        raise ErrorPedido("El mensaje contiene caracteres no permitidos")
    return mensaje


def parsear_cantidad(texto):
    texto = (texto or "").strip()
    if not texto.isdigit() or int(texto) not in CANTIDADES:
        raise ErrorPedido("Cantidad no válida. Escribe 6, 12 o 24")
    return int(texto)


# Antes de cifrar, se comprueba que las elecciones pertenecen al catálogo
def construir_tarta(bizcocho, cobertura, relleno, pisos, mensaje, fecha):
    cat = CATALOGO["tarta"]
    if pisos not in cat["precio_pisos"]:
        raise ErrorPedido("El número de pisos debe ser 1, 2 o 3")
    mensaje = validar_mensaje(mensaje)
    return {
        "producto": "tarta",
        "bizcocho": _elegir(bizcocho, cat["bizcocho"], "bizcocho"),
        "cobertura": _elegir(cobertura, cat["cobertura"], "cobertura"),
        "relleno": _elegir(relleno, cat["relleno"], "relleno"),
        "pisos": pisos,
        "mensaje": mensaje,
        "fecha_recogida": parsear_fecha(fecha),
        "precio": cat["precio_pisos"][pisos] + (cat["precio_mensaje"] if mensaje else 0),
    }


def construir_caja(producto, sabor, cantidad, fecha):
    if producto not in ("cupcakes", "galletas"):
        raise ErrorPedido("Producto no válido")
    if cantidad not in CANTIDADES:
        raise ErrorPedido("Cantidad no válida. Escribe 6, 12 o 24")
    cat = CATALOGO[producto]
    return {
        "producto": producto,
        "sabor": _elegir(sabor, cat["sabor"], "sabor"),
        "cantidad": cantidad,
        "fecha_recogida": parsear_fecha(fecha),
        "precio": round(cat["precio_unidad"] * cantidad, 2),
    }


def resumen(pedido):
    if pedido["producto"] == "tarta":
        texto = (f"Tarta de {pedido['pisos']} piso(s): bizcocho {pedido['bizcocho']}, "
                 f"relleno {pedido['relleno']}, cobertura {pedido['cobertura']}")
        if pedido["mensaje"]:
            texto += f', mensaje "{pedido["mensaje"]}"'
        return texto
    return f"{pedido['cantidad']} {pedido['producto']} de {pedido['sabor']}"


def nombre_corto(pedido):
    if pedido["producto"] == "tarta":
        return f"Tarta ({pedido['pisos']} piso{'s' if pedido['pisos'] > 1 else ''})"
    return f"{pedido['cantidad']} {pedido['producto']}"



# ---------- Gestión de pedidos ----------

class GestorPedidos:
    def __init__(self, dir_datos):
        self.ruta_pedidos = os.path.join(dir_datos, "pedidos.json")
        self.ruta_confirmaciones = os.path.join(dir_datos, "confirmaciones.json")
        self.dir_claves = os.path.join(dir_datos, "claves")
        self.dir_justificantes = os.path.join(dir_datos, "justificantes")

    # Los AAD se autentican con AES-GCM, pero no se cifran. Vinculan el
    # contenido con el ID y el cliente, impidiendo intercambiar registros sin detectarlo
    @staticmethod
    def _aad_pedido(pedido_id, cliente):
        return f"sweetsecure|pedido|{pedido_id}|{cliente}".encode("utf-8")

    @staticmethod
    def _aad_clave(pedido_id, cliente):
        return f"sweetsecure|clave|{pedido_id}|{cliente}".encode("utf-8")

    def _clave_publica(self, nombre):
        return cripto.cargar_clave_publica(os.path.join(self.dir_claves, nombre))

    @staticmethod
    def _requerir_cliente(sesion):
        if sesion is None or sesion.clave_cliente is None:
            raise ErrorPermisos("No tienes permisos para realizar esta operación")

    @staticmethod
    def _requerir_admin(sesion):
        if sesion is None or not sesion.es_admin():
            raise ErrorPermisos("No tienes permisos para realizar esta operación")

    # ---------- Información de claves ----------

    def info_firma(self):
        clave_firma = self._clave_publica("pasteleria_firma_pub.pem")
        clave_cifrado = self._clave_publica("pasteleria_cifrado_pub.pem")
        return {
            "algoritmo_firma": f"ECDSA {clave_firma.curve.name} (P-256) + SHA-256",
            "bits_firma": clave_firma.curve.key_size,
            "huella_firma": cripto.huella(clave_firma),
            "algoritmo_cifrado": "RSA-OAEP con SHA-256",
            "bits_cifrado": clave_cifrado.key_size,
            "huella_cifrado": cripto.huella(clave_cifrado),
        }

    def claves_coherentes(self, sesion):
        # Detecta si alguien ha sustituido las claves públicas del disco por otras suyas:
        # deben corresponder a las privadas que el administrador acaba de desbloquear
        self._requerir_admin(sesion)
        return (cripto.huella(sesion.clave_firma.public_key()) ==
                cripto.huella(self._clave_publica("pasteleria_firma_pub.pem")) and
                cripto.huella(sesion.clave_rsa.public_key()) ==
                cripto.huella(self._clave_publica("pasteleria_cifrado_pub.pem")))

    # ---------- Crear y listar ----------

    def crear(self, sesion, pedido):
        self._requerir_cliente(sesion)
        pedidos = leer_json(self.ruta_pedidos)
        pedido_id = secrets.token_hex(8)
        while pedido_id in pedidos:
            pedido_id = secrets.token_hex(8)

        # Cifrado híbrido: los datos se cifran con una clave AES nueva por pedido;
        # esa clave se protege de dos formas para que accedan cliente y pastelería
        clave_pedido = cripto.generar_clave_aes()
        datos = json.dumps(pedido, ensure_ascii=False).encode("utf-8")
        cliente = sesion.username

        pedidos[pedido_id] = {
            "cliente": cliente,
            "creado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "datos": cripto.cifrar_aes_gcm(clave_pedido, datos, self._aad_pedido(pedido_id, cliente)),
            # Copia de la clave para el cliente, cifrada con la clave derivada de su contraseña
            "clave_cliente": cripto.cifrar_aes_gcm(sesion.clave_cliente, clave_pedido,
                                                   self._aad_clave(pedido_id, cliente)),
            # Copia de la clave para la pastelería, cifrada con su clave pública RSA
            "clave_pasteleria": cripto.envolver_clave_rsa(
                self._clave_publica("pasteleria_cifrado_pub.pem"), clave_pedido),
        }
        guardar_json(self.ruta_pedidos, pedidos)
        return pedido_id