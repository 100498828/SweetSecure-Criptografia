# SweetSecure 🎂

Aplicación de gestión de pedidos para una pastelería, desarrollada en Python para la asignatura de Criptografía y Seguridad Informática. Incorpora autenticación de usuarios, cifrado de pedidos y firmas digitales para proteger la confidencialidad, integridad y autenticidad de la información.

## 1. Preparación inicial

Abrir una terminal en la carpeta del proyecto.

**Crear el entorno virtual (solo la primera vez):**

```powershell
python -m venv .venv
```

**Activar el entorno virtual (Windows / PowerShell):**

```powershell
.\.venv\Scripts\Activate.ps1
```

**Instalar las dependencias:**

```powershell
python -m pip install -r requirements.txt
```

## 2. Ejecutar SweetSecure

Con el entorno virtual activado:

```powershell
python main.py
```

En las siguientes ocasiones, solo será necesario activar el entorno virtual y ejecutar este comando.

## 3. Ejecutar las pruebas automáticas

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

**Resultado comprobado:** 60 pruebas superadas, sin fallos ni errores.

## 4. Salir del entorno virtual

```powershell
deactivate
```