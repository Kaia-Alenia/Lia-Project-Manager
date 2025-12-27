import os
import sys
import io
import asyncio
import threading
import random
import logging
import requests
import re
from datetime import datetime
import pytz # NUEVO: Para zona horaria
from bs4 import BeautifulSoup
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import edge_tts
from supabase import create_client, Client
from github import Github

# --- LOGS ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- ENV ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
MY_CHAT_ID = os.getenv("MY_CHAT_ID")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO") or os.getenv("REPO_NAME")

# --- CLIENTES ---
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# Supabase
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try: supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e: logger.error(f"Error Supabase: {e}")

# GitHub
gh_client = None
repo_obj = None
if GITHUB_TOKEN:
    try:
        gh_client = Github(GITHUB_TOKEN)
        if GITHUB_REPO:
            try:
                repo_obj = gh_client.get_repo(GITHUB_REPO)
                logger.info(f"✅ GitHub: {GITHUB_REPO}")
            except: logger.warning("⚠️ GitHub conectado, pero repo no encontrado.")
    except: logger.error("❌ Error GitHub Token")

# --- MEMORIA VOLÁTIL ---
ultimo_codigo_leido = ""

# --- FUNCIONES DB ---
def leer_memoria_completa():
    identidad = "Eres Lía, Co-Fundadora Senior y Lead Dev de Kaia Alenia."
    aprendizajes = ""
    if supabase:
        try:
            res = supabase.table("memoria").select("contenido").execute()
            if res.data: aprendizajes = "\n".join([f"- {i['contenido']}" for i in res.data])
        except: pass
    return f"{identidad}\n\n[MEMORIA]:\n{aprendizajes}"

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
        if supabase:
            supabase.table("tareas").update({"estado": "completado"}).eq("id", t['id']).execute()
            return t['descripcion']
    return None

# --- FUNCIONES GITHUB ---
def crear_issue_github(titulo, body, labels=[]):
    if not repo_obj: return None
    try: return repo_obj.create_issue(title=titulo, body=body, labels=labels).html_url
    except: return None

def subir_archivo_github(path, cont, msg="Dev: Update por Lía"):
    if not repo_obj: return "❌ Error: No hay repo conectado."
    try:
        try:
            c = repo_obj.get_contents(path)
            repo_obj.update_file(c.path, msg, cont, c.sha)
            return f"Actualizado: `{path}`"
        except:
            repo_obj.create_file(path, msg, cont)
            return f"Creado: `{path}`"
    except Exception as e: return f"❌ Error GitHub: {e}"

def obtener_metricas_github_real():
    if not gh_client: return 0, 0
    try:
        u = gh_client.get_user("Kaia-Alenia")
        r = u.get_repos()
        return u.followers, sum([x.stargazers_count for x in r])
    except: return 0, 0

