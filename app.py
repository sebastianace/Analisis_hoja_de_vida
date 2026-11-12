"""CV Rank: interfaz Streamlit.

Decisiones de interfaz:
- El puntaje que se muestra lo calcula Python con los pesos que elige quien
  evalúa; el modelo nunca devuelve un porcentaje global.
- Sin streaming: se necesita el resultado estructurado completo (`invoke`).
- El UUID del envío se genera antes de evaluar, así una reejecución de Streamlit
  o un reintento no crean un segundo registro.
"""

import json
import uuid

import streamlit as st

import almacenamiento as alm
import analisis as an
import documentos as doc
from informe import informe_markdown, informe_ranking

st.set_page_config(page_title="CV Rank", page_icon="📄", layout="wide")
st.title("📄 CV Rank")
st.caption(
    "Evalúa el ajuste documental de una hoja de vida al puesto que describas. "
    "Mide lo que el documento demuestra, no a la persona, y no decide contrataciones."
)

# --------------------------------------------------------------------------
# Carga inicial: si el historial está dañado se muestra el error y se detiene
# la app SIN modificar ningún archivo.
# --------------------------------------------------------------------------
try:
    alm.cargar_historial(alm.RUTA_HISTORIAL)
except alm.ErrorArchivoHistorial as e:
    st.error(
        f"El historial está dañado y no se modificará: {e}\n\n"
        "Corrígelo o restáuralo manualmente y vuelve a cargar la página."
    )
    st.stop()

st.session_state.setdefault("pesos", dict(an.PESOS_POR_DEFECTO))
st.session_state.setdefault("ultimos_resultados", [])


def mostrar_criterios(registro):
    """Tabla de criterios con pesos, puntuaciones y citas."""
    filas = []
    for criterio in registro["criterios"]:
        filas.append({
            "Criterio": an.CRITERIOS.get(criterio["codigo"], criterio["codigo"]),
            "Peso": registro["pesos"].get(criterio["codigo"], 0),
            "Puntuación": criterio["puntuacion"] if criterio["aplica"] else None,
            "Solicitado": "Sí" if criterio["aplica"] else "No",
            "Justificación": criterio["justificacion"],
        })
    st.dataframe(filas, width="stretch", hide_index=True)

    with st.expander("Ver las citas textuales que respaldan cada criterio"):
        hubo = False
        for criterio in registro["criterios"]:
            if not criterio["evidencias"]:
                continue
            hubo = True
            st.markdown(f"**{an.CRITERIOS.get(criterio['codigo'], criterio['codigo'])}**")
            for cita in criterio["evidencias"]:
                st.markdown(f"> {cita}")
        if not hubo:
            st.info("El modelo no citó ninguna sección del CV.")


def mostrar_resultado(registro):
    """Encabezado, métricas y detalle de una evaluación."""
    c1, c2, c3 = st.columns([2, 1, 1])
    c1.subheader(registro["candidato"])
    c2.metric("Puntaje de ajuste", f"{registro['puntaje']} / 100")
    c3.metric("Nivel", registro["nivel"])
    st.write(registro["resumen"])
    mostrar_criterios(registro)

    col_f, col_b, col_s = st.columns(3)
    with col_f:
        st.markdown("**Fortalezas**")
        for item in registro["fortalezas"]:
            st.markdown(f"- {item}")
    with col_b:
        st.markdown("**Brechas**")
        for item in registro["brechas"]:
            st.markdown(f"- {item}")
    with col_s:
        st.markdown("**Siguientes pasos**")
        for item in registro["siguientes_pasos"]:
            st.markdown(f"- {item}")

    st.download_button(
        "⬇️ Descargar informe (Markdown)",
        data=informe_markdown(registro),
        file_name=f"informe_{registro['candidato'].replace(' ', '_')}.md",
        mime="text/markdown",
        key=f"informe_{registro['id']}",
    )


