"""Pruebas positivas y negativas de SweetSecure"""

# Ejecutar desde la carpeta del proyecto con:  python -m unittest -v


import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date, timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cripto
import interfaz
import main
from almacen import guardar_json, leer_json
from pedidos import (CATALOGO, CONFIRMADO, MANIPULADO, PENDIENTE, ErrorPedido, ErrorPermisos, GestorPedidos,
                     construir_caja, construir_tarta, euros, fecha_es, parsear_cantidad, parsear_fecha)
from usuarios import ROL_ADMIN, ErrorAutenticacion, ErrorUsuario, GestorUsuarios

PASS_ADMIN = "Admin#Prueba1"
PASS_ANA = "Ana#Segura22"
PASS_LUIS = "Luis#Segura33"


def fecha_valida():
    return (date.today() + timedelta(days=5)).strftime("%d/%m/%Y")


def tarta_ejemplo():
    return construir_tarta("Chocolate oscuro", "Ganache de chocolate", "Caramelo salado", 2,
                           "Feliz cumple", fecha_valida())


def modificar_b64(texto):
    # Cambia un bit del primer byte para simular una manipulación
    datos = bytearray(cripto.de_b64(texto))
    datos[0] ^= 0x01
    return cripto.a_b64(bytes(datos))


class BaseSweetSecure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cripto.DEBUG = False
        # Se reducen las iteraciones solo en pruebas para que se ejecuten rápido
        cls.iteraciones_reales = cripto.PBKDF2_ITERACIONES
        cripto.PBKDF2_ITERACIONES = 1_000

    @classmethod
    def tearDownClass(cls):
        cripto.PBKDF2_ITERACIONES = cls.iteraciones_reales

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.usuarios = GestorUsuarios(self.dir)
        self.pedidos = GestorPedidos(self.dir)
        self.usuarios.registrar("admin", PASS_ADMIN, rol=ROL_ADMIN)
        self.usuarios.registrar("ana", PASS_ANA)
        self.usuarios.registrar("luis", PASS_LUIS)
        self.admin = self.usuarios.autenticar("admin", PASS_ADMIN)
        self.ana = self.usuarios.autenticar("ana", PASS_ANA)
        self.luis = self.usuarios.autenticar("luis", PASS_LUIS)

    def tearDown(self):
        shutil.rmtree(self.dir)

    def ruta(self, nombre):
        return os.path.join(self.dir, nombre)

    def texto(self, nombre):
        with open(self.ruta(nombre), encoding="utf-8") as f:
            return f.read()

    def pedido_confirmado(self):
        pedido_id = self.pedidos.crear(self.ana, tarta_ejemplo())
        self.pedidos.confirmar(self.admin, pedido_id)
        return pedido_id


class TestAutenticacion(BaseSweetSecure):
    def test_login_correcto(self):
        self.assertEqual(self.ana.username, "ana")
        self.assertEqual(self.ana.rol, "cliente")

    def test_password_no_se_guarda_en_claro(self):
        contenido = self.texto("usuarios.json")
        self.assertNotIn(PASS_ANA, contenido)
        datos = leer_json(self.ruta("usuarios.json"))
        self.assertNotEqual(datos["ana"]["sal_login"], datos["luis"]["sal_login"])
        self.assertNotEqual(datos["ana"]["sal_login"], datos["ana"]["sal_cifrado"])

    def test_misma_password_distinto_hash(self):
        self.usuarios.registrar("eva", PASS_ANA)
        datos = leer_json(self.ruta("usuarios.json"))
        self.assertNotEqual(datos["ana"]["hash"], datos["eva"]["hash"])

    def test_password_incorrecta_rechazada(self):
        with self.assertRaises(ErrorAutenticacion):
            self.usuarios.autenticar("ana", "Ana#Segura23")

    def test_usuario_inexistente_mismo_mensaje(self):
        with self.assertRaises(ErrorAutenticacion) as e1:
            self.usuarios.autenticar("nadie", PASS_ANA)
        with self.assertRaises(ErrorAutenticacion) as e2:
            self.usuarios.autenticar("ana", "Incorrecta#1")
        self.assertEqual(str(e1.exception), str(e2.exception))

    def test_password_debil_rechazada(self):
        for debil in ["Co1A!", "sinmayuscula1!", "SinNumero!!", "SinSimbolo123"]:
            with self.assertRaises(ErrorUsuario):
                self.usuarios.registrar("nuevo", debil)

    def test_usuario_duplicado_rechazado(self):
        with self.assertRaises(ErrorUsuario):
            self.usuarios.registrar("ana", PASS_LUIS)

    def test_username_invalido_rechazado(self):
        with self.assertRaises(ErrorUsuario):
            self.usuarios.registrar("../hack", PASS_LUIS)


