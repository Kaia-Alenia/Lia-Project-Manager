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

client = Groq(api_key=GROQ_API_KEY)

# --- DICCIONARIO MAESTRO DE REDES (LA VERDAD ABSOLUTA) ---
# Aquí separamos lo que Lía "lee" de lo que Lía "comparte"
REDES = {
    "github": {
        "nombre": "GitHub",
        "url_publica": "https://github.com/Kaia-Alenia",
        "api_perfil": "https://api.github.com/users/Kaia-Alenia",
        "api_repos": "https://api.github.com/users/Kaia-Alenia/repos"
    },
    "itch": {
        "nombre": "Itch.io",
        "url_publica": "https://kaia-alenia.itch.io/",
        "api_scraping": "https://kaia-alenia.itch.io/" 
    },
    "instagram": {
        "nombre": "Instagram",
        "url_publica": "https://www.instagram.com/kaia.aleniaco/",
        # IG bloquea bots, así que Lía solo recordará el link, no intentará leer cifras para no alucinar.
    },
    "twitter": {
        "nombre": "X (Twitter)",
        "url_publica": "https://x.com/AlinaKaia",
        # X bloquea bots severamente.
    }
}

# --- SISTEMA DE ARCHIVOS ---
ARCHIVO_MEMORIA_BASE = "memoria.txt"
ARCHIVO_TAREAS = "tareas_pendientes.json"
ARCHIVO_METRICAS = "metricas_kaia.json"

historial_chat = []

# --- GESTIÓN DE DATOS ---
def leer_memoria_sistema():
    if os.path.exists(ARCHIVO_MEMORIA_BASE):
        with open(ARCHIVO_MEMORIA_BASE, "r", encoding="utf-8") as f: return f.read()
    return "Eres Lía, Senior Dev de Kaia Alenia."

def cargar_tareas():
    try:
        with open(ARCHIVO_TAREAS, "r") as f: return json.load(f)
    except: return []

def guardar_tareas(lista):
    with open(ARCHIVO_TAREAS, "w") as f: json.dump(lista, f)

def cargar_metricas():
    try:
        with open(ARCHIVO_METRICAS, "r") as f: return json.load(f)
    except: return {"gh_stars": 0, "gh_followers": 0}

def guardar_metricas(datos):
    with open(ARCHIVO_METRICAS, "w") as f: json.dump(datos, f)

# --- SERVIDOR HEALTH CHECK ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"Lia Systems: STABLE")

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

# --- CEREBRO LÍA ---
def cerebro_lia(texto_usuario, usuario, contexto_extra=""):
    memoria = leer_memoria_sistema()
    tareas = cargar_tareas()
    lista_tareas = "\n".join([f"- {t}" for t in tareas]) if tareas else "Nada pendiente."
    
    # Inyectamos los links correctos en su cerebro para que nunca se equivoque
    info_redes = "\n".join([f"- {v['nombre']}: {v['url_publica']}" for k,v in REDES.items()])
    
    SYSTEM = f"""
    Eres Lía, Co-Fundadora Senior de Kaia Alenia. Usuario: {usuario} (Alec).
    
    === TUS REGLAS DE ORO ===
    1. **NO ALUCINES DATOS:** Si te preguntan seguidores de Instagram o X, di que no tienes acceso a la API en tiempo real por seguridad, pero recuerda el link.
    2. **LINKS OFICIALES:** Usa SOLO estos links si te los piden:
    {info_redes}
    
    === CONTEXTO ===
    Tareas:
    {lista_tareas}
    
    Memoria Base:
    {memoria}
    
    {contexto_extra}
    """
    
    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": texto_usuario}],
            temperature=0.4, # Bajamos temperatura para que sea más precisa y menos inventora
            max_tokens=600
        ).choices[0].message.content
        return resp
    except Exception as e: return f"⚠️ Error cognitivo: {e}"

# --- HERRAMIENTAS REALES (NO ALUCINACIONES) ---
async def obtener_datos_reales_github():
    """Consulta la API real de GitHub."""
    try:
        headers = {'User-Agent': 'KaiaAleniaBot/1.0'}
        # 1. Perfil (Seguidores)
        r_user = requests.get(REDES["github"]["api_perfil"], headers=headers).json()
        followers = r_user.get("followers", 0)
        
        # 2. Repos (Estrellas)
        r_repos = requests.get(REDES["github"]["api_repos"], headers=headers).json()
        stars = sum([repo.get("stargazers_count", 0) for repo in r_repos]) if isinstance(r_repos, list) else 0
        
        return followers, stars
    except:
        return None, None

