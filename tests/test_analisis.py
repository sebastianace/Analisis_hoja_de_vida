"""Pruebas de analisis.py. Ninguna llama a la API."""

import pytest
from conftest import CV_EJEMPLO, PUESTO_EJEMPLO, CadenaFalsa, analisis_valido, criterio

import analisis as an


# --------------------------------------------------------------------------
# Validación de entrada: se comprueba ANTES de llamar al modelo
# --------------------------------------------------------------------------
@pytest.mark.parametrize("cv", ["", "   ", "muy corto", "x" * 30_001])
def test_cv_invalido_no_llama_al_modelo(cv):
    cadena = CadenaFalsa(respuesta=analisis_valido())
    with pytest.raises(an.ErrorEntrada):
        an.evaluar_cv(cv, PUESTO_EJEMPLO, cadena=cadena)
    assert cadena.llamadas == 0


@pytest.mark.parametrize("puesto", ["", "   ", "corto", "y" * 12_001])
def test_puesto_invalido_no_llama_al_modelo(puesto):
    cadena = CadenaFalsa(respuesta=analisis_valido())
    with pytest.raises(an.ErrorEntrada):
        an.evaluar_cv(CV_EJEMPLO, puesto, cadena=cadena)
    assert cadena.llamadas == 0


# --------------------------------------------------------------------------
# Camino feliz
# --------------------------------------------------------------------------
def test_evaluacion_valida_devuelve_el_contrato(cadena_ok):
    resultado = an.evaluar_cv(CV_EJEMPLO, PUESTO_EJEMPLO, cadena=cadena_ok)
    assert isinstance(resultado, an.AnalisisCV)
    assert len(resultado.criterios) == 5
    assert cadena_ok.llamadas == 1


def test_la_cadena_recibe_cv_y_puesto(cadena_ok):
    an.evaluar_cv(CV_EJEMPLO, PUESTO_EJEMPLO, cadena=cadena_ok)
    assert set(cadena_ok.ultima_entrada) == {"cv", "puesto"}


def test_acepta_el_resultado_como_objeto_pydantic():
    objeto = an.AnalisisCV.model_validate(analisis_valido())
    cadena = CadenaFalsa(respuesta=objeto)
    assert an.evaluar_cv(CV_EJEMPLO, PUESTO_EJEMPLO, cadena=cadena).criterios


# --------------------------------------------------------------------------
# Verificación de citas: la defensa contra respuestas inventadas
# --------------------------------------------------------------------------
def test_cita_inventada_se_rechaza():
    inventado = analisis_valido(criterios=[
        criterio("experiencia", 100, evidencias=["diez años liderando equipos en Google"]),
        criterio("habilidades", 0, evidencias=[]),
        criterio("formacion", 0, evidencias=[]),
        criterio("logros", 0, evidencias=[]),
        criterio("idiomas", 0, evidencias=[]),
    ])
    cadena = CadenaFalsa(respuesta=inventado)
    with pytest.raises(an.ErrorCitas):
        an.evaluar_cv(CV_EJEMPLO, PUESTO_EJEMPLO, cadena=cadena)


def test_las_citas_toleran_acentos_mayusculas_y_saltos_de_linea():
    cv_con_saltos = CV_EJEMPLO.replace(" ", "\n", 6)
    analisis = an.AnalisisCV.model_validate(analisis_valido(criterios=[
        criterio("experiencia", 80, evidencias=["4 ANOS DE EXPERIENCIA en python"]),
        criterio("habilidades", 0, evidencias=[]),
        criterio("formacion", 0, evidencias=[]),
        criterio("logros", 0, evidencias=[]),
        criterio("idiomas", 0, evidencias=[]),
    ]))
    assert an.citas_no_encontradas(analisis, cv_con_saltos) == []


def test_citas_no_encontradas_devuelve_lista_vacia_cuando_todo_coincide():
    analisis = an.AnalisisCV.model_validate(analisis_valido())
    assert an.citas_no_encontradas(analisis, CV_EJEMPLO) == []


# --------------------------------------------------------------------------
# Coherencia del contrato
# --------------------------------------------------------------------------
def test_criterio_sin_citas_con_puntuacion_positiva_es_invalido():
    datos = analisis_valido(criterios=[
        criterio("experiencia", 90, evidencias=[]),
        criterio("habilidades", 0, evidencias=[]),
        criterio("formacion", 0, evidencias=[]),
        criterio("logros", 0, evidencias=[]),
        criterio("idiomas", 0, evidencias=[]),
    ])
    with pytest.raises(an.ErrorValidacion):
        an.evaluar_cv(CV_EJEMPLO, PUESTO_EJEMPLO, cadena=CadenaFalsa(respuesta=datos))


