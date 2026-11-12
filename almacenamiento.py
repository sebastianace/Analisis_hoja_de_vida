"""Historial de evaluaciones en JSON.

Este módulo NO sabe nada de Streamlit ni del modelo de lenguaje: solo maneja
archivos y listas de diccionarios. Así se puede probar sin interfaz y sin API.
"""

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Rutas calculadas desde la ubicación de este archivo, no desde el directorio
# actual: la app funciona igual si se lanza desde otra carpeta.
RAIZ = Path(__file__).resolve().parent
RUTA_HISTORIAL = RAIZ / "datos" / "historial.json"

CAMPOS_REGISTRO = (
    "id", "fecha_utc", "candidato", "puesto_titulo", "puntaje", "nivel",
    "criterios", "resumen", "fortalezas", "brechas", "siguientes_pasos",
    "pesos", "modelo", "version_prompt",
)


# --------------------------------------------------------------------------
# Excepciones propias
# --------------------------------------------------------------------------
class ErrorHistorial(Exception):
    """Base común de los errores de almacenamiento."""


class ErrorArchivoHistorial(ErrorHistorial):
    """El archivo existe pero es JSON inválido o tiene otro esquema."""


class ErrorEscritura(ErrorHistorial):
    """No se pudo escribir el archivo del historial."""


# --------------------------------------------------------------------------
# Lectura
# --------------------------------------------------------------------------
def _estructura_vacia():
    return {"version": 1, "evaluaciones": []}


def cargar_historial(ruta=RUTA_HISTORIAL):
    """Lee el diccionario persistente {'version', 'evaluaciones'}.

    - Si el archivo no existe: devuelve la estructura vacía (sin crearlo).
    - Si existe pero está dañado: lanza ErrorArchivoHistorial. Jamás se
      reemplaza por una lista vacía, porque se perderían datos reales.
    """
    ruta = Path(ruta)
    if not ruta.exists():
        return _estructura_vacia()
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ErrorArchivoHistorial(f"El historial no es un JSON válido: {e}") from e

    if (
        not isinstance(datos, dict)
        or datos.get("version") != 1
        or not isinstance(datos.get("evaluaciones"), list)
    ):
        raise ErrorArchivoHistorial(
            "Esquema inesperado: se esperaba {'version': 1, 'evaluaciones': [...]}."
        )
    if not all(isinstance(r, dict) for r in datos["evaluaciones"]):
        raise ErrorArchivoHistorial("Todas las evaluaciones deben ser objetos JSON.")
    return datos


# --------------------------------------------------------------------------
# Creación y guardado
# --------------------------------------------------------------------------
def crear_registro(candidato, puesto_titulo, analisis, puntaje, nivel_texto, pesos,
                   modelo, *, version_prompt, registro_id=None, fecha_utc=None):
    """Arma el registro final.

    El programa pone el id, la fecha, el candidato, el puntaje y los metadatos;
    el modelo solo aporta las puntuaciones por criterio y el texto.

    `registro_id` permite generar el UUID ANTES de evaluar y reutilizarlo en los
    reintentos, de modo que guardar sea idempotente.
    """
    return {
        "id": registro_id or str(uuid.uuid4()),
        "fecha_utc": fecha_utc or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "candidato": candidato,
        "puesto_titulo": puesto_titulo,
        "puntaje": puntaje,
        "nivel": nivel_texto,
        "criterios": [
            {
                "codigo": c.codigo,
                "aplica": c.aplica,
                "puntuacion": c.puntuacion,
                "requisito": c.requisito,
                "justificacion": c.justificacion,
                "evidencias": list(c.evidencias),
            }
            for c in analisis.criterios
        ],
        "resumen": analisis.resumen,
        "fortalezas": list(analisis.fortalezas),
        "brechas": list(analisis.brechas),
        "siguientes_pasos": list(analisis.siguientes_pasos),
        "pesos": dict(pesos),
        "modelo": modelo,
        "version_prompt": version_prompt,
    }


def _validar_registro(registro):
    faltan = [c for c in CAMPOS_REGISTRO if c not in registro]
    if faltan:
        raise ValueError(f"Al registro le faltan campos: {faltan}")
    if not isinstance(registro["puntaje"], int) or not 0 <= registro["puntaje"] <= 100:
        raise ValueError(f"Puntaje inválido: {registro['puntaje']!r}")


def guardar_evaluacion(ruta, registro):
    """Añade `registro` al historial sin perder los anteriores.

    Devuelve True si se escribió y False si ya existía un registro con ese id
    (idempotencia: un reintento o una reejecución de Streamlit no duplica).
    Cualquier fallo sube como excepción; nunca se silencia, para que la interfaz
    no confirme un guardado que no ocurrió.
    """
    _validar_registro(registro)
    ruta = Path(ruta)
    # Lee el estado actual. Si el archivo está dañado, lanza y NO lo toca.
    datos = cargar_historial(ruta)

    if any(r.get("id") == registro["id"] for r in datos["evaluaciones"]):
        return False

    datos["evaluaciones"].append(registro)

    # Escritura atómica: se escribe un temporal en el MISMO directorio (mismo
    # sistema de archivos) y se reemplaza con os.replace. Si el programa se
    # interrumpe a mitad, el archivo original queda intacto, no a medias.
    tmp_nombre = None
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=ruta.parent, prefix=ruta.name + ".",
            suffix=".tmp", delete=False,
        ) as tmp:
            tmp_nombre = tmp.name
            json.dump(datos, tmp, ensure_ascii=False, indent=2)
            tmp.flush()
            os.fsync(tmp.fileno())  # fuerza el volcado a disco antes del reemplazo
        os.replace(tmp_nombre, ruta)
    except OSError as e:
        if tmp_nombre and os.path.exists(tmp_nombre):
            try:
                os.unlink(tmp_nombre)
            except OSError:
                pass
        raise ErrorEscritura(f"No se pudo escribir {ruta}: {e}") from e
    return True


# --------------------------------------------------------------------------
# Consulta (funciones puras: no tocan disco ni modelo)
# --------------------------------------------------------------------------
def consultar_evaluaciones(registros, puesto_titulo=None, puntaje_minimo=None, candidato=None):
    """Filtra el historial. `None` significa 'todos'. Los filtros se combinan con AND."""
    def coincide(r):
        if puesto_titulo is not None and r.get("puesto_titulo") != puesto_titulo:
            return False
        if puntaje_minimo is not None and r.get("puntaje", 0) < puntaje_minimo:
            return False
        if candidato is not None and candidato.lower() not in r.get("candidato", "").lower():
            return False
        return True

    return [r for r in registros if coincide(r)]


def ranking(registros):
    """Ordena de mayor a menor puntaje; a igual puntaje, el más reciente primero."""
    return sorted(registros, key=lambda r: (r.get("puntaje", 0), r.get("fecha_utc", "")), reverse=True)


def puestos_registrados(registros):
    """Títulos de puesto presentes en el historial, ordenados alfabéticamente."""
    return sorted({r.get("puesto_titulo", "") for r in registros if r.get("puesto_titulo")})
