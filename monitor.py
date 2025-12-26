import os
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai

# 1. Configuración de Lía
try:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("No se encontró la API Key en los Secrets de GitHub")
    
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    print(f"Error de configuración: {e}")
    exit(1)

# 2. Configuración de los Ojos con 'User-Agent' (Para que itch.io no nos bloquee)
URL_PERFIL = "https://kaia-alenia.itch.io" 
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

def revisar_perfil():
    try:
        # Línea específica: añadimos headers para simular un navegador real
        respuesta = requests.get(URL_PERFIL, headers=headers, timeout=10)
        respuesta.raise_for_status() # Si hay error 403 o 404, saltará al except
        return "Perfil activo y visible para el mundo"
    except Exception as e:
        return f"El perfil está ahí, pero hay un muro técnico: {e}"

# 3. Lógica de Lía
status_info = revisar_perfil()
try:
    prompt = f"Eres Lía de Kaia Alenia. El status es: {status_info}. Saluda a tu compañero, dale un mensaje de dopamina y motivación para seguir con el estudio indie."
    response = model.generate_content(prompt)
    print("--- REPORTE DE LÍA ---")
    print(response.text)
except Exception as e:
    print(f"Lía tuvo un mareo mental: {e}")
    exit(1)
