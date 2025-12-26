import os
import asyncio
import threading
import random
import requests
from bs4 import BeautifulSoup
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
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
        self.wfile.write(b"Lia is alive and watching!")
    
    # Esto evita el error de "Unsupported method HEAD" que viste en los logs
    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    print(f"🌍 Servidor web falso escuchando en el puerto {port}")
    server.serve_forever()

# --- INICIATIVA PROPIA ---
async def pensamiento_autonomo(application: Application):
    """Lía 'despierta' y decide mandarte algo útil."""
    if not MY_CHAT_ID:
        print("⚠️ No hay MY_CHAT_ID configurado.")
        return

    try:
        chat_id_numerico = int(MY_CHAT_ID)
    except ValueError:
        return

    temas = [
        "Revisé itch.io y vi que los assets de 'Pixel Horror' están en tendencia. ¿Los checamos?",
        "Recordatorio: No hemos actualizado el GDD de Kaia Alenia esta semana.",
        "Reporte rápido: Todo estable en el servidor. 🟢",
        "¡Hora de código! ¿Le damos 30 mins a ese script pendiente?",
        "He detectado un pico de interés en juegos Metroidvania en Reddit.",
        "¿Y si probamos una paleta de colores nueva para el UI?"
    ]
    
    # Probabilidad del 20% de hablar (o quita el if para testear)
    if random.random() < 0.2:
        mensaje = random.choice(temas)
        await application.bot.send_message(chat_id=chat_id_numerico, text=f"🔔 **Iniciativa Lía:**\n{mensaje}")

# --- ### NUEVO: FUNCIÓN DE ARRANQUE SEGURO ### ---
async def post_init(application: Application):
    """Esta función corre DESPUÉS de que el bot ya tiene su loop listo."""
    print("⏰ Iniciando reloj interno de Lía (Scheduler)...")
    
    scheduler = AsyncIOScheduler()
    # Pasamos 'application' como argumento para que la función pueda enviar mensajes
    scheduler.add_job(pensamiento_autonomo, 'interval', hours=4, args=[application])
    scheduler.start()
    print("✅ Reloj iniciado con éxito.")
# --- MÓDULO DE VISIÓN (OJOS) BLINDADO ---
def espiar_itchio():
    """Lía entra a Itch.io, ignorando errores de estructura."""
    url = "https://itch.io/game-assets/free"
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            juegos = soup.find_all('div', class_='game_cell')
            
            if not juegos:
                return "⚠️ Entré a Itch.io pero no encontré la lista de juegos. Quizás cambiaron su diseño."

            reporte = "🎮 **Top Assets Gratuitos en Itch.io (Tiempo Real):**\n\n"
            contador = 0
            
            for juego in juegos:
                if contador >= 5: break
                
                # --- ZONA SEGURA ---
                # 1. Buscamos el contenedor del título primero
                title_div = juego.find('div', class_='game_title')
                if not title_div: continue # Si no tiene título, es basura/anuncio. Saltamos.
                
                # 2. Buscamos el link DENTRO del título
                link_tag = title_div.find('a')
                if not link_tag: continue # Si no tiene link, saltamos.
                
                # 3. Extraemos datos de forma segura
                titulo = link_tag.text.strip()
                link = link_tag.get('href') # .get() es más seguro que ['href']
                
                # 4. Descripción (Opcional)
                desc_div = juego.find('div', class_='game_text')
                # Limpiamos el texto para que no sea kilométrico
                desc_text = desc_div.text.strip().replace('\n', ' ')[:100] + "..." if desc_div else "Sin descripción"
                
                reporte += f"🔹 **{titulo}**\n📝 {desc_text}\n🔗 {link}\n\n"
                contador += 1
                # -------------------
            
            return reporte
        else:
            return f"⚠️ Itch.io me rechazó la conexión (Status: {response.status_code})"
    except Exception as e:
        return f"⚠️ Error visual grave: {str(e)}"
    
# --- COMANDOS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    historial_chat.clear()
    await update.message.reply_text(f"⚡ **Lía (Motor Groq)** en línea.\nID de chat: `{user_id}`")

async def aprender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = " ".join(context.args)
    if texto:
        guardar_recuerdo(texto)
        await update.message.reply_text(f"💾 Dato guardado: '{texto}'")
    else:
        await update.message.reply_text("❌ Uso: /aprende [dato]")

async def chat_con_lia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    usuario_dice = update.message.text
    user_name = update.effective_user.first_name
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')

    memoria_permanente = leer_memoria_largo_plazo()
    historial_texto = "\n".join(historial_chat[-10:])

    SYSTEM_PROMPT = f"""
    Eres Lía, Manager Senior y Co-creadora de 'Kaia Alenia'.
    Usuario: {user_name}.
    Memoria: {memoria_permanente}
    Personalidad: Senior Dev experta, divertida, jerga tech, proactiva.
    Historial:
    {historial_texto}
    """

    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"{user_name} dice: {usuario_dice}"}
            ],
            temperature=0.7,
            max_tokens=800,
        )
        texto_lia = completion.choices[0].message.content
        historial_chat.append(f"U: {usuario_dice}")
        historial_chat.append(f"L: {texto_lia}")
        await update.message.reply_text(texto_lia)
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error: {e}")

# --- MAIN ---
if __name__ == '__main__':
    # 1. Servidor Falso
    threading.Thread(target=run_dummy_server, daemon=True).start()
    
    print("🚀 Iniciando configuración del bot...")
    
    # 2. Construimos el bot CON el gancho post_init
    # Aquí es donde ocurre la magia: .post_init(post_init)
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("aprende", aprender))
    app.add_handler(CommandHandler("aprender", aprender))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat_con_lia))
    app.add_handler(CommandHandler("assets", comando_assets))
    # 3. Arrancamos
    app.run_polling()