def procesar_cv(nombre_archivo, contenido, puesto_texto, puesto_titulo, pesos, envio_id):
    """Extrae, evalúa y guarda UN CV. Devuelve (registro, error) con uno de los dos en None."""
    candidato = nombre_archivo.rsplit(".", 1)[0].replace("_", " ").strip() or "Sin nombre"
    try:
        texto_cv = doc.extraer_texto(nombre_archivo, contenido)
    except doc.ErrorDocumento as e:
        return None, f"**{candidato}** · No se pudo leer el documento: {e}"

    try:
        resultado = an.evaluar_cv(texto_cv, puesto_texto)
    except an.ErrorEntrada as e:
        return None, f"**{candidato}** · Entrada no válida: {e}"
    except an.ErrorCitas as e:
        # Caso propio: el modelo inventó una cita. No se guarda nada.
        return None, f"**{candidato}** · Respuesta descartada por citas no verificables: {e}"
    except an.ErrorValidacion as e:
        return None, f"**{candidato}** · La respuesta del modelo no fue válida: {e}"
    except an.ErrorAPI as e:
        return None, f"**{candidato}** · No se pudo consultar el modelo: {e}"

    puntaje = an.puntaje_total(resultado, pesos)
    registro = alm.crear_registro(
        candidato, puesto_titulo, resultado, puntaje, an.nivel(puntaje), pesos,
        an.nombre_modelo(), version_prompt=an.VERSION_PROMPT, registro_id=envio_id,
    )
    try:
        alm.guardar_evaluacion(alm.RUTA_HISTORIAL, registro)
    except alm.ErrorHistorial as e:
        return None, f"**{candidato}** · La evaluación NO se guardó: {e}"
    return registro, None


# --------------------------------------------------------------------------
# Barra lateral: pesos de los criterios
# --------------------------------------------------------------------------
with st.sidebar:
    st.header("Pesos de los criterios")
    st.caption(
        "Quien evalúa decide qué pesa más en su vacante. Un criterio que el "
        "puesto no pide no resta: su peso se reparte entre los demás."
    )
    for codigo, etiqueta in an.CRITERIOS.items():
        st.session_state.pesos[codigo] = st.slider(
            etiqueta, 0, 50, st.session_state.pesos[codigo], step=5, key=f"peso_{codigo}"
        )
    total_pesos = sum(st.session_state.pesos.values())
    if total_pesos == 0:
        st.error("Al menos un criterio debe tener peso mayor que cero.")
    else:
        st.caption(f"Suma de pesos: {total_pesos} (se normaliza a 100 al calcular).")
    if st.button("Restablecer pesos"):
        for codigo, valor in an.PESOS_POR_DEFECTO.items():
            st.session_state[f"peso_{codigo}"] = valor
        st.rerun()

pestana_evaluar, pestana_comparar, pestana_historial = st.tabs(
    ["Evaluar", "Comparar candidatos", "Historial"]
)

# --------------------------------------------------------------------------
# Evaluar: uno o varios CV contra un mismo puesto
# --------------------------------------------------------------------------
with pestana_evaluar:
    col_puesto, col_cv = st.columns(2)
    with col_puesto:
        puesto_titulo = st.text_input("Título del puesto", placeholder="Desarrollador Java junior")
        puesto_texto = st.text_area(
            "Requisitos y responsabilidades del puesto",
            height=260,
            placeholder="Describe el puesto: tecnologías, experiencia esperada, formación…",
        )
    with col_cv:
        archivos = st.file_uploader(
            "Hojas de vida (PDF con texto seleccionable o TXT en UTF-8)",
            type=["pdf", "txt"],
            accept_multiple_files=True,
        )
        st.caption(
            "Puedes subir varias a la vez: cada una se evalúa contra el mismo puesto "
            "y después se comparan en la pestaña siguiente."
        )

    if st.button("Evaluar", type="primary"):
        if not puesto_titulo.strip():
            st.error("Escribe el título del puesto: identifica el grupo en el historial.")
        elif not archivos:
            st.error("Sube al menos una hoja de vida.")
        elif sum(st.session_state.pesos.values()) == 0:
            st.error("Asigna peso a al menos un criterio en la barra lateral.")
        else:
            pesos = dict(st.session_state.pesos)
            resultados, errores = [], []
            barra = st.progress(0.0, text="Evaluando…")
            for indice, archivo in enumerate(archivos, start=1):
                barra.progress(
                    (indice - 1) / len(archivos), text=f"Evaluando {archivo.name}…"
                )
                # El UUID nace antes de llamar al modelo: un reintento reutiliza
                # el mismo id y guardar_evaluacion lo rechaza como duplicado.
                envio_id = str(uuid.uuid4())
                registro, error = procesar_cv(
                    archivo.name, archivo.getvalue(), puesto_texto,
                    puesto_titulo.strip(), pesos, envio_id,
                )
                if error:
                    errores.append(error)
                else:
                    resultados.append(registro)
            barra.empty()
            st.session_state.ultimos_resultados = resultados
            for error in errores:
                st.error(error)
            if resultados:
                st.success(
                    f"{len(resultados)} evaluación(es) guardada(s) en el historial."
                )

    for registro in st.session_state.ultimos_resultados:
        st.divider()
        mostrar_resultado(registro)

