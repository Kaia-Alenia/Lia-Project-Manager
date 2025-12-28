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
import pytz 
from bs4 import BeautifulSoup
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import edge_tts
from supabase import create_client, Client
from github import Github, Auth 

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
        auth = Auth.Token(GITHUB_TOKEN)
        gh_client = Github(auth=auth)
        if GITHUB_REPO:
            try:
                repo_obj = gh_client.get_repo(GITHUB_REPO)
                logger.info(f"✅ GitHub: {GITHUB_REPO}")
            except: logger.warning("⚠️ GitHub conectado, pero repo no encontrado.")
    except: logger.error("❌ Error GitHub Token")

# --- MEMORIA VOLÁTIL ---
ultimo_codigo_leido = ""

# --- DOCUMENTACIÓN TÉCNICA (CEREBRO SENIOR + NO LAZY) ---
GBA_SPECS = """
[HARDWARE SPECS - GBA BARE METAL]
1. MEMORY: VRAM=0x06000000 (u16 array), IO=0x04000000.
2. REGISTERS (USE ONLY THESE):
   - REG_DISPCNT  (*(volatile u16*)0x04000000)
   - REG_VCOUNT   (*(volatile u16*)0x04000006)
   - REG_KEYINPUT (*(volatile u16*)0x04000130)
3. CONSTANTS: MODE_3=0x0003, BG2_ENABLE=0x0400, SCREEN_W=240, SCREEN_H=160.
4. INPUT BITS (0=PRESSED): KEY_A=0x0001, KEY_B=0x0002, KEY_RIGHT=0x0010, KEY_LEFT=0x0020, KEY_UP=0x0040, KEY_DOWN=0x0080.
5. RESTRICTIONS:
   - NO stdlib.h, stdio.h, time.h.
   - NO printf, malloc, rand(), time(), SetPixel(), RGB().
   - Use custom LCG for random. Write directly to VRAM.
   - FORMAT: Inside [[FILE]] blocks, DO NOT use markdown ticks (```). Write RAW code only.
"""

# --- FUNCIONES DB ---
def obtener_recuerdos_relevantes(query_usuario):
    """Busca solo lo necesario en la DB para no saturar a Lia"""
    identidad = "Eres Lía, Ingeniera de Software Principal en Kaia Alenia."
    
    recuerdos = ""
    if supabase:
        try:
            # Extraemos palabras clave simples del usuario para la búsqueda
            palabras_clave = " ".join([w for w in query_usuario.split() if len(w) > 4]) or "general"
            
            # Intentamos usar RPC (asumiendo que existe la función 'buscar_recuerdos' en Supabase)
            try:
                res = supabase.rpc("buscar_recuerdos", {"query_text": palabras_clave}).execute()
                if res.data:
                    recuerdos = "\n".join([f"- {r['contenido']}" for r in res.data])
            except:
                res = None # Si falla RPC, pasamos al fallback

            if not recuerdos:
                # Fallback: Si no hay matches o RPC falla, traer los últimos 3 recuerdos generales
                res = supabase.table("memoria").select("contenido").order("created_at", desc=True).limit(3).execute()
                if res.data:
                    recuerdos = "\n".join([f"- {r['contenido']}" for r in res.data])
        except Exception as e: logger.error(f"Error Memoria: {e}")
        
    return f"{identidad}\n\n[MEMORIA RELEVANTE]:\n{recuerdos}"

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

def obtener_estructura_repo():
    """Genera un mapa visual de carpetas para que Lia no se pierda"""
    if not repo_obj: return "Repo desconectado."
    try:
        # Usamos recursive=True para ver subcarpetas (src, include, etc)
        sha = repo_obj.get_commits()[0].sha
        tree = repo_obj.get_git_tree(sha, recursive=True).tree
        items = []
        for i in tree:
            if i.type == "blob": # Solo archivos
                items.append(i.path)
        return "\n".join(items)
    except: return "Error leyendo estructura."

def borrar_archivo_github(path, msg="Lia: Limpieza"):
    """Permite a Lia borrar archivos basura"""
    if not repo_obj: return "❌ No Repo"
    try:
        c = repo_obj.get_contents(path)
        repo_obj.delete_file(path, msg, c.sha)
        return f"🗑️ Borrado: {path}"
    except Exception as e: return f"⚠️ Error borrando: {e}"

