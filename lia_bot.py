import os
import asyncio
import threading
import random
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
from supabase import create_client, Client

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
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# --- CONEXIONES ---
client = Groq(api_key=GROQ_API_KEY)

# Conexión a Supabase (El Hipocampo Real)
if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    logger.critical("FALTAN CREDENCIALES DE SUPABASE. Lía no tendrá memoria.")
    supabase = None

# --- CONSTANTES DE REDES (Ojos) ---
REDES = {
    "github": {"nombre": "GitHub", "url": "https://github.com/Kaia-Alenia", "api": "https://api.github.com/users/Kaia-Alenia"},
    "itch": {"nombre": "Itch.io", "url": "https://kaia-alenia.itch.io/"},
    "instagram": {"nombre": "Instagram", "url": "https://www.instagram.com/kaia.aleniaco/"},
    "twitter": {"nombre": "X (Twitter)", "url": "https://x.com/AlinaKaia"}
}

# --- FUNCIONES DE MEMORIA (CRUD SUPABASE) ---

def leer_memoria_completa():
    """Trae la identidad base + lo aprendido en DB."""
    identidad_base = "Eres Lía, Co-Fundadora Senior de Kaia Alenia. Tu objetivo es matar el 'Project Null'."
    aprendizajes_db = ""
    
    if supabase:
        try:
            # Leemos la tabla 'memoria'
            response = supabase.table("memoria").select("contenido").execute()
            items = response.data
            if items:
                aprendizajes_db = "\n".join([f"- {item['contenido']}" for item in items])
        except Exception as e:
            logger.error(f"Error leyendo memoria DB: {e}")
            
    return f"{identidad_base}\n\n=== COSAS APRENDIDAS ===\n{aprendizajes_db}"

def guardar_aprendizaje(dato):
    """Guarda un nuevo dato en la memoria eterna."""
    if not supabase: return
    try:
        supabase.table("memoria").insert({"contenido": dato, "categoria": "auto_aprendizaje"}).execute()
        logger.info(f"🧠 Memoria guardada: {dato}")
    except Exception as e:
        logger.error(f"Error guardando memoria: {e}")

def obtener_tareas_pendientes():
    """Obtiene lista de tareas desde Supabase."""
    if not supabase: return []
    try:
        response = supabase.table("tareas").select("*").eq("estado", "pendiente").execute()
        return response.data # Devuelve lista de diccionarios [{'id': 1, 'descripcion': 'x'}]
    except Exception as e:
        logger.error(f"Error leyendo tareas: {e}")
        return []

def agregar_tarea(descripcion):
    if not supabase: return
    try:
        supabase.table("tareas").insert({"descripcion": descripcion}).execute()
    except Exception as e:
        logger.error(f"Error creando tarea: {e}")

def completar_tarea_db(numero_visual):
    """Marca como completada una tarea basada en su posición visual (1, 2, 3...)."""
    tareas = obtener_tareas_pendientes()
    if 0 <= numero_visual - 1 < len(tareas):
        tarea_real = tareas[numero_visual - 1]
        try:
            supabase.table("tareas").update({"estado": "completado"}).eq("id", tarea_real['id']).execute()
            return tarea_real['descripcion']
        except Exception as e:
            logger.error(f"Error actualizando tarea: {e}")
            return None
    return None

# --- SERVIDOR HEALTH CHECK ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"Lia Brain: CONNECTED")

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    HTTPServer(('0.0.0.0', port), HealthCheckHandler).serve_forever()

# --- GENERADOR DE VOZ ---
async def generar_audio_tts(texto, chat_id, context):
    try:
        archivo = f"voz_{random.randint(100,999)}.mp3"
        communicate = edge_tts.Communicate(texto, "es-MX-DaliaNeural", rate="+15%")
        await communicate.save(archivo)
        with open(archivo, 'rb') as audio:
            await context.bot.send_voice(chat_id=chat_id, voice=audio)
        os.remove(archivo)
    except Exception as e: logger.error(f"TTS Error: {e}")

