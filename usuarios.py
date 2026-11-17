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