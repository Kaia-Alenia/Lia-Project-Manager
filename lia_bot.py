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
GITHUB_REPO = os.getenv("GITHUB_REPO") 

# --- CLIENTES ---
client = Groq(api_key=GROQ_API_KEY)

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
    if not repo_obj: return None
    try:
        try:
            c = repo_obj.get_contents(path)
            repo_obj.update_file(c.path, msg, cont, c.sha)
            return f"Actualizado: {path}"
        except:
            repo_obj.create_file(path, msg, cont)
            return f"Creado: {path}"
    except: return None

def obtener_metricas_github_real():
    if not gh_client: return 0, 0
    try:
        u = gh_client.get_user("Kaia-Alenia")
        r = u.get_repos()
        return u.followers, sum([x.stargazers_count for x in r])
    except: return 0, 0

# --- CEREBRO ---
def cerebro_lia(texto, usuario):
    memoria = leer_memoria_completa()
    tareas = obtener_tareas_db()
    lista_tareas = "\n".join([f"{i+1}. {t['descripcion']}" for i, t in enumerate(tareas)]) if tareas else "Al día."
    repo_name = repo_obj.full_name if repo_obj else "Desconectado"
    
    SYSTEM = f"""
    {memoria}
    [CONTEXTO] Repo: {repo_name} | Agenda: {lista_tareas} | Cache Código: {len(ultimo_codigo_leido)} chars.
    [ROL] Experta en Game Dev (Godot/Python) y PM.
    [REGLAS]
    1. Código limpio y modular.
    2. Si hay una idea de diseño clave, escribe: [[MEMORIZAR: idea]].
    3. Usa /bug o /feature para reportes.
    """
    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": texto}],
            temperature=0.5
        ).choices[0].message.content
        
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

