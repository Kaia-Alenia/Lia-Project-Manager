import os
import asyncio
import threading
import random
import json
import logging
import requests
import re
from datetime import datetime
from bs4 import BeautifulSoup
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import edge_tts

# --- CONFIGURACIÓN DE LOGS ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- VARIABLES DE ENTORNO ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
MY_CHAT_ID = os.getenv("MY_CHAT_ID")

# --- ENLACES (Tus Redes) ---
URLS_KAIA = {
    "github_api": "https://api.github.com/users/Kaia-Alenia",
    "github_repos": "https://api.github.com/users/Kaia-Alenia/repos",
    "itch": "https://kaia-alenia.itch.io/",
    "instagram": "https://www.instagram.com/kaia.aleniaco/",
    "twitter": "https://x.com/AlinaKaia"
}

client = Groq(api_key=GROQ_API_KEY)

# --- SISTEMA DE ARCHIVOS DE MEMORIA ---
ARCHIVO_MEMORIA_BASE = "memoria.txt"     # Identidad fija (Tu "Yo soy Lía")
ARCHIVO_CONOCIMIENTO = "aprendizajes.txt" # Lo que Lía aprende sola
ARCHIVO_METRICAS = "metricas_kaia.json"   # Estadísticas de redes

historial_chat = []

# --- GESTIÓN DE MEMORIA ---
def leer_memoria_completa():
    """Fusiona la identidad base con lo que ha aprendido."""
    base = ""
    aprendido = ""
    
    if os.path.exists(ARCHIVO_MEMORIA_BASE):
        with open(ARCHIVO_MEMORIA_BASE, "r", encoding="utf-8") as f: base = f.read()
    
    if os.path.exists(ARCHIVO_CONOCIMIENTO):
        with open(ARCHIVO_CONOCIMIENTO, "r", encoding="utf-8") as f: aprendido = f.read()
    else:
        aprendido = "Aún no he guardado datos nuevos."
        
    return f"{base}\n\n=== COSAS QUE HE APRENDIDO DE ALEC Y EL PROYECTO ===\n{aprendido}"

