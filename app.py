import os, requests
from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
from dotenv import load_dotenv

load_dotenv()

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
WA_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID")

app = FastAPI()

# --- Utilidad para enviar mensajes ---
def send_text(to: str, body: str):
    url = f"https://graph.facebook.com/v22.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WA_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body}
    }
    r = requests.post(url, headers=headers, json=payload, timeout=15)
    return r.status_code, r.text

def menu():
    return (
        "¡Hola! Soy el asistente virtual Loba 🐶, ¿cómo te puedo ayudar?\n\n"
        "1️⃣ Servicios de educación canina\n"
        "2️⃣ Servicios de educación para paseo\n"
        "3️⃣ Hablar con un humano\n\n"
        "Responde con 1, 2 o 3."
    )

# --- VERIFY TOKEN ---
@app.get("/webhook")
def verify(hub_mode: str = "", hub_challenge: str = "", hub_verify_token: str = ""):
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        return PlainTextResponse(hub_challenge)
    return PlainTextResponse("Token inválido", status_code=403)

# --- RECEIVE MESSAGES ---
@app.post("/webhook")
async def webhook(request: Request):
    body = await request.json()
    try:
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                messages = value.get("messages", [])
                if not messages:
                    continue

                msg = messages[0]
                wa_id = msg.get("from")
                text = msg.get("text", {}).get("body", "").strip()

                if text in ("1", "2", "3"):
                    if text == "1":
                        send_text(wa_id, "Genial 🐕 ¿Cómo se llama tu perrito?")
                    elif text == "2":
                        send_text(wa_id, "Perfecto 🚶‍♂️ ¿Cómo se llama tu perrito?")
                    else:
                        send_text(wa_id, "Te conecto con mi humana asistente ✨.")
                else:
                    send_text(wa_id, menu())
    except Exception as e:
        print("Error webhook:", e)

    return {"status": "ok"}

# --- endpoint opcional para disparar el menú ---
@app.get("/send")
def send_menu(to: str):
    code, resp = send_text(to, menu())
    return {"status_code": code, "response": resp}
