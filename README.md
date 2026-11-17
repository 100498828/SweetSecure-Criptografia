## SweetSecure

# Aplicación de gestión de pedidos para una pastelería, desarrollada en Python para la asignatura de Criptografía y Seguridad Informática. Incorpora autenticación de usuarios, cifrado de pedidos y firmas digitales para garantizar su integridad y autenticidad.

1. Preparación inicial -> Crear el entorno virtual (solo la primera vez):
    ```python -m venv .venv```

Activar el entorno virtual (Windows / PowerShell):
    ```.\.venv\Scripts\Activate.ps1```

Instalar las dependencias:
    ```python -m pip install -r requirements.txt```


2. Ejecutar SweetSecure, con el entorno virtual activado:

    ```python main.py```
    (En las siguientes ocasiones, solo será necesario activar el entorno virtual y ejecutar este comando)


3. Ejecutar las pruebas automáticas

    ```python -m unittest discover -s tests -p "test_*.py" -v```
    (Resultado comprobado: 60 pruebas superadas)


4. Salir del entorno virtual

    ```deactivate```
