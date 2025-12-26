import os
import asyncio
import threading
import random
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- CONFIGURACIÓN SEGURA ---
# Las claves se toman de las Variables de Entorno de Render
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
MY_CHAT_ID = os.getenv("MY_CHAT_ID") # Tu ID numérico para que te escriba sola

# Cliente Groq
client = Groq(api_key=GROQ_API_KEY)

# --- CEREBRO (MEMORIA) ---
ARCHIVO_MEMORIA = "memoria.txt"
historial_chat = []

def leer_memoria_largo_plazo():
    if not os.path.exists(ARCHIVO_MEMORIA): return "Sin datos previos."
    with open(ARCHIVO_MEMORIA, "r", encoding="utf-8") as f: return f.read()

def guardar_recuerdo(nuevo_dato):
    with open(ARCHIVO_MEMORIA, "a", encoding="utf-8") as f: f.write(f"\n- {nuevo_dato}")

# --- SERVIDOR FALSO (Para engañar a Render y que no se apague) ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Lia is alive and watching!")

def run_dummy_server():
    # Render asigna un puerto dinámico, o usamos 8080 por defecto
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    print(f"🌍 Servidor web falso escuchando en el puerto {port}")
    server.serve_forever()

# --- FUNCIONES DE INICIATIVA PROPIA (AUTONOMÍA) ---
async def pensamiento_autonomo(app):
    """Lía 'despierta' periódicamente y decide si mandarte un mensaje."""
    if not MY_CHAT_ID:
        print("⚠️ Lía quiere hablar sola pero no tiene configurado el MY_CHAT_ID en Render.")
        return

    try:
        chat_id_numerico = int(MY_CHAT_ID)
    except ValueError:
        print("⚠️ Error: MY_CHAT_ID no es un número válido.")
        return

    # Temas aleatorios para simular "vida" (Más adelante conectaremos esto a APIs reales)
    temas = [
        "Revisé itch.io y vi que los assets de 'Pixel Horror' están en tendencia. ¿Los checamos?",
        "Recordatorio: No hemos actualizado el GDD de Kaia Alenia esta semana.",
        "Reporte rápido: Todo estable en el servidor. 🟢",
        "¡Hora de código! ¿Le damos 30 mins a ese script pendiente?",
        "Estaba pensando... ¿y si añadimos un sistema de crafting simple al juego?",
        "He revisado las tendencias de Steam, los roguelikes siguen fuertes."
    ]
    
    # 20% de probabilidad de hablar para no ser spam (puedes ajustar esto)
    if random.random() < 0.2: # O quita el if para que hable siempre que toque el turno
        mensaje_spontaneo = random.choice(temas)
        await app.bot.send_message(chat_id=chat_id_numerico, text=f"🔔 **Iniciativa Lía:**\n{mensaje_spontaneo}")

# --- COMANDOS DEL BOT ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    historial_chat.clear()
    await update.message.reply_text(f"⚡ **Lía (Motor Groq)** en línea.\n\nTu ID de chat es: `{user_id}`\n(Copia este número y ponlo en las variables de Render como MY_CHAT_ID si quieres que tome iniciativa).")

async def aprender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = " ".join(context.args)
    if texto:
        guardar_recuerdo(texto)
        await update.message.reply_text(f"💾 Dato guardado en memoria: '{texto}'")
    else:
        await update.message.reply_text("❌ Uso: /aprende [dato importante]")

async def chat_con_lia(update: Update, context: ContextTypes.DEFAULT_TYPE):
    usuario_dice = update.message.text
    user_name = update.effective_user.first_name
    
    # Indicador de "Escribiendo..."
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')

    memoria_permanente = leer_memoria_largo_plazo()
    # Mantenemos solo los últimos 10 mensajes en memoria inmediata
    historial_texto = "\n".join(historial_chat[-10:])

    # PROMPT DE PERSONALIDAD (Aquí defines quién es ella)
    SYSTEM_PROMPT = f"""
    Eres Lía, Manager Senior y Co-creadora de 'Kaia Alenia'.
    
    CONTEXTO:
    - Tu compañero es {user_name} (CEO/Dev).
    - Somos un estudio indie de videojuegos.
    - Recuerdos clave: {memoria_permanente}
    
    PERSONALIDAD:
    - Eres una Senior Dev experta, pragmática pero divertida.
    - Hablas español natural y fluido.
    - Usas jerga tech/gamer (deploy, bug, run, push) sin asteriscos excesivos.
    - Eres proactiva: sugieres soluciones técnicas y mecánicas de juego.
    
    HISTORIAL RECIENTE:
    {historial_texto}
    """

    try:
        # Llamada a Groq (Usando Llama 3.3 Versatile)
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"{user_name} dice: {usuario_dice}"}
            ],
            temperature=0.7,
            max_tokens=800, # Respuesta un poco más larga permitida
        )
        
        texto_lia = completion.choices[0].message.content
        
        # Guardamos en historial RAM
        historial_chat.append(f"Usuario: {usuario_dice}")
        historial_chat.append(f"Lía: {texto_lia}")
        
        await update.message.reply_text(texto_lia)
    
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error en mi cerebro: {e}")

# --- MAIN ---
if __name__ == '__main__':
    # 1. Arrancar el servidor falso en un hilo separado
    threading.Thread(target=run_dummy_server, daemon=True).start()
    
    print("🚀 Iniciando Sistema Lía...")
    
    # 2. Configurar Bot
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # 3. Configurar Scheduler (El Reloj para iniciativa)
    scheduler = AsyncIOScheduler()
    # Configurado para revisar cada 4 horas si quiere hablarte
    scheduler.add_job(pensamiento_autonomo, 'interval', hours=4, args=[app])
    scheduler.start()
    
    # 4. Añadir manejadores
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("aprende", aprender)) # Comando abreviado
    app.add_handler(CommandHandler("aprender", aprender))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat_con_lia))
    
    # 5. Ejecutar
    app.run_polling()
