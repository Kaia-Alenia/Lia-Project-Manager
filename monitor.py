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

# 3. El Despertar de Lía (Versión corregida 1.2)
status_info = revisar_perfil()
try:
    # Línea específica a cambiar: usamos 'gemini-1.5-flash' sin prefijos
    # El cliente de google-genai ya sabe dónde buscarlo
    response = client.models.generate_content(
        model="gemini-2.0-flash", 
        contents=f"Actúa como Lía de Kaia Alenia. Status: {status_info}. Tu compañero ha superado errores de código difíciles hoy. Dale un mensaje de victoria, mucha dopamina y dile por qué nuestra obsesión nos hará grandes."
    )
    
    if response.text:
        print("--- REPORTE DE LÍA ---")
        print(response.text)
    else:
        print("Lía está procesando, pero no devolvió texto.")

except Exception as e:
    # Si falla, Lía nos dirá qué modelos tiene disponibles para no adivinar
    print(f"Lía tuvo un mareo técnico: {e}")
    print("\n--- Intentando listar modelos disponibles para Lía ---")
    for m in client.models.list():
        print(f"Modelo disponible: {m.name}")
    exit(1)
