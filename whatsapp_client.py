import os
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
import requests
from dotenv import load_dotenv

load_dotenv()

def _get_credentials():
    load_dotenv(override=True)
    token = os.getenv("WHATSAPP_ACCESS_TOKEN", "").strip()
    pid = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()
    return token, pid


def send_whatsapp_message(to: str, text: str) -> bool:
    """
    Sends a text message to a WhatsApp user using the WhatsApp Cloud API.
    If credentials are not configured, falls back to local logging (mock mode).
    """
    token, phone_number_id = _get_credentials()
    # Check if Cloud API credentials are configured
    if not token or not phone_number_id:
        print("\n----------------------------------------")
        print(f"[WHATSAPP SIMULATED OUTGOING MESSAGE]")
        print(f"To: {to}")
        print(f"Message:\n{text}")
        print("----------------------------------------\n")
        return True

    url = f"https://graph.facebook.com/v22.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {
            "body": text
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code in [200, 201]:
            print(f"[WHATSAPP] Successfully sent message to {to}")
            return True
        else:
            print(f"[WHATSAPP ERROR] Failed to send message: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"[WHATSAPP EXCEPTION] Error sending message: {e}")
        return False


def send_whatsapp_button_message(to: str, body_text: str, buttons: list) -> bool:
    """
    Sends an interactive button message to a WhatsApp user using the WhatsApp Cloud API.
    buttons: list of tuples or dicts, e.g. [("btn_submit", "Submit Form"), ("btn_cancel", "Cancel")]
    If credentials are not configured, falls back to local logging (mock mode).
    """
    formatted_buttons = []
    for btn in buttons:
        if isinstance(btn, (list, tuple)):
            btn_id, btn_title = btn[0], btn[1]
        elif isinstance(btn, dict):
            btn_id, btn_title = btn.get("id"), btn.get("title")
        else:
            btn_id, btn_title = str(btn), str(btn)
        formatted_buttons.append({
            "type": "reply",
            "reply": {
                "id": btn_id,
                "title": btn_title
            }
        })

    token, phone_number_id = _get_credentials()
    # Check if Cloud API credentials are configured
    if not token or not phone_number_id:
        btn_labels = "  ".join(f"[{b['reply']['title']}]" for b in formatted_buttons)
        print("\n----------------------------------------")
        print(f"[WHATSAPP SIMULATED BUTTON MESSAGE]")
        print(f"To: {to}")
        print(f"Message:\n{body_text}")
        print(f"Clickable Buttons: {btn_labels}")
        print("----------------------------------------\n")
        return True

    url = f"https://graph.facebook.com/v22.0/{phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "interactive",
        "interactive": {
            "type": "button",
            "body": {
                "text": body_text
            },
            "action": {
                "buttons": formatted_buttons
            }
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code in [200, 201]:
            print(f"[WHATSAPP] Successfully sent interactive button message to {to}")
            return True
        else:
            print(f"[WHATSAPP ERROR] Failed to send button message: {response.status_code} - {response.text}")
            # Fallback to plain text if interactive button is rejected
            return send_whatsapp_message(to, f"{body_text}\n\nReply 'Submit Form' or 'Cancel'.")
    except Exception as e:
        print(f"[WHATSAPP EXCEPTION] Error sending button message: {e}")
        return False

