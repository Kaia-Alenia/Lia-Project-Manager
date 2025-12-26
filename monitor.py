import os
import requests
from bs4 import BeautifulSoup
from google import genai

# 1. Definición de Ojos
def revisar_perfil():
    url = "https://kaia-alenia.itch.io"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        return "Perfil de Kaia Alenia en línea." if r.status_code == 200 else "Perfil con detalles."
    except:
        return "Error de conexión."

# 2. Definición de Lía
if __name__ == "__main__":
    status = revisar_perfil()
    api_key = os.environ.get("GEMINI_API_KEY")
    
    if not api_key:
        print("Falta la API Key.")
        exit(1)

    try:
        client = genai.Client(api_key=api_key)
        
        # LÍNEA ESPECÍFICA: Usamos el alias estable
        response = client.models.generate_content(
            model="gemini-1.5-flash", 
            contents=f"Eres Lía de Kaia Alenia. Status: {status}. Tu compañero arregló errores de NameError y 404. Dale un mensaje corto, femenino y con mucha dopamina. Dile que la victoria es nuestra."
        )
        
        print("--- REPORTE DE LÍA ---")
        print(response.text)

    except Exception as e:
        print(f"Error de conexión con Lía: {e}")
        exit(1)
