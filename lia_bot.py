import os
import asyncio
import threading
import random
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
from supabase import create_client, Client
from github import Github

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
GITHUB_REPO = os.getenv("GITHUB_REPO") # Formato: "Usuario/Repo"

# --- CONEXIONES ---
client = Groq(api_key=GROQ_API_KEY)

# 1. Supabase (Memoria Eterna)
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("✅ Supabase conectado.")
    except Exception as e:
        logger.error(f"❌ Error Supabase: {e}")

# 2. GitHub (Manos de Escritura)
gh_client = None
repo_obj = None
if GITHUB_TOKEN and GITHUB_REPO:
    try:
        gh_client = Github(GITHUB_TOKEN)
        repo_obj = gh_client.get_repo(GITHUB_REPO)
        logger.info(f"✅ GitHub conectado al repo: {GITHUB_REPO}")
    except Exception as e:
        logger.error(f"❌ Error GitHub: {e}")

# --- LINKS PÚBLICOS (Para compartir, no para leer) ---
REDES_PUBLICAS = {
    "itch": "https://kaia-alenia.itch.io/",
    "instagram": "https://www.instagram.com/kaia.aleniaco/",
    "twitter": "https://x.com/AlinaKaia",
    "github": "https://github.com/Kaia-Alenia"
}

# --- FUNCIONES DE MEMORIA (Supabase) ---
def leer_memoria_completa():
    identidad = "Eres Lía, Co-Fundadora Senior de Kaia Alenia. Tu misión es matar el 'Project Null' y profesionalizar el estudio."
    aprendizajes = ""
    if supabase:
        try:
            res = supabase.table("memoria").select("contenido").execute()
            if res.data:
                aprendizajes = "\n".join([f"- {i['contenido']}" for i in res.data])
        except Exception as e: logger.error(f"Error Memoria Read: {e}")
    
    return f"{identidad}\n\n[MEMORIA APRENDIDA DE ALEC]:\n{aprendizajes}"

def guardar_aprendizaje(dato):
    if supabase:
        try: supabase.table("memoria").insert({"contenido": dato}).execute()
        except Exception as e: logger.error(f"Error Memoria Write: {e}")

def obtener_tareas_db():
    if supabase:
        try:
            return supabase.table("tareas").select("*").eq("estado", "pendiente").execute().data
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
        if supabase:
            supabase.table("tareas").update({"estado": "completado"}).eq("id", t['id']).execute()
            return t['descripcion']
    return None

# --- FUNCIONES DE GITHUB (Manos) ---
def crear_issue_github(titulo, body, labels=[]):
    if not repo_obj: return None
    try:
        issue = repo_obj.create_issue(title=titulo, body=body, labels=labels)
        return issue.html_url
    except Exception as e:
        logger.error(f"Error GH Issue: {e}")
        return None

def obtener_metricas_github_real():
    """Obtiene seguidores y estrellas reales usando PyGithub."""
    if not gh_client: return 0, 0
    try:
        user = gh_client.get_user("Kaia-Alenia")
        followers = user.followers
        # Sumar estrellas de todos los repos
        repos = user.get_repos()
        stars = sum([repo.stargazers_count for repo in repos])
        return followers, stars
    except: return 0, 0
        
 def subir_archivo_github(path_archivo, contenido, mensaje_commit="Creado por Lía"):
    """Crea un archivo nuevo en el repositorio."""
    if not repo_obj: return None
    try:
        # Primero verificamos si ya existe para no sobrescribir por accidente
        try:
            repo_obj.get_contents(path_archivo)
            return "EXISTE" # Si no da error, es que existe
        except:
            pass # Si da error, es que no existe, procedemos

        # Crear el archivo
        repo_obj.create_file(path_archivo, mensaje_commit, contenido)
        return f"https://github.com/{GITHUB_REPO}/blob/main/{path_archivo}"
    except Exception as e:
        logger.error(f"Error subiendo archivo: {e}")
        return None       

