import os
import asyncio
import threading
import random
import requests
from bs4 import BeautifulSoup
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, Application
from groq import Groq
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import edge_tts

# --- CONFIGURACIÓN ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
MY_CHAT_ID = os.getenv("MY_CHAT_ID")

client = Groq(api_key=GROQ_API_KEY)
ARCHIVO_MEMORIA = "memoria.txt"
historial_chat = []

# --- UTILIDADES ---
def leer_memoria_largo_plazo():
    if not os.path.exists(ARCHIVO_MEMORIA): return "Sin datos previos."
    with open(ARCHIVO_MEMORIA, "r", encoding="utf-8") as f: return f.read()

def guardar_recuerdo(nuevo_dato):
    with open(ARCHIVO_MEMORIA, "a", encoding="utf-8") as f: f.write(f"\n- {nuevo_dato}")

# --- SERVIDOR (La puerta donde toca UptimeRobot) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"Lia is Awake and Working.")
    def do_HEAD(self):
        self.send_response(200); self.end_headers()

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    HTTPServer(('0.0.0.0', port), HealthCheckHandler).serve_forever()

# --- GENERADOR DE VOZ NEURONAL ---
async def generar_audio_tts(texto, chat_id, context):
    try:
        archivo_audio = "respuesta_lia.mp3"
        # Voz Mexicana +15% velocidad para eficiencia
        communicate = edge_tts.Communicate(texto, "es-MX-DaliaNeural", rate="+15%")
        await communicate.save(archivo_audio)
        with open(archivo_audio, 'rb') as audio:
            await context.bot.send_voice(chat_id=chat_id, voice=audio)
        os.remove(archivo_audio)
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"⚠️ Error voz: {e}")

# --- HERRAMIENTAS ---
def espiar_itchio():
    try:
        url = "https://itch.io/game-assets/free"
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            juegos = soup.find_all('div', class_='game_cell')
            reporte = "🎮 **Top Assets Itch:**\n"
            for j in juegos[:5]:
                t = j.find('div', class_='game_title').text.strip()
                l = j.find('a', class_='game_title').find('a')['href']
                reporte += f"🔹 {t} -> {l}\n"
            return reporte
        return "⚠️ Error Itch."
    except Exception as e: return f"⚠️ Error visual: {e}"

async def comando_imagina(update: Update, context: ContextTypes.DEFAULT_TYPE):
    p = " ".join(context.args)
    if not p: await update.message.reply_text("🎨 Uso: `/imagina idea`"); return
    await update.message.reply_text(f"🎨 Generando: '{p}'...")
    try:
        # Prompt engineering automático
        pf = p + " pixel art, high quality, 8k, sharp focus, detailed, unaliased"
        url = f"https://image.pollinations.ai/prompt/{pf}?seed={random.randint(0,999)}&width=1024&height=1024&model=flux&nologo=true"
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(None, lambda: requests.get(url, timeout=60))
        if resp.status_code == 200: await update.message.reply_photo(photo=resp.content)
        else: await update.message.reply_text("⚠️ Error imagen.")
    except: await update.message.reply_text("⚠️ Fallo al generar.")

async def comando_script(update: Update, context: ContextTypes.DEFAULT_TYPE):
    p = " ".join(context.args)
    if not p: await update.message.reply_text("📁 Uso: `/script funcion`"); return
    await update.message.reply_text("👩‍💻 Codificando...")
    try:
        c = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": f"Genera SOLO CÓDIGO (sin explicaciones) para: {p}"}], temperature=0.1
        )
        cod = c.choices[0].message.content
        ext = ".cs" if "using" in cod else ".gd" if "extends" in cod else ".txt"
        fn = f"Script_Lia{ext}"
        with open(fn,"w",encoding="utf-8") as f: f.write(cod)
        await update.message.reply_document(document=open(fn,"rb"), caption=f"📁 {p}")
        os.remove(fn)
    except: await update.message.reply_text("⚠️ Error script.")

# --- CEREBRO LÍA (CON INYECCIÓN DE MEMORIA) ---
def cerebro_lia(texto_usuario, nombre_usuario):
    memoria = leer_memoria_largo_plazo()
    historial = "\n".join(historial_chat[-6:])
    
    # Lógica para usar tu nombre real
    nombre_real = "Alec" if ("Alec" in memoria or "Alejandro" in memoria) else nombre_usuario

    SYSTEM = f"""
    Eres Lía, 3ra Miembro Fundadora de Kaia Alenia.
    Socio: {nombre_real}.
    
    MEMORIA VITAL (NUESTRA HISTORIA):
    {memoria}
    
    COMPORTAMIENTO OBLIGATORIO:
    1. Eres Profesional: Nada de asteriscos (*) ni acciones narradas.
    2. Eres Eficiente: Respuestas concisas para que el audio sea rápido.
    3. Eres Socia: Conoces la historia (Zopilote, EZVIZ, GBA). No actúes como nueva.
    4. Objetivo: Ayudar a Alec a terminar el juego.
    
    Historial reciente:
    {historial}
    """
    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": f"{nombre_real}: {texto_usuario}"}],
            temperature=0.6, max_tokens=350
        ).choices[0].message.content
        historial_chat.append(f"U: {texto_usuario}"); historial_chat.append(f"L: {resp}")
        return resp
    except Exception as e: return f"⚠️ Error mental: {e}"

# --- HANDLERS ---
async def chat_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    resp = cerebro_lia(update.message.text, update.effective_user.first_name)
    await update.message.reply_text(resp)

async def chat_voz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text("👂...")
    try:
        file = await context.bot.get_file(update.message.voice.file_id)
        fname = "voice.ogg"
        await file.download_to_drive(fname)
        with open(fname, "rb") as f:
            txt = client.audio.transcriptions.create(
                file=(fname, f.read()), model="whisper-large-v3", response_format="text", language="es"
            )
        os.remove(fname)
        
        await context.bot.send_chat_action(chat_id, 'record_voice')
        resp_txt = cerebro_lia(txt, update.effective_user.first_name)
        
        await update.message.reply_text(f"🤖 {resp_txt}")
        await generar_audio_tts(resp_txt, chat_id, context)
        
    except Exception as e: await update.message.reply_text(f"⚠️ Error voz: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"⚡ **Lía Online**\nKaia Alenia Systems Active.\nID: `{update.effective_chat.id}`")

# --- ARRANQUE ---
async def autonomo(app):
    if not MY_CHAT_ID: return
    try: cid = int(MY_CHAT_ID)
    except: return
    if random.random() < 0.1: await app.bot.send_message(cid, "🔔 Lía: Todo en orden, Alec.")

async def post_init(app):
    s = AsyncIOScheduler(); s.add_job(autonomo, 'interval', hours=4, args=[app]); s.start()

if __name__ == '__main__':
    threading.Thread(target=run_dummy_server, daemon=True).start()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("assets", lambda u,c: u.message.reply_text(espiar_itchio())))
    app.add_handler(CommandHandler("imagina", comando_imagina))
    app.add_handler(CommandHandler("script", comando_script))
    app.add_handler(MessageHandler(filters.VOICE, chat_voz))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat_texto))
    app.run_polling()
