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
from telegram import Update, InputFile
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

# --- SISTEMA DE ARCHIVOS TEMPORAL (PRE-SUPABASE) ---
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
    if os.path.exists(ARCHIVO_TAREAS):
        try:
            with open(ARCHIVO_TAREAS, "r") as f: return json.load(f)
        except: return []
    return []

def guardar_tareas(lista):
    with open(ARCHIVO_TAREAS, "w") as f: json.dump(lista, f)

def cargar_metricas():
    if os.path.exists(ARCHIVO_METRICAS):
        with open(ARCHIVO_METRICAS, "r") as f: return json.load(f)
    return {"gh_stars": 0, "gh_followers": 0}

def guardar_metricas(datos):
    with open(ARCHIVO_METRICAS, "w") as f: json.dump(datos, f)

# --- SERVIDOR HEALTH CHECK ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"Lia Systems: ACTIVE")

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
    lista_tareas_txt = "\n".join([f"- {t}" for t in tareas]) if tareas else "No hay tareas pendientes."
    
    historial = "\n".join(historial_chat[-5:])
    
    SYSTEM = f"""
    Eres Lía, Co-Fundadora Senior de Kaia Alenia.
    Usuario: {usuario} (Alec).
    
    === CONTEXTO TÉCNICO ===
    Memoria Base: {memoria}
    Tareas Pendientes (Project Null):
    {lista_tareas_txt}
    
    === INSTRUCCIONES ===
    1. Actúa como Senior Developer. Revisa código, sugiere mejoras.
    2. Si Alec te pide código complejo, escribe el código completo.
    3. Usa la lista de tareas para presionar si es necesario.
    4. {contexto_extra}
    
    Historial reciente: {historial}
    """
    
    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": texto_usuario}],
            temperature=0.5, max_tokens=600
        ).choices[0].message.content
        
        historial_chat.append(f"U: {texto_usuario[:50]}...") # Guardamos resumen
        return resp
    except Exception as e: return f"⚠️ Error cognitivo: {e}"

# --- MANEJO DE ARCHIVOS (LAS MANOS DE LÍA) ---
async def recibir_archivo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lía lee archivos .py, .txt, .md que le envíes."""
    documento = update.message.document
    nombre_archivo = documento.file_name
    
    # Filtro de seguridad y tamaño
    if documento.file_size > 1024 * 1024: # Máximo 1MB
        await update.message.reply_text("📁 Archivo demasiado grande para mi RAM actual, Alec.")
        return
        
    ext = os.path.splitext(nombre_archivo)[1].lower()
    if ext not in ['.py', '.txt', '.md', '.json', '.js', '.cs']:
        await update.message.reply_text("📁 Formato no soportado para lectura directa. Solo código.")
        return

    await update.message.reply_chat_action("typing")
    
    try:
        archivo_info = await context.bot.get_file(documento.file_id)
        # Descargar en memoria (bytes)
        contenido_bytes = await archivo_info.download_as_bytearray()
        contenido_texto = contenido_bytes.decode('utf-8')
        
        prompt_analisis = f"He subido el archivo '{nombre_archivo}'. Analiza este código/texto, busca errores, mejoras o resúmelo:\n\n{contenido_texto}"
        
        respuesta = cerebro_lia(prompt_analisis, "Alec", "Estás analizando un archivo subido por el usuario. Sé técnica.")
        
        await update.message.reply_text(f"📄 **Análisis de {nombre_archivo}:**\n\n{respuesta}", parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Error leyendo archivo: {e}")
        await update.message.reply_text("⚠️ No pude leer el archivo. Asegúrate de que sea texto plano utf-8.")

# --- GESTIÓN DE TAREAS (LA AGENDA) ---
async def cmd_tarea(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando: /tarea Revisar colisiones"""
    texto = " ".join(context.args)
    if not texto:
        await update.message.reply_text("📝 Uso: `/tarea [descripción]`")
        return
    
    tareas = cargar_tareas()
    tareas.append(texto)
    guardar_tareas(tareas)
    await update.message.reply_text(f"✅ Tarea agregada: *{texto}*")

async def cmd_pendientes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando: /pendientes"""
    tareas = cargar_tareas()
    if not tareas:
        await update.message.reply_text("🎉 No hay tareas pendientes (Project Null está tranquilo).")
        return
    
    lista = "\n".join([f"{i+1}. {t}" for i, t in enumerate(tareas)])
    await update.message.reply_text(f"📋 **Lista de Tareas:**\n\n{lista}\n\nUsa `/hecho [numero]` para completar.")

async def cmd_hecho(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando: /hecho 1"""
    if not context.args: return
    try:
        idx = int(context.args[0]) - 1
        tareas = cargar_tareas()
        if 0 <= idx < len(tareas):
            tarea_completada = tareas.pop(idx)
            guardar_tareas(tareas)
            
            # Lía celebra
            frase = cerebro_lia(f"Acabo de terminar la tarea: {tarea_completada}. Dame una frase corta de victoria.", "Alec")
            await update.message.reply_text(f"✅ **¡Completado!**\n_{frase}_")
        else:
            await update.message.reply_text("⚠️ Número de tarea inválido.")
    except:
        await update.message.reply_text("⚠️ Usa el número de la lista.")

# --- VIGILANCIA REDES ---
async def vigilar_redes(context: ContextTypes.DEFAULT_TYPE):
    if not MY_CHAT_ID: return
    metricas = cargar_metricas()
    reporte = ""
    cambios = False
    try:
        r = requests.get(URLS_KAIA['github_repos']).json()
        stars = sum([repo.get("stargazers_count", 0) for repo in r]) if isinstance(r, list) else 0
        if stars > metricas["gh_stars"]:
            reporte += f"🌟 Nuevas estrellas en GitHub (Total: {stars}).\n"
            metricas["gh_stars"] = stars
            cambios = True
        if cambios:
            msg = cerebro_lia(f"Reporta esto: {reporte}", "Alec")
            await context.bot.send_message(chat_id=MY_CHAT_ID, text=msg)
            guardar_metricas(metricas)
    except: pass

# --- ARRANQUE ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        f"⚡ **Lía Project Manager v4**\n"
        f"🆔: `{update.effective_chat.id}`\n\n"
        f"📁 **Manos:** Envíame archivos .py/.txt para revisar.\n"
        f"📝 **Agenda:** Usa `/tarea`, `/pendientes` y `/hecho`.\n"
        f"Vamos a terminar ese juego, Alec."
    )
    await update.message.reply_text(msg)

async def post_init(app):
    s = AsyncIOScheduler()
    s.add_job(vigilar_redes, 'interval', hours=2, args=[app])
    s.start()

if __name__ == '__main__':
    threading.Thread(target=run_health_server, daemon=True).start()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    
    # Comandos
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tarea", cmd_tarea))
    app.add_handler(CommandHandler("pendientes", cmd_pendientes))
    app.add_handler(CommandHandler("hecho", cmd_hecho))
    
    # Manejo de Texto y Archivos
    app.add_handler(MessageHandler(filters.Document.ALL, recibir_archivo)) # <--- MANOS
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), lambda u,c: u.message.reply_text(cerebro_lia(u.message.text, u.effective_user.first_name))))
    
    print(">>> LÍA: MÓDULOS DE ARCHIVOS Y TAREAS ACTIVOS <<<")
    app.run_polling()
