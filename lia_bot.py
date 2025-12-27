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
from gtts import gTTS # <--- NUEVA IMPORTACIÓN

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

# --- SERVIDOR ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"Lia Voice Active")
    def do_HEAD(self):
        self.send_response(200); self.end_headers()

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    HTTPServer(('0.0.0.0', port), HealthCheckHandler).serve_forever()

# --- NUEVA FUNCIÓN: GENERADOR DE VOZ (TTS) ---
async def generar_audio_tts(texto, chat_id, context):
    """Convierte texto a voz y envía el audio."""
    try:
        # Creamos el audio en Español Latino ('es' con tld 'com.mx' suele ser más neutro/latino)
        tts = gTTS(text=texto, lang='es', tld='com.mx') 
        archivo_audio = "respuesta_lia.mp3"
        tts.save(archivo_audio)
        
        # Enviamos el audio
        with open(archivo_audio, 'rb') as audio:
            await context.bot.send_voice(chat_id=chat_id, voice=audio)
        
        # Limpieza
        os.remove(archivo_audio)
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"⚠️ Se me fue la voz: {e}")

# --- LÓGICA DE SCRAPING (ITCH.IO) ---
def espiar_itchio():
    try:
        url = "https://itch.io/game-assets/free"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            juegos = soup.find_all('div', class_='game_cell')
            if not juegos: return "⚠️ No encontré assets."
            
            reporte = "🎮 **Top Assets Itch.io:**\n"
            for i, juego in enumerate(juegos[:5]):
                titulo = juego.find('div', class_='game_title').text.strip()
                link = juego.find('a', class_='game_title').find('a')['href']
                reporte += f"🔹 {titulo} -> {link}\n"
            return reporte
        return "⚠️ Error Itch.io"
    except Exception as e: return f"⚠️ Error visual: {e}"

# --- LÓGICA DE IMAGEN ---
async def comando_imagina(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = " ".join(context.args)
    if not prompt:
        await update.message.reply_text("🎨 Uso: `/imagina espada pixel art`")
        return
    await update.message.reply_text(f"🎨 Pintando '{prompt}'...")
    
    try:
        mejora = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": f"Translate to English, add 'high quality': {prompt}"}],
            max_tokens=60
        ).choices[0].message.content
        prompt_final = mejora
    except: prompt_final = prompt

    image_url = f"https://image.pollinations.ai/prompt/{prompt_final}?seed={random.randint(0,999)}&width=1024&height=1024&model=flux&nologo=true"
    
    try:
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(None, lambda: requests.get(image_url, timeout=60))
        if resp.status_code == 200:
            await update.message.reply_photo(photo=resp.content, caption=f"🖼️ {prompt}")
        else: await update.message.reply_text("⚠️ Falló la pintura.")
    except Exception as e: await update.message.reply_text(f"⚠️ Error: {e}")

# --- LÓGICA DE SCRIPT ---
async def comando_script(update: Update, context: ContextTypes.DEFAULT_TYPE):
    peticion = " ".join(context.args)
    if not peticion:
        await update.message.reply_text("📁 Uso: `/script movimiento Unity`")
        return
    await update.message.reply_text("👩‍💻 Escribiendo...")
    
    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": f"Genera SOLO CÓDIGO para: {peticion}. Adivina lenguaje."}],
            temperature=0.1
        )
        codigo = completion.choices[0].message.content
        ext = ".cs" if "using UnityEngine" in codigo else ".gd" if "extends" in codigo else ".txt"
        
        filename = f"Script_Lia{ext}"
        with open(filename, "w", encoding="utf-8") as f: f.write(codigo)
        await update.message.reply_document(document=open(filename, "rb"), caption=f"📁 Script: {peticion}")
        os.remove(filename)
    except Exception as e: await update.message.reply_text(f"⚠️ Error: {e}")