# --------------------------------------------------------------------------
# Comparar: ranking de candidatos de un mismo puesto (solo lectura)
# --------------------------------------------------------------------------
with pestana_comparar:
    st.subheader("Comparar candidatos de un puesto")
    registros = alm.cargar_historial(alm.RUTA_HISTORIAL)["evaluaciones"]
    puestos = alm.puestos_registrados(registros)
    if not puestos:
        st.info("Todavía no hay evaluaciones. Empieza en la pestaña «Evaluar».")
    else:
        puesto_elegido = st.selectbox("Puesto", puestos)
        filtrados = alm.consultar_evaluaciones(registros, puesto_titulo=puesto_elegido)
        ordenados = alm.ranking(filtrados)

        c1, c2, c3 = st.columns(3)
        c1.metric("Candidatos", len(ordenados))
        c2.metric("Mejor puntaje", max(r["puntaje"] for r in ordenados))
        c3.metric(
            "Promedio", round(sum(r["puntaje"] for r in ordenados) / len(ordenados))
        )

        st.dataframe(
            [
                {
                    "#": posicion,
                    "Candidato": r["candidato"],
                    "Puntaje": r["puntaje"],
                    "Nivel": r["nivel"],
                    "Fecha (UTC)": r["fecha_utc"],
                }
                for posicion, r in enumerate(ordenados, start=1)
            ],
            width="stretch",
            hide_index=True,
        )
        st.download_button(
            "⬇️ Descargar comparación (Markdown)",
            data=informe_ranking(ordenados, puesto_elegido),
            file_name=f"comparacion_{puesto_elegido.replace(' ', '_')}.md",
            mime="text/markdown",
        )
        st.caption(
            "El orden refleja el ajuste documental al puesto descrito. "
            "Puntajes de evaluaciones distintas solo son comparables si usaron los mismos pesos."
        )

# --------------------------------------------------------------------------
# Historial: filtros y descarga (nunca llama al modelo)
# --------------------------------------------------------------------------
with pestana_historial:
    st.subheader("Historial de evaluaciones")
    registros = alm.cargar_historial(alm.RUTA_HISTORIAL)["evaluaciones"]
    if not registros:
        st.info("El historial está vacío.")
    else:
        c1, c2, c3 = st.columns(3)
        with c1:
            filtro_puesto = st.selectbox(
                "Puesto",
                [None] + alm.puestos_registrados(registros),
                format_func=lambda p: "Todos" if p is None else p,
            )
        with c2:
            filtro_candidato = st.text_input("Candidato contiene", "")
        with c3:
            filtro_minimo = st.slider("Puntaje mínimo", 0, 100, 0, step=5)

        filtrados = alm.consultar_evaluaciones(
            registros,
            puesto_titulo=filtro_puesto,
            puntaje_minimo=filtro_minimo or None,
            candidato=filtro_candidato.strip() or None,
        )
        if not filtrados:
            st.info("Ninguna evaluación coincide con los filtros.")
        else:
            st.metric("Total filtrado", len(filtrados))
            st.dataframe(
                [
                    {
                        "Fecha (UTC)": r["fecha_utc"],
                        "Candidato": r["candidato"],
                        "Puesto": r["puesto_titulo"],
                        "Puntaje": r["puntaje"],
                        "Nivel": r["nivel"],
                        "Modelo": r["modelo"],
                    }
                    for r in alm.ranking(filtrados)
                ],
                width="stretch",
                hide_index=True,
            )
            st.download_button(
                "⬇️ Descargar JSON filtrado",
                data=json.dumps(
                    {"version": 1, "evaluaciones": filtrados}, ensure_ascii=False, indent=2
                ),
                file_name="evaluaciones_filtradas.json",
                mime="application/json",
            )
