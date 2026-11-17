"""Registro, autenticación y sesiones de usuario"""

import os
import re
from dataclasses import dataclass, field

import cripto
from almacen import guardar_json, leer_json

ROL_CLIENTE = "cliente"
ROL_ADMIN = "admin"


class ErrorUsuario(Exception):
    pass


class ErrorAutenticacion(Exception):
    pass


@dataclass
class Sesion:
    username: str
    rol: str
    # Las claves se mantienen en memoria durante la sesión y se excluyen
    # de la representación del objeto para evitar mostrarlas accidentalmente
    clave_cliente: bytes = field(default=None, repr=False)
    clave_rsa: object = field(default=None, repr=False)
    clave_firma: object = field(default=None, repr=False)

    def es_admin(self):
        # No basta con tener el rol admin: también debe estar disponible
        # la clave privada necesaria para firmar los pedidos.
        return self.rol == ROL_ADMIN and self.clave_firma is not None


def errores_password(password):
    # Se comprueba una longitud mínima y distintos tipos de caracteres
    # para evitar contraseñas demasiado sencillas
    errores = []
    if len(password) < 8:
        errores.append("mínimo 8 caracteres")
    if not re.search(r"[A-Z]", password):
        errores.append("al menos una mayúscula")
    if not re.search(r"[a-z]", password):
        errores.append("al menos una minúscula")
    if not re.search(r"\d", password):
        errores.append("al menos un número")
    if not re.search(r"[^A-Za-z0-9]", password):
        errores.append("al menos un símbolo")
    return errores


def validar_username(username):
    if not re.fullmatch(r"[A-Za-z0-9_]{3,20}", username):
        raise ErrorUsuario("El usuario debe tener entre 3 y 20 caracteres (letras, números o _)")


class GestorUsuarios:
    def __init__(self, dir_datos):
        self.ruta = os.path.join(dir_datos, "usuarios.json")
        self.dir_claves = os.path.join(dir_datos, "claves")

    def existe(self, username):
        return username in leer_json(self.ruta)

    def existe_admin(self):
        return any(u["rol"] == ROL_ADMIN for u in leer_json(self.ruta).values())

    def registrar(self, username, password, rol=ROL_CLIENTE):
        validar_username(username)
        errores = errores_password(password)
        if errores:
            raise ErrorUsuario("Contraseña poco robusta: " + ", ".join(errores))

        usuarios = leer_json(self.ruta)
        if username in usuarios:
            raise ErrorUsuario("No se ha podido completar el registro con ese nombre de usuario")
        if rol == ROL_ADMIN and self.existe_admin():
            raise ErrorUsuario("Ya existe un administrador")

        # Se generan dos sales aleatorias e independientes: una para
        # verificar la contraseña y otra para derivar la clave de cifrado.
        sal_login = cripto.generar_sal()
        sal_cifrado = cripto.generar_sal()
        iteraciones = cripto.PBKDF2_ITERACIONES

        # Se almacena el resultado de PBKDF2, nunca la contraseña original.
        # Las sales no son secretas y permiten repetir la derivación al iniciar sesión.
        usuarios[username] = {
            "rol": rol,
            "iteraciones": iteraciones,
            "sal_login": cripto.a_b64(sal_login),
            "hash": cripto.a_b64(cripto.hash_password(password, sal_login, iteraciones)),
            "sal_cifrado": cripto.a_b64(sal_cifrado),
        }

        if rol == ROL_ADMIN:
            cripto.generar_claves_pasteleria(self.dir_claves, password)
        guardar_json(self.ruta, usuarios)

    