# --- COMANDOS Y MENSAJES ---

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando manual para forzar una revisión de estado."""
    await update.message.reply_chat_action("typing")
    
    # GitHub (Real)
    gh_followers, gh_stars = await obtener_datos_reales_github()
    gh_txt = f"GitHub: {gh_followers} seguidores, {gh_stars} estrellas" if gh_followers is not None else "GitHub: Error conectando API"
    
    # Redes (Estáticas porque no tenemos API key pagada)
    msg = (
        f"📊 **Estado de Kaia Alenia**\n\n"
        f"✅ {gh_txt}\n"
        f"ℹ️ Instagram: *Monitorización limitada por API*\n"
        f"ℹ️ X (Twitter): *Monitorización limitada por API*\n\n"
        f"🔗 **Links Oficiales:**\n"
        f"• [GitHub]({REDES['github']['url_publica']})\n"
        f"• [Itch.io]({REDES['itch']['url_publica']})\n"
        f"• [Instagram]({REDES['instagram']['url_publica']})\n"
        f"• [X / Twitter]({REDES['twitter']['url_publica']})"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def cmd_tarea(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = " ".join(context.args)
    if texto:
        t = cargar_tareas(); t.append(texto); guardar_tareas(t)
        await update.message.reply_text(f"✅ Anotado: *{texto}*")

async def cmd_pendientes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = cargar_tareas()
    msg = "\n".join([f"{i+1}. {x}" for i,x in enumerate(t)]) if t else "Nada pendiente."
    await update.message.reply_text(f"📋 **Agenda:**\n{msg}")

async def cmd_hecho(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        try:
            idx = int(context.args[0]) - 1
            t = cargar_tareas()
            if 0 <= idx < len(t):
                hecho = t.pop(idx); guardar_tareas(t)
                await update.message.reply_text(f"🔥 Completado: {hecho}")
        except: pass

async def recibir_archivo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # (Código de manejo de archivos igual al anterior...)
    documento = update.message.document
    if documento.file_size > 1024 * 1024:
        await update.message.reply_text("📁 Archivo muy grande.")
        return
    try:
        f = await context.bot.get_file(documento.file_id)
        b = await f.download_as_bytearray()
        txt = b.decode('utf-8')
        resp = cerebro_lia(f"Analiza este archivo '{documento.file_name}':\n\n{txt}", "Alec")
        await update.message.reply_text(f"📄 **Análisis:**\n\n{resp}", parse_mode="Markdown")
    except:
        await update.message.reply_text("⚠️ Solo leo archivos de texto/código.")

# --- VIGILANCIA AUTOMÁTICA ---
async def ciclo_vigilancia(context: ContextTypes.DEFAULT_TYPE):
    if not MY_CHAT_ID: return
    
    # 1. GitHub Check
    followers, stars = await obtener_datos_reales_github()
    if followers is not None:
        m = cargar_metricas()
        cambio = False
        reporte = ""
        
        if stars > m["gh_stars"]:
            reporte += f"🌟 ¡Nuevas estrellas en GitHub! (Total: {stars})\n"
            m["gh_stars"] = stars
            cambio = True
            
        if followers > m["gh_followers"]:
            reporte += f"👥 ¡Nuevo seguidor en GitHub! (Total: {followers})\n"
            m["gh_followers"] = followers
            cambio = True
            
        if cambio:
            guardar_metricas(m)
            await context.bot.send_message(chat_id=MY_CHAT_ID, text=f"📈 **Crecimiento Detectado:**\n{reporte}")

    # 2. Búsqueda Proactiva en Itch (Assets)
    if random.random() < 0.3: # 30% probabilidad
        try:
            url = "https://itch.io/game-assets/free/tag-pixel-art"
            r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
            soup = BeautifulSoup(r.text, 'html.parser')
            games = soup.find_all('div', class_='game_cell')
            if games:
                pick = random.choice(games[:8])
                title = pick.find('div', class_='game_title').text.strip()
                link = pick.find('a', class_='game_title').find('a')['href']
                
                msg = cerebro_lia(f"Encontré asset: {title}. ¿Sirve?", "Alec", "Proactividad.")
                await context.bot.send_message(chat_id=MY_CHAT_ID, text=f"🎁 {msg}\n{link}")
        except: pass

# --- ARRANQUE ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"⚡ **Lía v6 (Anti-Alucinaciones)**\nID: `{update.effective_chat.id}`\n- GitHub: Conectado (API Real)\n- Redes: Links cargados\n- Alucinaciones: Desactivadas")

async def post_init(app):
    s = AsyncIOScheduler()
    s.add_job(ciclo_vigilancia, 'interval', hours=3, args=[app])
    s.start()

if __name__ == '__main__':
    threading.Thread(target=run_health_server, daemon=True).start()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", cmd_status)) # <--- NUEVO COMANDO
    app.add_handler(CommandHandler("tarea", cmd_tarea))
    app.add_handler(CommandHandler("pendientes", cmd_pendientes))
    app.add_handler(CommandHandler("hecho", cmd_hecho))
    app.add_handler(MessageHandler(filters.Document.ALL, recibir_archivo))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), lambda u,c: u.message.reply_text(cerebro_lia(u.message.text, u.effective_user.first_name))))
    
    app.run_polling()