class TestCifrado(BaseSweetSecure):
    def test_cifrado_y_descifrado_cliente_y_admin(self):
        pedido = tarta_ejemplo()
        pedido_id = self.pedidos.crear(self.ana, pedido)
        item_ana = self.pedidos.mis_pedidos(self.ana)[0]
        self.assertIsNone(item_ana["error"])
        self.assertEqual(item_ana["pedido"], pedido)
        item_admin = [p for p in self.pedidos.todos(self.admin) if p["id"] == pedido_id][0]
        self.assertEqual(item_admin["pedido"], pedido)

    def test_pedido_no_se_guarda_en_claro(self):
        self.pedidos.crear(self.ana, tarta_ejemplo())
        contenido = self.texto("pedidos.json")
        self.assertNotIn("Caramelo salado", contenido)
        self.assertNotIn("Feliz cumple", contenido)

    def test_nonces_y_claves_distintos_para_el_mismo_pedido(self):
        id1 = self.pedidos.crear(self.ana, tarta_ejemplo())
        id2 = self.pedidos.crear(self.ana, tarta_ejemplo())
        datos = leer_json(self.ruta("pedidos.json"))
        self.assertNotEqual(datos[id1]["datos"]["nonce"], datos[id2]["datos"]["nonce"])
        self.assertNotEqual(datos[id1]["datos"]["cifrado"], datos[id2]["datos"]["cifrado"])

    def _manipular(self, campo, subcampo):
        pedido_id = self.pedidos.crear(self.ana, tarta_ejemplo())
        datos = leer_json(self.ruta("pedidos.json"))
        datos[pedido_id][campo][subcampo] = modificar_b64(datos[pedido_id][campo][subcampo])
        guardar_json(self.ruta("pedidos.json"), datos)
        return pedido_id

    def test_cifrado_modificado_rechazado(self):
        self._manipular("datos", "cifrado")
        item = self.pedidos.mis_pedidos(self.ana)[0]
        self.assertIsNone(item["pedido"])
        self.assertIsNotNone(item["error"])

    def test_tag_modificado_rechazado(self):
        pedido_id = self.pedidos.crear(self.ana, tarta_ejemplo())
        datos = leer_json(self.ruta("pedidos.json"))
        # El tag de GCM son los últimos 16 bytes del texto cifrado
        cifrado = bytearray(cripto.de_b64(datos[pedido_id]["datos"]["cifrado"]))
        cifrado[-1] ^= 0x01
        datos[pedido_id]["datos"]["cifrado"] = cripto.a_b64(bytes(cifrado))
        guardar_json(self.ruta("pedidos.json"), datos)
        self.assertIsNone(self.pedidos.mis_pedidos(self.ana)[0]["pedido"])

    def test_nonce_modificado_rechazado(self):
        self._manipular("datos", "nonce")
        self.assertIsNone(self.pedidos.mis_pedidos(self.ana)[0]["pedido"])

    def test_intercambio_entre_pedidos_rechazado(self):
        id1 = self.pedidos.crear(self.ana, tarta_ejemplo())
        id2 = self.pedidos.crear(self.ana, construir_caja("cupcakes", "Limón", 6, fecha_valida()))
        datos = leer_json(self.ruta("pedidos.json"))
        # Se copia el pedido cifrado y la clave del pedido 1 dentro del pedido 2 (ataque de cortar y pegar)
        datos[id2]["datos"] = datos[id1]["datos"]
        datos[id2]["clave_cliente"] = datos[id1]["clave_cliente"]
        guardar_json(self.ruta("pedidos.json"), datos)
        resultado = {p["id"]: p for p in self.pedidos.mis_pedidos(self.ana)}
        self.assertIsNotNone(resultado[id1]["pedido"])
        self.assertIsNone(resultado[id2]["pedido"])

    def test_cambiar_cliente_del_pedido_rechazado(self):
        pedido_id = self.pedidos.crear(self.ana, tarta_ejemplo())
        datos = leer_json(self.ruta("pedidos.json"))
        datos[pedido_id]["cliente"] = "luis"
        guardar_json(self.ruta("pedidos.json"), datos)
        item = [p for p in self.pedidos.todos(self.admin) if p["id"] == pedido_id][0]
        self.assertIsNone(item["pedido"])

    def test_clave_incorrecta_rechazada(self):
        with self.assertRaises(cripto.ErrorIntegridad):
            paquete = cripto.cifrar_aes_gcm(cripto.generar_clave_aes(), b"pedido", b"aad")
            cripto.descifrar_aes_gcm(cripto.generar_clave_aes(), paquete, b"aad")

    def test_clave_envuelta_rsa_modificada_rechazada(self):
        pedido_id = self.pedidos.crear(self.ana, tarta_ejemplo())
        datos = leer_json(self.ruta("pedidos.json"))
        datos[pedido_id]["clave_pasteleria"] = modificar_b64(datos[pedido_id]["clave_pasteleria"])
        guardar_json(self.ruta("pedidos.json"), datos)
        self.assertIsNone(self.pedidos.todos(self.admin)[0]["pedido"])


