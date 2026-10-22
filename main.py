import json
import base64
import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from PIL import Image
import io
from openai import OpenAI

st.set_page_config(page_title="Control Remitos", layout="centered")
st.title("📥 Carga Inteligente de Remitos")

PROMPT = """Analiza este remito y extrae la información.
Devuelve estrictamente un objeto JSON (sin formato Markdown ni texto adicional) con:
{"fecha": "DD/MM/AAAA", "numero_remito": "string", "proveedor": "string", "cuit": "string", "total": "number o null"}"""

foto = st.file_uploader("Saca una foto o sube un remito", type=["jpg", "jpeg", "png"])

if foto and st.button("Procesar Remito"):
    with st.spinner("Analizando con Llama 3.2 vía OpenRouter..."):
        try:
            imagen = Image.open(foto)
            if imagen.mode != 'RGB':
                imagen = imagen.convert('RGB')
            imagen.thumbnail((1024, 1024))
            buffered = io.BytesIO()
            imagen.save(buffered, format="JPEG")
            img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")

            client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=st.secrets["OPENROUTER_API_KEY"],
            )
            
            respuesta = client.chat.completions.create(
                model="openrouter/free",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{img_str}"},
                            },
                        ],
                    }
                ]
            )
            
            texto_respuesta = respuesta.choices[0].message.content
            texto_limpio = texto_respuesta.replace("```json", "").replace("```", "").strip()
            datos = json.loads(texto_limpio)
            
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
