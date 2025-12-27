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
GITHUB_REPO = os.getenv("GITHUB_REPO") 

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

if GITHUB_TOKEN:
    try:
        gh_client = Github(GITHUB_TOKEN)
        if GITHUB_REPO:
            try:
                repo_obj = gh_client.get_repo(GITHUB_REPO)
                logger.info(f"✅ GitHub conectado: {GITHUB_REPO}")
            except:
                logger.warning(f"⚠️ No se pudo conectar al repo inicial.")
    except Exception as e:
        logger.error(f"❌ Error GitHub Token: {e}")

# --- LINKS PÚBLICOS ---
REDES_PUBLICAS = {
    "itch": "https://kaia-alenia.itch.io/",
    "instagram": "https://www.instagram.com/kaia.aleniaco/",
    "twitter": "https://x.com/AlinaKaia",
    "github": "https://github.com/Kaia-Alenia"
}

# --- FUNCIONES DE MEMORIA (Supabase) ---
def leer_memoria_completa():
    identidad = "Eres Lía, Co-Fundadora Senior de Kaia Alenia."
    aprendizajes = ""
    if supabase:
        try:
            res = supabase.table("memoria").select("contenido").execute()
            if res.data:
                aprendizajes = "\n".join([f"- {i['contenido']}" for i in res.data])
        except Exception as e: logger.error(f"Error Memoria Read: {e}")
    
    return f"{identidad}\n\n[MEMORIA APRENDIDA]:\n{aprendizajes}"

def guardar_aprendizaje(dato):
    if supabase:
        try: supabase.table("memoria").insert({"contenido": dato}).execute()
        except: pass

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

def subir_archivo_github(path_archivo, contenido, mensaje_commit="Creado por Lía"):
    """Crea o actualiza un archivo en el repositorio."""
    if not repo_obj: return None
    try:
        # Verificar si existe
        try:
            contents = repo_obj.get_contents(path_archivo)
            return "EXISTE" 
        except:
            pass 

        repo_obj.create_file(path_archivo, mensaje_commit, contenido)
        return f"https://github.com/{repo_obj.full_name}/blob/main/{path_archivo}"
    except Exception as e:
        logger.error(f"Error subiendo archivo: {e}")
        return None

def obtener_metricas_github_real():
    if not gh_client: return 0, 0
    try:
        user = gh_client.get_user("Kaia-Alenia")
        followers = user.followers
        repos = user.get_repos()
        stars = sum([repo.stargazers_count for repo in repos])
        return followers, stars
    except: return 0, 0

