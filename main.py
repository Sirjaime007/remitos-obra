
import base64
import json
import time
import streamlit as st
from google import genai
from google.genai import errors
import gspread
from google.oauth2.service_account import Credentials
from PIL import Image
from io import BytesIO

# ==================================================
# CONFIGURACION
# ==================================================

st.set_page_config(
    page_title="Control Remitos",
    page_icon="📥",
    layout="centered"
)

st.title("📥 Control Inteligente de Remitos")
st.caption("Extracción automática y registro en Google Sheets")

# Orden de preferencia: principal y respaldos
MODELOS = [
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
]

PROMPT = """
Lee cuidadosamente la imagen del remito.

Devuelve exclusivamente un objeto JSON válido con esta estructura:

{
  "fecha": "DD/MM/AAAA",
  "numero_remito": "string",
  "proveedor": "string",
  "cuit": "string",
  "total": 1234.56
}

Reglas:
- No inventes datos.
- Si un dato de texto falta o no es legible, devuelve "".
- Si el total no es identificable, devuelve null.
- El total debe ser numérico, sin símbolo monetario.
- Usa punto decimal.
- Conserva todos los dígitos del CUIT.
- No confundas factura con remito.
- Extrae el total final, no el subtotal.
- No agregues comentarios ni Markdown.
"""

# ==================================================
# FUNCIONES
# ==================================================

def preparar_imagen(archivo):
    """Comprime la imagen y devuelve Base64 y MIME."""

    imagen = Image.open(archivo).convert("RGB")

    # Limitar dimensiones, manteniendo legibilidad
    imagen.thumbnail((1600, 1600))

    buffer = BytesIO()
    imagen.save(buffer, format="JPEG", quality=88, optimize=True)

    imagen_b64 = base64.b64encode(
        buffer.getvalue()
    ).decode("utf-8")

    return imagen, imagen_b64


def es_error_temporal(error):
    """Identifica errores que pueden recuperarse."""

    codigo = getattr(error, "code", None)
    mensaje = str(error).lower()

    if codigo in (429, 500, 502, 503, 504):
        return True

    return any(frase in mensaje for frase in [
        "503 unavailable",
        "429 resource_exhausted",
        "500 internal",
        "502 bad gateway",
        "504 gateway timeout",
        "high demand",
        "temporarily unavailable",
        "model is currently experiencing high demand",
    ])


def extraer_datos(imagen_b64):
    """
    Prueba varios modelos.
    Hace hasta dos intentos por modelo ante errores temporales.
    """

    cliente = genai.Client(
        api_key=st.secrets["GEMINI_API_KEY"]
    )

    errores = []

    for modelo in MODELOS:

        for intento in range(2):

            try:
                respuesta = cliente.interactions.create(
                    model=modelo,
                    input=[
                        {
                            "type": "text",
                            "text": PROMPT
                        },
                        {
                            "type": "image",
                            "data": imagen_b64,
                            "mime_type": "image/jpeg"
                        }
                    ]
                )

                texto = respuesta.output_text

                if not texto:
                    raise ValueError(
                        "El modelo devolvió una respuesta vacía."
                    )

                texto = texto.strip()

                # Limpiar posibles bloques Markdown
                if texto.startswith("```"):
                    texto = texto.replace("```json", "", 1)
                    texto = texto.replace("```", "")
                    texto = texto.strip()

                datos = json.loads(texto)

                # Validar estructura mínima
                if not isinstance(datos, dict):
                    raise ValueError(
                        "La respuesta no es un objeto JSON."
                    )

                campos = [
                    "fecha",
                    "numero_remito",
                    "proveedor",
                    "cuit",
                    "total"
                ]

                for campo in campos:
                    if campo not in datos:
                        datos[campo] = (
                            None if campo == "total" else ""
                        )

                for campo in [
                    "fecha",
                    "numero_remito",
                    "proveedor",
                    "cuit"
                ]:
                    if datos[campo] is None:
                        datos[campo] = ""
                    else:
                        datos[campo] = str(datos[campo])

                total = datos["total"]

                if total is not None:
                    if isinstance(total, bool):
                        raise ValueError(
                            "El total detectado no es válido."
                        )

                    datos["total"] = float(total)

                return datos, modelo

            except Exception as error:

                errores.append(
                    f"{modelo}: {str(error)[:250]}"
                )

                # Si es temporal, reintentar brevemente
                if es_error_temporal(error):

                    if intento == 0:
                        time.sleep(1)
                        continue

                    # Pasar al modelo siguiente
                    break

                mensaje = str(error).lower()

                # Si el modelo no existe o no está habilitado,
                # probar el siguiente de la lista.
                if (
                    "404" in mensaje
                    or "not found" in mensaje
                    or "no longer available" in mensaje
                    or "unsupported" in mensaje
                ):
                    break

                # Errores de autenticación, formato u otros:
                # no insistir con los mismos datos.
                raise RuntimeError(
                    f"Error con {modelo}: {error}"
                ) from error

    raise RuntimeError(
        "Ningún modelo pudo procesar el remito. "
        "Detalle: " + " | ".join(errores[-6:])
    )


