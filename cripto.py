"""Operaciones criptográficas de SweetSecure"""

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
def _pbkdf2(sal, iteraciones):
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=sal, iterations=iteraciones)


def hash_password(password, sal, iteraciones=None):
    iteraciones = iteraciones or PBKDF2_ITERACIONES
    resultado = _pbkdf2(sal, iteraciones).derive(password.encode("utf-8"))
    log(f"PBKDF2-HMAC-SHA256 | {iteraciones} iteraciones | sal {len(sal) * 8} bits | salida 256 bits")
    return resultado


def verificar_password(password, sal, hash_guardado, iteraciones):
    # verify() compara en tiempo constante, evitando ataques de temporización
    try:
        _pbkdf2(sal, iteraciones).verify(password.encode("utf-8"), hash_guardado)
        return True
    except Exception:
        return False


def derivar_clave_cliente(password, sal, iteraciones):
    # Se usa una sal distinta a la del login para que la clave de cifrado no coincida con el hash guardado
    clave = _pbkdf2(sal, iteraciones).derive(password.encode("utf-8"))
    log(f"Clave del cliente derivada con PBKDF2 (AES-{len(clave) * 8}), no se almacena")
    return clave



# ---------- Cifrado autenticado (AES-GCM) ----------
# AES-GCM proporciona confidencialidad mediante cifrado simétrico
# e integridad y autenticación de los datos mediante un tag.
def generar_clave_aes():
    return AESGCM.generate_key(bit_length=CLAVE_AES_BITS)


def cifrar_aes_gcm(clave, datos, aad):
    # Nonce aleatorio nuevo en cada cifrado: nunca se repite un par (clave, nonce)
    nonce = os.urandom(NONCE_BYTES)
    cifrado = AESGCM(clave).encrypt(nonce, datos, aad)
    log(f"AES-{len(clave) * 8}-GCM | nonce {nonce.hex()} | tag 128 bits | "
        f"cifrado {cifrado[:12].hex()}... ({len(cifrado)} bytes)")
    return {"nonce": a_b64(nonce), "cifrado": a_b64(cifrado)}


def descifrar_aes_gcm(clave, paquete, aad):
    try:
        nonce = de_b64(paquete["nonce"])
        cifrado = de_b64(paquete["cifrado"])
        datos = AESGCM(clave).decrypt(nonce, cifrado, aad)
    except (InvalidTag, KeyError, ValueError, TypeError) as e:
        log("AES-GCM: verificación del tag FALLIDA, datos rechazados")
        raise ErrorIntegridad("Los datos cifrados no superan la verificación de integridad") from e
    log(f"AES-{len(clave) * 8}-GCM | tag verificado correctamente")
    return datos



# ---------- Claves asimétricas de la pastelería ----------

def _guardar_privada(clave, ruta, password):
    pem = clave.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        # Se cifra la clave privada con la contraseña del administrador
        encryption_algorithm=serialization.BestAvailableEncryption(password.encode("utf-8")),
    )
    # Se crea el fichero con permisos 0600 (solo el propietario puede leerlo)
    descriptor = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as f:
        f.write(pem)


def _guardar_publica(clave, ruta):
    pem = clave.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    with open(ruta, "wb") as f:
        f.write(pem)


def generar_claves_pasteleria(directorio, password):
    # Se usan dos pares distintos: RSA solo para cifrar y ECDSA solo para firmar
    os.makedirs(directorio, exist_ok=True)

    clave_rsa = rsa.generate_private_key(public_exponent=65537, key_size=RSA_BITS)
    _guardar_privada(clave_rsa, os.path.join(directorio, "pasteleria_cifrado_priv.pem"), password)
    _guardar_publica(clave_rsa.public_key(), os.path.join(directorio, "pasteleria_cifrado_pub.pem"))
    log(f"Par RSA-{RSA_BITS} generado para cifrado (OAEP), privada protegida con PKCS#8 cifrado")

    clave_ec = ec.generate_private_key(CURVA_FIRMA)
    _guardar_privada(clave_ec, os.path.join(directorio, "pasteleria_firma_priv.pem"), password)
    _guardar_publica(clave_ec.public_key(), os.path.join(directorio, "pasteleria_firma_pub.pem"))
    log(f"Par ECDSA {CURVA_FIRMA.name} generado para firma, privada protegida con PKCS#8 cifrado")


def cargar_clave_privada(ruta, password):
    try:
        with open(ruta, "rb") as f:
            return serialization.load_pem_private_key(f.read(), password=password.encode("utf-8"))
    except (ValueError, TypeError, OSError) as e:
        raise ErrorClave("No se ha podido descifrar la clave privada") from e


def cargar_clave_publica(ruta):
    try:
        with open(ruta, "rb") as f:
            return serialization.load_pem_public_key(f.read())
    except (ValueError, OSError) as e:
        raise ErrorClave("No se ha podido cargar la clave pública") from e


def huella(clave_publica):
    # Huella SHA-256 de la clave pública: permite compararla con la publicada por la pastelería,
    # pero no es un certificado (nadie de confianza la vincula con una identidad)
    der = clave_publica.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    digest = hashes.Hash(hashes.SHA256())
    digest.update(der)
    return digest.finalize().hex()



# ---------- Cifrado asimétrico (RSA-OAEP) para envolver claves ----------

def _oaep():
    return padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None)


# Cifrado híbrido: RSA protege la clave AES del pedido, en lugar
# de cifrar directamente todo su contenido, que se cifra con AES-GCM.
def envolver_clave_rsa(clave_publica, clave):
    envuelta = clave_publica.encrypt(clave, _oaep())
    log(f"Clave del pedido envuelta con RSA-{clave_publica.key_size}-OAEP-SHA256")
    return a_b64(envuelta)


def desenvolver_clave_rsa(clave_privada, envuelta_b64):
    try:
        return clave_privada.decrypt(de_b64(envuelta_b64), _oaep())
    except (ValueError, TypeError) as e:
        log("RSA-OAEP: no se ha podido desenvolver la clave, datos rechazados")
        raise ErrorIntegridad("La clave envuelta del pedido no es válida") from e



# ---------- Firma digital (ECDSA P-256 + SHA-256) ----------

# La pastelería firma con su clave privada. La firma permite comprobar
# la integridad del justificante y autenticar su origen si se confía
# en la clave pública utilizada para verificarla.
def firmar(clave_privada, datos):
    firma = clave_privada.sign(datos, ec.ECDSA(hashes.SHA256()))
    log(f"Firma ECDSA {clave_privada.curve.name} + SHA-256 generada ({len(firma)} bytes DER)")
    return a_b64(firma)


def verificar_firma(clave_publica, datos, firma_b64):
    try:
        clave_publica.verify(de_b64(firma_b64), datos, ec.ECDSA(hashes.SHA256()))
    except (InvalidSignature, ValueError, TypeError) as e:
        log("Firma ECDSA INVÁLIDA, justificante rechazado")
        raise FirmaInvalida("La firma no corresponde al contenido del justificante") from e
    log(f"Firma ECDSA {clave_publica.curve.name} + SHA-256 verificada correctamente")
