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
from github import Github # Importamos las manos nuevas

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
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO") # Ej: "Kaia-Alenia/Project-Null"

# --- CONEXIONES ---
client = Groq(api_key=GROQ_API_KEY)

# 1. Supabase (Memoria)
if SUPABASE_URL and SUPABASE_KEY:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
else:
    logger.critical("FALTAN CREDENCIALES DE SUPABASE.")
    supabase = None

# 2. GitHub (Manos)
gh_client = None
repo_obj = None
if GITHUB_TOKEN and GITHUB_REPO:
    try:
        gh_client = Github(GITHUB_TOKEN)
        repo_obj = gh_client.get_repo(GITHUB_REPO)
        logger.info(f"✅ Conectado al repo: {GITHUB_REPO}")
    except Exception as e:
        logger.error(f"❌ Error conectando a GitHub: {e}")

# --- FUNCIONES DE MEMORIA (Supabase) ---
def leer_memoria_completa():
    identidad = "Eres Lía, PM y Senior Dev de Kaia Alenia."
    aprendizajes = ""
    if supabase:
        try:
            res = supabase.table("memoria").select("contenido").execute()
            if res.data: aprendizajes = "\n".join([f"- {i['contenido']}" for i in res.data])
        except: pass
    return f"{identidad}\n\n[MEMORIA APRENDIDA]:\n{aprendizajes}"

def guardar_aprendizaje(dato):
    if supabase:
        try: supabase.table("memoria").insert({"contenido": dato}).execute()
        except: pass

def obtener_tareas_db():
    if supabase:
        try: return supabase.table("tareas").select("*").eq("estado", "pendiente").execute().data
        except: return []
    return []

def agregar_tarea_db(desc):
    if supabase:
        try: supabase.table("tareas").insert({"descripcion": desc}).execute()
        except: pass

def cerrar_tarea_db(numero):
    tareas = obtener_tareas_db()
    if 0 <= numero - 1 < len(tareas):
        t = tareas[numero - 1]
        if supabase: supabase.table("tareas").update({"estado": "completado"}).eq("id", t['id']).execute()
        return t['descripcion']
    return None

# --- FUNCIONES DE GESTIÓN (GitHub) ---
def crear_issue_github(titulo, body, labels=[]):
    """Crea un Issue real en GitHub."""
    if not repo_obj: return None
    try:
        issue = repo_obj.create_issue(title=titulo, body=body, labels=labels)
        return issue.html_url
    except Exception as e:
        logger.error(f"Error GitHub: {e}")
        return None

# --- CEREBRO ---
def cerebro_lia(texto, usuario):
    memoria = leer_memoria_completa()
    tareas = obtener_tareas_db()
    lista_tareas = "\n".join([f"{i+1}. {t['descripcion']}" for i, t in enumerate(tareas)]) if tareas else "Sin pendientes."
    
    SYSTEM = f"""
    Eres Lía. Usuario: {usuario}.
    
    [MEMORIA]: {memoria}
    [AGENDA]: {lista_tareas}
    
    Si {usuario} te pide crear un BUG o FEATURE, confirma que usarás los comandos de GitHub.
    Si te da un dato personal importante, escribe al final: [[MEMORIZAR: dato]].
    """
    
    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": texto}],
            temperature=0.6
        ).choices[0].message.content
        
        if "[[MEMORIZAR:" in resp:
            import re
            match = re.search(r'\[\[MEMORIZAR: (.*?)\]\]', resp)
            if match:
                guardar_aprendizaje(match.group(1))
                resp = resp.replace(match.group(0), "💾")
        return resp
    except: return "Error mental."

# --- COMANDOS ---
async def cmd_tarea(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guarda tarea simple en Supabase."""
    texto = " ".join(context.args)
    if texto:
        agregar_tarea_db(texto)
        await update.message.reply_text(f"✅ Agenda actualizada: {texto}")

async def cmd_bug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Crea un ISSUE tipo BUG en GitHub."""
    texto = " ".join(context.args)
    if not texto: return
    
    await update.message.reply_chat_action("typing")
    url = crear_issue_github(f"🐛 {texto}", f"Reportado por Alec vía Lía.\n\nDescripción: {texto}", labels=["bug"])
    
    if url: await update.message.reply_text(f"🚨 **Bug Reportado en GitHub**\nLink: {url}")
    else: await update.message.reply_text("❌ Error conectando con GitHub (Revisa el Token).")

async def cmd_feature(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Crea un ISSUE tipo ENHANCEMENT en GitHub."""
    texto = " ".join(context.args)
    if not texto: return
    
    await update.message.reply_chat_action("typing")
    url = crear_issue_github(f"✨ {texto}", f"Idea de Alec vía Lía.\n\nDetalle: {texto}", labels=["enhancement"])
    
    if url: await update.message.reply_text(f"🚀 **Feature Creada en GitHub**\nLink: {url}")
    else: await update.message.reply_text("❌ Error conectando con GitHub.")

async def cmd_pendientes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = obtener_tareas_db()
    msg = "\n".join([f"{i+1}. {x['descripcion']}" for i,x in enumerate(t)]) if t else "Nada."
    await update.message.reply_text(f"📋 **Agenda:**\n{msg}")

async def cmd_hecho(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        try:
            res = cerrar_tarea_db(int(context.args[0]))
            if res: await update.message.reply_text(f"🔥 Cerrado: {res}")
        except: pass

async def recibir_archivo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # (Misma lógica de lectura de archivos que ya tenías)
    pass 

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    estado_gh = "✅ Conectado" if repo_obj else "❌ Desconectado"
    estado_db = "✅ Conectada" if supabase else "❌ Desconectada"
    await update.message.reply_text(f"⚡ **Lía Manager v2.0**\n\n🧠 Memoria: {estado_db}\n🐙 GitHub: {estado_gh}\n\nComandos nuevos:\n`/bug [desc]` -> Reporta bug en Repo\n`/feature [idea]` -> Crea solicitud en Repo")

# --- MAIN ---
async def post_init(app):
    # Aquí puedes reactivar la vigilancia si quieres
    pass

if __name__ == '__main__':
    threading.Thread(target=run_health_server, daemon=True).start() # Asegúrate de tener la función run_health_server definida arriba (la omití por espacio, usa la del script anterior)
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tarea", cmd_tarea))
    app.add_handler(CommandHandler("bug", cmd_bug))      # NUEVO
    app.add_handler(CommandHandler("feature", cmd_feature)) # NUEVO
    app.add_handler(CommandHandler("pendientes", cmd_pendientes))
    app.add_handler(CommandHandler("hecho", cmd_hecho))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), lambda u,c: u.message.reply_text(cerebro_lia(u.message.text, u.effective_user.first_name))))
    
    app.run_polling()