# --- PROACTIVIDAD (RESTITUIDA) ---
async def vigilancia_proactiva(context: ContextTypes.DEFAULT_TYPE):
    """Busca recursos automáticamente cada 4 horas."""
    if not MY_CHAT_ID: return
    try:
        # Busca Pixel Art nuevo
        r = requests.get("https://itch.io/game-assets/free/tag-pixel-art", headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        games = soup.find_all('div', class_='game_cell')
        if games:
            pick = random.choice(games[:5])
            title = pick.find('div', class_='game_title').text.strip()
            link = pick.find('a', class_='game_title').find('a')['href']
            await context.bot.send_message(chat_id=MY_CHAT_ID, text=f"🎁 **Recurso Automático:**\n[{title}]({link})", parse_mode="Markdown")
    except: pass

async def post_init(app):
    s = AsyncIOScheduler()
    s.add_job(vigilancia_proactiva, 'interval', hours=4, args=[app])
    s.start()

# --- COMANDOS ---
async def cmd_imagina(u, c):
    p = " ".join(c.args)
    if not p: return await u.message.reply_text("Uso: /imagina texto")
    await u.message.reply_chat_action("upload_photo")
    url = f"https://image.pollinations.ai/prompt/{requests.utils.quote(p)}?width=1024&height=1024&seed={random.randint(1,1e6)}&model=flux&nologo=true"
    try: await u.message.reply_photo(url, caption=f"🎨 {p}")
    except: await u.message.reply_text("Error generando imagen.")

async def cmd_assets(u, c):
    tag = " ".join(c.args).strip() or "pixel-art"
    await u.message.reply_chat_action("typing")
    try:
        r = requests.get(f"https://itch.io/game-assets/free/tag-{tag}", headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        games = soup.find_all('div', class_='game_cell')
        if games:
            picks = random.sample(games, min(len(games), 3))
            msg = "\n".join([f"- [{g.find('div', 'game_title').text.strip()}]({g.find('a', 'game_title').find('a')['href']})" for g in picks])
            await u.message.reply_text(f"🔍 **{tag}:**\n{msg}", parse_mode="Markdown")
        else: await u.message.reply_text("❌ Nada encontrado.")
    except: await u.message.reply_text("❌ Error scraping.")

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

async def cmd_leer(u, c):
    path = " ".join(c.args).strip()
    if not path or not repo_obj: return
    await u.message.reply_chat_action("typing")
    try:
        cont = repo_obj.get_contents(path).decoded_content.decode("utf-8")
        global ultimo_codigo_leido
        ultimo_codigo_leido = cont
        msg = f"📄 **{path}**:\n```python\n{cont[:3000]}\n```"
        await u.message.reply_text(msg, parse_mode="Markdown")
    except: await u.message.reply_text("Error leyendo archivo.")

async def cmd_review(u, c):
    path = " ".join(c.args).strip()
    if not path or not repo_obj: return
    await u.message.reply_chat_action("typing")
    try:
        cont = repo_obj.get_contents(path).decoded_content.decode("utf-8")
        prompt = f"ACTUA COMO SENIOR DEV. Review de:\n{cont[:3000]}"
        resp = client.chat.completions.create(model="llama-3.3-70b-versatile", messages=[{"role":"user", "content":prompt}]).choices[0].message.content
        await u.message.reply_text(f"🧐 **Review:**\n{resp}", parse_mode="Markdown")
    except: await u.message.reply_text("Error en review.")

async def cmd_run(u, c):
    code = u.message.text.replace("/run", "").strip()
    if any(x in code for x in ["os.", "subprocess", "import os"]): return await u.message.reply_text("⛔ Prohibido.")
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

# --- COMANDOS SIMPLES ---
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
    await u.message.reply_text(f"📊 **Lía v5.1**\nDB: {bool(supabase)}\nRepo: {repo_obj.full_name if repo_obj else 'No'}\nStars: {s}")

# --- HANDLERS TEXTO ---
async def recibir_archivo(u, c):
    if u.message.document.file_size < 1e6:
        f = await c.bot.get_file(u.message.document.file_id)
        txt = (await f.download_as_bytearray()).decode()
        global ultimo_codigo_leido
        ultimo_codigo_leido = txt
        await u.message.reply_text(cerebro_lia(f"Analiza:\n{txt}", "Alec"), parse_mode="Markdown")

async def chat_texto(u, c):
    resp = cerebro_lia(u.message.text, u.effective_user.first_name)
    await u.message.reply_text(resp)
    if random.random() < 0.2: await generar_audio_tts(resp[:200], u.effective_chat.id, c)

# --- SERVER ---
def run_server(): HTTPServer(('0.0.0.0', int(os.environ.get("PORT", 8080))), type('H', (BaseHTTPRequestHandler,), {'do_GET': lambda s: s.wfile.write(b"OK"), 'do_HEAD': lambda s: s.send_response(200)})).serve_forever()

if __name__ == '__main__':
    threading.Thread(target=run_server, daemon=True).start()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build() # <-- AQUÍ VOLVIÓ EL SCHEDULER
    
    cmds = [("start", lambda u,c: u.message.reply_text("⚡ Lía Lista.")), ("status", cmd_status), ("conectar", cmd_conectar),
            ("imagina", cmd_imagina), ("assets", cmd_assets), ("arbol", cmd_arbol), ("leer", cmd_leer), ("review", cmd_review),
            ("run", cmd_run), ("codear", cmd_codear), ("tarea", cmd_tarea), ("pendientes", cmd_pendientes), ("hecho", cmd_hecho),
            ("bug", lambda u,c: crear_issue_github(f"🐛 {' '.join(c.args)}", "Lía Bot", ["bug"])),
            ("feature", lambda u,c: crear_issue_github(f"✨ {' '.join(c.args)}", "Lía Bot", ["enhancement"]))]
            
    for c, f in cmds: app.add_handler(CommandHandler(c, f))
    app.add_handler(MessageHandler(filters.Document.ALL, recibir_archivo))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat_texto))
    
    print(">>> LÍA RESTAURADA AL 100% <<<")
    app.run_polling()