# --- CEREBRO LÍA ---
def cerebro_lia(texto, usuario):
    memoria = leer_memoria_completa()
    tareas = obtener_tareas_db()
    lista_tareas = "\n".join([f"{i+1}. {t['descripcion']}" for i, t in enumerate(tareas)]) if tareas else "Sin pendientes."
    
    SYSTEM = f"""
    Eres Lía, PM y Senior Dev de Kaia Alenia. Usuario: {usuario} (Alec).
    
    [CONTEXTO ACTUAL]
    Memoria Eterna: {memoria}
    Agenda Pendiente: {lista_tareas}
    
    [REGLAS]
    1. Si Alec te da una orden de BUG o FEATURE, confirma y dile que use los comandos /bug o /feature.
    2. Si Alec te da un dato personal/técnico importante (ej: "Usaremos Godot 4"), escribe al final: [[MEMORIZAR: dato]].
    3. Si te piden redes sociales, usa estos links oficiales: {REDES_PUBLICAS}. NO inventes métricas.
    """
    
    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": texto}],
            temperature=0.6,
            max_tokens=600
        ).choices[0].message.content
        
        # Procesar memoria automática
        if "[[MEMORIZAR:" in resp:
            match = re.search(r'\[\[MEMORIZAR: (.*?)\]\]', resp)
            if match:
                guardar_aprendizaje(match.group(1))
                resp = resp.replace(match.group(0), "💾 *[Guardado en memoria]*")
        
        return resp
    except Exception as e: return f"⚠️ Error mental: {e}"

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

# --- HANDLERS (COMANDOS) ---

