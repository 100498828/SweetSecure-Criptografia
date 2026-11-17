"""Operaciones criptográficas de SweetSecure."""

import base64
import json
import os

from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# Iteraciones recomendadas por OWASP para PBKDF2-HMAC-SHA256
PBKDF2_ITERACIONES = 600_000
SAL_BYTES = 16
CLAVE_AES_BITS = 256
# Tamaño de nonce recomendado para AES-GCM (96 bits)
NONCE_BYTES = 12
RSA_BITS = 3072
CURVA_FIRMA = ec.SECP256R1()

# Modo demostración criptográfica: si está activo se muestran algoritmos y parámetros públicos
DEBUG = False
# La interfaz puede sustituir esta función para dar formato a los mensajes
salida_log = print


class ErrorIntegridad(Exception):
    """Los datos cifrados, el tag o los datos asociados han sido modificados."""


class FirmaInvalida(Exception):
    """La firma no corresponde a los datos o a la clave pública."""


class ErrorClave(Exception):
    """No se ha podido cargar o usar una clave."""


def log(mensaje):
    # Nunca se registran claves ni contraseñas, solo algoritmos y datos públicos
    if DEBUG:
        salida_log(f"[CRIPTO] {mensaje}")


def a_b64(datos):
    return base64.b64encode(datos).decode("ascii")


def de_b64(texto):
    return base64.b64decode(texto.encode("ascii"), validate=True)


def bytes_canonicos(diccionario):
    # Se ordenan las claves para que el mismo contenido produzca siempre los mismos bytes al firmar
    return json.dumps(diccionario, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


# ---------- Contraseñas y derivación de claves (PBKDF2) ----------

def generar_sal():
    return os.urandom(SAL_BYTES)

# PBKDF2 aplica repetidamente HMAC-SHA256 para dificultar los ataques
# de fuerza bruta sobre contraseñas. La sal evita resultados idénticos
# cuando dos usuarios tienen la misma contraseña.
def _pbkdf2(password, sal, iteraciones):
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=sal, iterations=iteraciones)


def hash_password(password, sal, iteraciones=None):
    iteraciones = iteraciones or PBKDF2_ITERACIONES
    resultado = _pbkdf2(password, sal, iteraciones).derive(password.encode("utf-8"))
    log(f"PBKDF2-HMAC-SHA256 | {iteraciones} iteraciones | sal {len(sal) * 8} bits | salida 256 bits")
    return resultado


def verificar_password(password, sal, hash_guardado, iteraciones):
    # verify() compara en tiempo constante, evitando ataques de temporización
    try:
        _pbkdf2(password, sal, iteraciones).verify(password.encode("utf-8"), hash_guardado)
        return True
    except Exception:
        return False


def derivar_clave_cliente(password, sal, iteraciones):
    # Se usa una sal distinta a la del login para que la clave de cifrado no coincida con el hash guardado
    clave = _pbkdf2(password, sal, iteraciones).derive(password.encode("utf-8"))
    log(f"Clave del cliente derivada con PBKDF2 (AES-{len(clave) * 8}), no se almacena")
    return clave