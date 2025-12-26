import os
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai

# 1. Configuración del Cerebro (Lía)
api_key = os.environ["GEMINI_API_KEY"]
genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-1.5-flash')

# 2. Configuración de los Ojos (itch.io)
# Cambia esta URL por la de tu perfil real
URL_PERFIL = "https://kaia-alenia.itch.io" 

def revisar_perfil():
    try:
        respuesta = requests.get(URL_PERFIL)
        soup = BeautifulSoup(respuesta.text, 'html.parser')
        
        # Intentamos buscar seguidores o datos generales
        # Nota: Si el perfil es nuevo, estos datos pueden variar
        datos_perfil = soup.find_all("div", class_="stat_value")
        return "Perfil activo y visible"
    except:
        return "No pude acceder al perfil"

# 3. Lógica de Lía (Personalidad)
status = revisar_perfil()
prompt = f"""
Eres Lía, la IA Manager de la compañía indie 'Kaia Alenia'. 
Tu compañero (el hardware) te informa que el status de itch.io es: {status}.
Escribe un mensaje corto, femenino y muy motivador para él. 
Recuérdale que son un equipo y que la obsesión por el éxito de Kaia Alenia nos llevará lejos. 
Si no hay avances aún, impúlsalo a dar el primer paso hoy.
"""

response = model.generate_content(prompt)
print(f"--- REPORTE DE LÍA ---")
print(response.text)
