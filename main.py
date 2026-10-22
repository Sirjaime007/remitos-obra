
import json
import io
import streamlit as st
from google import genai
from google.genai import types
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
st.caption(
    "Subí una imagen del remito para extraer sus datos "
    "y guardarlos en Google Sheets."
)

PROMPT = """
Analiza cuidadosamente la imagen del remito y extrae
los siguientes datos.

Devuelve exclusivamente un objeto JSON válido con
esta estructura exacta:

{
    "fecha": "DD/MM/AAAA",
    "numero_remito": "string",
    "proveedor": "string",
    "cuit": "string",
    "total": number o null
}

Reglas:
- No inventes datos que no sean legibles.
- Si falta un dato de texto, devuelve una cadena vacía.
- El total debe ser numérico, sin símbolo monetario.
- Usa punto decimal si hay decimales.
- Conserva el CUIT completo.
- Distingue el número de remito del número de factura.
- No confundas el subtotal con el total final.
- Devuelve únicamente el JSON, sin Markdown.
"""

# --------------------------------------------------
# CARGA DE IMAGEN
# --------------------------------------------------

foto = st.file_uploader(
    "📷 Sacá una foto o subí un remito",
    type=["jpg", "jpeg", "png"]
)

if foto:
    st.image(
        foto,
        caption="Imagen del remito",
        use_container_width=True
    )

# --------------------------------------------------
# PROCESAMIENTO
# --------------------------------------------------

if foto and st.button(
    "Procesar Remito",
    type="primary",
    use_container_width=True
):

    try:
        # 1. Preparar la imagen
        with st.spinner("Preparando imagen..."):

            imagen = Image.open(foto).convert("RGB")
            imagen.thumbnail((1600, 1600))

            buffer = io.BytesIO()
            imagen.save(buffer, format="JPEG", quality=90)
            imagen_bytes = buffer.getvalue()

        # 2. Conectar con Gemini
        with st.spinner("Gemini está leyendo el remito..."):

            api_key = st.secrets["GEMINI_API_KEY"]
            client = genai.Client(api_key=api_key)

            # API de Interactions con imagen y texto
            response = client.interactions.create(
                model="gemini-3.8-flash",
                input=[
                    {
                        "type": "text",
                        "text": PROMPT
                    },
                    {
                        "type": "image",
                        "data": imagen_bytes,
                        "mime_type": "image/jpeg"
                    }
                ]
            )

            texto = response.output_text

            if not texto:
                raise ValueError(
                    "Gemini no devolvió texto. "
                    "Intentá con una imagen más nítida."
                )

            # Limpiar posibles bloques Markdown
            texto = texto.strip()

            if texto.startswith("```"):
                texto = texto.replace("```json", "", 1)
                texto = texto.replace("```", "")
                texto = texto.strip()

            datos = json.loads(texto)

        # 3. Normalizar los campos
        campos_texto = [
            "fecha",
            "numero_remito",
            "proveedor",
            "cuit"
        ]

        for campo in campos_texto:
            valor = datos.get(campo, "")
            datos[campo] = "" if valor is None else str(valor)

        total = datos.get("total")

        if total is not None:
            if isinstance(total, bool):
                raise ValueError(
                    "El total devuelto no es numérico."
                )
            total = float(total)

        datos["total"] = total

        # 4. Mostrar datos detectados
        st.subheader("📋 Datos detectados")

        st.write("**Fecha:**", datos["fecha"])
        st.write("**Número de remito:**", datos["numero_remito"])
        st.write("**Proveedor:**", datos["proveedor"])
        st.write("**CUIT:**", datos["cuit"])
        st.write("**Total:**", datos["total"])

        # 5. Confirmar antes de guardar
        st.warning(
            "Verificá que los datos coincidan con el remito "
            "antes de registrarlos."
        )

        if st.button(
            "Confirmar y guardar en Google Sheets",
            type="primary",
            use_container_width=True
        ):

            with st.spinner("Guardando en Google Sheets..."):

                # Credenciales de Google
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

                client_gs = gspread.authorize(creds)

                # Abrir planilla
                spreadsheet = client_gs.open_by_key(
                    st.secrets["SHEET_ID"]
                )

                sheet = spreadsheet.sheet1

                # Guardar fila
                sheet.append_row(
                    [
                        datos["fecha"],
                        datos["numero_remito"],
                        datos["proveedor"],
                        datos["cuit"],
                        datos["total"]
                    ],
                    value_input_option="USER_ENTERED"
                )

            st.success(
                "✅ ¡Remito guardado correctamente en Google Sheets!"
            )

    except json.JSONDecodeError:
        st.error(
            "Gemini no devolvió un JSON válido. "
            "Intentá nuevamente con una imagen más clara."
        )

    except KeyError as e:
        st.error(
            f"Falta una configuración en Secrets: {e}. "
            "Revisá GEMINI_API_KEY, GOOGLE_JSON y SHEET_ID."
        )

    except Exception as e:
        st.error(f"❌ Error: {str(e)}")