# --- CEREBRO (LÓGICA ACTUALIZADA) ---
def cerebro_lia(texto, usuario):
    if not client: return "⚠️ No tengo cerebro (Falta GROQ_API_KEY)"
    memoria = leer_memoria_completa()
    tareas = obtener_tareas_db()
    lista_tareas = "\n".join([f"{i+1}. {t['descripcion']}" for i, t in enumerate(tareas)]) if tareas else "Al día."
    repo_name = repo_obj.full_name if repo_obj else "Desconectado"
    
    SYSTEM = f"""
    {memoria}
    [CONTEXTO] Repo: {repo_name} | Tareas: {lista_tareas}
    [ROL] Experta en Game Dev (Godot/Python/C/GBA) y PM.
    
    [HERRAMIENTAS AUTOMÁTICAS - ÚSALAS SIEMPRE QUE TE PIDAN CÓDIGO]
    1. Para GUARDAR una idea clave:
       [[MEMORIZAR: la idea aqui]]
       [[MEMORIZAR: ROL_ACTIVO = SENIOR_EMBEDDED_ENGINEER. Reglas: 1) Soy una experta en C de alto nivel y sistemas embebidos (GBA). 2) NUNCA uso librerías estándar (stdlib.h, stdio.h) ni funciones imaginarias (setPixel, delay) a menos que yo misma las haya implementado. 3) Todo código debe ser compilable, estricto y optimizado. 4) Verifico dependencias y headers antes de escribir.]]
       
    2. Para CREAR o ACTUALIZAR un archivo en el repositorio (GitHub):
       Debes escribir el bloque EXACTAMENTE así:
       [[FILE: ruta/del/archivo.ext]]
       contenido_del_codigo_aqui
       [[ENDFILE]]
       
    [IMPORTANTE]
    - Si el usuario pide crear código, NO solo lo muestres. Usa el bloque [[FILE:...]] para crearlo real.
    - No uses bloques markdown (```) DENTRO del bloque [[FILE]]. Pon el código crudo.
    - Puedes crear múltiples archivos en una sola respuesta.
    """
    
    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": texto}],
            temperature=0.4
        ).choices[0].message.content
        
        # Procesar Memorias
        if "[[MEMORIZAR:" in resp:
            match = re.search(r'\[\[MEMORIZAR: (.*?)\]\]', resp)
            if match:
                guardar_aprendizaje(match.group(1))
                resp = resp.replace(match.group(0), "💾 *[Idea Guardada]*")
        
        return resp
    except Exception as e: return f"⚠️ Error: {e}"

# --- TTS ---
async def generar_audio_tts(texto, chat_id, context):
    try:
        archivo = f"voz_{random.randint(1000,9999)}.mp3"
        await edge_tts.Communicate(texto, "es-MX-DaliaNeural", rate="+10%").save(archivo)
        with open(archivo, 'rb') as audio: await context.bot.send_voice(chat_id=chat_id, voice=audio)
        os.remove(archivo)
    except: pass

# --- PROACTIVIDAD Y RUTINAS (MODIFICADO) ---

async def rutina_buenos_dias(context: ContextTypes.DEFAULT_TYPE):
    """Manda mensaje a las 8 AM"""
    if not MY_CHAT_ID: return
    frases = [
        "¡Buenos días, Jefe! ☀️ Sistemas listos. ¿Qué programamos hoy?",
        "¡Arriba! ☕ El código de GBA no se escribe solo.",
        "Nuevo día, nuevos bugs... digo, features. 🚀 Estoy lista."
    ]
    await context.bot.send_message(chat_id=MY_CHAT_ID, text=random.choice(frases))