def test_criterio_no_solicitado_con_puntuacion_es_invalido():
    malo = criterio("idiomas", 0, aplica=False)
    malo["puntuacion"] = 70
    datos = analisis_valido(criterios=[
        criterio("experiencia", 80, evidencias=["4 años de experiencia en Python"]),
        criterio("habilidades", 0, evidencias=[]),
        criterio("formacion", 0, evidencias=[]),
        criterio("logros", 0, evidencias=[]),
        malo,
    ])
    with pytest.raises(an.ErrorValidacion):
        an.evaluar_cv(CV_EJEMPLO, PUESTO_EJEMPLO, cadena=CadenaFalsa(respuesta=datos))


def test_faltan_criterios_es_invalido():
    datos = analisis_valido(criterios=[criterio("experiencia", 0, aplica=False)])
    with pytest.raises(an.ErrorValidacion):
        an.evaluar_cv(CV_EJEMPLO, PUESTO_EJEMPLO, cadena=CadenaFalsa(respuesta=datos))


def test_ningun_criterio_aplicable_es_invalido():
    datos = analisis_valido(criterios=[
        criterio(codigo, 0, aplica=False) for codigo in an.CRITERIOS
    ])
    with pytest.raises(an.ErrorValidacion):
        an.evaluar_cv(CV_EJEMPLO, PUESTO_EJEMPLO, cadena=CadenaFalsa(respuesta=datos))


def test_cita_demasiado_corta_es_invalida():
    datos = analisis_valido(criterios=[
        criterio("experiencia", 80, evidencias=["Python"]),
        criterio("habilidades", 0, evidencias=[]),
        criterio("formacion", 0, evidencias=[]),
        criterio("logros", 0, evidencias=[]),
        criterio("idiomas", 0, evidencias=[]),
    ])
    with pytest.raises(an.ErrorValidacion):
        an.evaluar_cv(CV_EJEMPLO, PUESTO_EJEMPLO, cadena=CadenaFalsa(respuesta=datos))


# --------------------------------------------------------------------------
# Errores del proveedor: nunca se convierten en un puntaje de respaldo
# --------------------------------------------------------------------------
def test_fallo_de_api_sube_como_error_api():
    cadena = CadenaFalsa(error=ConnectionError("sin red"))
    with pytest.raises(an.ErrorAPI):
        an.evaluar_cv(CV_EJEMPLO, PUESTO_EJEMPLO, cadena=cadena)


def test_respuesta_nula_sube_como_error_validacion():
    with pytest.raises(an.ErrorValidacion):
        an.evaluar_cv(CV_EJEMPLO, PUESTO_EJEMPLO, cadena=CadenaFalsa(respuesta=None))


def test_sin_clave_no_se_puede_construir_la_cadena():
    with pytest.raises(an.ErrorAPI):
        an.construir_cadena()


def test_sin_modelo_configurado_falla(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "  ")
    with pytest.raises(an.ErrorAPI):
        an.nombre_modelo()


# --------------------------------------------------------------------------
# Puntaje: lo calcula Python, no el modelo
# --------------------------------------------------------------------------
def test_puntaje_con_pesos_por_defecto():
    analisis = an.AnalisisCV.model_validate(analisis_valido())
    # 80*35 + 75*30 + 60*15 + 70*12 + 50*8 = 7190 sobre 100 de peso total
    assert an.puntaje_total(analisis) == 72


def test_los_pesos_cambian_el_puntaje():
    analisis = an.AnalisisCV.model_validate(analisis_valido())
    solo_experiencia = {"experiencia": 100, "habilidades": 0, "formacion": 0,
                        "logros": 0, "idiomas": 0}
    assert an.puntaje_total(analisis, solo_experiencia) == 80


def test_un_criterio_no_solicitado_no_resta():
    datos = analisis_valido(criterios=[
        criterio("experiencia", 100, evidencias=["4 años de experiencia en Python"]),
        criterio("habilidades", 100, evidencias=["Python y Django"]),
        criterio("formacion", 100, evidencias=["Tecnóloga en desarrollo de software"]),
        criterio("logros", 100, evidencias=["redujo el tiempo de respuesta en un 40"]),
        criterio("idiomas", 0, aplica=False),
    ])
    analisis = an.AnalisisCV.model_validate(datos)
    # El peso de idiomas se reparte: el candidato sigue en 100, no baja a 92.
    assert an.puntaje_total(analisis) == 100


def test_pesos_todos_en_cero_es_error():
    analisis = an.AnalisisCV.model_validate(analisis_valido())
    with pytest.raises(an.ErrorValidacion):
        an.puntaje_total(analisis, dict.fromkeys(an.CRITERIOS, 0))


@pytest.mark.parametrize("puntaje,esperado", [
    (100, "Ajuste alto"), (80, "Ajuste alto"), (79, "Ajuste medio"),
    (60, "Ajuste medio"), (59, "Ajuste bajo"), (40, "Ajuste bajo"),
    (39, "Sin ajuste documental"), (0, "Sin ajuste documental"),
])
def test_umbrales_de_nivel(puntaje, esperado):
    assert an.nivel(puntaje) == esperado
