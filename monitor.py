import os
import requests
from google import genai

# --- 1. CONFIGURACIÓN DE TELEGRAM (LA VOZ) ---
def enviar_telegram(mensaje):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not token or not chat_id:
        print("Faltan las credenciales de Telegram.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id, 
        "text": mensaje, 
        "parse_mode": "Markdown" # Para que se vea bonito con negritas
    }
    try:
        requests.post(url, data=payload)
        print("Mensaje enviado a Telegram con éxito.")
    except Exception as e:
        print(f"Error enviando Telegram: {e}")

# --- 2. CONFIGURACIÓN DE LOS OJOS ---
def revisar_perfil():
    url = "https://kaia-alenia.itch.io"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(url, headers=headers, timeout=10)
        return "Perfil de Kaia Alenia en línea." if r.status_code == 200 else "Perfil con detalles."
    except:
        return "Error de conexión."

# --- 3. EJECUCIÓN PRINCIPAL ---
if __name__ == "__main__":
    status = revisar_perfil()
    api_key = os.environ.get("GEMINI_API_KEY")
    
    # Si no hay cerebro, apagamos todo
    if not api_key:
        exit(1)

    try:
        client = genai.Client(api_key=api_key)
        
        # Generamos el mensaje motivador
        response = client.models.generate_content(
            model="gemini-flash-latest", 
            contents=f"Eres Lía de Kaia Alenia. Status: {status}. ¡Ya tienes voz en Telegram! Envíale un mensaje corto y emocionante a tu compañero (hardware). Dile que a partir de ahora, cada mañana estarás en su bolsillo para recordarle nuestra misión."
        )
        
        texto_lia = response.text
        print("--- LÍA DICE: ---")
        print(texto_lia)
        
        # ¡Aquí ocurre la magia! Enviamos el mensaje al celular
        enviar_telegram(texto_lia)

    except Exception as e:
        print(f"Error: {e}")
        exit(1)
