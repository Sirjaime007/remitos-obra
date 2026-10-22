import json
import base64
import requests
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from PIL import Image
import io

st.set_page_config(page_title="Control Remitos", layout="centered")
st.title("📥 Carga Inteligente de Remitos")

PROMPT = """Analiza este remito y extrae la información.
Devuelve estrictamente un objeto JSON con:
{"fecha": "DD/MM/AAAA", "numero_remito": "string", "proveedor": "string", "cuit": "string", "total": "number o null"}"""

foto = st.file_uploader("Saca una foto o sube un remito", type=["jpg", "jpeg", "png"])

if foto and st.button("Procesar Remito"):
    with st.spinner("Buscando modelo autorizado y procesando..."):
        try:
            api_key = st.secrets["GEMINI_API_KEY"]
            
            # 1. AUTO-DETECTAR EL NOMBRE EXACTO DEL MODELO
            url_modelos = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
            respuesta_modelos = requests.get(url_modelos).json()
            
            modelo_detectado = None
            for m in respuesta_modelos.get("models", []):
                if "flash" in m.get("name", "") and "generateContent" in m.get("supportedGenerationMethods", []):
                    # Extrae la parte final (ej. "gemini-1.5-flash-001")
                    modelo_detectado = m["name"].split("/")[-1]
                    break
            
            if not modelo_detectado:
                st.error("❌ Tu API Key no tiene modelos Flash habilitados.")
                st.stop()
                
            # 2. COMPRESIÓN DE LA IMAGEN
            imagen = Image.open(foto)
            if imagen.mode != 'RGB':
                imagen = imagen.convert('RGB')
            imagen.thumbnail((800, 800))
            buffered = io.BytesIO()
            imagen.save(buffered, format="JPEG")
            img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")

            # 3. CONEXIÓN DIRECTA CON EL NOMBRE DETECTADO
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo_detectado}:generateContent?key={api_key}"
            
            payload = {
                "contents": [{"parts": [{"text": PROMPT}, {"inline_data": {"mime_type": "image/jpeg", "data": img_str}}]}],
                "generationConfig": {"response_mime_type": "application/json"}
            }

            respuesta = requests.post(url, json=payload, timeout=60)
            
            if respuesta.status_code != 200:
                st.error(f"Error de API: {respuesta.text}")
                st.stop()
                
            # 4. EXTRACCIÓN Y GUARDADO
            datos = json.loads(respuesta.json()["candidates"][0]["content"]["parts"][0]["text"])
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
