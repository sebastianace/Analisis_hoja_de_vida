"""Extracción del texto de una hoja de vida, en memoria y sin guardar el archivo.

Se admiten PDF con texto seleccionable y TXT en UTF-8. Un PDF escaneado es solo
una imagen: no tiene texto que extraer y se rechaza con un mensaje claro en vez
de enviar una cadena vacía al modelo.
"""

from io import BytesIO
from pathlib import Path

MAX_BYTES = 5 * 1024 * 1024
MAX_PAGINAS = 15
MAX_CARACTERES = 30_000
MIN_CARACTERES = 80


class ErrorDocumento(Exception):
    """El documento no se admite o no tiene texto utilizable."""


def _limpiar(texto):
    # El byte nulo rompe la comparación de citas y algunos visores lo insertan.
    return texto.replace("\x00", "").strip()


def extraer_texto(nombre, contenido):
    """Devuelve el texto del archivo o lanza ErrorDocumento.

    `contenido` son los bytes del archivo; nada se escribe en disco.
    """
    if not contenido:
        raise ErrorDocumento("El archivo está vacío.")
    if len(contenido) > MAX_BYTES:
        raise ErrorDocumento("El archivo no puede pesar más de 5 MB.")

    extension = Path(nombre).suffix.lower()
    if extension == ".txt":
        try:
            texto = contenido.decode("utf-8-sig")
        except UnicodeDecodeError as e:
            raise ErrorDocumento("El TXT debe estar codificado en UTF-8.") from e
    elif extension == ".pdf":
        texto = _extraer_pdf(contenido)
    else:
        raise ErrorDocumento("Usa un PDF con texto seleccionable o un TXT en UTF-8.")

    texto = _limpiar(texto)
    if len(texto) < MIN_CARACTERES:
        raise ErrorDocumento(
            "No se encontró texto suficiente. Si el PDF es un escaneo, necesita OCR: "
            "exporta el CV de nuevo desde Word o Google Docs."
        )
    if len(texto) > MAX_CARACTERES:
        raise ErrorDocumento(f"El CV supera {MAX_CARACTERES:,} caracteres.")
    return texto


def _extraer_pdf(contenido):
    """Lee el PDF página por página. Import diferido para no exigir pypdf en los tests de TXT."""
    try:
        from pypdf import PdfReader
    except ImportError as e:  # pragma: no cover
        raise ErrorDocumento("Falta la dependencia pypdf: pip install -r requirements.txt") from e

    if not contenido.startswith(b"%PDF-"):
        raise ErrorDocumento("El contenido no corresponde a un PDF válido.")
    try:
        lector = PdfReader(BytesIO(contenido))
        if lector.is_encrypted:
            raise ErrorDocumento("El PDF está protegido. Sube una copia sin contraseña.")
        if len(lector.pages) > MAX_PAGINAS:
            raise ErrorDocumento(f"El CV no debe superar {MAX_PAGINAS} páginas.")
        partes = []
        for pagina in lector.pages:
            partes.append(pagina.extract_text() or "")
            if sum(map(len, partes)) > MAX_CARACTERES:
                raise ErrorDocumento(f"El CV supera {MAX_CARACTERES:,} caracteres.")
        return "\n\n".join(partes)
    except ErrorDocumento:
        raise
    except Exception as e:  # noqa: BLE001 - PDF corrupto o con estructura rara
        raise ErrorDocumento(
            "No se pudo leer el PDF. Exporta de nuevo el CV como PDF o TXT UTF-8."
        ) from e
