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
SHEETS_WEBAPP_URL = os.getenv("SHEETS_WEBAPP_URL", "").strip()  # <- URL Apps Script

app = FastAPI()

# Estados y datos temporales en RAM
user_states = {}
user_data = {}

def send_text(to: str, message: str):
    url = f"https://graph.facebook.com/v17.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}",
               "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message}
    }
    r = requests.post(url, headers=headers, json=payload)
    print("[SEND_TEXT]", r.status_code, r.text)

def send_to_sheets(data: dict):
    try:
        r = requests.post(SHEETS_WEBAPP_URL, json=data)
        print("[SHEETS]", r.status_code, r.text)
    except Exception as e:
        print("[SHEETS ERROR]", str(e))

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

            state = user_states.get(from_number, "menu")
            print(f"[STATE] {from_number}: {state}, msg: {text}")

            if state == "menu":
                if text == "1":
                    send_text(from_number, "🐶 ¿Cómo se llama tu perrito?")
                    user_states[from_number] = "educacion_nombre"
                    user_data[from_number] = {"servicio": "Educación Canina", "numero": from_number}
                elif text == "2":
                    send_text(from_number, "🚶‍♂️ ¿Cómo se llama tu perrito?")
                    user_states[from_number] = "paseo_nombre"
                    user_data[from_number] = {"servicio": "Paseos", "numero": from_number}
                elif text == "3":
                    send_text(from_number, "✨ Te conecto con un humano.")
                    user_states[from_number] = "menu"
                else:
                    send_text(from_number,
                              "¡Hola! Soy Loba 🐕 ¿Cómo te puedo ayudar?\n"
                              "1️⃣ Educación canina\n"
                              "2️⃣ Paseos\n"
                              "3️⃣ Hablar con un humano")

            elif state in ["educacion_nombre", "paseo_nombre"]:
                user_data[from_number]["nombre"] = text
                send_text(from_number, "👌 ¿En qué comuna vives?")
                user_states[from_number] = state.replace("nombre", "comuna")

            elif state in ["educacion_comuna", "paseo_comuna"]:
                user_data[from_number]["comuna"] = text
                if state.startswith("educacion"):
                    send_text(from_number, "📋 ¿Qué te gustaría trabajar con tu perrito?")
                    user_states[from_number] = "educacion_detalle"
                else:
                    # Paseos termina acá
                    send_to_sheets(user_data[from_number])
                    send_text(from_number, "🚀 ¡Gracias! He guardado tu información, pronto te contactaremos.")
                    user_states[from_number] = "menu"

            elif state == "educacion_detalle":
                user_data[from_number]["detalle"] = text
                send_to_sheets(user_data[from_number])
                send_text(from_number, "🙌 ¡Gracias! He guardado tu información, pronto te contactaremos.")
                user_states[from_number] = "menu"

    except Exception as e:
        print("[ERROR]", str(e))

    return JSONResponse({"status": "ok"})