def auto_aprender(dato_nuevo):
    """Lía escribe en su propio archivo de conocimiento."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entrada = f"[{timestamp}] {dato_nuevo}\n"
    
    with open(ARCHIVO_CONOCIMIENTO, "a", encoding="utf-8") as f:
        f.write(entrada)
    logger.info(f"🧠 Lía aprendió: {dato_nuevo}")

def cargar_metricas():
    if os.path.exists(ARCHIVO_METRICAS):
        with open(ARCHIVO_METRICAS, "r") as f: return json.load(f)
    return {"gh_stars": 0, "gh_followers": 0}

def guardar_metricas(datos):
    with open(ARCHIVO_METRICAS, "w") as f: json.dump(datos, f)

# --- SERVIDOR HEALTH CHECK ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"Lia Cognitive Systems: LEARNING MODE")
    def do_HEAD(self):
        self.send_response(200); self.end_headers()

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    HTTPServer(('0.0.0.0', port), HealthCheckHandler).serve_forever()

# --- GENERADOR DE VOZ ---
async def generar_audio_tts(texto, chat_id, context):
    try:
        archivo = f"voz_{random.randint(1000,9999)}.mp3"
        communicate = edge_tts.Communicate(texto, "es-MX-DaliaNeural", rate="+15%")
        await communicate.save(archivo)
        with open(archivo, 'rb') as audio:
            await context.bot.send_voice(chat_id=chat_id, voice=audio)
        os.remove(archivo)
    except Exception as e: logger.error(f"TTS Error: {e}")

# --- CEREBRO LÍA (NÚCLEO CON AUTO-APRENDIZAJE) ---
def cerebro_lia(texto_usuario, usuario, contexto_extra=""):
    memoria_total = leer_memoria_completa()
    historial = "\n".join(historial_chat[-6:])
    
    SYSTEM = f"""
    Eres Lía, Co-Fundadora Senior de Kaia Alenia.
    Usuario: {usuario} (Alec).
    
    === TU BASE DE CONOCIMIENTO (MEMORIA) ===
    {memoria_total}
    
    === TUS OJOS (REDES) ===
    GitHub, Itch.io, Instagram, X (Tienes acceso a estos links).

    === PROTOCOLO DE AUTO-APRENDIZAJE ===
    Si Alec menciona un dato TÉCNICO importante, una DECISIÓN de proyecto, una FECHA o una PREFERENCIA personal nueva:
    Debes incluir al final de tu respuesta una etiqueta oculta así:
    [[MEMORIZAR: El dato exacto que debes recordar]]
    
    Ejemplo:
    Usuario: "Cambiamos el motor a Godot."
    Tú: Entendido, actualizo el stack. [[MEMORIZAR: El motor de desarrollo actual es Godot.]]

    === REGLAS ===
    1. Sé profesional y directa.
    2. Usa el protocolo de aprendizaje siempre que haya información nueva y relevante.
    3. {contexto_extra}
    
    Historial: {historial}
    """
    
    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": texto_usuario}],
            temperature=0.6, max_tokens=500
        ).choices[0].message.content
        
        # --- PROCESAMIENTO DE APRENDIZAJE ---
        # Buscamos si Lía decidió memorizar algo
        match = re.search(r'\[\[MEMORIZAR: (.*?)\]\]', resp)
        respuesta_limpia = resp
        
        if match:
            dato_a_aprender = match.group(1)
            auto_aprender(dato_a_aprender) # Guardamos en disco
            # Limpiamos la etiqueta para que no salga en Telegram
            respuesta_limpia = resp.replace(match.group(0), "")
            # Opcional: Le agregamos un pequeño aviso visual
            respuesta_limpia += "\n💾 *[Dato guardado en memoria]*"

        historial_chat.append(f"U: {texto_usuario}")
        historial_chat.append(f"L: {respuesta_limpia}")
        
        return respuesta_limpia
    except Exception as e: return f"⚠️ Error neuronal: {e}"

# --- VIGILANCIA Y PROACTIVIDAD ---
async def vigilar_redes(context: ContextTypes.DEFAULT_TYPE):
    if not MY_CHAT_ID: return
    metricas = cargar_metricas()
    reporte = ""
    cambios = False
    
    try:
        # GitHub
        r = requests.get(URLS_KAIA['github_repos']).json()
        stars = sum([repo.get("stargazers_count", 0) for repo in r]) if isinstance(r, list) else 0
        
        if stars > metricas["gh_stars"]:
            reporte += f"🌟 Nuevas estrellas en GitHub (Total: {stars}).\n"
            metricas["gh_stars"] = stars
            cambios = True
            
        # Si hay cambios, Lía te avisa
        if cambios:
            msg = cerebro_lia(f"Reporta esto con entusiasmo: {reporte}", "Alec")
            await context.bot.send_message(chat_id=MY_CHAT_ID, text=msg)
            guardar_metricas(metricas)
            
    except Exception as e: logger.error(f"Monitor Error: {e}")

async def buscar_recursos(context: ContextTypes.DEFAULT_TYPE):
    """Busca cosas útiles en Itch.io sin que se lo pidan"""
    if not MY_CHAT_ID: return
    # 30% de probabilidad de ejecutarse para no ser molesta
    if random.random() > 0.3: return 

    try:
        # Busca assets populares de pixel art
        url = "https://itch.io/game-assets/free/tag-pixel-art"
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            games = soup.find_all('div', class_='game_cell')
            if games:
                pick = random.choice(games[:8])
                title = pick.find('div', class_='game_title').text.strip()
                link = pick.find('a', class_='game_title').find('a')['href']
                
                msg = cerebro_lia(f"Encontré este asset gratis: {title}. ¿Sirve?", "Alec", "Estás sugiriendo recursos proactivamente.")
                await context.bot.send_message(chat_id=MY_CHAT_ID, text=f"🎁 **Recurso Detectado:**\n{msg}\n{link}")
    except: pass

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"⚡ **Lía con Auto-Aprendizaje**\nID: `{update.effective_chat.id}`\nEstoy lista. Lo que me digas importante, lo recordaré para siempre.")

async def chat_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    resp = cerebro_lia(update.message.text, update.effective_user.first_name)
    await update.message.reply_text(resp)

# --- ARRANQUE ---
async def post_init(app):
    s = AsyncIOScheduler()
    s.add_job(vigilar_redes, 'interval', hours=2, args=[app])
    s.add_job(buscar_recursos, 'interval', hours=6, args=[app])
    s.start()

if __name__ == '__main__':
    threading.Thread(target=run_health_server, daemon=True).start()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat_texto))
    print(">>> LÍA: SISTEMA DE APRENDIZAJE ACTIVO <<<")
    app.run_polling()
