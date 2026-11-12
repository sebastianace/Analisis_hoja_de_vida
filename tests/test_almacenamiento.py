"""Pruebas de almacenamiento.py: persistencia, idempotencia y filtros."""

import json
import os
import stat

import pytest
from conftest import analisis_valido

import almacenamiento as alm
import analisis as an


def registro(id_="a1", candidato="Laura Gómez", puesto="Backend Python", puntaje=72,
             fecha="2026-11-12T10:00:00+00:00"):
    analisis = an.AnalisisCV.model_validate(analisis_valido())
    return alm.crear_registro(
        candidato, puesto, analisis, puntaje, an.nivel(puntaje),
        an.PESOS_POR_DEFECTO, "modelo-de-prueba",
        version_prompt="1.0", registro_id=id_, fecha_utc=fecha,
    )


# --------------------------------------------------------------------------
# Lectura
# --------------------------------------------------------------------------
def test_archivo_inexistente_devuelve_estructura_vacia(tmp_path):
    ruta = tmp_path / "no_existe.json"
    assert alm.cargar_historial(ruta) == {"version": 1, "evaluaciones": []}
    assert not ruta.exists()  # no se crea por leerlo


def test_json_danado_lanza_error_y_se_conserva(tmp_path):
    ruta = tmp_path / "historial.json"
    ruta.write_text("{roto", encoding="utf-8")
    with pytest.raises(alm.ErrorArchivoHistorial):
        alm.cargar_historial(ruta)
    assert ruta.read_text(encoding="utf-8") == "{roto"


@pytest.mark.parametrize("contenido", [
    '[]',
    '{"version": 2, "evaluaciones": []}',
    '{"version": 1, "evaluaciones": {}}',
    '{"version": 1, "evaluaciones": ["texto"]}',
])
def test_esquema_inesperado_lanza_error(tmp_path, contenido):
    ruta = tmp_path / "historial.json"
    ruta.write_text(contenido, encoding="utf-8")
    with pytest.raises(alm.ErrorArchivoHistorial):
        alm.cargar_historial(ruta)


# --------------------------------------------------------------------------
# Guardado
# --------------------------------------------------------------------------
def test_guardar_crea_archivo_y_no_pierde_previos(tmp_path):
    ruta = tmp_path / "historial.json"
    assert alm.guardar_evaluacion(ruta, registro("a1")) is True
    assert alm.guardar_evaluacion(ruta, registro("a2", candidato="Juan Pérez")) is True

    datos = alm.cargar_historial(ruta)
    assert [r["id"] for r in datos["evaluaciones"]] == ["a1", "a2"]
    assert datos["evaluaciones"][1]["candidato"] == "Juan Pérez"


def test_mismo_id_no_se_duplica(tmp_path):
    ruta = tmp_path / "historial.json"
    alm.guardar_evaluacion(ruta, registro("a1"))
    assert alm.guardar_evaluacion(ruta, registro("a1")) is False
    assert len(alm.cargar_historial(ruta)["evaluaciones"]) == 1


def test_dos_candidatos_distintos_son_dos_registros(tmp_path):
    ruta = tmp_path / "historial.json"
    alm.guardar_evaluacion(ruta, registro("a1", candidato="Laura Gómez"))
    alm.guardar_evaluacion(ruta, registro("a2", candidato="Laura Gómez"))
    # Mismo nombre, envíos independientes: dos registros con ids distintos.
    assert len(alm.cargar_historial(ruta)["evaluaciones"]) == 2


def test_no_se_guarda_sobre_un_archivo_danado(tmp_path):
    ruta = tmp_path / "historial.json"
    ruta.write_text("{roto", encoding="utf-8")
    with pytest.raises(alm.ErrorArchivoHistorial):
        alm.guardar_evaluacion(ruta, registro("a1"))
    assert ruta.read_text(encoding="utf-8") == "{roto"


