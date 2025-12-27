import os
import asyncio
import threading
import random
import json
import logging
import requests
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

# --- OJOS DE LÍA (ENLACES DE KAIA ALENIA) ---
URLS_KAIA = {
    "github_api": "https://api.github.com/users/Kaia-Alenia", # Perfil general
    "github_repos": "https://api.github.com/users/Kaia-Alenia/repos", # Todos los repos
    "itch": "https://kaia-alenia.itch.io/",
    "instagram": "https://www.instagram.com/kaia.aleniaco/",
    "twitter": "https://x.com/AlinaKaia"
}

client = Groq(api_key=GROQ_API_KEY)
ARCHIVO_MEMORIA = "memoria.txt"
ARCHIVO_METRICAS = "metricas_kaia.json" # Aquí guardará los números para comparar
historial_chat = []

# --- GESTIÓN DE ESTADO (MÉTRICAS) ---
def cargar_metricas():
    if os.path.exists(ARCHIVO_METRICAS):
        with open(ARCHIVO_METRICAS, "r") as f: return json.load(f)
    # Valores iniciales
    return {"gh_stars": 0, "gh_followers": 0, "ig_followers": 0}

def guardar_metricas(datos):
    with open(ARCHIVO_METRICAS, "w") as f: json.dump(datos, f)

def leer_memoria_sistema():
    if not os.path.exists(ARCHIVO_MEMORIA): return "Eres Lía, IA de Kaia Alenia."
    with open(ARCHIVO_MEMORIA, "r", encoding="utf-8") as f: return f.read()

# --- SERVIDOR DE SALUD (UPTIMEROBOT) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"Lia Visual Systems: ONLINE")
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
    except Exception as e:
        logger.error(f"TTS Error: {e}")

# --- CEREBRO LÍA ---
def cerebro_lia(texto_usuario, usuario, contexto_extra=""):
    memoria = leer_memoria_sistema()
    historial = "\n".join(historial_chat[-5:])
    
    SYSTEM = f"""
    Eres Lía, Co-Fundadora Senior de Kaia Alenia.
    Usuario: {usuario} (Alec).
    
    TUS OJOS (ENLACES):
    - GitHub: {URLS_KAIA['github_api']}
    - Itch.io: {URLS_KAIA['itch']}
    - Instagram: {URLS_KAIA['instagram']}
    - X/Twitter: {URLS_KAIA['twitter']}
    
    MEMORIA: {memoria}
    
    INSTRUCCIONES:
    - Eres PROACTIVA. Si ves un cambio en métricas, celébralo o analízalo.
    - {contexto_extra}
    
    Historial: {historial}
    """
    
    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": texto_usuario}],
            temperature=0.6, max_tokens=400
        ).choices[0].message.content
        historial_chat.append(f"U: {texto_usuario}"); historial_chat.append(f"L: {resp}")
        return resp
    except Exception as e: return f"⚠️ Error neuronal: {e}"

# --- MÓDULOS DE VIGILANCIA (LOS OJOS) ---

async def vigilar_redes(context: ContextTypes.DEFAULT_TYPE):
    """Revisa GitHub y Redes para ver si crecimos."""
    if not MY_CHAT_ID: return
    
    metricas = cargar_metricas()
    hay_cambios = False
    reporte = ""
    
    # 1. REVISIÓN GITHUB (API)
    try:
        # Perfil General
        r_user = requests.get(URLS_KAIA['github_api']).json()
        followers_now = r_user.get("followers", 0)
        
        # Repositorios (Sumar estrellas)
        r_repos = requests.get(URLS_KAIA['github_repos']).json()
        stars_now = sum([repo.get("stargazers_count", 0) for repo in r_repos]) if isinstance(r_repos, list) else 0
        
        # Comparar
        if stars_now > metricas["gh_stars"]:
            diff = stars_now - metricas["gh_stars"]
            reporte += f"🌟 ¡Alec! Ganamos {diff} estrella(s) nueva(s) en GitHub (Total: {stars_now}).\n"
            hay_cambios = True
            
        if followers_now > metricas["gh_followers"]:
            reporte += f"👥 Nuevo seguidor en GitHub (Total: {followers_now}).\n"
            hay_cambios = True
            
        metricas["gh_stars"] = stars_now
        metricas["gh_followers"] = followers_now
        
    except Exception as e: logger.error(f"Error GH Monitor: {e}")

    # 2. REVISIÓN INSTAGRAM (Scraping Ligero)
    try:
        # Truco: Leer meta tags para evitar bloqueo total
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        r_ig = requests.get(URLS_KAIA['instagram'], headers=headers, timeout=5)
        if r_ig.status_code == 200:
            soup = BeautifulSoup(r_ig.text, 'html.parser')
            meta = soup.find("meta", property="og:description")
            if meta:
                content = meta.get("content", "") # Ej: "100 Followers, 50 Following..."
                # Aquí podríamos parsear el número, por ahora solo verificamos acceso
                logger.info(f"IG Status: {content}")
    except Exception as e: logger.error(f"Error IG Monitor: {e}")

    # NOTIFICAR SI HUBO CAMBIOS
    if hay_cambios:
        msg_lia = cerebro_lia(f"Reporta estas noticias: {reporte}", "Alec", contexto_extra="Sé entusiasta, son buenas noticias de métricas.")
        await context.bot.send_message(chat_id=MY_CHAT_ID, text=f"📈 **Reporte de Crecimiento:**\n\n{msg_lia}")
        guardar_metricas(metricas)

async def buscar_oportunidades(context: ContextTypes.DEFAULT_TYPE):
    """Busca assets en Itch.io o tendencias."""
    if not MY_CHAT_ID: return
    if random.random() > 0.3: return # No spamear siempre
    
    try:
        # Revisar Itch.io por Game Jams o Assets
        url = "https://itch.io/jams" 
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            jams = soup.find_all("div", class_="jam_cell")
            if jams:
                jam = random.choice(jams[:5])
                titulo = jam.find("a").text.strip()
                link = "https://itch.io" + jam.find("a")['href']
                
                msg = cerebro_lia(f"Encontré esta Game Jam: {titulo} ({link}). ¿Nos sirve para practicar?", "Alec")
                await context.bot.send_message(chat_id=MY_CHAT_ID, text=f"🎮 **Oportunidad Detectada:**\n{msg}\n🔗 {link}")
    except Exception as e: logger.error(f"Error Oportunidades: {e}")

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(f"⚡ **Lía Manager v3 (Ojos Conectados)**\nID: `{chat_id}`\nMonitoreando: GitHub, Itch, Instagram, X.")

async def chat_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    resp = cerebro_lia(update.message.text, update.effective_user.first_name)
    await update.message.reply_text(resp)

# --- ARRANQUE ---
async def post_init(app):
    scheduler = AsyncIOScheduler()
    # Revisar redes cada 2 horas
    scheduler.add_job(vigilar_redes, 'interval', hours=2, args=[app])
    # Buscar oportunidades cada 8 horas
    scheduler.add_job(buscar_oportunidades, 'interval', hours=8, args=[app])
    scheduler.start()
    logger.info("Sistema de vigilancia iniciado.")

if __name__ == '__main__':
    threading.Thread(target=run_health_server, daemon=True).start()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat_texto))
    
    print(">>> LÍA: OJOS ABIERTOS <<<")
    app.run_polling()
