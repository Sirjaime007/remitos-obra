import time
import json
import streamlit as st
import google.generativeai as genai
import gspread
from google.oauth2.service_account import Credentials
from PIL import Image

st.set_page_config(page_title="Control Remitos", layout="centered")
st.title("📥 Carga Inteligente de Remitos")

PROMPT = """
Analiza este remito y extrae la información.
Devuelve estrictamente un objeto JSON con los siguientes campos:
{"fecha": "DD/MM/AAAA", "numero_remito": "string", "proveedor": "string", "cuit": "string", "total": "number o null"}
No agregues texto adicional.
"""

foto = st.file_uploader("Saca una foto o sube un remito", type=["jpg", "jpeg", "png"])

if foto and st.button("Procesar Remito"):
    with st.spinner("Analizando con Gemini..."):
        try:
            # 1. Configuración de la librería clásica
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
            model = genai.GenerativeModel("gemini-1.5-flash")
            
            # 2. Compresión para evitar el error 504 (timeout)
            imagen = Image.open(foto)
            imagen.thumbnail((1024, 1024))

            response = None
            ultimo_error = None

            # 3. Reintentos automáticos
            for intento in range(3):
                try:
                    response = model.generate_content(
                        [PROMPT, imagen],
                        generation_config={"response_mime_type": "application/json"}
                    )
                    break
                except Exception as e:
                    ultimo_error = e
                    if "503" in str(e) or "429" in str(e) or "504" in str(e):
                        time.sleep(2 ** intento)
                    else:
                        raise
            
            if response is None:
                raise ultimo_error

            # 4. Procesamiento de datos
            datos = json.loads(response.text)
            st.success(f"Datos extraídos: {datos.get('proveedor')} - ${datos.get('total')}")

            # 5. Guardado en Google Sheets
            st.info("Guardando en Google Sheets...")
            cred_dict = json.loads(st.secrets["GOOGLE_JSON"])
            scope = [
                "https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive",
            ]
            creds = Credentials.from_service_account_info(cred_dict, scopes=scope)
            client_gs = gspread.authorize(creds)

            sheet = client_gs.open_by_key(st.secrets["SHEET_ID"]).sheet1
            sheet.append_row([
                datos.get("fecha"),
                datos.get("numero_remito"),
                datos.get("proveedor"),
                datos.get("cuit"),
                datos.get("total"),
            ])

            st.success("✅ ¡Fila agregada exitosamente!")

        except Exception as e:
            st.error(f"❌ Error: {str(e)}")