def test_se_escribe_utf8_legible(tmp_path):
    ruta = tmp_path / "historial.json"
    alm.guardar_evaluacion(ruta, registro("a1", candidato="Laura Gómez"))
    crudo = ruta.read_text(encoding="utf-8")
    assert "Laura Gómez" in crudo  # ensure_ascii=False


def test_registro_sin_campos_es_rechazado(tmp_path):
    with pytest.raises(ValueError):
        alm.guardar_evaluacion(tmp_path / "h.json", {"id": "a1"})


def test_puntaje_fuera_de_rango_es_rechazado(tmp_path):
    malo = registro("a1")
    malo["puntaje"] = 150
    with pytest.raises(ValueError):
        alm.guardar_evaluacion(tmp_path / "h.json", malo)


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0,
                    reason="los permisos de solo lectura no aplican aquí")
def test_destino_sin_permisos_sube_error_y_conserva(tmp_path):
    carpeta = tmp_path / "solo_lectura"
    carpeta.mkdir()
    ruta = carpeta / "historial.json"
    alm.guardar_evaluacion(ruta, registro("a1"))
    antes = ruta.read_text(encoding="utf-8")
    carpeta.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        with pytest.raises(alm.ErrorEscritura):
            alm.guardar_evaluacion(ruta, registro("a2"))
        assert ruta.read_text(encoding="utf-8") == antes
    finally:
        carpeta.chmod(stat.S_IRWXU)
    # No quedan archivos temporales a medias.
    assert [p.name for p in carpeta.iterdir()] == ["historial.json"]


def test_el_archivo_final_es_json_valido(tmp_path):
    ruta = tmp_path / "historial.json"
    alm.guardar_evaluacion(ruta, registro("a1"))
    alm.guardar_evaluacion(ruta, registro("a2"))
    json.loads(ruta.read_text(encoding="utf-8"))  # no lanza


# --------------------------------------------------------------------------
# Consulta y ranking (funciones puras)
# --------------------------------------------------------------------------
@pytest.fixture
def muestras():
    return [
        registro("a1", "Laura Gómez", "Backend Python", 85, "2026-11-10T10:00:00+00:00"),
        registro("a2", "Juan Pérez", "Backend Python", 60, "2026-11-11T10:00:00+00:00"),
        registro("a3", "Ana Ruiz", "Frontend React", 90, "2026-11-12T10:00:00+00:00"),
        registro("a4", "Luis Soto", "Backend Python", 60, "2026-11-12T11:00:00+00:00"),
    ]


def test_sin_filtros_devuelve_todo(muestras):
    assert len(alm.consultar_evaluaciones(muestras)) == 4


def test_filtro_por_puesto(muestras):
    assert len(alm.consultar_evaluaciones(muestras, puesto_titulo="Backend Python")) == 3


def test_filtro_por_puntaje_minimo(muestras):
    assert len(alm.consultar_evaluaciones(muestras, puntaje_minimo=80)) == 2


def test_filtro_por_candidato_no_distingue_mayusculas(muestras):
    assert len(alm.consultar_evaluaciones(muestras, candidato="laura")) == 1


def test_filtros_combinados(muestras):
    resultado = alm.consultar_evaluaciones(
        muestras, puesto_titulo="Backend Python", puntaje_minimo=80
    )
    assert [r["candidato"] for r in resultado] == ["Laura Gómez"]


def test_consultar_no_modifica_la_lista_original(muestras):
    copia = list(muestras)
    alm.consultar_evaluaciones(muestras, puntaje_minimo=80)
    assert muestras == copia


def test_ranking_ordena_por_puntaje_y_desempata_por_fecha(muestras):
    ordenados = alm.ranking(muestras)
    assert [r["id"] for r in ordenados] == ["a3", "a1", "a4", "a2"]


def test_puestos_registrados(muestras):
    assert alm.puestos_registrados(muestras) == ["Backend Python", "Frontend React"]


def test_ranking_de_lista_vacia():
    assert alm.ranking([]) == []
