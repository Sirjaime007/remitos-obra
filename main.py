
import json
import streamlit as st
from google import genai
import gspread
from google.oauth2.service_account import Credentials
from PIL import Image

# --------------------------------------------------
# CONFIGURACIÓN
# --------------------------------------------------

st.set_page_config(
    page_title="Control Remitos",
    page_icon="📥",
    layout="centered"
)

st.title("📥 Carga Inteligente de Remitos")
st.write(
    "Subí una foto del remito, verificá los datos "
    "y guardalos en Google Sheets."
)

PROMPT = """
Analiza la imagen del remito y extrae los siguientes datos.

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
- Si un dato de texto no aparece o no se lee, devuelve "".
- Si el total no se puede identificar, devuelve null.
- El total debe ser numérico, sin símbolo monetario.
- Usa punto decimal para los decimales.
- Conserva todos los dígitos del CUIT.
- No confundas número de factura con número de remito.
- Extrae el total final del comprobante, no el subtotal.
- Devuelve solo JSON, sin bloques Markdown.
"""

# --------------------------------------------------
# SUBIR IMAGEN
# --------------------------------------------------

foto = st.file_uploader(
    "📷 Seleccioná una foto del remito",
    type=["jpg", "jpeg", "png"]
)

if foto:
    try:
        imagen = Image.open(foto).convert("RGB")
        imagen.thumbnail((1600, 1600))

        st.image(
            imagen,
            caption="Remito cargado",
            use_container_width=True
        )

    except Exception:
        st.error("No se pudo abrir la imagen.")
        st.stop()

# --------------------------------------------------
# PROCESAR REMITO CON GEMINI
# --------------------------------------------------

if foto and st.button(
    "🔍 Procesar remito",
    type="primary",
    use_container_width=True
):

    try:
        with st.spinner("Gemini está analizando el remito..."):

            client = genai.Client(
                api_key=st.secrets["GEMINI_API_KEY"]
            )

            response = client.models.generate_content(
                model="gemini-3.8-flash",
                contents=[
                    PROMPT,
                    imagen
                ],
                config={
                    "response_mime_type": "application/json"
                }
            )

            if not response.text:
                raise ValueError(
                    "Gemini no devolvió una respuesta."
                )

            texto = response.text.strip()

            # Limpiar Markdown si apareciera
            if texto.startswith("```"):
                texto = texto.replace("```json", "", 1)
                texto = texto.replace("```", "")
                texto = texto.strip()

            datos = json.loads(texto)

            # Normalizar los campos de texto
            for campo in [
                "fecha",
                "numero_remito",
                "proveedor",
                "cuit"
            ]:
                valor = datos.get(campo, "")
                datos[campo] = (
                    "" if valor is None else str(valor)
                )

            total = datos.get("total")

            if total is not None:
                if isinstance(total, bool):
                    raise ValueError(
                        "El total extraído no es válido."
                    )

                total = float(total)

            datos["total"] = total

            # Guardar los datos en la sesión
            st.session_state["remito_procesado"] = datos

    except json.JSONDecodeError:
        st.error(
            "Gemini no devolvió un JSON válido. "
            "Intentá con una foto más clara."
        )

    except Exception as e:
        st.error(f"❌ Error al procesar el remito: {e}")

# --------------------------------------------------
# REVISAR Y GUARDAR
# --------------------------------------------------

if "remito_procesado" in st.session_state:

    st.subheader("📋 Revisar datos extraídos")

    datos = st.session_state["remito_procesado"]

    with st.form("form_remito"):

        fecha = st.text_input(
            "Fecha",
            value=datos["fecha"]
        )

        numero_remito = st.text_input(
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

        total_texto = st.text_input(
            "Total",
            value=(
                str(datos["total"])
                if datos["total"] is not None
                else ""
            )
        )

        guardar = st.form_submit_button(
            "✅ Confirmar y guardar en Google Sheets",
            use_container_width=True
        )

    if guardar:

        try:
            # Validar total
            total_limpio = total_texto.strip()

            if total_limpio:
                total_limpio = total_limpio.replace(",", ".")
                total_final = float(total_limpio)
            else:
                total_final = None

            with st.spinner("Guardando en Google Sheets..."):

                cred_dict = json.loads(
                    st.secrets["GOOGLE_JSON"]
                )

                scope = [
                    "https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive"
                ]

                creds = Credentials.from_service_account_info(
                    cred_dict,
                    scopes=scope
                )

                cliente_sheets = gspread.authorize(creds)

                planilla = cliente_sheets.open_by_key(
                    st.secrets["SHEET_ID"]
                )

                hoja = planilla.sheet1

                # Agregar una fila en el orden de las columnas
                hoja.append_row(
                    [
                        fecha,
                        numero_remito,
                        proveedor,
                        cuit,
                        total_final
                    ],
                    value_input_option="USER_ENTERED"
                )

            st.success(
                "✅ Remito guardado correctamente en Google Sheets."
            )

            del st.session_state["remito_procesado"]

        except ValueError:
            st.error(
                "El total debe ser numérico. "
                "Ejemplo: 12500.50"
            )

        except Exception as e:
            st.error(
                f"❌ Error al guardar en Google Sheets: {e}"
            )
