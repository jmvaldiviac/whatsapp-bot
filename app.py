import os
import requests
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Query
from fastapi.responses import PlainTextResponse, JSONResponse

# Carga .env
load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=True)

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "").strip()
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "").strip()
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID", "").strip()
SHEETS_WEBAPP_URL = os.getenv("SHEETS_WEBAPP_URL", "").strip()
ASISTENTE_NUMERO = os.getenv("ASISTENTE_NUMERO", "").strip()

app = FastAPI()

# Estados y datos en memoria
user_states = {}
user_data = {}

# ---------------- Helpers ----------------
def send_text(to: str, message: str):
    url = f"https://graph.facebook.com/v23.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message}
    }
    r = requests.post(url, headers=headers, json=payload, timeout=20)
    print("[SEND_TEXT]", r.status_code, r.text)

def send_contact(to: str, full_name: str, phone_e164: str):
    url = f"https://graph.facebook.com/v23.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "contacts",
        "contacts": [{
            "name": {"formatted_name": full_name, "first_name": full_name},
            "phones": [{"phone": f"+{phone_e164}", "type": "CELL"}]
        }]
    }
    r = requests.post(url, headers=headers, json=payload, timeout=20)
    print("[SEND_CONTACT]", r.status_code, r.text)

def send_to_sheets(data: dict):
    """Envía un JSON al WebApp de Apps Script con claves en minúsculas."""
    try:
        r = requests.post(SHEETS_WEBAPP_URL, json=data, timeout=20)
        print("[SHEETS]", r.status_code, r.text)
    except Exception as e:
        print("[SHEETS ERROR]", str(e))

def send_list_menu(to: str):
    """Envia menú inicial con List Messages"""
    url = f"https://graph.facebook.com/v23.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "list",
            "body": {"text": "¡Hola! Soy Loba 🐕 ¿Cómo te puedo ayudar?"},
            "footer": {"text": "Selecciona una opción"},
            "action": {
                "button": "Ver opciones",
                "sections": [{
                    "title": "Servicios",
                    "rows": [
                        {"id": "educacion", "title": "🐶 Educación Canina", "description": "Clases y modificación de conducta"},
                        {"id": "paseos", "title": "🚶 Paseos", "description": "Paseos educativos"},
                        {"id": "humano", "title": "👤 Hablar con humano", "description": "Derivar a asistente"}
                    ]
                }]
            }
        }
    }
    r = requests.post(url, headers=headers, json=payload, timeout=20)
    print("[SEND_LIST_MENU]", r.status_code, r.text)

# ---------------- Webhook ----------------
@app.get("/webhook")
def verify(hub_mode: str = Query("", alias="hub.mode"),
           hub_challenge: str = Query("", alias="hub.challenge"),
           hub_verify_token: str = Query("", alias="hub.verify_token")):
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        return PlainTextResponse(hub_challenge)
    return PlainTextResponse("Token inválido", status_code=403)

