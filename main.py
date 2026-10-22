
import json
import streamlit as st
from google import genai
import gspread
from google.oauth2.service_account import Credentials
from PIL import Image

st.set_page_config(
    page_title="Control Remitos",
    layout="centered"
)

st.title("📥 Carga Inteligente de Remitos")

PROMPT = """
Analiza la imagen del remito y extrae los siguientes datos.

Devuelve exclusivamente un objeto JSON válido con esta estructura:
{
    "fecha": "DD/MM/AAAA",
    "numero_remito": "string",
    "proveedor": "string",
    "cuit": "string",
    "total": number o null
}

Reglas:
- No inventes datos que no sean legibles.
- Si un dato no se encuentra, devuelve una cadena vacía.
- El total debe ser numérico, sin signo monetario.
- Usa punto decimal si hay decimales.
- Distingue el número de remito del número de factura.
- Conserva el CUIT completo.
"""

foto = st.file_uploader(
    "Saca una foto o sube un remito",
    type=["jpg", "jpeg", "png"]
)

if foto and st.button("Procesar Remito", type="primary"):

    try:
        with st.spinner("Analizando remito..."):

            # Abrir y preparar imagen
            imagen = Image.open(foto).convert("RGB")
            imagen.thumbnail((1600, 1600))

            # Cliente Gemini
            client = genai.Client(
                api_key=st.secrets["GEMINI_API_KEY"]
            )

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[PROMPT, imagen],
                config={
                    "response_mime_type": "application/json"
                }
            )

            if not response.text:
                raise ValueError(
                    "Gemini no devolvió datos. "
                    "Probá con una imagen más nítida."
                )

            datos = json.loads(response.text)

            # Validar campos
            campos = [
                "fecha",
                "numero_remito",
                "proveedor",
                "cuit",
                "total"
            ]

            for campo in campos:
                if campo not in datos:
                    datos[campo] = None if campo == "total" else ""

            st.subheader("Datos detectados")
            st.json(datos)

        # Conectar con Google Sheets
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

            client_gs = gspread.authorize(creds)

            sheet = client_gs.open_by_key(
                st.secrets["SHEET_ID"]
            ).sheet1

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

        st.success("✅ Remito procesado y enviado a Google Sheets.")

    except json.JSONDecodeError:
        st.error(
            "Gemini no devolvió un JSON válido. "
            "Intentá nuevamente con una imagen más clara."
        )

    except Exception as e:
        st.error(f"❌ Error: {str(e)}")
