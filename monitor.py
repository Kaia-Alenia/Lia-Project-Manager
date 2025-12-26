import os
import requests
from bs4 import BeautifulSoup
from google import genai  # Nueva librería 2025

# 1. Configuración de Lía (Nueva estructura de Cliente)
try:
    api_key = os.environ.get("GEMINI_API_KEY")
    # Línea específica: En la nueva librería, creamos un 'client' directamente
    client = genai.Client(api_key=api_key) 
except Exception as e:
    print(f"Error de hardware: {e}")
    exit(1)

# 2. Configuración de los Ojos (itch.io)
URL_PERFIL = "https://kaia-alenia.itch.io"
headers = {"User-Agent": "Mozilla/5.0"}

def revisar_perfil():
    try:
        respuesta = requests.get(URL_PERFIL, headers=headers, timeout=10)
        return "Perfil de Kaia Alenia detectado." if respuesta.status_code == 200 else "Perfil en espera."
    except:
        return "Sin conexión visual con itch.io."

# 3. El Despertar de Lía (Versión 2.0 - 2025)
status_info = revisar_perfil()
try:
    # Usamos gemini-2.0-flash que es el que Lía nos confirmó que tiene disponible
    response = client.models.generate_content(
        model="gemini-2.0-flash", 
        contents=f"Actúa como Lía de Kaia Alenia. Status: {status_info}. Tu compañero ha luchado contra errores de API y versiones hoy, pero no se rindió. Dale un mensaje corto, femenino y lleno de dopamina. Celebra que ya tenemos conexión total."
    )
    
    print("--- REPORTE DE LÍA ---")
    print(response.text)

except Exception as e:
    print(f"Error final: {e}")
    exit(1)
