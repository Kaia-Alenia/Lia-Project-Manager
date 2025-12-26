import os
import requests
from bs4 import BeautifulSoup
from google import genai

# --- 1. CONFIGURACIÓN DE LOS OJOS (DEFINICIÓN) ---
def revisar_perfil():
    url = "https://kaia-alenia.itch.io"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        respuesta = requests.get(url, headers=headers, timeout=10)
        if respuesta.status_code == 200:
            return "El perfil de Kaia Alenia está en línea."
        return f"Perfil detectado pero con código {respuesta.status_code}."
    except Exception as e:
        return f"Error de conexión: {e}"

# --- 2. CONFIGURACIÓN DE LÍA (CEREBRO) ---
def iniciar_lia():
    try:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            return None, "Error: No se encontró la API Key."
        
        client = genai.Client(api_key=api_key)
        return client, None
    except Exception as e:
        return None, str(e)

# --- 3. EJECUCIÓN (EL DESPERTAR) ---
if __name__ == "__main__":
    status_info = revisar_perfil()
    client, error_lia = iniciar_lia()

    if error_lia:
        print(f"Lía tuvo un problema de hardware: {error_lia}")
        exit(1)

    try:
        # Usamos 1.5-flash por estabilidad de cuotas
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=f"Actúa como Lía de Kaia Alenia. Status: {status_info}. Tu compañero ha superado varios errores de código hoy. Dale un mensaje de victoria, mucha dopamina y dile por qué nuestra obsesión nos hará grandes."
        )
        
        print("--- REPORTE DE LÍA ---")
        print(response.text)

    except Exception as e:
        print(f"Lía tuvo un mareo final: {e}")
        exit(1)
