import json
import streamlit as st
from google import genai
import gspread
from google.oauth2.service_account import Credentials
from PIL import Image

st.set_page_config(page_title="Control Remitos", layout="centered")
st.title("📥 Carga Inteligente de Remitos")

PROMPT = """Analiza este remito y extrae la información.
Devuelve estrictamente un objeto JSON con:
{"fecha": "DD/MM/AAAA", "numero_remito": "string", "proveedor": "string", "cuit": "string", "total": "number o null"}"""

foto = st.file_uploader("Saca una foto o sube un remito", type=["jpg", "jpeg", "png"])

if foto and st.button("Procesar Remito"):
    with st.spinner("Analizando imagen..."):
        try:
            # Compresión obligatoria para evitar el error 504
            imagen = Image.open(foto)
            imagen.thumbnail((800, 800))
            
            client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
            
            # Modelo rápido (8b) con salida estructurada
            response = client.models.generate_content(
                model="gemini-1.5-flash-8b",
                contents=[PROMPT, imagen],
                config={"response_mime_type": "application/json"}
            )
            
            datos = json.loads(response.text)
            st.success(f"Datos extraídos: {datos.get('proveedor')} - ${datos.get('total')}")
            
            cred_dict = json.loads(st.secrets["GOOGLE_JSON"])
            scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
            creds = Credentials.from_service_account_info(cred_dict, scopes=scope)
            client_gs = gspread.authorize(creds)
            
            sheet = client_gs.open_by_key(st.secrets["SHEET_ID"]).sheet1
            sheet.append_row([datos.get("fecha"), datos.get("numero_remito"), datos.get("proveedor"), datos.get("cuit"), datos.get("total")])
            
            st.success("✅ ¡Fila agregada exitosamente!")
        except Exception as e:
            st.error(f"❌ Error: {str(e)}")