@app.post("/webhook")
async def receive(request: Request):
    body = await request.json()
    print("[POST webhook] body:", body)

    try:
        entry = body["entry"][0]["changes"][0]["value"]
        if "messages" in entry:
            msg = entry["messages"][0]
            from_number = msg["from"]
            text = msg.get("text", {}).get("body", "").strip()
            msg_type = msg["type"]

            # Si el mensaje viene de un menú interactivo (List Messages)
            if msg_type == "interactive":
                interactive = msg["interactive"]
                if interactive["type"] == "list_reply":
                    text = interactive["list_reply"]["id"]

            state = user_states.get(from_number, "menu")
            ud = user_data.get(from_number, {"numero": from_number})
            print(f"[STATE] {from_number}: {state}, msg: {text}")

            # -------- MENÚ PRINCIPAL --------
            if state == "menu":
                if text == "educacion":
                    ud.update({"servicio": "Educación Canina"})
                    user_data[from_number] = ud
                    send_text(from_number, "🐶 ¿Cómo se llama tu perrito?")
                    user_states[from_number] = "educacion_nombre"

                elif text == "paseos":
                    ud.update({"servicio": "Paseos"})
                    user_data[from_number] = ud
                    send_text(from_number, "🚶‍♂️ ¿Cómo se llama tu perrito?")
                    user_states[from_number] = "paseo_nombre"

                elif text == "humano":
                    ud.update({"servicio": "Derivación a humano"})
                    user_data[from_number] = ud
                    send_text(from_number, "🧑‍🤝‍🧑 Perfecto, te conecto con mi asistente.\nAntes, ¿cuál es tu *nombre*?")
                    user_states[from_number] = "humano_nombre"

                else:
                    send_list_menu(from_number)

            # -------- FLUJO EDUCACIÓN --------
            elif state == "educacion_nombre":
                ud["nombre_perro"] = text
                user_data[from_number] = ud
                send_text(from_number, "👌 ¿En qué comuna vives?")
                user_states[from_number] = "educacion_comuna"

            elif state == "educacion_comuna":
                ud["comuna"] = text
                user_data[from_number] = ud
                send_text(from_number, "📋 ¿Qué te gustaría trabajar con tu perrito?")
                user_states[from_number] = "educacion_detalle"

            elif state == "educacion_detalle":
                ud["detalle"] = text
                user_data[from_number] = ud
                # <-- Claves en minúsculas para Apps Script
                send_to_sheets({
                    "nombre": ud.get("nombre_cliente", ud.get("nombre_perro", "")),
                    "comuna": ud.get("comuna", ""),
                    "detalle": ud.get("detalle", ""),
                    "servicio": ud.get("servicio", "Educación Canina"),
                    "numero": ud.get("numero", "")
                })
                send_text(from_number, "🙌 ¡Gracias! He guardado tu información. Pronto te contactaremos.")
                user_states[from_number] = "menu"

            # -------- FLUJO PASEOS --------
            elif state == "paseo_nombre":
                ud["nombre_perro"] = text
                user_data[from_number] = ud
                send_text(from_number, "👌 ¿En qué comuna vives?")
                user_states[from_number] = "paseo_comuna"

            elif state == "paseo_comuna":
                ud["comuna"] = text
                user_data[from_number] = ud
                send_to_sheets({
                    "nombre": ud.get("nombre_cliente", ud.get("nombre_perro", "")),
                    "comuna": ud.get("comuna", ""),
                    "detalle": ud.get("detalle", ""),
                    "servicio": ud.get("servicio", "Paseos"),
                    "numero": ud.get("numero", "")
                })
                send_text(from_number, "🚀 ¡Gracias! He guardado tu información. Pronto te contactaremos.")
                user_states[from_number] = "menu"

            # -------- FLUJO HUMANO --------
            elif state == "humano_nombre":
                ud["nombre_cliente"] = text
                user_data[from_number] = ud
                send_text(from_number, "✍️ Gracias. Ahora cuéntame brevemente tu *motivo de consulta*.")
                user_states[from_number] = "humano_motivo"

            elif state == "humano_motivo":
                ud["motivo"] = text
                user_data[from_number] = ud
                send_to_sheets({
                    "nombre": ud.get("nombre_cliente", ud.get("nombre_perro", "")),
                    "comuna": ud.get("comuna", ""),
                    "detalle": ud.get("motivo", ""),
                    "servicio": ud.get("servicio", "Derivación a humano"),
                    "numero": ud.get("numero", "")
                })
                send_text(from_number, "✨ Gracias, te conecto con mi asistente. Te escribirá en breve.")
                aviso = (
                    "👤 *Nuevo cliente solicita humano*\n"
                    f"• Nombre: {ud.get('nombre_cliente', ud.get('nombre_perro',''))}\n"
                    f"• Número: +{from_number}\n"
                    f"• Motivo: {ud.get('motivo','')}\n"
                    f"🔗 Chat directo: https://wa.me/{from_number}"
                )
                if ASISTENTE_NUMERO:
                    send_text(ASISTENTE_NUMERO, aviso)
                    send_contact(ASISTENTE_NUMERO, ud.get("nombre_cliente", ud.get("nombre_perro","Cliente Loba")), from_number)
                user_states[from_number] = "menu"

            # -------- fallback --------
            else:
                send_list_menu(from_number)
                user_states[from_number] = "menu"

    except Exception as e:
        print("[ERROR]", str(e))

    return JSONResponse({"status": "ok"})
