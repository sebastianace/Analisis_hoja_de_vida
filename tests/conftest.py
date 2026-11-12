"""Configuración común de las pruebas.

Ninguna prueba llama a la API: la clave se borra del entorno y el modelo se
sustituye por un objeto falso con `.invoke`.
"""

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

CV_EJEMPLO = (
    "Laura Gómez. Desarrolladora backend con 4 años de experiencia en Python y Django. "
    "Construí una API REST que redujo el tiempo de respuesta en un 40 por ciento. "
    "Tecnóloga en desarrollo de software del SENA. Inglés nivel B2 certificado."
)
PUESTO_EJEMPLO = (
    "Desarrollador backend Python. Se requieren 3 años de experiencia, Django, "
    "APIs REST, PostgreSQL y nivel de inglés intermedio."
)


def criterio(codigo, puntuacion=80, aplica=True, evidencias=None):
    """Arma un criterio del contrato con valores razonables."""
    return {
        "codigo": codigo,
        "aplica": aplica,
        "puntuacion": puntuacion if aplica else 0,
        "requisito": f"El puesto pide {codigo}.",
        "justificacion": f"Se evaluó el criterio {codigo} con la evidencia disponible.",
        "evidencias": list(evidencias or []) if aplica else [],
    }


def analisis_valido(**cambios):
    """Diccionario que cumple el contrato, con citas que SÍ están en CV_EJEMPLO."""
    datos = {
        "resumen": "El CV demuestra experiencia backend en Python alineada con el puesto.",
        "criterios": [
            criterio("experiencia", 80, evidencias=["4 años de experiencia en Python"]),
            criterio("habilidades", 75, evidencias=["Python y Django"]),
            criterio("formacion", 60, evidencias=["Tecnóloga en desarrollo de software"]),
            criterio("logros", 70, evidencias=["redujo el tiempo de respuesta en un 40"]),
            criterio("idiomas", 50, evidencias=["Inglés nivel B2 certificado"]),
        ],
        "fortalezas": ["Experiencia comprobada en Python"],
        "brechas": ["No hay evidencia documental de PostgreSQL"],
        "siguientes_pasos": ["Añadir una línea sobre bases de datos usadas"],
    }
    datos.update(cambios)
    return datos


class CadenaFalsa:
    """Sustituye al modelo: cuenta llamadas y devuelve lo que se le indique."""

    def __init__(self, respuesta=None, error=None):
        self.respuesta = respuesta
        self.error = error
        self.llamadas = 0
        self.ultima_entrada = None

    def invoke(self, entrada):
        self.llamadas += 1
        self.ultima_entrada = entrada
        if self.error is not None:
            raise self.error
        return self.respuesta


@pytest.fixture(autouse=True)
def sin_api(monkeypatch):
    """Garantiza que ninguna prueba pueda usar la API real."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_MODEL", "modelo-de-prueba")


@pytest.fixture
def cadena_ok():
    return CadenaFalsa(respuesta=analisis_valido())