class TestFirma(BaseSweetSecure):
    def test_firma_y_verificacion_correctas(self):
        pedido_id = self.pedido_confirmado()
        contenido = self.pedidos.verificar_guardada(self.ana, pedido_id)
        self.assertEqual(contenido["pedido_id"], pedido_id)
        self.assertEqual(contenido["estado"], "CONFIRMADO")

    def test_confirmacion_alterada_rechazada(self):
        pedido_id = self.pedido_confirmado()
        ruta = self.pedidos.exportar(self.ana, pedido_id)
        confirmacion = leer_json(ruta)
        confirmacion["contenido"]["total_eur"] = 1.0
        guardar_json(ruta, confirmacion)
        with self.assertRaises(cripto.FirmaInvalida):
            self.pedidos.verificar_fichero(self.ana, ruta, pedido_id)

    def test_firma_modificada_rechazada(self):
        pedido_id = self.pedido_confirmado()
        confirmaciones = leer_json(self.ruta("confirmaciones.json"))
        confirmaciones[pedido_id]["firma"] = modificar_b64(confirmaciones[pedido_id]["firma"])
        guardar_json(self.ruta("confirmaciones.json"), confirmaciones)
        with self.assertRaises(cripto.FirmaInvalida):
            self.pedidos.verificar_guardada(self.ana, pedido_id)

    def test_firma_con_otra_clave_rechazada(self):
        pedido_id = self.pedido_confirmado()
        confirmaciones = leer_json(self.ruta("confirmaciones.json"))
        contenido = confirmaciones[pedido_id]["contenido"]
        otra_clave = cripto.ec.generate_private_key(cripto.CURVA_FIRMA)
        confirmaciones[pedido_id]["firma"] = cripto.firmar(otra_clave, cripto.bytes_canonicos(contenido))
        guardar_json(self.ruta("confirmaciones.json"), confirmaciones)
        with self.assertRaises(cripto.FirmaInvalida):
            self.pedidos.verificar_guardada(self.ana, pedido_id)

    def test_confirmacion_reutilizada_en_otro_pedido_rechazada(self):
        id_confirmado = self.pedido_confirmado()
        id_pendiente = self.pedidos.crear(self.ana, tarta_ejemplo())
        ruta = self.pedidos.exportar(self.ana, id_confirmado)
        # La firma es válida, pero corresponde a otro pedido: es un intento de repetición
        with self.assertRaises(cripto.FirmaInvalida):
            self.pedidos.verificar_fichero(self.ana, ruta, id_pendiente)

    def test_confirmacion_no_se_firma_dos_veces(self):
        pedido_id = self.pedido_confirmado()
        with self.assertRaises(ErrorPedido):
            self.pedidos.confirmar(self.admin, pedido_id)

    def test_no_se_firma_pedido_manipulado(self):
        pedido_id = self.pedidos.crear(self.ana, tarta_ejemplo())
        datos = leer_json(self.ruta("pedidos.json"))
        datos[pedido_id]["datos"]["cifrado"] = modificar_b64(datos[pedido_id]["datos"]["cifrado"])
        guardar_json(self.ruta("pedidos.json"), datos)
        with self.assertRaises(cripto.ErrorIntegridad):
            self.pedidos.confirmar(self.admin, pedido_id)

