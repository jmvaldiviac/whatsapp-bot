import os
import re
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

# Lista de comunas válidas de Santiago (ejemplo, amplía si quieres todas)
COMUNAS_SANTIAGO = {
    "providencia", "las condes", "la florida", "ñuñoa", "santiago centro",
    "puente alto", "maipú", "peñalolén", "vitacura", "macul"
}

# Regex validación de nombres (perros y clientes)
NOMBRE_REGEX = re.compile(r"^[A-Za-zÁÉÍÓÚáéíóúÑñ ]+$")

def validar_nombre(s: str) -> bool:
    return bool(NOMBRE_REGEX.match(s.strip()))

# --- Helpers ---
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

def send_main_menu(to: str):
    """Muestra el menú principal como lista interactiva con descripciones y emojis"""
    url = f"https://graph.facebook.com/v17.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": "¡Hola! Soy Loba 🐶 ¿cómo te ayudo hoy?"},
            "footer": {"text": "Selecciona una opción 👇"},
            "action": {
                "button": "Elige una opción",
                "sections": [
                    {
                        "title": "Servicios",
                        "rows": [
                            {
                                "id": "educacion",
                                "title": "Educación canina",
                                "description": "🐾 Entrenamiento y modificación de conducta"
                            },
                            {
                                "id": "paseos",
                                "title": "Paseos",
                                "description": "🚶 Paseos educativos y recreativos"
                            },
                            {
                                "id": "humano",
                                "title": "Hablar con humano",
                                "description": "🧑‍💼 Derivación directa a asistente"
                            }
                        ]
                    }
                ]
            }
        }
    }
    r = requests.post(url, headers=headers, json=payload, timeout=20)
    print("[SEND_MENU]", r.status_code, r.text)

def send_to_sheets(data: dict):
    try:
        r = requests.post(SHEETS_WEBAPP_URL, json=data, timeout=10)
        print("[SHEETS] response:", r.status_code, r.text)
    except Exception as e:
        print("[SHEETS ERROR]", e)

# --- Endpoints ---
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

                # Si viene de un botón/selección de lista
                if message.get("type") == "interactive":
                    text = message["interactive"]["list_reply"]["id"]
                else:
                    text = message.get("text", {}).get("body", "").strip().lower()

                state = user_states.get(from_number, "menu")
                ud = user_data.get(from_number, {})

                print(f"[STATE={state}] From {from_number}: {text}")

                # --- Menú principal ---
                if state == "menu":
                    if text == "educacion":
                        user_states[from_number] = "educacion_nombre"
                        user_data[from_number] = {}
                        send_text(from_number, "🐾 ¿Cómo se llama tu perrito?")
                    elif text == "paseos":
                        user_states[from_number] = "paseo_nombre"
                        user_data[from_number] = {}
                        send_text(from_number, "🐕 ¿Cómo se llama tu perrito?")
                    elif text == "humano":
                        user_states[from_number] = "humano_nombre"
                        user_data[from_number] = {}
                        send_text(from_number, "👤 ¿Cuál es tu nombre?")
                    else:
                        send_main_menu(from_number)

                # --- Educación Canina ---
                elif state == "educacion_nombre":
                    if not validar_nombre(text):
                        send_text(from_number, "🤔 El nombre debería tener solo letras (puede incluir tildes y espacios). Inténtalo de nuevo 🐾.")
                        return JSONResponse({"status": "ok"})
                    ud["nombre_perro"] = text
                    user_data[from_number] = ud
                    send_text(from_number, "📍 ¿En qué comuna vives?")
                    user_states[from_number] = "educacion_comuna"

                elif state == "educacion_comuna":
                    if text.lower() not in COMUNAS_SANTIAGO:
                        send_text(from_number, "📍 Esa comuna no la reconozco en Santiago. Por favor escribe otra 🙏.")
                        return JSONResponse({"status": "ok"})
                    ud["comuna"] = text
                    user_data[from_number] = ud
                    send_text(from_number, "📋 ¿Qué te gustaría trabajar con tu perrito?")
                    user_states[from_number] = "educacion_detalle"

                elif state == "educacion_detalle":
                    if len(text) < 5:
                        send_text(from_number, "📝 Por favor dame un poco más de detalle (mínimo 5 caracteres).")
                        return JSONResponse({"status": "ok"})
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
                    if not validar_nombre(text):
                        send_text(from_number, "🤔 El nombre debería tener solo letras (puede incluir tildes y espacios). Inténtalo de nuevo 🐕.")
                        return JSONResponse({"status": "ok"})
                    ud["nombre_perro"] = text
                    user_data[from_number] = ud
                    send_text(from_number, "📍 ¿En qué comuna vives?")
                    user_states[from_number] = "paseo_comuna"

                elif state == "paseo_comuna":
                    if text.lower() not in COMUNAS_SANTIAGO:
                        send_text(from_number, "📍 Esa comuna no la reconozco en Santiago. Por favor escribe otra 🙏.")
                        return JSONResponse({"status": "ok"})
                    ud["comuna"] = text
                    user_data[from_number] = ud
                    send_to_sheets({
                        "nombre": ud.get("nombre_perro", ""),
                        "comuna": ud.get("comuna", ""),
                        "detalle": "",  # vacío para paseos
                        "servicio": "Paseos",
                        "numero": from_number
                    })
                    send_text(from_number, "✅ Gracias, tu información fue registrada para Paseos 🐕.")
                    user_states[from_number] = "menu"

                # --- Hablar con humano ---
                elif state == "humano_nombre":
                    if not validar_nombre(text):
                        send_text(from_number, "👤 El nombre debería tener solo letras (puede incluir tildes y espacios). Intenta nuevamente.")
                        return JSONResponse({"status": "ok"})
                    ud["nombre_cliente"] = text
                    user_data[from_number] = ud
                    send_text(from_number, "📋 ¿Cuál es el motivo de tu consulta?")
                    user_states[from_number] = "humano_motivo"

                elif state == "humano_motivo":
                    if len(text) < 5:
                        send_text(from_number, "📝 Por favor dime un poco más de tu consulta (mínimo 5 caracteres).")
                        return JSONResponse({"status": "ok"})
                    ud["motivo"] = text
                    user_data[from_number] = ud
                    send_to_sheets({
                        "nombre": ud.get("nombre_cliente", ""),
                        "comuna": "",
                        "detalle": ud.get("motivo", ""),
                        "servicio": "Derivado a humano",
                        "numero": from_number
                    })
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