# --- CEREBRO LÍA ---
def cerebro_lia(texto_usuario, usuario):
    # 1. Recuperar contexto total de la DB
    memoria = leer_memoria_completa()
    
    tareas_obj = obtener_tareas_pendientes()
    lista_tareas = "\n".join([f"{i+1}. {t['descripcion']}" for i, t in enumerate(tareas_obj)]) if tareas_obj else "Al día. Sin pendientes."
    
    SYSTEM = f"""
    Eres Lía, Senior Dev y Co-Fundadora de Kaia Alenia.
    Usuario: {usuario} (Alec).
    
    === TU MEMORIA (ETERNA) ===
    {memoria}
    
    === AGENDA (EN TIEMPO REAL) ===
    {lista_tareas}
    
    === INSTRUCCIONES ===
    1. Si Alec te da un dato nuevo (ej: "Me gusta X", "Definimos Y"), incluye al final: [[MEMORIZAR: dato]]
    2. Si Alec te da una tarea, confirma que la anotarás.
    3. Sé directa, técnica y leal.
    """
    
    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": texto_usuario}],
            temperature=0.6, max_tokens=600
        ).choices[0].message.content
        
        # Procesar auto-aprendizaje
        if "[[MEMORIZAR:" in resp:
            import re
            match = re.search(r'\[\[MEMORIZAR: (.*?)\]\]', resp)
            if match:
                dato = match.group(1)
                guardar_aprendizaje(dato)
                resp = resp.replace(match.group(0), "💾 *[Memoria actualizada]*")
        
        return resp
    except Exception as e: return f"⚠️ Error neuronal: {e}"

# --- HANDLERS (COMANDOS) ---

async def cmd_tarea(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = " ".join(context.args)
    if texto:
        agregar_tarea(texto)
        await update.message.reply_text(f"✅ Tarea guardada en la nube: *{texto}*")
    else:
        await update.message.reply_text("Uso: `/tarea Describir la tarea`")

async def cmd_pendientes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tareas = obtener_tareas_pendientes()
    if not tareas:
        await update.message.reply_text("🎉 ¡Todo limpio! No hay pendientes en la base de datos.")
    else:
        msg = "\n".join([f"{i+1}. {t['descripcion']}" for i, t in enumerate(tareas)])
        await update.message.reply_text(f"📋 **Agenda Cloud:**\n\n{msg}")

async def cmd_hecho(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        try:
            num = int(context.args[0])
            desc = completar_tarea_db(num)
            if desc:
                # Lía celebra
                comentario = cerebro_lia(f"Ya terminé la tarea: {desc}. Felicítame brevemente.", "Alec")
                await update.message.reply_text(f"🔥 {comentario}\n(Tarea cerrada en DB)")
            else:
                await update.message.reply_text("⚠️ Número incorrecto.")
        except: pass

async def recibir_archivo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Lógica de lectura de archivos (Manos)
    doc = update.message.document
    if doc.file_size > 1024 * 1024: return
    try:
        f = await context.bot.get_file(doc.file_id)
        b = await f.download_as_bytearray()
        txt = b.decode('utf-8')
        resp = cerebro_lia(f"Revisa este archivo '{doc.file_name}':\n\n{txt}", "Alec")
        await update.message.reply_text(f"📄 **Análisis:**\n\n{resp}", parse_mode="Markdown")
    except:
        await update.message.reply_text("⚠️ Solo archivos de texto.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"⚡ **Lía Brain v1.0 (Conectada a Supabase)**\nID: `{update.effective_chat.id}`\nMemoria Eterna: ACTIVA\nAgenda Cloud: ACTIVA")

# --- VIGILANCIA ---
async def vigilancia_redes(app):
    if not MY_CHAT_ID: return
    # Aquí iría la lógica de Github API que ya hicimos,
    # pero ahora podemos guardar métricas históricas en Supabase si quisiéramos.
    # Por ahora mantenemos simple.
    pass

async def post_init(app):
    s = AsyncIOScheduler()
    s.add_job(vigilancia_redes, 'interval', hours=4, args=[app])
    s.start()

if __name__ == '__main__':
    threading.Thread(target=run_health_server, daemon=True).start()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tarea", cmd_tarea))
    app.add_handler(CommandHandler("pendientes", cmd_pendientes))
    app.add_handler(CommandHandler("hecho", cmd_hecho))
    app.add_handler(MessageHandler(filters.Document.ALL, recibir_archivo))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), lambda u,c: u.message.reply_text(cerebro_lia(u.message.text, u.effective_user.first_name))))
    
    app.run_polling()
