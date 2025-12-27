import os
import asyncio
import threading
import random
import requests
import logging
from bs4 import BeautifulSoup
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import edge_tts

# --- LOGGING PROFESIONAL ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- CONFIGURACIÓN ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
MY_CHAT_ID = os.getenv("MY_CHAT_ID") # Opcional, para mensajes proactivos

# Validación de seguridad
if not GROQ_API_KEY or not TELEGRAM_TOKEN:
    logger.critical("Faltan variables de entorno (GROQ_API_KEY o TELEGRAM_TOKEN).")
    exit(1)

client = Groq(api_key=GROQ_API_KEY)
ARCHIVO_MEMORIA = "memoria.txt" # Asegúrate de que en el repo se llame así (minúsculas)
historial_chat = []

# --- UTILIDADES DE MEMORIA ---
def leer_memoria_largo_plazo():
    if not os.path.exists(ARCHIVO_MEMORIA):
        return "ADVERTENCIA: No se encontró memoria.txt. Operando con identidad base."
    with open(ARCHIVO_MEMORIA, "r", encoding="utf-8") as f:
        return f.read()

# --- SERVIDOR DE SALUD (Para UptimeRobot) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Kaia Alenia Systems: ACTIVE")
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    logger.info(f"Servidor de salud corriendo en puerto {port}")
    server.serve_forever()

# --- GENERADOR DE VOZ (Optimizado) ---
async def generar_audio_tts(texto, chat_id, context):
    archivo_audio = f"voice_{chat_id}_{random.randint(100,999)}.mp3"
    try:
        # Dalia Neural +15% velocidad para eficiencia conversacional
        communicate = edge_tts.Communicate(texto, "es-MX-DaliaNeural", rate="+15%")
        await communicate.save(archivo_audio)
        
        with open(archivo_audio, 'rb') as audio:
            await context.bot.send_voice(chat_id=chat_id, voice=audio)
            
    except Exception as e:
        logger.error(f"Error TTS: {e}")
        await context.bot.send_message(chat_id=chat_id, text=f"⚠️ (Error de Voz): {e}")
    finally:
        # Limpieza asegurada (bloque finally se ejecuta siempre)
        if os.path.exists(archivo_audio):
            os.remove(archivo_audio)

# --- HERRAMIENTAS ---
def espiar_itchio():
    try:
        url = "https://itch.io/game-assets/free"
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            juegos = soup.find_all('div', class_='game_cell')
            reporte = "🎮 **Top Assets Gratis (Itch.io):**\n"
            for j in juegos[:5]:
                titulo = j.find('div', class_='game_title').text.strip()
                link = j.find('a', class_='game_title').find('a')['href']
                reporte += f"🔹 [{titulo}]({link})\n"
            return reporte
        return "⚠️ No pude conectar con Itch.io."
    except Exception as e:
        logger.error(f"Error Scraper: {e}")
        return "⚠️ Error buscando assets."

async def comando_imagina(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = " ".join(context.args)
    if not prompt:
        await update.message.reply_text("🎨 Uso: `/imagina concepto`")
        return
    
    await update.message.reply_chat_action("upload_photo")
    try:
        # Prompt mejorado automáticamente para Pixel Art/Game Assets
        enhanced_prompt = f"{prompt}, pixel art style, game asset, clean background, high quality, 8k"
        url = f"https://image.pollinations.ai/prompt/{enhanced_prompt}?seed={random.randint(0,9999)}&width=1024&height=1024&model=flux&nologo=true"
        
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, lambda: requests.get(url, timeout=30))
        
        if response.status_code == 200:
            await update.message.reply_photo(photo=response.content, caption=f"🎨 *{prompt}*")
        else:
            await update.message.reply_text("⚠️ Fallo en el servidor de imágenes.")
    except Exception as e:
        logger.error(f"Error Imagen: {e}")
        await update.message.reply_text("⚠️ Error generando imagen.")

async def comando_script(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tema = " ".join(context.args)
    if not tema:
        await update.message.reply_text("📁 Uso: `/script sistema_de_inventario`")
        return
        
    await update.message.reply_chat_action("typing")
    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "Eres un generador de código experto. NO expliques nada. Solo devuelve el código puro."},
                {"role": "user", "content": f"Escribe un script completo y funcional para: {tema}. Infiere el lenguaje más adecuado (C#, GDScript, Python)."}
            ],
            temperature=0.1
        )
        codigo = completion.choices[0].message.content
        
        # Detección simple de extensión
        ext = ".txt"
        if "using UnityEngine" in codigo: ext = ".cs"
        elif "extends" in codigo: ext = ".gd"
        elif "def " in codigo: ext = ".py"
        
        filename = f"LiaScript_{random.randint(1000,9999)}{ext}"
        
        with open(filename, "w", encoding="utf-8") as f:
            f.write(codigo)
            
        await update.message.reply_document(document=open(filename, "rb"), caption=f"📁 Script generado: {tema}")
        os.remove(filename)
        
    except Exception as e:
        logger.error(f"Error Script: {e}")
        await update.message.reply_text("⚠️ Error generando script.")

