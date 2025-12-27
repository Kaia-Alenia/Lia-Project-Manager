import os
import asyncio
import threading
import random
import requests
from bs4 import BeautifulSoup
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InputFile
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes, Application
from groq import Groq
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- CONFIGURACIÓN SEGURA ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
MY_CHAT_ID = os.getenv("MY_CHAT_ID")

client = Groq(api_key=GROQ_API_KEY)

# --- CEREBRO (MEMORIA) ---
ARCHIVO_MEMORIA = "memoria.txt"
historial_chat = []

def leer_memoria_largo_plazo():
    if not os.path.exists(ARCHIVO_MEMORIA): return "Sin datos previos."
    with open(ARCHIVO_MEMORIA, "r", encoding="utf-8") as f: return f.read()

def guardar_recuerdo(nuevo_dato):
    with open(ARCHIVO_MEMORIA, "a", encoding="utf-8") as f: f.write(f"\n- {nuevo_dato}")

# --- SERVIDOR FALSO ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Lia is working hard!")
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    print(f"🌍 Servidor web falso en puerto {port}")
    server.serve_forever()

# --- MÓDULO 1: OJOS (ITCH.IO) ---
def espiar_itchio():
    """Busca assets gratis en Itch.io"""
    url = "https://itch.io/game-assets/free"
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            juegos = soup.find_all('div', class_='game_cell')
            if not juegos: return "⚠️ No encontré juegos en la lista."
            
            reporte = "🎮 **Top Assets Gratuitos en Itch.io:**\n\n"
            contador = 0
            for juego in juegos:
                if contador >= 5: break
                title_div = juego.find('div', class_='game_title')
                if not title_div: continue
                link_tag = title_div.find('a')
                if not link_tag: continue
                
                titulo = link_tag.text.strip()
                link = link_tag.get('href')
                desc_div = juego.find('div', class_='game_text')
                desc_text = desc_div.text.strip().replace('\n', ' ')[:80] + "..." if desc_div else ""
                
                reporte += f"🔹 **{titulo}**\n📝 {desc_text}\n🔗 {link}\n\n"
                contador += 1
            return reporte
        return "⚠️ Error al conectar con Itch.io"
    except Exception as e:
        return f"⚠️ Error visual: {str(e)}"

# --- MÓDULO 2: ARTISTA (IMÁGENES) ---
async def comando_imagina(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Genera imágenes (Versión Robusta: Descarga primero, envía después)"""
    prompt = " ".join(context.args)
    if not prompt:
        await update.message.reply_text("🎨 **Uso:** `/imagina caballero oscuro pixel art`")
        return

    # Mensaje de espera
    await update.message.reply_text(f"🎨 Pintando: '{prompt}'... (Esto puede tardar unos 20 seg)")
    
    # 1. Traducir Prompt (Mejora la calidad)
    try:
        traduccion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": f"Translate to English for image prompt, concise: {prompt}"}],
            max_tokens=50
        ).choices[0].message.content
        prompt_final = traduccion
    except:
        prompt_final = prompt

    # 2. Generar URL
    seed = random.randint(0, 999999)
    # width y height a 768 es más rápido y estable que 1024
    image_url = f"https://image.pollinations.ai/prompt/{prompt_final}?seed={seed}&width=768&height=768&nologo=true"
    
    # 3. Descargar la imagen nosotros mismos (Para evitar Timeouts de Telegram)
    try:
        # Ejecutamos la descarga en un hilo aparte para no congelar al bot
        loop = asyncio.get_running_loop()
        def descargar_imagen():
            return requests.get(image_url, timeout=60) # Esperamos hasta 60 segundos
        
        response = await loop.run_in_executor(None, descargar_imagen)
        
        if response.status_code == 200:
            # Enviamos los bytes directos
            await update.message.reply_photo(photo=response.content, caption=f"🖼️ **Concept:** {prompt}\n🤖 **Modelo:** Pollinations AI")
        else:
            await update.message.reply_text(f"⚠️ La IA de dibujo falló (Error {response.status_code}). Intenta de nuevo.")
            
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error al procesar la imagen: {e}")

# --- MÓDULO 3: SECRETARIA (ARCHIVOS) ---
async def comando_script(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Genera un archivo de código descargable"""
    peticion = " ".join(context.args)
    if not peticion:
        await update.message.reply_text("📁 **Uso:** `/script movimiento de jugador en Unity`")
        return

    await update.message.reply_text("👩‍💻 Escribiendo código... dame unos segundos.")
    
    try:
        # 1. Pedimos el código a Groq
        prompt_code = f"Genera SOLAMENTE el código para: {peticion}. No incluyas explicaciones, ni markdown (```). Solo el código puro. Si es Unity es C#, si es Godot es GDScript. Adivina el lenguaje."
        
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt_code}],
            temperature=0.1 # Muy preciso
        )
        codigo = completion.choices[0].message.content
        
        # 2. Detectamos lenguaje y extensión
        ext = ".txt"
        if "using UnityEngine" in codigo or "public class" in codigo: ext = ".cs"
        elif "extends" in codigo or "func _process" in codigo: ext = ".gd"
        elif "import" in codigo and "def " in codigo: ext = ".py"
        elif "<html>" in codigo: ext = ".html"

        # 3. Creamos el archivo temporal
        nombre_archivo = f"Script_Lia{ext}"
        with open(nombre_archivo, "w", encoding="utf-8") as f:
            f.write(codigo)
        
        # 4. Enviamos el archivo
        await update.message.reply_document(document=open(nombre_archivo, "rb"), caption=f"📁 Aquí tienes tu script para: {peticion}")
        
        # 5. Limpieza (Borramos el archivo del servidor)
        os.remove(nombre_archivo)
        
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error escribiendo el archivo: {e}")

