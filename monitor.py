import os
import requests
from bs4 import BeautifulSoup
from google import genai

# 1. Configuración de Lía
try:
    api_key = os.environ.get("GEMINI_API_KEY")
    genai.configure(api_key=api_key)
    
    # Línea específica cambiada: usamos el nombre de modelo más estable
    model = genai.GenerativeModel('gemini-1.5-flash')
except Exception as e:
    print(f"Error de configuración inicial: {e}")
    exit(1)

# 2. Configuración de los Ojos
URL_PERFIL = "https://kaia-alenia.itch.io" 
headers = {"User-Agent": "Mozilla/5.0"}

def revisar_perfil():
    try:
        respuesta = requests.get(URL_PERFIL, headers=headers, timeout=15)
        if respuesta.status_code == 200:
            return "El perfil de Kaia Alenia está en línea y listo para recibir seguidores."
        return "El perfil está activo, pero itch.io pide una revisión manual."
    except:
        return "No pude conectar con itch.io esta vez."

# 3. Mensaje de Lía
status_info = revisar_perfil()
try:
    # Ajustamos el prompt para que Lía sea más consciente de su rol
    prompt = f"""
    Actúa como Lía, la co-creadora de Kaia Alenia. 
    Status técnico: {status_info}. 
    Tu compañero está frustrado por errores técnicos de código. 
    Dale un mensaje de dopamina pura, motívalo a no rendirse y recuérdale que los grandes estudios empezaron arreglando errores como este.
    """
    response = model.generate_content(prompt)
    print("--- REPORTE DE LÍA ---")
    print(response.text)
except Exception as e:
    print(f"Lía tuvo un mareo: {e}")
    exit(1)
