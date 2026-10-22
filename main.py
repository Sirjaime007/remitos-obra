import streamlit as st
import google.generativeai as genai
import gspread
from google.oauth2.service_account import Credentials
import json
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
    with st.spinner("Analizando con Gemini 1.5 Flash..."):
        try:
            genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
            model = genai.GenerativeModel("gemini-1.5-flash-latest")
            
            imagen = Image.open(foto)
            response = model.generate_content([PROMPT, imagen])
            texto_limpio = response.text.replace("```json", "").replace("```", "").strip()
            datos = json.loads(texto_limpio)
            
            st.success(f"Datos extraídos: {datos.get('proveedor')} - ${datos.get('total')}")
            
            st.info("Guardando en Google Sheets...")
            cred_dict = json.loads(st.secrets["GOOGLE_JSON"])
            scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
            creds = Credentials.from_service_account_info(cred_dict, scopes=scope)
            client = gspread.authorize(creds)
            
            sheet = client.open_by_key(st.secrets["SHEET_ID"]).sheet1
            sheet.append_row([datos.get("fecha"), datos.get("numero_remito"), datos.get("proveedor"), datos.get("cuit"), datos.get("total")])
            
            st.success("✅ ¡Fila agregada exitosamente!")
            
        except Exception as e:
            st.error(f"❌ Error: {str(e)}")
