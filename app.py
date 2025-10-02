import os
import requests
from fastapi import FastAPI, Request, Query
from fastapi.responses import PlainTextResponse, JSONResponse
from dotenv import load_dotenv
from pathlib import Path

# Cargar variables de entorno
load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=True)

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "").strip()
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "").strip()
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID", "").strip()
SHEETS_WEBAPP_URL = os.getenv("SHEETS_WEBAPP_URL", "").strip()
ASISTENTE_NUMERO = os.getenv("ASISTENTE_NUMERO", "").strip()

app = FastAPI()

# Estados de conversación
user_states = {}
user_data = {}

# Enviar mensaje de texto
def send_text(to: str, text: str):
    url = f"https://graph.facebook.com/v17.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text}
    }
    r = requests.post(url, headers=headers, json=payload)
    print("[SEND_TEXT] response:", r.status_code, r.text)

# Guardar en Google Sheets
def send_to_sheets(data: dict):
    try:
        r = requests.post(SHEETS_WEBAPP_URL, json=data, timeout=10)
        print("[SHEETS] response:", r.status_code, r.text)
    except Exception as e:
        print("[SHEETS ERROR]", e)

# --- Rutas ---
@app.get("/debug")
def debug():
    return {"verify_token_server": VERIFY_TOKEN}

@app.get("/webhook")
def verify(
    hub_mode: str = Query("", alias="hub.mode"),
    hub_challenge: str = Query("", alias="hub.challenge"),
    hub_verify_token: str = Query("", alias="hub.verify_token")
):
    if hub_mode == "subscribe" and hub_verify_token.strip() == VERIFY_TOKEN:
        return PlainTextResponse(hub_challenge)
    return PlainTextResponse("Token inválido", status_code=403)

@app.post("/webhook")
async def receive(request: Request):
    body = await request.json()
    print("[POST webhook] body:", body)

    if "entry" not in body: 
        return {"status": "ignored"}

    for entry in body["entry"]:
        changes = entry.get("changes", [])
        for change in changes:
            value = change.get("value", {})
            messages = value.get("messages", [])
            for message in messages:
                from_number = message["from"]
                text = message.get("text", {}).get("body", "").strip().lower()
                state = user_states.get(from_number, "menu")
                ud = user_data.get(from_number, {})

                print(f"[STATE={state}] From {from_number}: {text}")

                # --- Menú principal ---
                if state == "menu":
                    if text in ["1", "educacion", "educación"]:
                        user_states[from_number] = "educacion_nombre"
                        user_data[from_number] = {}  # limpiar
                        send_text(from_number, "🐾 ¿Cómo se llama tu perrito?")
                    elif text in ["2", "paseos", "paseo"]:
                        user_states[from_number] = "paseo_nombre"
                        user_data[from_number] = {}  # limpiar
                        send_text(from_number, "🐕 ¿Cómo se llama tu perrito?")
                    elif text in ["3", "humano", "asistente"]:
                        user_states[from_number] = "humano_nombre"
                        user_data[from_number] = {}  # limpiar
                        send_text(from_number, "👤 ¿Cuál es tu nombre?")
                    else:
                        send_text(from_number,
                            "¡Hola! Soy Loba 🐶, ¿cómo te ayudo?\n"
                            "1️⃣ Educación canina\n"
                            "2️⃣ Paseos\n"
                            "3️⃣ Hablar con humano"
                        )

                # --- Educación ---
                elif state == "educacion_nombre":
                    ud["nombre_perro"] = text
                    user_data[from_number] = ud
                    send_text(from_number, "📍 ¿En qué comuna vives?")
                    user_states[from_number] = "educacion_comuna"

                elif state == "educacion_comuna":
                    ud["comuna"] = text
                    user_data[from_number] = ud
                    send_text(from_number, "📋 ¿Qué te gustaría trabajar con tu perrito?")
                    user_states[from_number] = "educacion_detalle"

                elif state == "educacion_detalle":
                    ud["detalle"] = text
                    user_data[from_number] = ud
                    send_to_sheets({
                        "nombre": ud.get("nombre_perro", ""),
                        "comuna": ud.get("comuna", ""),
                        "detalle": ud.get("detalle", ""),
                        "servicio": "Educación Canina",
                        "numero": from_number
                    })
                    send_text(from_number, "✅ Gracias, tu información fue registrada para Educación Canina 🐾.")
                    user_states[from_number] = "menu"

                # --- Paseos ---
                elif state == "paseo_nombre":
                    ud["nombre_perro"] = text
                    user_data[from_number] = ud
                    send_text(from_number, "📍 ¿En qué comuna vives?")
                    user_states[from_number] = "paseo_comuna"

                elif state == "paseo_comuna":
                    ud["comuna"] = text
                    user_data[from_number] = ud
                    send_to_sheets({
                        "nombre": ud.get("nombre_perro", ""),
                        "comuna": ud.get("comuna", ""),
                        "detalle": "",  # vacío
                        "servicio": "Paseos",
                        "numero": from_number
                    })
                    send_text(from_number, "✅ Gracias, tu información fue registrada para Paseos 🐕.")
                    user_states[from_number] = "menu"

                # --- Hablar con humano ---
                elif state == "humano_nombre":
                    ud["nombre_cliente"] = text
                    user_data[from_number] = ud
                    send_text(from_number, "📋 ¿Cuál es el motivo de tu consulta?")
                    user_states[from_number] = "humano_motivo"

                elif state == "humano_motivo":
                    ud["motivo"] = text
                    user_data[from_number] = ud
                    # Notificar a Sheets
                    send_to_sheets({
                        "nombre": ud.get("nombre_cliente", ""),
                        "comuna": "",
                        "detalle": ud.get("motivo", ""),
                        "servicio": "Derivado a humano",
                        "numero": from_number
                    })
                    # Notificar al asistente
                    if ASISTENTE_NUMERO:
                        send_text(
                            ASISTENTE_NUMERO,
                            f"📩 Nuevo cliente quiere hablar contigo:\n"
                            f"👤 Nombre: {ud.get('nombre_cliente','')}\n"
                            f"📱 Número: {from_number}\n"
                            f"📝 Motivo: {ud.get('motivo','')}"
                        )
                    send_text(from_number, "🙋 Te estoy derivando con mi asistente, en breve te contactará.")
                    user_states[from_number] = "menu"

    return JSONResponse({"status": "ok"})
