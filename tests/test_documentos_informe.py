"""Pruebas de documentos.py e informe.py."""

import pytest
from conftest import analisis_valido

import almacenamiento as alm
import analisis as an
import documentos as doc
from informe import informe_markdown, informe_ranking

TEXTO_LARGO = (
    "Laura Gómez. Desarrolladora backend con 4 años de experiencia en Python y Django. "
    "Construí una API REST. Tecnóloga del SENA. Inglés B2."
)


# --------------------------------------------------------------------------
# Extracción de documentos
# --------------------------------------------------------------------------
def test_txt_utf8_se_lee():
    assert "Laura Gómez" in doc.extraer_texto("cv.txt", TEXTO_LARGO.encode("utf-8"))


def test_txt_con_bom_se_lee():
    contenido = "\ufeff".encode("utf-8") + TEXTO_LARGO.encode("utf-8")
    assert doc.extraer_texto("cv.txt", contenido).startswith("Laura")


def test_archivo_vacio_se_rechaza():
    with pytest.raises(doc.ErrorDocumento):
        doc.extraer_texto("cv.txt", b"")


def test_texto_demasiado_corto_se_rechaza():
    with pytest.raises(doc.ErrorDocumento):
        doc.extraer_texto("cv.txt", "Hola".encode("utf-8"))


def test_extension_no_admitida_se_rechaza():
    with pytest.raises(doc.ErrorDocumento):
        doc.extraer_texto("cv.docx", TEXTO_LARGO.encode("utf-8"))


def test_archivo_demasiado_grande_se_rechaza():
    with pytest.raises(doc.ErrorDocumento):
        doc.extraer_texto("cv.txt", b"a" * (doc.MAX_BYTES + 1))


def test_txt_que_no_es_utf8_se_rechaza():
    with pytest.raises(doc.ErrorDocumento):
        doc.extraer_texto("cv.txt", TEXTO_LARGO.encode("latin-1") + b"\xff\xfe")


def test_pdf_falso_se_rechaza():
    with pytest.raises(doc.ErrorDocumento):
        doc.extraer_texto("cv.pdf", b"esto no es un pdf" * 20)


def test_se_eliminan_los_bytes_nulos():
    contenido = (TEXTO_LARGO + "\x00").encode("utf-8")
    assert "\x00" not in doc.extraer_texto("cv.txt", contenido)


# --------------------------------------------------------------------------
# Informes
# --------------------------------------------------------------------------
@pytest.fixture
def registro():
    analisis = an.AnalisisCV.model_validate(analisis_valido())
    return alm.crear_registro(
        "Laura Gómez", "Backend Python", analisis, 72, an.nivel(72),
        an.PESOS_POR_DEFECTO, "modelo-de-prueba",
        version_prompt="1.0", registro_id="a1", fecha_utc="2026-11-12T10:00:00+00:00",
    )


def test_el_informe_incluye_datos_clave(registro):
    texto = informe_markdown(registro)
    assert "Laura Gómez" in texto
    assert "72 / 100" in texto
    assert "Backend Python" in texto
    assert "modelo-de-prueba" in texto


def test_el_informe_incluye_las_citas(registro):
    assert "4 años de experiencia en Python" in informe_markdown(registro)


def test_el_informe_marca_los_criterios_no_solicitados():
    datos = analisis_valido()
    datos["criterios"][4] = {
        "codigo": "idiomas", "aplica": False, "puntuacion": 0,
        "requisito": "El puesto no pide idiomas.",
        "justificacion": "El puesto no menciona ningún idioma.",
        "evidencias": [],
    }
    analisis = an.AnalisisCV.model_validate(datos)
    registro = alm.crear_registro(
        "Laura", "Backend", analisis, 70, an.nivel(70), an.PESOS_POR_DEFECTO,
        "m", version_prompt="1.0", registro_id="a1",
    )
    assert "(no solicitado)" in informe_markdown(registro)


def test_el_ranking_ordena_y_numera(registro):
    otro = dict(registro, id="a2", candidato="Juan Pérez", puntaje=90)
    texto = informe_ranking(alm.ranking([registro, otro]), "Backend Python")
    assert texto.index("Juan Pérez") < texto.index("Laura Gómez")
    assert "| 1 | Juan Pérez" in texto