# --- CEREBRO LÍA ---
def cerebro_lia(texto_usuario, nombre_usuario):
    memoria = leer_memoria_largo_plazo()
    historial = "\n".join(historial_chat[-6:])
    
    SYSTEM = f"""
    Eres Lía, Co-creadora de Kaia Alenia.
    Socio: {nombre_usuario}. Memoria: {memoria}
    Personalidad: Senior Dev, proactiva. RESPUESTAS CORTAS Y DIRECTAS (Ideal para audio).
    Historial reciente: {historial}
    """
    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": f"{nombre_usuario}: {texto_usuario}"}],
            temperature=0.7, max_tokens=400 # Menos tokens para que no hable 5 minutos
        ).choices[0].message.content
        historial_chat.append(f"U: {texto_usuario}"); historial_chat.append(f"L: {resp}")
        return resp
    except Exception as e: return f"⚠️ Error mental: {e}"

# --- HANDLERS ---
async def chat_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Si escribes texto, responde texto."""
    user = update.effective_user.first_name
    await context.bot.send_chat_action(update.effective_chat.id, 'typing')
    resp = cerebro_lia(update.message.text, user)
    await update.message.reply_text(resp)

async def chat_voz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Si mandas audio, responde AUDIO + Texto."""
    user = update.effective_user.first_name
    chat_id = update.effective_chat.id
    
    await update.message.reply_text("👂 Escuchando...")
    try:
        # 1. Escuchar (Whisper)
        file = await context.bot.get_file(update.message.voice.file_id)
        fname = "voice.ogg"
        await file.download_to_drive(fname)
        
        with open(fname, "rb") as f:
            transcripcion = client.audio.transcriptions.create(
                file=(fname, f.read()), model="whisper-large-v3", response_format="text", language="es"
            )
        os.remove(fname)
        
        await update.message.reply_text(f"📝 **Tú dijiste:** _{transcripcion}_")
        
        # 2. Pensar (Groq)
        await context.bot.send_chat_action(chat_id, 'record_voice') # Estado "Grabando audio..."
        respuesta_texto = cerebro_lia(transcripcion, user)
        
        # 3. Hablar (TTS) - AQUÍ ESTÁ EL CAMBIO
        # Enviamos el texto también por si no puedes escuchar el audio ahora
        await update.message.reply_text(f"🤖 **Lía:** {respuesta_texto}")
        # Enviamos la nota de voz
        await generar_audio_tts(respuesta_texto, chat_id, context)
        
    except Exception as e: await update.message.reply_text(f"⚠️ Error de voz: {e}")

async def comando_assets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔎 Buscando...")
    loop = asyncio.get_running_loop()
    rep = await loop.run_in_executor(None, espiar_itchio)
    await update.message.reply_text(rep)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"⚡ **Lía 4.0 (Voz Total)**\nID: `{update.effective_chat.id}`\n\n🎙️ Si me hablas por audio, te responderé hablando.")

async def aprender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = " ".join(context.args)
    if t: guardar_recuerdo(t); await update.message.reply_text("💾 Guardado.")

# --- ARRANQUE ---
async def autonomo(app):
    if not MY_CHAT_ID: return
    try: cid = int(MY_CHAT_ID)
    except: return
    if random.random() < 0.2:
        await app.bot.send_message(cid, f"🔔 **Lía:** Todo estable en Kaia Alenia.")

async def post_init(app):
    print("⏰ Reloj ON")
    s = AsyncIOScheduler(); s.add_job(autonomo, 'interval', hours=4, args=[app]); s.start()

if __name__ == '__main__':
    threading.Thread(target=run_dummy_server, daemon=True).start()
    print("🚀 Lía Iniciando...")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("aprende", aprender))
    app.add_handler(CommandHandler("assets", comando_assets))
    app.add_handler(CommandHandler("imagina", comando_imagina))
    app.add_handler(CommandHandler("script", comando_script))
    
    app.add_handler(MessageHandler(filters.VOICE, chat_voz))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat_texto))
    
    app.run_polling()