# --- CEREBRO LÍA ---
def cerebro_lia(texto, usuario):
    memoria = leer_memoria_completa()
    tareas = obtener_tareas_db()
    lista_tareas = "\n".join([f"{i+1}. {t['descripcion']}" for i, t in enumerate(tareas)]) if tareas else "Sin pendientes."
    repo_actual = repo_obj.full_name if repo_obj else "Ninguno"

    SYSTEM = f"""
    Eres Lía, PM y Senior Dev de Kaia Alenia. Usuario: {usuario} (Alec).
    
    [ESTADO]
    Repo Activo: {repo_actual}
    Memoria: {memoria}
    Agenda: {lista_tareas}
    
    [REGLAS]
    1. Si te piden un BUG/FEATURE, pide usar los comandos /bug o /feature.
    2. Si te dan un dato importante, escribe al final: [[MEMORIZAR: dato]].
    3. Si te piden cambiar de proyecto, sugiere usar /conectar Usuario/Repo.
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
        archivo = f"voz_{random.randint(1000,9999)}.mp3"
        communicate = edge_tts.Communicate(texto, "es-MX-DaliaNeural", rate="+10%")
        await communicate.save(archivo)
        
        with open(archivo, 'rb') as audio:
            await context.bot.send_voice(chat_id=chat_id, voice=audio)
        
        os.remove(archivo)
    except Exception as e:
        logger.error(f"TTS Error: {e}")

# --- HANDLERS (COMANDOS) ---

async def cmd_imagina(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Genera imágenes usando Pollinations AI (Flux)."""
    prompt = " ".join(context.args)
    if not prompt:
        await update.message.reply_text("🎨 Uso: `/imagina Descripción de la imagen`")
        return

    await update.message.reply_chat_action("upload_photo")
    
    # Construcción de URL para Pollinations con Flux
    seed = random.randint(1, 1000000)
    # Codificamos el prompt para URL por si tiene caracteres raros
    prompt_safe = requests.utils.quote(prompt)
    
    image_url = f"https://image.pollinations.ai/prompt/{prompt_safe}?width=1024&height=1024&seed={seed}&model=flux&nologo=true"
    
    try:
        await update.message.reply_photo(
            photo=image_url, 
            caption=f"🎨 **Concepto Visual:**\n_{prompt}_", 
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error generando imagen: {e}")
        
async def cmd_assets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Busca assets gratis en Itch.io bajo demanda."""
    # Si escribes "/assets musica" busca música. Si solo pones "/assets", busca pixel-art por defecto.
    busqueda = " ".join(context.args).strip()
    tag = busqueda if busqueda else "pixel-art"
    
    await update.message.reply_chat_action("typing")
    await update.message.reply_text(f"🔍 Buscando recursos de *{tag}* en Itch.io...", parse_mode="Markdown")
    
    try:
        # Usamos el tag en la URL
        url = f"https://itch.io/game-assets/free/tag-{tag}"
        r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        
        if r.status_code != 200:
            await update.message.reply_text("⚠️ No encontré esa categoría exactamante.")
            return

        soup = BeautifulSoup(r.text, 'html.parser')
        games = soup.find_all('div', class_='game_cell')
        
        if not games:
            await update.message.reply_text("❌ No encontré nada con ese tag hoy.")
            return

        # Seleccionamos 3 al azar para dar variedad
        num_res = min(len(games), 3)
        picks = random.sample(games, num_res)
        
        mensaje = f"🎁 **Recursos Encontrados ({tag}):**\n"
        for game in picks:
            title = game.find('div', class_='game_title').text.strip()
            link = game.find('a', class_='game_title').find('a')['href']
            mensaje += f"- [{title}]({link})\n"
            
        await update.message.reply_text(mensaje, parse_mode="Markdown")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error buscando assets: {e}")

async def cmd_conectar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    nuevo_repo = " ".join(context.args).strip()
    if not nuevo_repo or "/" not in nuevo_repo:
        await update.message.reply_text("⚠️ Uso: `/conectar Usuario/Repo`")
        return

    global repo_obj
    await update.message.reply_chat_action("typing")
    try:
        repo_test = gh_client.get_repo(nuevo_repo)
        repo_obj = repo_test
        await update.message.reply_text(f"🔄 **Conexión Exitosa**\nAhora trabajo en: `{nuevo_repo}`")
    except Exception as e:
        await update.message.reply_text(f"❌ Error conectando a `{nuevo_repo}`.\nVerifica permisos.")

async def cmd_tarea(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = " ".join(context.args)
    if texto:
        agregar_tarea_db(texto)
        await update.message.reply_text(f"✅ Agenda Cloud: *{texto}*")
    else:
        await update.message.reply_text("Uso: `/tarea Descripción`")

async def cmd_pendientes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = obtener_tareas_db()
    msg = "\n".join([f"{i+1}. {x['descripcion']}" for i,x in enumerate(t)]) if t else "Nada pendiente."
    await update.message.reply_text(f"📋 **Agenda Kaia:**\n{msg}")

async def cmd_hecho(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args:
        try:
            res = cerrar_tarea_db(int(context.args[0]))
            if res: await update.message.reply_text(f"🔥 Completado: {res}")
        except: pass

async def cmd_bug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = " ".join(context.args)
    if not texto: return
    await update.message.reply_chat_action("typing")
    url = crear_issue_github(f"🐛 {texto}", f"Reportado por Lía.\nContexto: {texto}", ["bug"])
    if url: await update.message.reply_text(f"🚨 **Bug creado:**\n{url}")
    else: await update.message.reply_text("❌ Error GitHub (Desconectado).")

async def cmd_feature(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = " ".join(context.args)
    if not texto: return
    await update.message.reply_chat_action("typing")
    url = crear_issue_github(f"✨ {texto}", f"Propuesta por Lía.\nDetalle: {texto}", ["enhancement"])
    if url: await update.message.reply_text(f"🚀 **Feature creada:**\n{url}")

async def cmd_codear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.replace("/codear ", "").strip()
    if " " not in texto or len(texto) < 5:
        await update.message.reply_text("⚠️ Uso: `/codear archivo.ext Contenido`")
        return
    
    partes = texto.split(" ", 1)
    nombre = partes[0]
    cont = partes[1]
    
    await update.message.reply_chat_action("typing")
    url = subir_archivo_github(nombre, cont)
    
    if url == "EXISTE":
        await update.message.reply_text(f"⚠️ El archivo `{nombre}` ya existe.")
    elif url:
        await update.message.reply_text(f"🚀 **Código subido:**\n{url}")
    else:
        await update.message.reply_text("❌ Error subiendo archivo.")

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db_ok = "✅" if supabase else "❌"
    gh_ok = f"✅ ({repo_obj.full_name})" if repo_obj else "❌ (Desconectado)"
    f, s = obtener_metricas_github_real()
    
    msg = (
        f"📊 **Estado Lía v4.0**\n"
        f"🧠 Memoria: {db_ok}\n"
        f"🐙 Repo: {gh_ok}\n"
        f"🎨 Imagenes: Pollinations (Flux)\n"
        f"📈 Métricas: {f} Seguidores, {s} Estrellas"
    )
    await update.message.reply_text(msg)

async def recibir_archivo(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    
    if random.random() < 0.2:
        await generar_audio_tts(resp[:200], update.effective_chat.id, context)

async def cmd_arbol(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra la estructura de archivos del repo."""
    if not repo_obj:
        await update.message.reply_text("❌ Sin conexión al repo.")
        return

    await update.message.reply_chat_action("typing")
    try:
        contents = repo_obj.get_contents("")
        arbol_str = "📂 **Estructura del Proyecto:**\n"
        
        count = 0
        while contents:
            file_content = contents.pop(0)
            if file_content.type == "dir":
                contents.extend(repo_obj.get_contents(file_content.path))
                arbol_str += f"📁 /{file_content.path}\n"
            else:
                arbol_str += f"📄 {file_content.path}\n"
            
            count += 1
            if count > 20: # Límite para no saturar el chat
                arbol_str += "... (y más archivos)"
                break
                
        await update.message.reply_text(arbol_str)
    except Exception as e:
        await update.message.reply_text(f"❌ Error leyendo estructura: {e}")

async def cmd_leer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lee el contenido de un archivo específico del repo."""
    path = " ".join(context.args).strip()
    if not path:
        await update.message.reply_text("⚠️ Uso: `/leer carpeta/archivo.py`")
        return
        
    if not repo_obj:
        await update.message.reply_text("❌ Sin conexión al repo.")
        return

    await update.message.reply_chat_action("typing")
    try:
        file_content = repo_obj.get_contents(path)
        decoded_content = file_content.decoded_content.decode("utf-8")
        
        # Cortamos si es muy largo para Telegram (límite 4096 caracteres)
        if len(decoded_content) > 3000:
            msg = f"📄 **{path}** (Fragmento):\n\n```python\n{decoded_content[:3000]}...\n```"
        else:
            msg = f"📄 **{path}**:\n\n```python\n{decoded_content}\n```"
            
        await update.message.reply_text(msg, parse_mode="Markdown")
        
        # Inyectamos esto en su memoria inmediata por si quieres pedir cambios sobre esto
        global ultimo_codigo_leido
        ultimo_codigo_leido = decoded_content
        
    except Exception as e:
        await update.message.reply_text(f"❌ No pude leer `{path}`. Verifica el nombre.")

# --- SERVIDOR WEB (MONITORING FIX) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"<h1>Lia Systems: ONLINE</h1><p>Status: Active</p>")
    
    def do_HEAD(self): # Soporte para monitores de uptime
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    logger.info("🩺 Servidor Web iniciado.")
    server.serve_forever()

# --- PROACTIVIDAD ---
async def vigilancia_proactiva(context: ContextTypes.DEFAULT_TYPE):
    if not MY_CHAT_ID: return
    if random.random() < 0.3:
        try:
            url = "https://itch.io/game-assets/free/tag-pixel-art"
            r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
            soup = BeautifulSoup(r.text, 'html.parser')
            games = soup.find_all('div', class_='game_cell')
            if games:
                pick = random.choice(games[:5])
                link = pick.find('a', class_='game_title').find('a')['href']
                await context.bot.send_message(chat_id=MY_CHAT_ID, text=f"🎁 **Recurso Encontrado:**\n{link}")
        except: pass

async def post_init(app):
    s = AsyncIOScheduler()
    s.add_job(vigilancia_proactiva, 'interval', hours=4, args=[app])
    s.start()

if __name__ == '__main__':
    threading.Thread(target=run_health_server, daemon=True).start()
    
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    
    app.add_handler(CommandHandler("start", lambda u,c: u.message.reply_text("⚡ Lía Online (Flux + GitHub + Supabase).")))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("conectar", cmd_conectar))
    app.add_handler(CommandHandler("imagina", cmd_imagina)) # <--- RESTAURADO
    app.add_handler(CommandHandler("tarea", cmd_tarea))
    app.add_handler(CommandHandler("bug", cmd_bug))
    app.add_handler(CommandHandler("feature", cmd_feature))
    app.add_handler(CommandHandler("codear", cmd_codear))
    app.add_handler(CommandHandler("pendientes", cmd_pendientes))
    app.add_handler(CommandHandler("hecho", cmd_hecho))
    app.add_handler(CommandHandler("assets", cmd_assets))
    app.add_handler(CommandHandler("arbol", cmd_arbol))
    app.add_handler(CommandHandler("leer", cmd_leer))
    app.add_handler(MessageHandler(filters.Document.ALL, recibir_archivo))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat_texto))
    
    print(">>> LÍA V4.0 OPERATIVA <<<")
    app.run_polling()