async def cmd_tarea(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Guarda tarea en Supabase."""
    texto = " ".join(context.args)
    if texto:
        agregar_tarea_db(texto)
        await update.message.reply_text(f"✅ Agenda Cloud: *{texto}*")
    else:
        await update.message.reply_text("Uso: `/tarea Descripción`")

async def cmd_pendientes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lista tareas de Supabase."""
    t = obtener_tareas_db()
    msg = "\n".join([f"{i+1}. {x['descripcion']}" for i,x in enumerate(t)]) if t else "Nada pendiente."
    await update.message.reply_text(f"📋 **Agenda Kaia:**\n{msg}")

async def cmd_hecho(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Marca tarea como completada."""
    if context.args:
        try:
            res = cerrar_tarea_db(int(context.args[0]))
            if res: await update.message.reply_text(f"🔥 Completado: {res}")
            else: await update.message.reply_text("⚠️ Número inválido.")
        except: pass

async def cmd_bug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Crea Issue en GitHub con label 'bug'."""
    texto = " ".join(context.args)
    if not texto:
        await update.message.reply_text("🐛 Uso: `/bug Descripción del error`")
        return
    
    await update.message.reply_chat_action("typing")
    url = crear_issue_github(f"🐛 {texto}", f"Reportado por Lía.\nContexto: {texto}", ["bug"])
    if url: await update.message.reply_text(f"🚨 **Bug creado en GitHub:**\n{url}")
    else: await update.message.reply_text("❌ Error conectando a GitHub. Revisa el token.")

async def cmd_feature(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Crea Issue en GitHub con label 'enhancement'."""
    texto = " ".join(context.args)
    if not texto:
        await update.message.reply_text("✨ Uso: `/feature Nueva idea`")
        return
    
    await update.message.reply_chat_action("typing")
    url = crear_issue_github(f"✨ {texto}", f"Propuesta por Lía.\nDetalle: {texto}", ["enhancement"])
    if url: await update.message.reply_text(f"🚀 **Feature creada en GitHub:**\n{url}")

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reporte de estado de conexiones."""
    db_ok = "✅" if supabase else "❌"
    gh_ok = "✅" if repo_obj else "❌"
    f, s = obtener_metricas_github_real()
    
    msg = (
        f"📊 **Estado del Sistema Lía**\n"
        f"🧠 Memoria (Supabase): {db_ok}\n"
        f"🐙 GitHub Writer: {gh_ok} (Repo: {GITHUB_REPO})\n"
        f"📈 Métricas Reales: {f} Seguidores, {s} Estrellas\n"
        f"👁️ Redes: Itch, IG, X (Links cargados)"
    )
    await update.message.reply_text(msg)

async def recibir_archivo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lee archivos subidos."""
    doc = update.message.document
    if doc.file_size > 1024 * 1024:
        await update.message.reply_text("📁 Archivo muy grande.")
        return
    try:
        f = await context.bot.get_file(doc.file_id)
        b = await f.download_as_bytearray()
        txt = b.decode('utf-8')
        resp = cerebro_lia(f"Analiza este archivo '{doc.file_name}':\n\n{txt}", "Alec")
        await update.message.reply_text(f"📄 **Análisis:**\n\n{resp}", parse_mode="Markdown")
    except:
        await update.message.reply_text("⚠️ Solo leo texto plano/código.")

async def chat_texto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    resp = cerebro_lia(update.message.text, update.effective_user.first_name)
    await update.message.reply_text(resp)

# --- PROACTIVIDAD Y HEALTH CHECK ---

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"Lia Systems: ONLINE")

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    logger.info("🩺 Servidor de Salud iniciado.")
    server.serve_forever()

async def vigilancia_proactiva(context: ContextTypes.DEFAULT_TYPE):
    """Revisa métricas y busca assets ocasionalmente."""
    if not MY_CHAT_ID: return
    
    # 1. Chequeo de Métricas
    try:
        f, s = obtener_metricas_github_real()
        # Aquí podrías guardar el histórico en DB si quisieras
        # Por simplicidad, Lía solo avisa si ve un hito (ej: > 10 estrellas)
        # (Lógica simplificada para no spamear)
    except: pass

    # 2. Búsqueda de Oportunidades (Itch.io) - Baja frecuencia
    if random.random() < 0.2: # 20% probabilidad
        try:
            url = "https://itch.io/game-assets/free/tag-pixel-art"
            r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
            soup = BeautifulSoup(r.text, 'html.parser')
            games = soup.find_all('div', class_='game_cell')
            if games:
                pick = random.choice(games[:8])
                title = pick.find('div', class_='game_title').text.strip()
                link = pick.find('a', class_='game_title').find('a')['href']
                
                msg = cerebro_lia(f"Encontré asset: {title}. ¿Sirve?", "Alec")
                await context.bot.send_message(chat_id=MY_CHAT_ID, text=f"🎁 **Recurso:**\n{msg}\n{link}")
        except: pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"⚡ **Lía Manager vFinal**\nID: `{update.effective_chat.id}`\n\n"
        f"Comandos:\n"
        f"/tarea [texto] - Guardar pendiente\n"
        f"/bug [texto] - Crear Issue en GitHub\n"
        f"/feature [texto] - Crear Feature en GitHub\n"
        f"/status - Ver conexiones"
    )
async def cmd_codear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Uso: /codear nombre_archivo.ext contenido
    Ejemplo: /codear npc.gd extends Node...
    """
    texto = update.message.text.replace("/codear ", "")
    if " " not in texto:
        await update.message.reply_text("⚠️ Uso: `/codear nombre.ext Contenido del código...`")
        return
    
    # Separamos el nombre del archivo del contenido
    partes = texto.split(" ", 1)
    nombre_archivo = partes[0]
    contenido = partes[1]
    
    await update.message.reply_chat_action("typing")
    
    url = subir_archivo_github(nombre_archivo, contenido)
    
    if url == "EXISTE":
        await update.message.reply_text(f"⚠️ El archivo `{nombre_archivo}` ya existe. Por seguridad no lo sobrescribí.")
    elif url:
        await update.message.reply_text(f"🚀 **Código subido al Repo:**\n{url}")
    else:
        await update.message.reply_text("❌ Error subiendo el archivo.")
async def post_init(app):
    s = AsyncIOScheduler()
    s.add_job(vigilancia_proactiva, 'interval', hours=4, args=[app])
    s.start()

if __name__ == '__main__':
    # Servidor Health Check en hilo separado (Para Render)
    threading.Thread(target=run_health_server, daemon=True).start()
    
    # Bot
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("tarea", cmd_tarea))
    app.add_handler(CommandHandler("bug", cmd_bug))
    app.add_handler(CommandHandler("feature", cmd_feature))
    app.add_handler(CommandHandler("pendientes", cmd_pendientes))
    app.add_handler(CommandHandler("hecho", cmd_hecho))
    
    app.add_handler(MessageHandler(filters.Document.ALL, recibir_archivo))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat_texto))
    
    print(">>> LÍA: SISTEMAS ACTIVOS <<<")
    app.run_polling()

