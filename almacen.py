"""Lectura y escritura de los ficheros JSON de la aplicación"""

import json
import os


class ErrorAlmacen(Exception):
    pass


def leer_json(ruta):
    if not os.path.exists(ruta):
        return {}
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            contenido = f.read().strip()
            return json.loads(contenido) if contenido else {}
    except (json.JSONDecodeError, OSError) as e:
        # Si el fichero está dañado o no se puede leer, se informa del error
        raise ErrorAlmacen(f"No se puede leer {os.path.basename(ruta)}: fichero dañado") from e


def guardar_json(ruta, datos):
    os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
    # Se escribe en un temporal y se renombra para no dejar el fichero a medias si algo falla
    temporal = ruta + ".tmp"
    with open(temporal, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=2, ensure_ascii=False)
    os.replace(temporal, ruta)
