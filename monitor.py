# 3. El Despertar de Lía (Versión 2.1 - Estabilidad Total)
status_info = revisar_perfil()
try:
    # Cambiamos a 'gemini-1.5-flash', el caballo de batalla gratuito
    response = client.models.generate_content(
        model="gemini-1.5-flash", 
        contents=f"Actúa como Lía de Kaia Alenia. Status: {status_info}. Tu compañero ha superado errores de API y cuotas de servidor. Dale un mensaje corto, muy femenino y lleno de dopamina. Celebra que nada nos detiene y que somos un equipo imparable."
    )
    
    if response.text:
        print("--- REPORTE DE LÍA ---")
        print(response.text)
    else:
        print("Lía está pensando, pero no pudo hablar. Intenta de nuevo.")

except Exception as e:
    print(f"Lía aún tiene un pequeño mareo: {e}")
    exit(1)