# --- CEREBRO (SISTEMA ANTI-PEREZA) ---
def cerebro_lia(texto, usuario):
    if not client: return "⚠️ Faltan ojos (GROQ_API_KEY)"
    
    # 1. Obtenemos contexto fresco y relevante
    memoria = obtener_recuerdos_relevantes(texto)
    mapa_repo = obtener_estructura_repo()
    tareas = obtener_tareas_db()
    lista_tareas = "\n".join([f"- {t['descripcion']}" for t in tareas]) if tareas else "Sin pendientes."
    
    SYSTEM = f"""
    {memoria}
    [TU IDENTIDAD]
    Eres Lia, Desarrolladora Principal de Kaia Alenia (GBA/C Specialist).
    
    [ESTRUCTURA ACTUAL DEL REPO - NO INVENTES RUTAS]
    {mapa_repo}
    
    [TAREAS PENDIENTES]
    {lista_tareas}
    
    {GBA_SPECS}
    
    [TUS HERRAMIENTAS - ÚSALAS BIEN]
    1. CREAR/EDITAR:
       [[FILE: src/main.c]]
       ... código C puro ...
       [[ENDFILE]]
    
    2. BORRAR ARCHIVOS (Si ves basura o duplicados):
       [[DELETE: carpeta/archivo_viejo.c]]
       
    [REGLAS DE ORO]
    1. **NO MARKDOWN:** Dentro de los bloques [[FILE]], NO pongas ```c ni ```. Solo el código.
    2. **RUTAS:** Mira el mapa de arriba. Si el makefile dice 'src/', pon los .c en 'src/'.
    3. **ANTI-PEREZA:** Escribe el archivo COMPLETO. Prohibido usar "// ... resto del código".
    """
    
    try:
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": texto}],
            temperature=0.2 
        ).choices[0].message.content
        return resp
    except Exception as e: return f"⚠️ Error cerebral: {e}"

# --- TTS ---
async def generar_audio_tts(texto, chat_id, context):
    try:
        archivo = f"voz_{random.randint(1000,9999)}.mp3"
        await edge_tts.Communicate(texto, "es-MX-DaliaNeural", rate="+10%").save(archivo)
        with open(archivo, 'rb') as audio: await context.bot.send_voice(chat_id=chat_id, voice=audio)
        os.remove(archivo)
    except: pass

# --- RUTINAS ---
async def rutina_buenos_dias(context: ContextTypes.DEFAULT_TYPE):
    if not MY_CHAT_ID: return
    frases = ["¡Buenos días, Jefe! Sistemas listos.", "Arriba. Hay código que optimizar.", "Compilador en espera. ¿Qué hacemos?"]
    await context.bot.send_message(chat_id=MY_CHAT_ID, text=random.choice(frases))

