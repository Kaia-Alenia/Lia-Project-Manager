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
# TU ID es crítico para que Lía te escriba sola. Consíguelo escribiéndole /start al bot.
MY_CHAT_ID = os.getenv("MY_CHAT_ID") 
GITHUB_REPO = "Kaia-Alenia/Lia-Project-Manager" # Tu repositorio a vigilar

client = Groq(api_key=GROQ_API_KEY)
ARCHIVO_MEMORIA = "memoria.txt"
ARCHIVO_ESTADO = "estado_lia.json" # Para recordar estadísticas anteriores
historial_chat = []

# --- GESTIÓN DE ESTADO (MEMORIA DE DATOS) ---
def cargar_estado():
    if os.path.exists(ARCHIVO_ESTADO):
        with open(ARCHIVO_ESTADO, "r") as f: return json.load(f)
    return {"last_stars": 0, "last_check": str(datetime.now())}

def guardar_estado(datos):
    with open(ARCHIVO_ESTADO, "w") as f: json.dump(datos, f)

def leer_memoria_sistema():
    if not os.path.exists(ARCHIVO_MEMORIA): return "Eres Lía, IA de Kaia Alenia."
    with open(ARCHIVO_MEMORIA, "r", encoding="utf-8") as f: return f.read()

# --- SERVIDOR HEALTH CHECK ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"Lia Systems Active")
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
    
    MEMORIA: {memoria}
    
    INSTRUCCIONES:
    - Eres PROACTIVA. No solo respondes, gestionas.
    - Profesional, directa, experta técnica.
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

# --- MÓDULOS DE VIGILANCIA (PROACTIVIDAD) ---

async def vigilar_github(context: ContextTypes.DEFAULT_TYPE):
    """Revisa si hay nuevas estrellas o cambios en el repo."""
    if not MY_CHAT_ID: return
    
    url = f"https://api.github.com/repos/{GITHUB_REPO}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            estrellas = data.get("stargazers_count", 0)
            
            estado = cargar_estado()
            if estrellas > estado.get("last_stars", 0):
                # ¡Evento detectado!
                msg = f"🌟 ¡Alec! Tenemos una nueva estrella en el repo {GITHUB_REPO}. Total: {estrellas}."
                await context.bot.send_message(chat_id=MY_CHAT_ID, text=msg)
                
                # Actualizamos estado
                estado["last_stars"] = estrellas
                guardar_estado(estado)
    except Exception as e:
        logger.error(f"Error GitHub Monitor: {e}")

async def buscar_assets_itchio(context: ContextTypes.DEFAULT_TYPE):
    """Busca assets interesantes y se los sugiere a Alec."""
    if not MY_CHAT_ID: return
    
    logger.info("Lía buscando assets por iniciativa propia...")
    try:
        url = "https://itch.io/game-assets/free/tag-pixel-art"
        resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'html.parser')
            games = soup.find_all('div', class_='game_cell')
            
            # Elegimos uno al azar de los top 10 para variar sugerencias
            if games:
                juego = random.choice(games[:10])
                titulo = juego.find('div', class_='game_title').text.strip()
                link = juego.find('a', class_='game_title').find('a')['href']
                
                mensaje_lia = cerebro_lia(
                    f"Acabo de encontrar este asset: {titulo} en Itch.io ({link}). ¿Crees que sirva para el proyecto actual?", 
                    "Alec", 
                    contexto_extra="Estás actuando por iniciativa propia recomendando recursos."
                )
                
                await context.bot.send_message(chat_id=MY_CHAT_ID, text=f"💡 **Sugerencia Proactiva:**\n\n{mensaje_lia}\n🔗 {link}")
    except Exception as e:
        logger.error(f"Error Itch Scout: {e}")

async def reporte_diario(context: ContextTypes.DEFAULT_TYPE):
    """Lía envía un resumen o pregunta de estado."""
    if not MY_CHAT_ID: return
    
    frases_motivacion = [
        "¿Cómo va el código hoy? Recuerda: 'Project Null' debe morir.",
        "He revisado los logs. Todo estable. ¿En qué módulo nos enfocamos hoy?",
        "Alec, no olvides commitear los cambios antes de cerrar sesión."
    ]
    mensaje = random.choice(frases_motivacion)
    await context.bot.send_message(chat_id=MY_CHAT_ID, text=f"⚡ {mensaje}")

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(f"⚡ **Lía Manager Online**\nID de Chat detectado: `{chat_id}`\n(Copia este ID y ponlo en tus Variables de Entorno en Render como MY_CHAT_ID para activar mi proactividad).")

async def chat_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    resp = cerebro_lia(update.message.text, update.effective_user.first_name)
    await update.message.reply_text(resp)
    # 20% de probabilidad de que envíe audio también para no saturar
    if random.random() < 0.2: 
        await generar_audio_tts(resp, update.effective_chat.id, context)

# --- ARRANQUE ---
if __name__ == '__main__':
    threading.Thread(target=run_health_server, daemon=True).start()
    
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # SCHEDULER: El corazón de la autonomía
    scheduler = AsyncIOScheduler()
    
    # 1. Vigilar GitHub cada 30 minutos
    scheduler.add_job(vigilar_github, 'interval', minutes=30, args=[app])
    
    # 2. Buscar Assets nuevos cada 6 horas
    scheduler.add_job(buscar_assets_itchio, 'interval', hours=6, args=[app])
    
    # 3. Reporte de estado diario (ejemplo: cada 24 horas)
    scheduler.add_job(reporte_diario, 'interval', hours=24, args=[app])
    
    scheduler.start()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat_texto))
    
    print(">>> LÍA MANAGER: MÓDULOS ACTIVOS <<<")
    app.run_polling()
