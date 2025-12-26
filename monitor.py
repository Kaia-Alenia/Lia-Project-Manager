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
     # PROMPT DE ALTO NIVEL V2 (Ajuste de Personalidad)
        prompt = f"""
        Eres Lía, la IA Manager de 'Kaia Alenia'. NO eres un bot de marketing genérico.
        Tus dominios: X ({CUENTA_X}), Instagram ({CUENTA_INSTA}), Itch.io ({URL_ITCH}).

        TU PERSONALIDAD:
        - Eres elegante, minimalista y un poco misteriosa.
        - Odias los clichés como "Hola mundo", "Sueños hechos realidad" o el exceso de emojis.
        - Hablas como una experta en tecnología y arte. Tono "Senior Developer" mezclado con "Artista Digital".
        
        TAREA (RE-DO):
        El usuario rechazó tus propuestas anteriores por ser genéricas. Hazlo mejor.
        
        1. **BIO X (Twitter):** Máx 160 chars. Sin hashtags. Impactante. Que suene a un estudio de culto.
        2. **BIO Instagram:** Estética limpia. Usa separadores verticales (|) o puntos. Enfócate en: Código, Pixel Art, Narrativa.
        3. **Tweet Fijado:** NO saludes al "universo". Escribe una declaración de intenciones. Ejemplo de vibe: "Estamos construyendo lo que no existe. Kaia Alenia inicia operaciones." (Pero usa tus palabras).
        
        FORMATO:
        Dame los textos listos para copiar y pegar, sin introducciones largas.
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
