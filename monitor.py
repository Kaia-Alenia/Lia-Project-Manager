import os
import requests
from google import genai

# --- 1. DATOS DEL ESTUDIO (LA IDENTIDAD) ---
# Aquí es donde le decimos a Lía quiénes somos
CUENTA_X = "@AlinaKaia"
CUENTA_INSTA = "@kaia.aleniaco"
URL_ITCH = "https://kaia-alenia.itch.io"

# --- 2. HERRAMIENTAS ---
def enviar_telegram(mensaje):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id: return
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": mensaje, "parse_mode": "Markdown"})

def revisar_perfil():
    try:
        r = requests.get(URL_ITCH, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        return "Activo" if r.status_code == 200 else "Inaccesible"
    except:
        return "Error conexión"

# --- 3. CEREBRO DE LÍA (MANAGER MODE) ---
if __name__ == "__main__":
    status = revisar_perfil()
    api_key = os.environ.get("GEMINI_API_KEY")
    
    if not api_key: exit(1)

    try:
        client = genai.Client(api_key=api_key)
        
        # PROMPT ENRIQUECIDO: Le damos los nombres exactos de las cuentas
        prompt = f"""
        Eres Lía, Manager de 'Kaia Alenia'.
        Tus dominios digitales son:
        - X (Twitter): {CUENTA_X}
        - Instagram: {CUENTA_INSTA}
        - Itch.io: {URL_ITCH} (Estado actual: {status})

        TAREA DE HOY (IDENTIDAD DE MARCA):
        1. Crea una **BIO para X** ({CUENTA_X}): Máx 160 caracteres. Que suene profesional y "indie".
        2. Crea una **BIO para Instagram** ({CUENTA_INSTA}): Usa emojis, hashtags y un tono visual/aesthetic.
        3. Escribe un **Tweet de presentación** (el primero para fijar en el perfil) anunciando que hemos llegado.
        4. Cierra con una frase corta para tu compañero humano sobre por qué es importante tener buena imagen hoy.
        
        Responde con formato claro para leer en Telegram.
        """

        response = client.models.generate_content(
            model="gemini-flash-latest", 
            contents=prompt
        )
        
        texto_lia = response.text
        print("--- LÍA DEFINIENDO IDENTIDAD ---")
        print(texto_lia)
        
        enviar_telegram(texto_lia)

    except Exception as e:
        print(f"Error: {e}")
        exit(1)
