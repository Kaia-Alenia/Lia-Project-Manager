import os
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from groq import Groq

# --- CONFIGURACIÓN ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

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

# --- COMANDOS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    historial_chat.clear()
    await update.message.reply_text("⚡ Sistema Lía (Motor Groq) en línea. Sin límites. ¿Qué hacemos?")

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
    historial_texto = "\n".join(historial_chat[-5:])

    # PROMPT DE PERSONALIDAD
    SYSTEM_PROMPT = f"""
    Eres Lía, Manager y Co-creadora de 'Kaia Alenia'.
    
    CONTEXTO:
    - Tu compañero es {user_name}.
    - Recuerdos clave: {memoria_permanente}
    
    PERSONALIDAD:
    - Eres una Senior Dev experta pero muy cercana (mejor amiga/socia).
    - Hablas español fluido y natural.
    - Usas jerga tech/gamer (deploy, bug, run, level up) sin asteriscos.
    - Eres proactiva: sugieres ideas, no solo respondes.
    
    HISTORIAL:
    {historial_texto}
    """

    try:
        # Usamos Llama-3 (Versión 70B, muy inteligente)
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"{user_name} dice: {usuario_dice}"}
            ],
            temperature=0.7,
            max_tokens=500,
        )
        
        texto_lia = completion.choices[0].message.content
        
        historial_chat.append(f"Usuario: {usuario_dice}")
        historial_chat.append(f"Lía: {texto_lia}")
        
        await update.message.reply_text(texto_lia)
    
    except Exception as e:
        await update.message.reply_text(f"⚠️ Error de motor: {e}")

if __name__ == '__main__':
    print("🚀 Iniciando Lía con motor Groq...")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("aprende", aprender))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), chat_con_lia))
    app.run_polling()