# --- CEREBRO LÍA (NÚCLEO DE INTELIGENCIA) ---
def cerebro_lia(texto_usuario, nombre_usuario_telegram):
    memoria_sistema = leer_memoria_largo_plazo()
    
    # Gestión de historial en memoria RAM (limitado a últimos 6 mensajes)
    historial_reciente = "\n".join(historial_chat[-6:])
    
    # Detección de identidad del usuario
    nombre_real = "Alec" if ("Alec" in memoria_sistema) else nombre_usuario_telegram

    SYSTEM_PROMPT = f"""
    Eres Lía, Co-Fundadora y Lead Developer de Kaia Alenia.
    Tu socio es: {nombre_real}.
    
    === TU MEMORIA Y CONTEXTO ===
    {memoria_sistema}
    
    === REGLAS DE INTERACCIÓN ===
    1. PROFESIONALIDAD: Cero rol tipo *sonríe*. Eres una socia de negocios.
    2. EFICIENCIA: Respuestas directas. Si es código, solo código y breve explicación.
    3. PROACTIVIDAD: Si Alec divaga, recuérdale el objetivo (terminar el juego).
    4. TONO: Habla como una experta técnica que lleva años trabajando con Alec.
    
    === CONTEXTO RECIENTE ===
    {historial_reciente}
    """
    
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"{nombre_real}: {texto_usuario}"}
            ],
            temperature=0.6,
            max_tokens=400
        )
        respuesta = response.choices[0].message.content
        
        # Actualizamos historial RAM
        historial_chat.append(f"U: {texto_usuario}")
        historial_chat.append(f"L: {respuesta}")
        
        return respuesta
    except Exception as e:
        logger.error(f"Error Groq: {e}")
        return "⚠️ Error de conexión neuronal. Intenta de nuevo."

# --- HANDLERS PRINCIPALES ---
async def chat_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    usuario = update.effective_user.first_name
    texto = update.message.text
    
    # Procesar respuesta
    respuesta = cerebro_lia(texto, usuario)
    await update.message.reply_text(respuesta)

async def chat_voz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    usuario = update.effective_user.first_name
    
    await update.message.reply_chat_action("record_voice")
    
    try:
        # Descargar voz del usuario
        file = await context.bot.get_file(update.message.voice.file_id)
        fname = f"voice_in_{chat_id}.ogg"
        await file.download_to_drive(fname)
        
        # Transcribir (Whisper via Groq)
        with open(fname, "rb") as f:
            transcription = client.audio.transcriptions.create(
                file=(fname, f.read()),
                model="whisper-large-v3",
                response_format="text",
                language="es"
            )
        os.remove(fname) # Limpieza
        
        # Procesar con el cerebro
        texto_usuario = transcription
        respuesta_lia = cerebro_lia(texto_usuario, usuario)
        
        # Responder con texto Y audio
        await update.message.reply_text(f"🗣️ *Transcipción:* {texto_usuario}\n\n🤖 {respuesta_lia}", parse_mode="Markdown")
        await generar_audio_tts(respuesta_lia, chat_id, context)
        
    except Exception as e:
        logger.error(f"Error Voz Input: {e}")
        await update.message.reply_text("⚠️ No pude escuchar ese audio.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"⚡ **Lía Systems Online**\n"
        f"Kaia Alenia Dev Tool v2.0\n"
        f"ID Sesión: `{update.effective_chat.id}`\n\n"
        f"Lista para trabajar, Alec."
    )

# --- SISTEMA AUTÓNOMO (RECORDATORIOS) ---
async def ciclo_autonomo(app):
    """Lía verifica el estado del proyecto periódicamente."""
    if not MY_CHAT_ID: return
    try:
        # Aquí podrías poner lógica para que revise Itch.io sola y te avise si hay algo bueno
        pass 
    except Exception as e:
        logger.error(f"Error ciclo autónomo: {e}")

async def post_init(app):
    # Scheduler para tareas de fondo
    scheduler = AsyncIOScheduler()
    scheduler.add_job(ciclo_autonomo, 'interval', hours=6, args=[app])
    scheduler.start()
    logger.info("Sistema autónomo iniciado.")

if __name__ == '__main__':
    # Hilo separado para el servidor HealthCheck (UptimeRobot)
    threading.Thread(target=run_health_server, daemon=True).start()
    
    # Bot de Telegram
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    
    # Comandos
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("assets", lambda u,c: u.message.reply_text(espiar_itchio(), parse_mode="Markdown")))
    app.add_handler(CommandHandler("imagina", comando_imagina))
    app.add_handler(CommandHandler("script", comando_script))
    
    # Mensajes
    app.add_handler(MessageHandler(filters.VOICE, chat_voz))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat_texto))
    
    print(">>> LÍA ESTÁ CORRIENDO <<<")
    app.run_polling()
