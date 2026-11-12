"""Informe en Markdown a partir de un registro del historial.

Función pura: recibe un diccionario y devuelve texto. No toca disco ni modelo,
así que se puede probar sin interfaz.
"""

from analisis import CRITERIOS


def informe_markdown(registro):
    """Devuelve el informe completo de UNA evaluación."""
    lineas = [
        f"# Evaluación de hoja de vida: {registro['candidato']}",
        "",
        f"- **Puesto:** {registro['puesto_titulo']}",
        f"- **Puntaje de ajuste:** {registro['puntaje']} / 100 ({registro['nivel']})",
        f"- **Fecha (UTC):** {registro['fecha_utc']}",
        f"- **Modelo:** {registro['modelo']} · versión de prompt {registro['version_prompt']}",
        "",
        "> El puntaje mide el ajuste documental del CV al puesto descrito. No es una",
        "> decisión de contratación ni una valoración de la persona.",
        "",
        "## Resumen",
        "",
        registro["resumen"],
        "",
        "## Criterios",
        "",
        "| Criterio | Peso | Puntuación | Justificación |",
        "| --- | ---: | ---: | --- |",
    ]
    for criterio in registro["criterios"]:
        etiqueta = CRITERIOS.get(criterio["codigo"], criterio["codigo"])
        peso = registro["pesos"].get(criterio["codigo"], 0)
        if criterio["aplica"]:
            puntuacion = f"{criterio['puntuacion']}"
        else:
            etiqueta += " (no solicitado)"
            puntuacion = "—"
        justificacion = criterio["justificacion"].replace("|", "/").replace("\n", " ")
        lineas.append(f"| {etiqueta} | {peso} | {puntuacion} | {justificacion} |")

    lineas += ["", "## Evidencias citadas del CV", ""]
    hay_citas = False
    for criterio in registro["criterios"]:
        if not criterio["evidencias"]:
            continue
        hay_citas = True
        lineas.append(f"**{CRITERIOS.get(criterio['codigo'], criterio['codigo'])}**")
        lineas += [f"- «{cita}»" for cita in criterio["evidencias"]]
        lineas.append("")
    if not hay_citas:
        lineas += ["Ninguna sección del CV respaldó los criterios solicitados.", ""]

    for titulo, clave in (
        ("Fortalezas", "fortalezas"),
        ("Brechas", "brechas"),
        ("Siguientes pasos", "siguientes_pasos"),
    ):
        lineas += [f"## {titulo}", ""]
        lineas += [f"- {item}" for item in registro[clave]]
        lineas.append("")

    return "\n".join(lineas).rstrip() + "\n"


def informe_ranking(registros, puesto_titulo):
    """Tabla comparativa de varios candidatos para un mismo puesto."""
    lineas = [
        f"# Comparación de candidatos: {puesto_titulo}",
        "",
        f"Candidatos evaluados: {len(registros)}",
        "",
        "| # | Candidato | Puntaje | Nivel | Fecha (UTC) |",
        "| ---: | --- | ---: | --- | --- |",
    ]
    for posicion, registro in enumerate(registros, start=1):
        lineas.append(
            f"| {posicion} | {registro['candidato']} | {registro['puntaje']} | "
            f"{registro['nivel']} | {registro['fecha_utc']} |"
        )
    lineas += [
        "",
        "> El orden refleja el ajuste documental al puesto descrito, no una",
        "> recomendación de contratación.",
    ]
    return "\n".join(lineas) + "\n"