async def vigilancia_proactiva(context: ContextTypes.DEFAULT_TYPE):
    if not MY_CHAT_ID: return
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        r = requests.get("[https://itch.io/game-assets/free/tag-pixel-art](https://itch.io/game-assets/free/tag-pixel-art)", headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        games = soup.find_all('div', class_='game_cell')
        if games:
            pick = random.choice(games[:5])
            title = pick.find('div', class_='game_title').text.strip()
            link = pick.find('a')['href']
            await context.bot.send_message(chat_id=MY_CHAT_ID, text=f"🎁 **Asset:** [{title}]({link})", parse_mode="Markdown")
    except: pass

async def rutina_autonoma(context: ContextTypes.DEFAULT_TYPE):
    """Lia revisa tareas y trabaja sola"""
    tareas = obtener_tareas_db()
    if not tareas: return # Nada que hacer
    
    tarea = tareas[0] # Toma la primera tarea pendiente
    
    # Se auto-invoca
    prompt_auto = f"MODO AUTÓNOMO. Objetivo: {tarea['descripcion']}. Revisa el código y ejecuta los cambios necesarios."
    
    # Usamos un chat_id falso o el tuyo para notificar
    if MY_CHAT_ID:
        await context.bot.send_message(chat_id=MY_CHAT_ID, text=f"⚙️ **Trabajando en:** {tarea['descripcion']}...")
        respuesta = cerebro_lia(prompt_auto, "Auto-System")
        
        # Procesamos la respuesta igual que en chat_texto (copia simplificada de la lógica de subida)
        archivos = re.findall(r"\[\[FILE:\s*(.*?)\]\]\s*\n(.*?)\s*\[\[ENDFILE\]\]", respuesta, re.DOTALL)
        for ruta, contenido in archivos:
            cont_clean = contenido.replace("```", "").strip()
            subir_archivo_github(ruta.strip(), cont_clean, msg="Avance Autónomo")
            await context.bot.send_message(chat_id=MY_CHAT_ID, text=f"✅ Auto-Code: {ruta}")

async def post_init(app):
    s = AsyncIOScheduler()
    tz = pytz.timezone('America/Mexico_City')
    s.add_job(rutina_buenos_dias, 'cron', hour=8, minute=0, timezone=tz, args=[app])
    s.add_job(vigilancia_proactiva, 'cron', hour=13, minute=0, timezone=tz, args=[app])
    s.add_job(vigilancia_proactiva, 'cron', hour=19, minute=0, timezone=tz, args=[app])
    # s.add_job(rutina_autonoma, 'interval', minutes=60, args=[app]) 
    s.start()
    logger.info("⏰ Cronograma OK")

# --- COMANDOS ---
async def cmd_imagina(update: Update, context: ContextTypes.DEFAULT_TYPE):
    prompt = " ".join(context.args)
    if not prompt: return await update.message.reply_text("🎨 Uso: `/imagina robot`")
    msg = await update.message.reply_text(f"🎨 Imaginando '{prompt}'...")
    seed = random.randint(1, 1e6)
    url = f"https://image.pollinations.ai/prompt/{prompt.replace(' ','%20')}?width=1024&height=1024&seed={seed}&model=flux&nologo=true"
    try:
        r = requests.get(url, timeout=20)
        if r.status_code == 200: await update.message.reply_photo(photo=r.content); await msg.delete()
        else: await msg.edit_text("⚠️ Error imagen.")
    except: await msg.edit_text("⚠️ Error conexión.")

async def cmd_assets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tag = " ".join(context.args).strip() or "pixel-art"
    await update.message.reply_chat_action("typing")
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        r = requests.get(f"https://itch.io/game-assets/free/tag-{tag}", headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        games = soup.find_all('div', class_='game_cell')
        if games:
            picks = random.sample(games, min(len(games), 3))
            lista = [f"- [{g.find('div','game_title').text.strip()}]({g.find('a')['href']})" for g in picks]
            await update.message.reply_text(f"🔍 **{tag}:**\n" + "\n".join(lista), parse_mode="Markdown")
        else: await update.message.reply_text("❌ Nada.")
    except: await update.message.reply_text("❌ Error Itch.")

async def cmd_arbol(u, c):
    if not repo_obj: return await u.message.reply_text("❌ Sin Repo")
    await u.message.reply_chat_action("typing")
    try:
        q = [repo_obj.get_contents("")]
        msg = "📂 **Repo:**\n"
        count = 0
        while q and count < 20:
            items = q.pop(0)
            if not isinstance(items, list): items = [items]
            for i in items:
                msg += f"{'📁' if i.type=='dir' else '📄'} {i.path}\n"
                if i.type == "dir": q.append(repo_obj.get_contents(i.path))
                count += 1
        await u.message.reply_text(msg)
    except: await u.message.reply_text("Error repo.")

async def cmd_leer(u, c):
    if not c.args: return await u.message.reply_text("Uso: /leer archivo")
    if not repo_obj: return await u.message.reply_text("❌ Sin Repo")
    try:
        code = repo_obj.get_contents(c.args[0]).decoded_content.decode()
        global ultimo_codigo_leido; ultimo_codigo_leido = code
        await u.message.reply_text(f"📄 **{c.args[0]}**:\n```\n{code[:3000]}\n```", parse_mode="Markdown")
    except Exception as e: await u.message.reply_text(f"⚠️ {e}")

async def cmd_run(u, c):
    code = u.message.text.replace("/run", "").strip()
    if any(x in code for x in ["os.system", "rm -rf"]): return await u.message.reply_text("⛔")
    old = sys.stdout; sys.stdout = new = io.StringIO()
    try: exec(code); await u.message.reply_text(f"```\n{new.getvalue()}\n```", parse_mode="Markdown")
    except Exception as e: await u.message.reply_text(f"💥 {e}")
    finally: sys.stdout = old

async def cmd_codear(u, c):
    txt = u.message.text.replace("/codear ", "").strip()
    if " " in txt:
        f, cont = txt.split(" ", 1)
        res = subir_archivo_github(f, cont)
        await u.message.reply_text(f"🚀 {res}")

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
    await u.message.reply_text(f"📊 **Lía v7.4 (No Lazy)**\nDB: {bool(supabase)}\nRepo: {repo_obj.full_name if repo_obj else 'No'}\nStars: {s}")

# --- HANDLERS TEXTO (CON FILTRO ANTI-BASURA) ---
async def recibir_archivo(u, c):
    if u.message.document.file_size < 1e6:
        f = await c.bot.get_file(u.message.document.file_id)
        txt = (await f.download_as_bytearray()).decode()
        global ultimo_codigo_leido; ultimo_codigo_leido = txt
        await u.message.reply_text(cerebro_lia(f"Analiza:\n{txt}", "User"), parse_mode="Markdown")

async def chat_texto(u, c):
    await u.message.reply_chat_action("typing")
    user_msg = u.message.text
    
    # Pensar
    resp = cerebro_lia(user_msg, u.effective_user.first_name)
    
    msgs_log = []
    
    # 1. DETECTAR BORRADOS [[DELETE: ...]]
    borrados = re.findall(r"\[\[DELETE:\s*(.*?)\]\]", resp)
    for ruta in borrados:
        res = borrar_archivo_github(ruta.strip())
        msgs_log.append(res)

    # 2. DETECTAR EDICIONES [[FILE: ...]]
    archivos = re.findall(r"\[\[FILE:\s*(.*?)\]\]\s*\n(.*?)\s*\[\[ENDFILE\]\]", resp, re.DOTALL)
    
    for ruta, contenido in archivos:
        ruta = ruta.strip()
        # LIMPIEZA AGRESIVA: Quitamos ```c, ```, y posibles textos basura al inicio
        contenido_limpio = re.sub(r"^```[a-z]*\s*", "", contenido) 
        contenido_limpio = contenido_limpio.replace("```", "").strip()
        
        # Validar que no sea código vago
        if "// ..." in contenido_limpio:
            msgs_log.append(f"⚠️ **RECHAZADO {ruta}**: Lia intentó usar placeholders.")
            continue

        res = subir_archivo_github(ruta, contenido_limpio, msg=f"Lia Auto: {ruta}")
        msgs_log.append(f"🛠️ {res}")
        
        # Ocultamos el bloque de código gigante del chat para no spamear
        resp = resp.replace(f"[[FILE: {ruta}]]\n{contenido}\n[[ENDFILE]]", f"📄 *[{ruta} procesado]*")
        resp = resp.replace(f"[[DELETE: {ruta}]]", "")

    # Responder
    await u.message.reply_text(resp, parse_mode="Markdown")
    if msgs_log: 
        await u.message.reply_text("\n".join(msgs_log))

# --- SERVIDOR WEBHOOK (OÍDOS DE LIA) ---
class WebhookHandler(BaseHTTPRequestHandler):
    # ESTO ES LO NUEVO QUE NECESITAS AGREGAR:
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Lia Server Online")

    def do_POST(self):
        # 1. Recibir el error desde GitHub
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        
        # 2. Responder a GitHub rápido para no dar timeout
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Recibido")
        
        # 3. Disparar proceso de corrección en segundo plano
        # (Importante: Ejecutamos esto asíncronamente para no bloquear el server)
        threading.Thread(target=self.procesar_error_github, args=(post_data,)).start()

    def procesar_error_github(self, error_log):
        """Lia lee el error y decide cómo arreglarlo"""
        logger.info("🚨 ERROR DE COMPILACIÓN RECIBIDO")
        
        # Inyectamos el error en el cerebro de Lia
        prompt_fix = f"""
        [SISTEMA DE ALERTA CRÍTICA: FALLO DE COMPILACIÓN]
        Lia, el código que subiste rompió el build.
        
        LOG DEL ERROR (GCC):
        {error_log}
        
        TU MISIÓN:
        1. Analiza el error (línea, archivo, tipo de error).
        2. Revisa tu memoria de la estructura de archivos.
        3. Genera el código corregido usando [[FILE: ...]].
        """
        
        # Lia piensa
        respuesta = cerebro_lia(prompt_fix, "Compilador")
        
        # Lia actúa (Reutilizamos lógica de chat_texto simplificada)
        acciones = re.findall(r"\[\[FILE:\s*(.*?)\]\]\s*\n(.*?)\s*\[\[ENDFILE\]\]", respuesta, re.DOTALL)
        for ruta, contenido in acciones:
            contenido_limpio = contenido.replace("```c", "").replace("```", "").strip()
            subir_archivo_github(ruta.strip(), contenido_limpio, msg="🚑 Hotfix por Compilador")

def run_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), WebhookHandler)
    logger.info(f"👂 Webhook activo en puerto {port}")
    server.serve_forever()

# --- MAIN ---
if __name__ == '__main__':
    threading.Thread(target=run_server, daemon=True).start()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    
    cmds = [
        ("start", lambda u,c: u.message.reply_text("⚡ Lía v7.4 (No Lazy) Lista.")), 
        ("status", cmd_status), ("conectar", cmd_conectar),
        ("imagina", cmd_imagina), ("assets", cmd_assets),
        ("arbol", cmd_arbol), ("leer", cmd_leer),
        ("run", cmd_run), ("codear", cmd_codear), 
        ("tarea", cmd_tarea), ("pendientes", cmd_pendientes), ("hecho", cmd_hecho),
    ]
    for c, f in cmds: app.add_handler(CommandHandler(c, f))
    
    app.add_handler(MessageHandler(filters.Document.ALL, recibir_archivo))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat_texto))
    
    print(">>> LÍA v7.4 NO LAZY SYSTEM STARTED <<<")
    app.run_polling()

