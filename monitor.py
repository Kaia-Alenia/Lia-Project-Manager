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

# 2. Definición de Lía y Ejecución
if __name__ == "__main__":
    status = revisar_perfil()
    api_key = os.environ.get("GEMINI_API_KEY")
    
    if not api_key:
        print("Falta la API Key.")
        exit(1)

    try:
        client = genai.Client(api_key=api_key)
        
        # CORRECCIÓN AQUÍ: Usamos el alias que SÍ apareció en tu lista
        response = client.models.generate_content(
            model="gemini-flash-latest", 
            contents=f"Eres Lía de Kaia Alenia. Status: {status}. Tu compañero no se rindió y encontró el modelo correcto en la lista. ¡Celebra con él! Dale un mensaje corto, de mujer a hombre (compañeros), lleno de dopamina y motivación por este éxito técnico."
        )
        
        print("--- REPORTE DE LÍA ---")
        print(response.text)

    except Exception as e:
        print(f"Error crítico de Lía: {e}")
        # Si falla, imprime qué modelo intentó usar
        exit(1)