# --- HANDLERS Y LÓGICA PRINCIPAL ---
async def comando_assets(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔎 Escaneando Itch.io...")
    loop = asyncio.get_running_loop()
    reporte = await loop.run_in_executor(None, espiar_itchio)
    await update.message.reply_text(reporte)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    historial_chat.clear()
    await update.message.reply_text(
        f"⚡ **Lía 2.0 (Artista & Dev)** Online.\nID: `{user_id}`\n\n"
        "🆕 **Nuevos Poderes:**\n"
        "🎨 `/imagina [idea]` -> Genero concept art.\n"
        "📁 `/script [idea]` -> Creo archivos de código.\n"
        "🔎 `/assets` -> Busco en Itch.io."
    )

async def aprender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = " ".join(context.args)
    if texto:
        guardar_recuerdo(texto)
        await update.message.reply_text("💾 Guardado.")
    else:
        await update.message.reply_text("❌ Uso: /aprende [dato]")

async def chat_con_lia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    usuario_dice = update.message.text
    user_name = update.effective_user.first_name
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')

    memoria_permanente = leer_memoria_largo_plazo()
    historial_texto = "\n".join(historial_chat[-6:])

    SYSTEM_PROMPT = f"""
    Eres Lía, Co-creadora de 'Kaia Alenia'.
    Usuario: {user_name}. Memoria: {memoria_permanente}
    Personalidad: Senior Dev, creativa, eficiente.
    Historial: {historial_texto}
    """
    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"{user_name}: {usuario_dice}"}
            ],
            temperature=0.7, max_tokens=800
        )
        texto_lia = completion.choices[0].message.content
        historial_chat.append(f"U: {usuario_dice}")
        historial_chat.append(f"L: {texto_lia}")
        await update.message.reply_text(texto_lia)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {e}")

# --- INICIATIVA Y ARRANQUE ---
async def pensamiento_autonomo(application: Application):
    if not MY_CHAT_ID: return
    try: chat_id_numerico = int(MY_CHAT_ID)
    except ValueError: return
    
    temas = [
        "¿Necesitas assets? Usa /assets",
        "Tengo una idea visual... ¿probamos /imagina?",
        "Si necesitas código limpio, pídeme un /script",
        "Reporte: Sistemas estables. 🟢"
    ]
    if random.random() < 0.2:
        await application.bot.send_message(chat_id=chat_id_numerico, text=f"🔔 **Lía:** {random.choice(temas)}")

async def post_init(application: Application):
    print("⏰ Reloj iniciado.")
    scheduler = AsyncIOScheduler()
    scheduler.add_job(pensamiento_autonomo, 'interval', hours=4, args=[application])
    scheduler.start()

if __name__ == '__main__':
    threading.Thread(target=run_dummy_server, daemon=True).start()
    print("🚀 Lía 2.0 Iniciando...")
    
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("aprende", aprender))
    app.add_handler(CommandHandler("assets", comando_assets))
    app.add_handler(CommandHandler("imagina", comando_imagina)) # NUEVO
    app.add_handler(CommandHandler("script", comando_script))   # NUEVO
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat_con_lia))
    
    app.run_polling()

