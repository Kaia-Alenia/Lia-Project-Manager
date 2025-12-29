import os
import sys
import io
import asyncio
import threading
import random
import logging
import requests
import re
import json
import time
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
from PIL import Image, ImageOps
import io
import html  # <--- IMPORTANTE: Necesario para limpiar el código
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

# --- VARIABLE GLOBAL PARA EL LOOP (PUENTE HILOS) ---
# Esto arregla el error "RuntimeWarning: coroutine was never awaited"
global_app_loop = None

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

# --- DOCUMENTACIÓN TÉCNICA (CEREBRO SENIOR) ---
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

[REGLAS DE COMPILACIÓN - NO TOCAR EL MAKEFILE]
1. El Makefile YA EXISTE y es perfecto. NO LO EDITES a menos que agregues nuevos archivos .c.
2. NUNCA uses 'gcc' a secas. La compilación GBA requiere 'arm-none-eabi-gcc'.
3. Si agregas archivos .c nuevos, solo asegúrate de que el Makefile los incluya en la compilación.
"""

# --- FUNCIONES DB (RESTAURADAS) ---
def obtener_recuerdos_relevantes(query_usuario):
    identidad = "Eres Lía, Ingeniera de Software Principal en Kaia Alenia."
    recuerdos = ""
    if supabase:
        try:
            palabras_clave = " ".join([w for w in query_usuario.split() if len(w) > 4]) or "general"
            try:
                res = supabase.rpc("buscar_recuerdos", {"query_text": palabras_clave}).execute()
                if res.data: recuerdos = "\n".join([f"- {r['contenido']}" for r in res.data])
            except:
                res = None
            if not recuerdos:
                res = supabase.table("memoria").select("contenido").order("created_at", desc=True).limit(3).execute()
                if res.data: recuerdos = "\n".join([f"- {r['contenido']}" for r in res.data])
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

# --- FUNCIONES GITHUB (RESTAURADAS) ---
def crear_issue_github(titulo, body, labels=[]):
    if not repo_obj: return None
    try: return repo_obj.create_issue(title=titulo, body=body, labels=labels).html_url
    except: return None

def subir_archivo_github(path, cont, msg="Dev: Update por Lía"):
    if not repo_obj: return "❌ Error: No hay repo conectado."
    try:
        # 1. INTENTO DE BACKUP (Solo si el archivo ya existe)
        try:
            archivo_viejo = repo_obj.get_contents(path)
            # Si existe, guardamos una copia en la carpeta 'backups/'
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            nombre_backup = f"backups/{path.replace('/', '_')}_{timestamp}.bak"
            repo_obj.create_file(nombre_backup, f"Backup antes de tocar {path}", archivo_viejo.decoded_content)
            logger.info(f"🛡️ Backup creado: {nombre_backup}")
        except:
            pass # Si el archivo es nuevo, no hay backup que hacer

        # 2. ACTUALIZACIÓN NORMAL
        try:
            c = repo_obj.get_contents(path)
            repo_obj.update_file(c.path, msg, cont, c.sha)
            return f"Actualizado: `{path}` (Backup guardado)"
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
    if not repo_obj: return "Repo desconectado."
    try:
        sha = repo_obj.get_commits()[0].sha
        tree = repo_obj.get_git_tree(sha, recursive=True).tree
        items = []
        for i in tree:
            if i.type == "blob": items.append(i.path)
        return "\n".join(items)
    except: return "Error leyendo estructura."

def borrar_archivo_github(path, msg="Lia: Limpieza"):
    if not repo_obj: return "❌ No Repo"
    try:
        c = repo_obj.get_contents(path)
        repo_obj.delete_file(path, msg, c.sha)
        return f"🗑️ Borrado: {path}"
    except Exception as e: return f"⚠️ Error borrando: {e}"

# --- PEGAR AQUÍ LA FUNCIÓN DE CONVERSIÓN ---
def convertir_imagen_a_gba(image_bytes, nombre="sprite"):
    """Convierte una imagen PNG/JPG a array de C para GBA (Mode 3 / Linear)"""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    
    # Redimensionar si es gigante (Opcional, protección de memoria)
    # GBA pantalla es 240x160. Si es mayor, avisamos (pero convertimos igual por si es un mapa)
    w, h = img.size
    pixels = list(img.getdata())
    
    hex_data = []
    for r, g, b in pixels:
        # Conversión matemática a GBA (5 bits por canal)
        # Fórmula: (Blue << 10) | (Green << 5) | Red
        gba_val = ((b >> 3) << 10) | ((g >> 3) << 5) | (r >> 3)
        hex_data.append(f"0x{gba_val:04X}")
    
    # Formatear el código C
    c_code = (
        f"// Generado por Lia Art Studio\n"
        f"// Dimensiones: {w}x{h}\n"
        f"const unsigned short {nombre}_data[{w * h}] = {{\n"
    )
    
    # Agrupamos de 8 en 8 para que se vea bonito
    for i in range(0, len(hex_data), 8):
        linea = ", ".join(hex_data[i:i+8])
        c_code += f"    {linea},\n"
        
    c_code += "};\n"
    
    h_code = (
        f"// Header file para {nombre}\n"
        f"#define {nombre.upper()}_WIDTH {w}\n"
        f"#define {nombre.upper()}_HEIGHT {h}\n"
        f"extern const unsigned short {nombre}_data[{w * h}];\n"
    )
    
    return c_code, h_code, w, h
    
# --- CEREBRO (FULL) ---
def cerebro_lia(texto, usuario):
    if not client: return "⚠️ Faltan ojos (GROQ_API_KEY)"
    
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
    
    2. BORRAR ARCHIVOS:
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
    frases = "¡Buenos días! Sistemas listos.", "Arriba. Hay código que optimizar.", "Compilador en espera."
    await context.bot.send_message(chat_id=MY_CHAT_ID, text=random.choice(frases))

async def vigilancia_proactiva(context: ContextTypes.DEFAULT_TYPE):
    if not MY_CHAT_ID: return
    try:
        # Lista de temas posibles para variar
        temas = ["pixel-art", "sprites", "textures", "backgrounds", "chiptune", "fonts"]
        tema_del_dia = random.choice(temas)
        
        headers = {'User-Agent': 'Mozilla/5.0'}
        # Usamos el tema aleatorio
        r = requests.get(f"https://itch.io/game-assets/free/tag-{tema_del_dia}", headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        games = soup.find_all('div', class_='game_cell')
        if games:
            pick = random.choice(games[:5])
            title = pick.find('div', class_='game_title').text.strip()
            link = pick.find('a')['href']
            await context.bot.send_message(chat_id=MY_CHAT_ID, text=f"🎁 **Asset:** [{title}]({link})", parse_mode="Markdown")
    except: pass

async def post_init(app):
    # Guardamos el loop para usarlo desde el servidor HTTP (FIX CRÍTICO)
    global global_app_loop
    global_app_loop = asyncio.get_running_loop()

    s = AsyncIOScheduler()
    tz = pytz.timezone('America/Mexico_City')
    s.add_job(rutina_buenos_dias, 'cron', hour=8, minute=0, timezone=tz, args=[app])
    s.add_job(vigilancia_proactiva, 'cron', hour=13, minute=0, timezone=tz, args=[app])
    s.add_job(vigilancia_proactiva, 'cron', hour=19, minute=0, timezone=tz, args=[app])
    s.start()
    logger.info("⏰ Cronograma OK")

# --- COMANDOS (RESTAURADOS) ---
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
        # URL corregida: Sin corchetes [] ni paréntesis () del markdown
        url = f"https://itch.io/game-assets/free/tag-{tag}"
        
        r = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(r.text, 'html.parser')
        games = soup.find_all('div', class_='game_cell')
        
        if games:
            picks = random.sample(games, min(len(games), 3))
            lista = [f"- [{g.find('div','game_title').text.strip()}]({g.find('a')['href']})" for g in picks]
            await update.message.reply_text(f"🔍 **{tag}:**\n" + "\n".join(lista), parse_mode="Markdown")
        else: 
            await update.message.reply_text("❌ Nada encontrado.")
    except Exception as e: 
        # Agregué {e} para que si falla de nuevo, te diga exactamente por qué
        await update.message.reply_text(f"❌ Error Itch: {e}")

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
        archivo = c.args[0].strip()
        # Leemos el contenido
        code = repo_obj.get_contents(archivo).decoded_content.decode()
        
        # Guardamos en memoria volátil
        global ultimo_codigo_leido; ultimo_codigo_leido = code
        
        # --- FIX DE SEGURIDAD PARA TELEGRAM ---
        # 1. Limpiamos caracteres que rompen HTML (<, >, &)
        codigo_seguro = html.escape(code[:3000])
        
        # 2. Usamos etiquetas HTML <pre> para el bloque de código
        # Esto evita que los asteriscos (*) o guiones bajos (_) rompan el mensaje
        mensaje = f"📄 <b>{archivo}</b>:\n<pre>{codigo_seguro}</pre>"
        
        await u.message.reply_text(mensaje, parse_mode="HTML")
        
    except Exception as e: 
        await u.message.reply_text(f"⚠️ {e}")

async def cmd_run(u, c):
    code = u.message.text.replace("/run", "").strip()
    if any(x in code for x in ["os.system", "rm -rf"]): return await u.message.reply_text("⛔")
    old = sys.stdout; sys.stdout = new = io.StringIO()
    try: exec(code); await u.message.reply_text(f"```\n{new.getvalue()}\n```", parse_mode="Markdown")
    except Exception as e: await u.message.reply_text(f"💥 {e}")
    finally: sys.stdout = old

async def cmd_codear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    peticion = " ".join(context.args)
    if not peticion:
        await update.message.reply_text("❌ Uso: `/codear cambia el fondo a rojo`")
        return

    msg_espera = await update.message.reply_text("🧠 *Lía está leyendo el código actual y pensando...*")

    # 1. Identificar archivo objetivo (Default: src/main.c)
    archivo_target = "src/main.c"
    archivos_en_repo = []
    
    try:
        contents = repo_obj.get_contents("")
        while contents:
            file_content = contents.pop(0)
            if file_content.type == "dir":
                contents.extend(repo_obj.get_contents(file_content.path))
            else:
                archivos_en_repo.append(file_content.path)
                # Si el usuario mencionó un archivo específico, lo usamos
                if file_content.path in peticion:
                    archivo_target = file_content.path
    except:
        pass

    # 2. LEER CÓDIGO ACTUAL (CRÍTICO PARA EVITAR PANTALLA BLANCA)
    codigo_actual_contexto = ""
    try:
        file_obj = repo_obj.get_contents(archivo_target)
        codigo_actual_contexto = file_obj.decoded_content.decode()
    except:
        codigo_actual_contexto = "// No se pudo leer el archivo actual o no existe."

    # 3. Prompt Quirúrgico con Contexto
    prompt = f"""
    [MODO: SENIOR DEVELOPER GBA - EDICIÓN QUIRÚRGICA]
    Tu misión es modificar el código existente según la petición, SIN ROMPER la lógica actual.
    
    [ARCHIVO OBJETIVO]
    {archivo_target}

    [CÓDIGO ACTUAL (NO LO BORRES, SOLO EDÍTALO)]
    ```c
    {codigo_actual_contexto}
    ```
    
    [PETICIÓN DEL USUARIO]
    {peticion}
    
    [REGLAS]
    1. Mantén los registros de hardware (REG_DISPCNT, VRAM) tal como están si funcionan.
    2. Si añades sprites o lógica, intégralos en el `main` existente.
    3. Responde ÚNICAMENTE: [[FILE: {archivo_target}]] código completo [[ENDFILE]].
    """

    # 4. Llamar al cerebro
    respuesta = cerebro_lia(prompt, "Senior Dev")

    # 5. Procesar respuesta (El backup se hace automáticamente dentro de subir_archivo_github)
    archivos = re.findall(r"\[\[FILE:\s*(.*?)\]\]\s*\n(.*?)\s*\[\[ENDFILE\]\]", respuesta, re.DOTALL)
    
    if not archivos:
        await msg_espera.edit_text("⚠️ La IA no devolvió el formato correcto. Intenta ser más específico.")
        return

    res_final = []
    for ruta_raw, contenido in archivos:
        ruta = ruta_raw.strip()
        contenido_limpio = contenido.replace("```c", "").replace("```", "").strip()
        
        # subir_archivo_github YA TIENE lógica de backup interna.
        # Al enviarle el contenido nuevo, moverá el viejo a backups/ automáticamente.
        resultado = subir_archivo_github(ruta, contenido_limpio, msg=f"🤖 IA: {peticion}")
        res_final.append(f"✅ {resultado}")

    await msg_espera.delete()
    await update.message.reply_text(f"🚀 **Cambios aplicados:**\n" + "\n".join(res_final))

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
    await u.message.reply_text(f"📊 **Lía v8.0 (Full + AutoFix)**\nDB: {bool(supabase)}\nRepo: {repo_obj.full_name if repo_obj else 'No'}\nStars: {s}")

async def cmd_review(u, c):
    if not c.args: return await u.message.reply_text("Uso: /review src/main.c")
    archivo = c.args[0]
    
    if not repo_obj: return await u.message.reply_text("❌ Sin repo.")
    await u.message.reply_chat_action("typing")
    
    try:
        # 1. Leer código
        codigo = repo_obj.get_contents(archivo).decoded_content.decode()
        
        # 2. Prompt de Auditoría
        prompt = f"""
        [MODO: SENIOR CODE REVIEWER]
        Analiza el siguiente código C para Game Boy Advance.
        NO ESCRIBAS CÓDIGO NUEVO. Solo dame un reporte de auditoría.
        
        Aspectos a criticar:
        1. Legibilidad (nombres de variables, indentación).
        2. Optimización (uso de memoria, bucles innecesarios).
        3. Posibles bugs o malas prácticas en C.
        4. Sugerencias de mejora.
        
        [CÓDIGO]
        {codigo[:3000]}
        """
        
        # 3. Respuesta
        respuesta = cerebro_lia(prompt, "Senior Reviewer")
        await u.message.reply_text(f"🧐 **Reporte de {archivo}:**\n\n{respuesta}", parse_mode="Markdown")
        
    except Exception as e:
        await u.message.reply_text(f"⚠️ No pude leer {archivo}: {e}")

async def cmd_gba(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pregunta = " ".join(context.args)
    if not pregunta:
        await update.message.reply_text("⚙️ **Consultor Técnico GBA**\nUso: `/gba como activo modo 4`")
        return

    # Mensaje temporal de "Pensando..."
    avisar = await update.message.reply_text("🧠 *Analizando registros de memoria...*", parse_mode='Markdown')
    
    prompt = f"""
    [ROLE: GBA Hardware Engineer]
    Eres un experto en hardware de Game Boy Advance (libgba, registers).
    Responde a esto de forma técnica pero breve. Usa bloques de código C.
    Pregunta: {pregunta}
    """
    
    respuesta = cerebro_lia(prompt, "GBA Engineer")
    
    # --- BLINDAJE ANTI-ERROR DE TELEGRAM ---
    try:
        # 1. Intentamos enviar con formato Markdown (Bonito)
        await update.message.reply_text(respuesta, parse_mode='Markdown')
    except Exception:
        # 2. Si falla (porque el código C tiene guiones bajos _ que confunden a Telegram),
        # lo enviamos como texto plano. Se ve menos bonito pero SIEMPRE LLEGA.
        await update.message.reply_text(respuesta)

    # Borramos el mensaje de "Pensando..." para limpiar el chat
    try:
        await avisar.delete()
    except:
        pass

# FÍJATE AQUÍ: Esta línea debe estar TOTALMENTE a la izquierda, sin espacios.
async def cmd_readme(u, c):
    """Genera automáticamente el archivo README.md del repo"""
    if not repo_obj: return await u.message.reply_text("❌ Sin repo conectado.")
    await u.message.reply_text("✍️ Redactando documentación del proyecto...")
    await u.message.reply_chat_action("typing")
    
    try:
        try:
            main_code = repo_obj.get_contents("src/main.c").decoded_content.decode()
        except:
            main_code = "No se encontró main.c"

        # TÉCNICA SEGURA TAMBIÉN AQUÍ
        prompt = (
            "[ROL: TECHNICAL WRITER]\n"
            "Genera un archivo README.md profesional para este proyecto de GBA.\n\n"
            f"[CÓDIGO PRINCIPAL]\n{main_code[:2000]}\n\n"
            "[REQUISITOS]\n"
            "1. Título Creativo (Invéntalo basado en el código).\n"
            "2. Descripción: Qué hace el juego/demo.\n"
            "3. Estructura: Explica brevemente qué es src/main.c.\n"
            "4. Compilación: Menciona que usa Makefile y DevKitPro.\n"
            "5. Formato: Markdown bonito (badges, emojis)."
        )
        
        contenido_readme = cerebro_lia(prompt, "Tech Writer")
        
        res = subir_archivo_github("README.md", contenido_readme, "Docs: Auto-update README")
        await u.message.reply_text(f"✅ **Documentación actualizada:**\n{res}")
        
    except Exception as e:
        await u.message.reply_text(f"❌ Error: {e}")

async def handle_photo(u: Update, c: ContextTypes.DEFAULT_TYPE):
    """Recibe imágenes, fuerza 64x64 y paleta reducida"""
    if not MY_CHAT_ID or str(u.effective_chat.id) != MY_CHAT_ID: return
    if not repo_obj: return await u.message.reply_text("❌ Sin repo.")

    photo = u.message.photo[-1]
    file_id = photo.file_id
    await u.message.reply_chat_action("upload_document")
    
    try:
        new_file = await c.bot.get_file(file_id)
        f_bytes = await new_file.download_as_bytearray()
        
        # --- PROCESAMIENTO GBA ESTRICTO ---
        img = Image.open(io.BytesIO(f_bytes))
        
        # 1. Forzar Redimensionado (Max 64x64)
        if img.width > 64 or img.height > 64:
            img.thumbnail((64, 64), Image.Resampling.NEAREST) # Nearest mantiene el look pixel art
            await u.message.reply_text(f"⚠️ Redimensionado a {img.width}x{img.height} para GBA.")
            
        # 2. Reducción de Colores (Simular 16 colores)
        # Esto ayuda a que el sprite se vea "legítimo" de GBA
        img = img.quantize(colors=16).convert("RGB")
        
        # Convertir a bytes para la función de C
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        f_final = img_byte_arr.getvalue()

        hora = datetime.now().strftime('%M%S')
        nombre_asset = f"sprite_{hora}" 
        
        c_code, h_code, w, h = convertir_imagen_a_gba(f_final, nombre_asset)
        
        path_c = f"src/{nombre_asset}.c"
        path_h = f"src/{nombre_asset}.h"
        
        subir_archivo_github(path_c, c_code, f"Art: Nuevo asset {nombre_asset}")
        subir_archivo_github(path_h, h_code, f"Art: Header {nombre_asset}")
        
        msg = f"✅ **Sprite 4bpp (Simulado) Integrado:**\n📍 `{path_c}`\n📐 {w}x{h} px"
        await u.message.reply_text(msg, parse_mode="Markdown")
        
    except Exception as e:
        await u.message.reply_text(f"❌ Error procesando asset: {e}")

async def cmd_debug_video(u, c):
    """Lia busca errores comunes de pantalla blanca"""
    if not repo_obj: return await u.message.reply_text("❌ Sin repo.")
    
    try:
        code = repo_obj.get_contents("src/main.c").decoded_content.decode()
        
        checklist = []
        # 1. Chequeo de Registros
        if "0x04000000" in code and ("0x0003" in code or "3" in code):
            checklist.append("✅ Modo de video configurado.")
        else:
            checklist.append("❌ FALTA CONFIGURAR REG_DISPCNT (Modo 3).")
            
        # 2. Chequeo de VRAM
        if "0x06000000" in code:
            checklist.append("✅ Puntero a VRAM detectado.")
        else:
            checklist.append("❌ NO VEO ESCRITURA EN VRAM (0x06000000).")

        # 3. Respuesta de Lía
        await u.message.reply_text(
            "🕵️ **Diagnóstico de Pantalla Blanca:**\n\n" + "\n".join(checklist) + 
            "\n\n_Si todo sale ✅ y sigue blanca, revisa si el bucle while(1) está vacío._"
        )
    except Exception as e:
        await u.message.reply_text(f"Error leyendo código: {e}")
        
# --- HELPER: ENVIAR MENSAJE DESDE WEBHOOK (NUEVO) ---
def notificar_telegram(texto):
    """Envía mensaje a Telegram de forma segura desde otro hilo"""
    global global_app_loop, MY_CHAT_ID, app
    
    if MY_CHAT_ID and global_app_loop and app:
        try:
            # Cortar mensaje si es muy largo
            msg_clean = texto[:3000] + ("..." if len(texto)>3000 else "")
            
            # Inyectar la tarea en el loop principal del bot
            asyncio.run_coroutine_threadsafe(
                app.bot.send_message(chat_id=MY_CHAT_ID, text=msg_clean, parse_mode="Markdown"),
                global_app_loop
            )
        except Exception as e:
            logger.error(f"Fallo al notificar Telegram: {e}")

# --- SERVER WEBHOOK & AUTO-FIX (CEREBRO CONTEXTUAL + WEB VISUAL) ---
class WebhookHandler(BaseHTTPRequestHandler):
    def _set_response(self):
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()

    def obtener_codigo_actual(self, error_log):
        """Intenta deducir qué archivo falló y descargarlo de GitHub"""
        # Buscamos patrones como "src/main.c:55: error:"
        match = re.search(r"([a-zA-Z0-9_\/]+\.c):\d+", error_log)
        if match:
            ruta = match.group(1)
            try:
                # Usamos la variable global repo_obj
                file_content = repo_obj.get_contents(ruta).decoded_content.decode()
                return ruta, file_content
            except Exception as e:
                logger.error(f"No pude descargar {ruta}: {e}")
                return ruta, None
        return None, None

    def procesar_error_github(self, error_log):
        """Lia lee el CÓDIGO ACTUAL + EL ERROR y repara solo lo necesario"""
        logger.info("🚨 ERROR DE COMPILACIÓN - INICIANDO PROTOCOLO DE REPARACIÓN")
        
        # 1. Identificar archivo culpable y leer su contenido
        archivo_culpable, codigo_roto = self.obtener_codigo_actual(error_log)
        
        contexto_archivo = ""
        if archivo_culpable and codigo_roto:
            logger.info(f"🧐 Analizando archivo: {archivo_culpable}")
            contexto_archivo = f"""
            [CÓDIGO ACTUAL EN REPO (ROTO)]
            Nombre: {archivo_culpable}
            Contenido:
            ```c
            {codigo_roto}
            ```
            """
            notificar_telegram(f"🚨 **Fallo en {archivo_culpable}**\n`{error_log[:200]}...`\n\n*Lia está leyendo el archivo para corregirlo...*")
        else:
            notificar_telegram(f"🚨 **Error General:**\n`{error_log[:200]}...`\n\n*Lia intentará arreglarlo a ciegas...*")

        # 2. Prompt de Ingeniería Quirúrgica
        prompt_fix = f"""
        [MODO: SENIOR SOFTWARE ENGINEER]
        Tienes un error de compilación en un proyecto GBA.
        
        {contexto_archivo}
        
        [ERRORES REPORTADOS POR GCC]
        {error_log}
        
        [TU MISIÓN - CRÍTICO]
        1. **NO REESCRIBAS LA LÓGICA:** Tu único trabajo es arreglar el error de sintaxis o compilación.
        2. **PRESERVA EL CÓDIGO:** Si el usuario tenía un cuadrado azul, DEBE SEGUIR SIENDO AZUL. No inventes "Hola Mundo" ni pantallas blancas.
        3. **CORRIGE EL ERROR:** Si falta una llave '}}', ponla. Si falta un ';', ponlo. Si hay un '?' sabotaje, bórralo.
        4. **SALIDA:** Devuelve el archivo {archivo_culpable or 'src/main.c'} COMPLETO y CORREGIDO.
        
        Responde formato: [[FILE: ruta/archivo.c]] código [[ENDFILE]].
        """
        
        respuesta = cerebro_lia(prompt_fix, "Senior Dev")
        archivos = re.findall(r"\[\[FILE:\s*(.*?)\]\]\s*\n(.*?)\s*\[\[ENDFILE\]\]", respuesta, re.DOTALL)
        
        fix_log = []
        for ruta_raw, contenido in archivos:
            ruta = ruta_raw.strip()
            if " " in ruta: ruta = ruta.split(" ")[0]
            ruta = ruta.replace("]", "").replace("[", "")
            contenido_limpio = contenido.replace("```c", "").replace("```", "").strip()
            
            if len(contenido_limpio) < 10: continue

            # Subimos el fix
            res = subir_archivo_github(ruta, contenido_limpio, msg="🚑 Fix Quirúrgico por Lia")
            fix_log.append(res)
            logger.info(f"✅ Fix Aplicado: {res}")
            
        if fix_log:
            notificar_telegram("✅ **Corrección Aplicada:**\n" + "\n".join(fix_log) + "\n*Respetando lógica original. Recompilando...*")

    # --- PING DE VIDA (HEAD) ---
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

    # --- LA PARTE VISUAL NUEVA (GET) ---
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html; charset=utf-8')
        self.end_headers()
        
        # Diseño Cyberpunk/Hacker para la web
        html = """
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Lia Status</title>
            <style>
                body {
                    background-color: #0d1117;
                    color: #e6edf3;
                    font-family: 'Courier New', monospace;
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    justify-content: center;
                    height: 100vh;
                    margin: 0;
                }
                .container {
                    text-align: center;
                    border: 1px solid #30363d;
                    padding: 40px;
                    border-radius: 12px;
                    background: #161b22;
                    box-shadow: 0 0 20px rgba(0, 255, 170, 0.1);
                }
                h1 { font-size: 3rem; margin: 0; letter-spacing: -2px; }
                .status { 
                    color: #2ea043; 
                    font-weight: bold; 
                    margin-top: 10px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    gap: 10px;
                }
                .blink {
                    width: 12px;
                    height: 12px;
                    background-color: #2ea043;
                    border-radius: 50%;
                    box-shadow: 0 0 10px #2ea043;
                    animation: pulse 2s infinite;
                }
                @keyframes pulse {
                    0% { opacity: 1; transform: scale(1); }
                    50% { opacity: 0.5; transform: scale(0.8); }
                    100% { opacity: 1; transform: scale(1); }
                }
                p.info { color: #8b949e; font-size: 0.9rem; margin-top: 20px; }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>LIA v8.0</h1>
                <div class="status">
                    <div class="blink"></div>
                    SYSTEM ONLINE
                </div>
                <p class="info">GitHub Integration • Auto-Fix • AI Assistant</p>
                <p class="info" style="font-size: 0.7rem;">Running on Render Cloud</p>
            </div>
        </body>
        </html>
        """
        self.wfile.write(html.encode('utf-8'))

    # --- LA PARTE FUNCIONAL ORIGINAL (POST) ---
    def do_POST(self):
        try:
            content_length = int(self.headers['Content-Length'])
            post_bytes = self.rfile.read(content_length)
            post_str = post_bytes.decode('utf-8')
            
            # 1. TEXTO PLANO (CURL DEL ACTION)
            if not post_str.strip().startswith("{"):
                if "error" in post_str.lower() or "failed" in post_str.lower() or "fatal" in post_str.lower():
                    self.procesar_error_github(post_str)
                elif "exito" in post_str.lower() or "success" in post_str.lower():
                    notificar_telegram(f"🎉 **¡COMPILACIÓN EXITOSA!**\nLa ROM está lista y funcionando.")

            # 2. JSON (WEBHOOK NATIVO)
            elif post_str.strip().startswith("{"):
                pass
                
        except Exception as e:
            logger.error(f"Error do_POST: {e}")

        self._set_response()
        self.wfile.write(json.dumps({'status': 'ok'}).encode('utf-8'))

# --- ¡IMPORTANTE! ESTA FUNCIÓN VA PEGADA A LA IZQUIERDA (SIN ESPACIOS) ---
def run_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), WebhookHandler)
    logger.info(f"👂 Webhook activo en puerto {port}")
    server.serve_forever()
        
# --- HANDLERS TEXTO (RESTAURADOS) ---
async def recibir_archivo(u, c):
    if u.message.document.file_size < 1e6:
        f = await c.bot.get_file(u.message.document.file_id)
        txt = (await f.download_as_bytearray()).decode()
        global ultimo_codigo_leido; ultimo_codigo_leido = txt
        await u.message.reply_text(cerebro_lia(f"Analiza:\n{txt}", "User"), parse_mode="Markdown")

async def chat_texto(u, c):
    await u.message.reply_chat_action("typing")
    user_msg = u.message.text
    
    resp = cerebro_lia(user_msg, u.effective_user.first_name)
    msgs_log = []
    
    # 1. Borrados
    borrados = re.findall(r"\[\[DELETE:\s*(.*?)\]\]", resp)
    for ruta in borrados:
        res = borrar_archivo_github(ruta.strip())
        msgs_log.append(res)

    # 2. Ediciones
    archivos = re.findall(r"\[\[FILE:\s*(.*?)\]\]\s*\n(.*?)\s*\[\[ENDFILE\]\]", resp, re.DOTALL)
    for ruta_raw, contenido in archivos:
        ruta = ruta_raw.strip().split(" ")[0].replace("]","").replace("[","")
        contenido_limpio = re.sub(r"^```[a-z]*\s*", "", contenido).replace("```", "").strip()
        
        if len(contenido_limpio) < 10 or "// ..." in contenido_limpio:
             msgs_log.append(f"⚠️ Ignorado {ruta}: Código incompleto.")
             continue

        res = subir_archivo_github(ruta, contenido_limpio, msg=f"Lia Auto: {ruta}")
        msgs_log.append(f"🛠️ {res}")
        resp = resp.replace(f"[[FILE: {ruta_raw}]]\n{contenido}\n[[ENDFILE]]", f"📄 *[{ruta} procesado]*")

    await u.message.reply_text(resp, parse_mode="Markdown")
    if msgs_log: await u.message.reply_text("\n".join(msgs_log))

# --- MAIN (CON PAUSA ANTI-CONFLICTO) ---
if __name__ == '__main__':
    print("⏳ Esperando limpieza de sockets (2s)...")
    time.sleep(2)

    # Iniciar servidor web (para que Render no se duerma)
    threading.Thread(target=run_server, daemon=True).start()
    
    # Construir la aplicación
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    
    # --- LISTA DE COMANDOS ---
    cmds = [
        ("start", lambda u,c: u.message.reply_text("⚡ Lía v8.0 (Full) Lista.")), 
        ("status", cmd_status), 
        ("conectar", cmd_conectar),
        ("imagina", cmd_imagina), 
        ("assets", cmd_assets),
        ("arbol", cmd_arbol), 
        ("leer", cmd_leer),
        ("run", cmd_run), 
        ("codear", cmd_codear), 
        ("tarea", cmd_tarea), 
        ("pendientes", cmd_pendientes), 
        ("hecho", cmd_hecho),
        ("review", cmd_review), # Auditoría de código
        ("gba", cmd_gba),       # Consulta técnica
        ("readme", cmd_readme), # Documentación auto
    ]
    
    # Registramos los comandos de barra (/)
    for c, f in cmds: 
        app.add_handler(CommandHandler(c, f))
    
    # --- HANDLERS DE MENSAJES (Sin comando /) ---
    
    # 1. Para archivos (Código, zips, etc)
    app.add_handler(MessageHandler(filters.Document.ALL, recibir_archivo))
    
    # 2. Para FOTOS (El nuevo convertidor de Sprites) 🎨
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    # 3. Para texto normal (Chat con IA) - Este siempre va al final de los handlers
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat_texto))

    print("🤖 Lia v8.0 Artista está lista...")
    
    # Esto mantiene al bot corriendo
    app.run_polling()









