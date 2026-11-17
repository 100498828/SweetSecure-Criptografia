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