def guardar_en_sheets(datos):
    """Agrega una fila a Google Sheets."""

    cred_dict = json.loads(st.secrets["GOOGLE_JSON"])

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    credenciales = Credentials.from_service_account_info(
        cred_dict,
        scopes=scopes
    )

    cliente = gspread.authorize(credenciales)

    planilla = cliente.open_by_key(
        st.secrets["SHEET_ID"]
    )

    hoja = planilla.sheet1

    hoja.append_row(
        [
            datos["fecha"],
            datos["numero_remito"],
            datos["proveedor"],
            datos["cuit"],
            datos["total"]
        ],
        value_input_option="USER_ENTERED"
    )


# ==================================================
# CARGA Y PROCESAMIENTO
# ==================================================

archivo = st.file_uploader(
    "📷 Subí una foto del remito",
    type=["jpg", "jpeg", "png"]
)

if archivo:
    st.image(
        archivo,
        caption="Imagen original",
        use_container_width=True
    )

    if st.button(
        "🔍 Procesar remito",
        type="primary",
        use_container_width=True
    ):

        try:
            with st.spinner("Preparando imagen..."):
                _, imagen_b64 = preparar_imagen(archivo)

            with st.spinner(
                "Analizando remito con Gemini..."
            ):
                datos, modelo_usado = extraer_datos(imagen_b64)

            st.session_state["remito_datos"] = datos
            st.session_state["remito_modelo"] = modelo_usado
            st.session_state["remito_guardado"] = False

            st.success(
                f"Datos extraídos con {modelo_usado}"
            )

        except Exception as error:
            st.error(f"❌ No se pudo procesar el remito: {error}")

# ==================================================
# REVISION Y GUARDADO
# ==================================================

if "remito_datos" in st.session_state:

    st.subheader("📋 Revisá los datos")

    datos = st.session_state["remito_datos"]

    if st.session_state.get("remito_guardado"):
        st.success("Este remito ya fue guardado en esta sesión.")

    else:
        with st.form("formulario_remito"):

            fecha = st.text_input(
                "Fecha",
                value=datos["fecha"]
            )

            numero = st.text_input(
                "Número de remito",
                value=datos["numero_remito"]
            )

            proveedor = st.text_input(
                "Proveedor",
                value=datos["proveedor"]
            )

            cuit = st.text_input(
                "CUIT",
                value=datos["cuit"]
            )

            total = st.text_input(
                "Total",
                value=(
                    str(datos["total"])
                    if datos["total"] is not None
                    else ""
                )
            )

            confirmar = st.form_submit_button(
                "✅ Confirmar y guardar",
                use_container_width=True
            )

        if confirmar:

            try:
                if total.strip():
                    total_final = float(
                        total.strip().replace(",", ".")
                    )
                else:
                    total_final = None

                datos_finales = {
                    "fecha": fecha.strip(),
                    "numero_remito": numero.strip(),
                    "proveedor": proveedor.strip(),
                    "cuit": cuit.strip(),
                    "total": total_final
                }

                with st.spinner(
                    "Guardando en Google Sheets..."
                ):
                    guardar_en_sheets(datos_finales)

                st.session_state["remito_guardado"] = True
                st.success("✅ Remito guardado correctamente.")

            except ValueError:
                st.error(
                    "El total debe ser numérico. "
                    "Ejemplo: 12500.50"
                )

            except Exception as error:
                st.error(
                    f"Error al guardar en Google Sheets: {error}"
                )

st.divider()
st.caption(
    "La disponibilidad de Gemini depende de los límites "
    "y del estado del servicio de Google."
)