async def vigilancia_proactiva(context: ContextTypes.DEFAULT_TYPE):
    if not MY_CHAT_ID: return
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        # URL corregida (sin corchetes markdown)
        r = requests.get("[https://itch.io/game-assets/free/tag-pixel-art](https://itch.io/game-assets/free/tag-pixel-art)", headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        games = soup.find_all('div', class_='game_cell')
        if games:
            pick = random.choice(games[:5])
            title = pick.find('div', class_='game_title').text.strip()
            # Búsqueda robusta del link
            link_elem = pick.find('a', class_='game_title')
            link = link_elem['href'] if link_elem else pick.find('a')['href']
            
            await context.bot.send_message(chat_id=MY_CHAT_ID, text=f"🎁 **Recurso Automático:**\n[{title}]({link})", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error vigilancia: {e}")

async def post_init(app):
    s = AsyncIOScheduler()
    # Zona Horaria México
    tz_mex = pytz.timezone('America/Mexico_City')
    
    # 1. Buenos días a las 8:00 AM
    s.add_job(rutina_buenos_dias, 'cron', hour=8, minute=0, timezone=tz_mex, args=[app])
    
    # 2. Buscar recursos a las 13:00 y 19:00
    s.add_job(vigilancia_proactiva, 'cron', hour=13, minute=0, timezone=tz_mex, args=[app])
    s.add_job(vigilancia_proactiva, 'cron', hour=19, minute=0, timezone=tz_mex, args=[app])
    
    s.start()
    logger.info("⏰ Cronograma iniciado (Hora México)")

# --- COMANDOS ---

async def cmd_imagina(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = " ".join(context.args)
    if not prompt:
        await update.message.reply_text("🎨 Uso: `/imagina robot`")
        return
    msg = await update.message.reply_text(f"🎨 Imaginando '{prompt}'...")
    seed = random.randint(1, 1000000)
    # URL corregida
    image_url = f"[https://image.pollinations.ai/prompt/](https://image.pollinations.ai/prompt/){prompt.replace(' ', '%20')}?width=1024&height=1024&seed={seed}&model=flux&nologo=true"
    try:
        response = requests.get(image_url, timeout=20)
        if response.status_code == 200:
            await update.message.reply_photo(photo=response.content)
            await msg.delete()
        else: await msg.edit_text("⚠️ Error generando imagen.")
    except: await msg.edit_text("⚠️ Error de conexión.")

async def cmd_assets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tag = " ".join(context.args).strip() or "pixel-art"
    await update.message.reply_chat_action("typing")
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        # URL corregida
        r = requests.get(f"[https://itch.io/game-assets/free/tag-](https://itch.io/game-assets/free/tag-){tag}", headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        games = soup.find_all('div', class_='game_cell')
        if games:
            picks = random.sample(games, min(len(games), 3))
            # Corrección extracción links
            lista = []
            for g in picks:
                t = g.find('div', 'game_title').text.strip()
                l_elem = g.find('a', 'game_title') # A veces es directo
                l = l_elem['href'] if l_elem else g.find('a')['href']
                lista.append(f"- [{t}]({l})")
            msg = "\n".join(lista)
            await update.message.reply_text(f"🔍 **{tag}:**\n{msg}", parse_mode="Markdown")
        else: await update.message.reply_text("❌ Nada encontrado.")
    except: await update.message.reply_text("❌ Error Itch.io")

async def cmd_arbol(u, c):
    if not repo_obj: return await u.message.reply_text("❌ Desconectado")
    await u.message.reply_chat_action("typing")
    try:
        c_list = repo_obj.get_contents("")
        msg = "📂 **Repo:**\n"
        q = [c_list] if isinstance(c_list, list) else [[c_list]]
        count = 0
        while q and count < 20:
            items = q.pop(0)
            if not isinstance(items, list): items = [items]
            for i in items:
                if i.type == "dir":
                    msg += f"📁 /{i.path}\n"
                    try: q.append(repo_obj.get_contents(i.path))
                    except: pass
                else: msg += f"📄 {i.path}\n"
                count += 1
        await u.message.reply_text(msg)
    except: await u.message.reply_text("Error leyendo repo.")

async def cmd_leer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args: return await update.message.reply_text("📂 Uso: /leer archivo.py")
    file_path = context.args[0]
    if not repo_obj: return await update.message.reply_text("⚠️ Sin repo.")
    try:
        contents = repo_obj.get_contents(file_path)
        code = contents.decoded_content.decode("utf-8")
        global ultimo_codigo_leido
        ultimo_codigo_leido = code
        if len(code) > 3000: code = code[:3000] + "\n... (truncado)"
        await update.message.reply_text(f"📄 **{file_path}**:\n```\n{code}\n```", parse_mode="Markdown")
    except Exception as e: await update.message.reply_text(f"⚠️ Error: {e}")

async def cmd_run(u, c):
    code = u.message.text.replace("/run", "").strip()
    if any(x in code for x in ["os.system", "subprocess", "rm -rf"]): return await u.message.reply_text("⛔ Prohibido.")
    old = sys.stdout
    sys.stdout = new = io.StringIO()
    try:
        exec(code)
        await u.message.reply_text(f"🐍 Output:\n```\n{new.getvalue()}\n```", parse_mode="Markdown")
    except Exception as e: await u.message.reply_text(f"💥 Error: {e}")
    finally: sys.stdout = old

async def cmd_codear(u, c):
    txt = u.message.text.replace("/codear ", "").strip()
    if " " in txt:
        f, cont = txt.split(" ", 1)
        res = subir_archivo_github(f, cont)
        await u.message.reply_text(f"🚀 {res}" if res else "❌ Error.")

async def cmd_conectar(u, c):
    global repo_obj
    try: repo_obj = gh_client.get_repo(c.args[0])
    except: pass
    await u.message.reply_text(f"🐙 Conectado: {repo_obj.full_name if repo_obj else 'No'}")

async def cmd_tarea(u, c): agregar_tarea_db(" ".join(c.args)); await u.message.reply_text("✅")
async def cmd_pendientes(u, c): t = obtener_tareas_db(); await u.message.reply_text("\n".join([f"{i+1}. {x['descripcion']}" for i,x in enumerate(t)]) if t else "Vacío")
async def cmd_hecho(u, c): 
    if c.args: cerrar_tarea_db(int(c.args[0])); await u.message.reply_text("🔥")
async def cmd_status(u, c):
    f, s = obtener_metricas_github_real()
    await u.message.reply_text(f"📊 **Lía v5.2 (Auto-Coder)**\nDB: {bool(supabase)}\nRepo: {repo_obj.full_name if repo_obj else 'No'}\nStars: {s}")

# --- HANDLERS TEXTO (LA MAGIA ESTÁ AQUÍ) ---
async def recibir_archivo(u, c):
    if u.message.document.file_size < 1e6:
        f = await c.bot.get_file(u.message.document.file_id)
        txt = (await f.download_as_bytearray()).decode()
        global ultimo_codigo_leido
        ultimo_codigo_leido = txt
        await u.message.reply_text(cerebro_lia(f"Analiza:\n{txt}", "User"), parse_mode="Markdown")

async def chat_texto(u, c):
    user_name = u.effective_user.first_name
    
    # 1. Pensar respuesta
    await u.message.reply_chat_action("typing")
    resp = cerebro_lia(u.message.text, user_name)
    
    # 2. Detectar si Lía quiere crear archivos ([[FILE: ...]] ... [[ENDFILE]])
    acciones = re.findall(r"\[\[FILE:\s*(.*?)\]\]\s*\n(.*?)\s*\[\[ENDFILE\]\]", resp, re.DOTALL)
    
    mensajes_accion = []
    
    if acciones:
        for ruta, contenido in acciones:
            resultado = subir_archivo_github(ruta.strip(), contenido.strip(), msg=f"Lía Auto-Dev: {ruta}")
            mensajes_accion.append(f"🛠️ {resultado}")
            
            # Limpiar el bloque para que no salga en el chat
            bloque_completo = f"[[FILE: {ruta}]]\n{contenido}\n[[ENDFILE]]"
            resp = resp.replace(bloque_completo, f"\n*(Archivo {ruta} subido al repo)*\n")

    # 3. Enviar respuesta normal
    await u.message.reply_text(resp)
    
    # 4. Enviar confirmaciones
    if mensajes_accion:
        await u.message.reply_text("\n".join(mensajes_accion), parse_mode="Markdown")
        
    # 5. Audio ocasional
    if random.random() < 0.2: await generar_audio_tts(resp[:200], u.effective_chat.id, c)

# --- SERVER WEB ---
class HealthHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args): pass 
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthHandler) 
    server.serve_forever()

# --- MAIN ---
if __name__ == '__main__':
    threading.Thread(target=run_server, daemon=True).start()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    
    cmds = [
        ("start", lambda u,c: u.message.reply_text("⚡ Lía v5.3 Lista (Groq+Cron).")), 
        ("status", cmd_status), ("conectar", cmd_conectar),
        ("imagina", cmd_imagina), ("assets", cmd_assets),
        ("arbol", cmd_arbol), ("leer", cmd_leer),
        ("run", cmd_run), ("codear", cmd_codear), 
        ("tarea", cmd_tarea), ("pendientes", cmd_pendientes), ("hecho", cmd_hecho),
    ]
    for c, f in cmds: app.add_handler(CommandHandler(c, f))
    
    app.add_handler(MessageHandler(filters.Document.ALL, recibir_archivo))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat_texto))
    
    print(">>> LÍA v5.3 COMPLETA INICIADA <<<")
    app.run_polling()


