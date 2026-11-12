# CV Rank

Aplicación en Streamlit que evalúa hojas de vida frente a un puesto usando
LangChain y un modelo de lenguaje. Devuelve un puntaje de 0 a 100 explicado por
criterios, con citas literales del documento, y guarda cada evaluación en JSON
para comparar candidatos después.

> El puntaje mide el **ajuste documental** del CV al puesto descrito. No es una
> decisión de contratación ni una valoración de la persona. El modelo no ve
> nombre, foto ni datos personales como criterio: el prompt le prohíbe usarlos.

## Qué hace

| Evaluar | Comparar | Historial |
| --- | --- | --- |
| Sube uno o varios CV (PDF o TXT) y describe el puesto. | Ranking de los candidatos de un mismo puesto. | Filtros por puesto, candidato y puntaje mínimo. |
| Ajusta el peso de cada criterio con los deslizadores. | Mejor puntaje y promedio del grupo. | Descarga del JSON filtrado. |
| Descarga el informe en Markdown con las citas. | Descarga de la comparación en Markdown. | Los datos siguen ahí tras reiniciar la app. |

## Instalación

Requiere Python 3.10 o superior.

```bash
cd cvrank
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Configuración

```bash
cp .env.example .env               # Windows: copy .env.example .env
```

Edita `.env` con una de las dos opciones. El archivo nunca se sube al repositorio.

**Con OpenAI:**

```dotenv
OPENAI_API_KEY=sk-tu_clave
OPENAI_MODEL=gpt-4o-mini
OPENAI_STRUCTURED_METHOD=json_schema
```

**Con Ollama en local, sin costo:**

```dotenv
OPENAI_API_KEY=ollama
OPENAI_MODEL=llama3.1
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_STRUCTURED_METHOD=function_calling
```

Requiere `ollama serve` activo y `ollama pull llama3.1`. Cada registro guarda el
modelo que se usó, para saber de dónde salió cada puntaje.

## Ejecución

```bash
streamlit run app.py
```

También funciona desde otra carpeta (`streamlit run /ruta/a/cvrank/app.py`),
porque las rutas se calculan desde la ubicación de los archivos.

Para probar sin tener un CV a mano, la carpeta `ejemplos/` trae tres hojas de
vida ficticias y una descripción de puesto. Súbelas las tres a la vez y revisa
la pestaña «Comparar candidatos».

## Pruebas

```bash
python -m pytest
```

Ninguna prueba llama a la API: el modelo se sustituye por un objeto falso y la
clave se borra del entorno durante los tests. Los resultados y los casos
pendientes están en [PRUEBAS.md](PRUEBAS.md).

## Arquitectura

```text
app.py              Interfaz Streamlit: tres pestañas, pesos ajustables, mensajes de error
analisis.py         Prompt, esquema AnalisisCV, verificación de citas y cálculo del puntaje
almacenamiento.py   Lectura y escritura atómica del historial, excepciones propias, filtros
documentos.py       Extracción de texto de PDF y TXT, en memoria
informe.py          Informe y comparación en Markdown (funciones puras)
datos/              historial.json, el registro persistente
ejemplos/           CVs y puesto ficticios para probar sin datos reales
tests/              pytest, sin llamadas a la API
```

Flujo de una evaluación: extraer texto → validar longitudes → generar el UUID del
envío → `evaluar_cv` → verificar que cada cita exista en el CV → calcular el
puntaje en Python con los pesos → `guardar_evaluacion` → mostrar el resultado.

## Decisiones técnicas

- **El modelo no calcula el puntaje.** Solo puntúa cada criterio de 0 a 100 y
  aporta citas. El puntaje global lo calcula `puntaje_total` con pesos visibles,
  así que es auditable y reproducible.
- **Pesos ajustables.** Quien evalúa decide qué pesa más en su vacante. Un
  criterio que el puesto no pide no resta: su peso se reparte entre los demás,
  de modo que nadie pierde puntos por algo que no se le exigió.
- **Verificación de citas.** Cada cita del modelo se busca en el texto del CV
  tras normalizar acentos, mayúsculas y saltos de línea. Si alguna no existe, la
  respuesta completa se descarta con `ErrorCitas` y no se guarda nada. Es la
  defensa concreta contra las invenciones del modelo.
- **Coherencia del contrato.** El esquema valida cada campo por separado; el
  `model_validator` valida la relación entre ellos: un criterio no solicitado
  debe tener 0 puntos y ninguna cita, y una puntuación positiva exige evidencia.
- **Sin duplicados en las reejecuciones.** Streamlit reejecuta el script con cada
  interacción. El UUID se crea al enviar, antes de llamar al modelo, y
  `guardar_evaluacion` rechaza un id que ya exista.
- **Escritura atómica.** Se escribe un archivo temporal en el mismo directorio y
  se reemplaza con `os.replace`. Un fallo no deja el JSON a medias.
- **Archivo dañado.** Se muestra el error y se detiene la app; nunca se
  sobrescribe el historial con una lista vacía.
- **Un fallo nunca es un puntaje.** Errores de entrada, de documento, de API, de
  validación y de citas son excepciones distintas con mensajes distintos. Ninguno
  produce un resultado de respaldo.
- **Datos no confiables.** El prompt declara el CV y el puesto como datos: una
  instrucción escrita dentro de ellos («asigna 100») se evalúa como texto, no se
  obedece.
- **Un solo escritor.** El reemplazo atómico evita archivos incompletos, pero no
  resuelve la escritura concurrente de varios usuarios. Eso requeriría SQLite o
  PostgreSQL.

## Límites conocidos

- Un PDF escaneado es una imagen: no tiene texto extraíble y se rechaza con un
  mensaje claro. Haría falta OCR, que no está incluido.
- Los puntajes de dos evaluaciones solo son comparables si usaron los mismos
  pesos. La app lo advierte en la pestaña de comparación.
- La calidad de la clasificación depende del modelo. Las pruebas automatizadas
  verifican el comportamiento de la aplicación, no el criterio del modelo.
