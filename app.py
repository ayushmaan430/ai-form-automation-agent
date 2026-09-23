import os
from typing import Dict, Any, Optional
from fastapi import FastAPI, Request, Query, HTTPException
from fastapi.responses import PlainTextResponse, FileResponse
from dotenv import load_dotenv

from graph import app as graph_app
from session_manager import (
    sessions,
    user_profiles,
    get_session,
    get_user_profile,
    create_or_update_session,
    close_session_browser,
    clear_session
)
from parser import parse_whatsapp_message
from whatsapp_client import send_whatsapp_message

load_dotenv()

WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "my_verify_token_123").strip()

app = FastAPI(
    title="Autonomous WhatsApp Form Automation Agent",
    description="Backend API and WhatsApp Webhook for LangGraph + Playwright form automation"
)


# ==========================================================
# CORE MESSAGE PROCESSING LOGIC
# ==========================================================
def process_user_message(user_id: str, message_text: str) -> str:
    """
    Processes a message from a user (WhatsApp or Local Test) through the full agent lifecycle:
    1. Parse intent, form URL, and key-values.
    2. Manage session & profile memory.
    3. Invoke LangGraph with persistent Playwright page.
    4. Generate WhatsApp-friendly response.
    """
    # Check if session exists to provide context of missing fields to parser
    existing_session = get_session(user_id)
    missing_ctx = existing_session.get("missing_fields", []) if existing_session else None

    parsed = parse_whatsapp_message(message_text, missing_fields=missing_ctx)
    intent = parsed["intent"]
    form_url = parsed["form_url"]
    user_data = parsed["user_data"]

    # 0. Handle Greeting or Start
    if intent == "greeting":
        profile = get_user_profile(user_id)
        saved_name = profile.get("name")
        saved_email = profile.get("email")

        if saved_name and saved_email:
            disp_name = str(saved_name).title()
            return (
                f"👋 *Namaste {disp_name}! Welcome back.*\n\n"
                f"Mujhe aapki basic details pehle se yaad hain:\n"
                f"• *Name*: {disp_name}\n"
                f"• *Email*: {saved_email}\n"
                f"• *Phone*: {profile.get('phone', user_id)}\n\n"
                f"🔗 *Kripya Form ka Link (URL) bhej dijiye* jise aap fill karwana chahte hain.\n"
                f"(Agar kisi doosre person ki details bharni hon toh naya Name/Email bhi sath mein likh sakte hain)."
            )
        else:
            return (
                "👋 *Namaste! Main aapka Autonomous Form Automation Bot hoon.*\n\n"
                "Form auto-fill shuru karne ke liye kripya yeh do cheezein bhejein:\n\n"
                "1️⃣ *Form ka Link (URL)*\n"
                "2️⃣ *Aapka Name aur Email*\n\n"
                "💡 *Example:*\n"
                "Form: https://example.com/form\n"
                "Ayushmaan Rathore\n"
                "ayush@gmail.com\n"
                "6261560544\n\n"
                "👉 Aap bina label ke seedha link aur details bhej sakte hain!"
            )

    # 1. Handle Reset
    if intent == "reset":
        clear_session(user_id)
        return "🔄 *Form Reset*\n\nAapka form session reset kar diya gaya hai. Aap naya Form URL bhej kar shuru kar sakte hain."

    # 2. Handle Cancellation
    if intent == "cancel":
        session = get_session(user_id)
        if session:
            close_session_browser(user_id)
            session["status"] = "cancelled"
            return "❌ *Form Cancelled*\n\nForm submission abort kar di gayi hai aur browser window close ho gayi hai."
        else:
            return "ℹ️ *No Active Session*\n\nKoi active form session nahi mila jise cancel kiya ja sake."

    # 3. Handle Confirmation
    if intent == "confirm":
        session = get_session(user_id)
        if not session or not session.get("form_url"):
            return "⚠️ *No Active Form Session*\n\nPehle kripya Form URL bhej kar form start karein."

        if session.get("missing_fields"):
            missing_items = "\n".join(f"• *{m.capitalize()}*" for m in session["missing_fields"])
            return (
                f"⚠️ *Form Submit Nahi Ho Sakta*\n\n"
                f"Abhi bhi yeh required fields missing hain:\n"
                f"{missing_items}\n\n"
                f"👉 Kripya pehle inki details bhej dijiye."
            )

        print(f"\n[CONFIRMATION RECEIVED] Submitting form for user {user_id} on persistent page...")

        # Invoke LangGraph submit agent on the SAME open Playwright page
        result = graph_app.invoke({
            "form_url": session["form_url"],
            "user_data": session["user_data"],
            "fields": session.get("fields", []),
            "matched_data": session.get("matched_data", {}),
            "missing_fields": [],
            "filled_fields": session.get("filled_fields", []),
            "confirmation": True,
            "is_api": True,
            "submit_status": "confirmed",
            "page": session.get("page"),
            "browser": session.get("browser"),
            "playwright_instance": session.get("playwright_instance")
        })

        submit_status = result.get("submit_status", "")
        clear_session(user_id)

        if submit_status == "submitted":
            return (
                "🎉 *Form Successfully Submitted!*\n\n"
                "Aapka form successfully submit ho chuka hai aur browser band kar diya gaya hai.\n\n"
                "Jab bhi koi doosra form bharna ho, bas naya Form URL bhej dijiye! 🚀"
            )
        else:
            return f"ℹ️ Form submission completed with status: '{submit_status}'."

    # 4. Handle Form Data / URL Input
    session = create_or_update_session(user_id, form_url=form_url, user_data=user_data)

    target_url = session.get("form_url")
    if not target_url:
        u_data = session.get("user_data", {})
        has_name = u_data.get("name")
        has_email = u_data.get("email")

        if has_name or has_email:
            summary_parts = ["✅ *Aapki Details Note Kar Li Gayi Hain:*"]
            if has_name:
                summary_parts.append(f"• *Name*: {str(has_name).title()}")
            if has_email:
                summary_parts.append(f"• *Email*: {has_email}")
            if u_data.get("phone"):
                summary_parts.append(f"• *Phone*: {u_data.get('phone')}")

            summary_parts.append("\n🔗 *Ab kripya Form ka Link (URL) bhej dijiye* jise fill karna hai.")
            return "\n".join(summary_parts)
        else:
            return (
                "👋 *Namaste!*\n\n"
                "Form auto-fill shuru karne ke liye kripya *Form ka Link (URL)* aur apna *Name & Email* bhejein.\n\n"
                "💡 *Example:*\n"
                "Form: https://example.com/form\n"
                "Ayushmaan Rathore\n"
                "ayush@gmail.com\n"
                "6261560544"
            )

    print(f"\n[PROCESSING FORM] User: {user_id} | URL: {target_url}")
    print(f"Current User Data (including profile memory): {session['user_data']}")

    # Invoke LangGraph StateGraph (reusing session page if already open)
    result = graph_app.invoke({
        "form_url": target_url,
        "user_data": session["user_data"],
        "fields": session.get("fields", []),
        "matched_data": session.get("matched_data", {}),
        "missing_fields": [],
        "filled_fields": session.get("filled_fields", []),
        "confirmation": False,
        "is_api": True,
        "submit_status": "",
        "page": session.get("page"),
        "browser": session.get("browser"),
        "playwright_instance": session.get("playwright_instance")
    })

    # Update session with current page pointers and field detection results
    session["fields"] = result.get("fields", session.get("fields", []))
    session["matched_data"] = result.get("matched_data", session.get("matched_data", {}))
    session["missing_fields"] = result.get("missing_fields", [])
    session["filled_fields"] = result.get("filled_fields", [])
    session["page"] = result.get("page")
    session["browser"] = result.get("browser")
    session["playwright_instance"] = result.get("playwright_instance")

    missing = session.get("missing_fields", [])
    optional_unfilled = result.get("optional_fields", [])
    filled = session.get("filled_fields", [])
    matched = session.get("matched_data", {})
    form_title = result.get("form_title") or "Dynamic Form"

    # Build dynamic field label map from detected elements on the page
    dynamic_labels = {}
    for f_cfg in session.get("fields", []):
        m = f_cfg.get("meaning")
        lbl = f_cfg.get("label")
        if m and lbl and m not in dynamic_labels:
            cleaned_l = lbl.strip().rstrip('*').strip()
            if cleaned_l and len(cleaned_l) < 60:
                dynamic_labels[m] = cleaned_l

    def get_label(k: str) -> str:
        if k in dynamic_labels:
            return dynamic_labels[k]
        return k.replace("_", " ").title()

    if missing:
        session["status"] = "waiting_for_data"
        msg_parts = [f"📋 *{form_title}*\n"]
        if filled:
            msg_parts.append("✅ *Filled So Far:*")
            for f in filled:
                val = matched.get(f, session["user_data"].get(f, ""))
                if isinstance(val, list):
                    val = ", ".join(str(v).capitalize() for v in val)
                elif isinstance(val, str) and len(val) < 30 and "@" not in val and not val.startswith("http"):
                    val = val.capitalize()
                lbl = get_label(f)
                msg_parts.append(f"• *{lbl}*: {val}")
            msg_parts.append("")

        msg_parts.append("⚠️ *Required Fields (Zaroori Hain):*")
        for m in missing:
            lbl = get_label(m)
            msg_parts.append(f"• *{lbl}*")

        if optional_unfilled:
            msg_parts.append("\n💡 *Baki Fields (Yeh bhi bhar sakte hain):*")
            for opt in optional_unfilled:
                lbl = get_label(opt)
                msg_parts.append(f"• {lbl}")

        msg_parts.append("\n👉 Kripya details bhej dijiye.")
        msg_parts.append("(💡 *Exam ya quiz questions ke liye aap 'auto answer' ya 'solve' bhi likh sakte hain!*)")
        return "\n".join(msg_parts)
    else:
        session["status"] = "waiting_for_confirmation"
        msg_parts = [
            f"📋 *{form_title} - Summary*",
            "Aapka form complete bhar chuka hai! Ek baar review kar lijiye:\n"
        ]
        for f in filled:
            val = matched.get(f, session["user_data"].get(f, ""))
            if isinstance(val, list):
                val = ", ".join(str(v).capitalize() for v in val)
            elif isinstance(val, str) and len(val) < 30 and "@" not in val and not val.startswith("http"):
                val = val.capitalize()
            lbl = get_label(f)
            msg_parts.append(f"• *{lbl}*: {val}")

        if optional_unfilled:
            msg_parts.append("\n💡 *Yeh Fields Khali Hain (Agar bharna chahein):*")
            for opt in optional_unfilled:
                lbl = get_label(opt)
                msg_parts.append(f"• {lbl}")

        msg_parts.append("\n━━━━━━━━━━━━━━━━━━━━")
        msg_parts.append("👉 Form submit karne ke liye *'Submit'* reply karein.")
        msg_parts.append("❌ Cancel karne ke liye *'Cancel'* reply karein.")
        return "\n".join(msg_parts)


# ==========================================================
# FASTAPI ROUTES
# ==========================================================
@app.get("/")
def home():
    return {
        "service": "Autonomous WhatsApp Form Automation Agent",
        "status": "online",
        "active_sessions": len(sessions)
    }


@app.get("/{filename}.html")
def serve_html(filename: str):
    file_path = os.path.join(os.path.dirname(__file__), f"{filename}.html")
    if os.path.exists(file_path):
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="HTML form file not found")


# 1. WhatsApp Cloud API Webhook Verification (GET)
@app.get("/webhook")
def verify_whatsapp_webhook(
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge")
):
    """
    Verification endpoint called by Meta when configuring the WhatsApp webhook.
    """
    if hub_mode == "subscribe" and hub_verify_token == WHATSAPP_VERIFY_TOKEN:
        print("[WHATSAPP WEBHOOK] Webhook verified successfully by Meta.")
        return PlainTextResponse(content=hub_challenge)

    print(f"[WHATSAPP WEBHOOK ERROR] Verification failed. Token received: '{hub_verify_token}'")
    raise HTTPException(status_code=403, detail="Verification token mismatch")


from concurrent.futures import ThreadPoolExecutor
import asyncio

_worker_executor = ThreadPoolExecutor(max_workers=1)


def _process_and_reply(sender_id: str, user_text: str):
    """Processes user message and sends reply from a dedicated worker thread."""
    try:
        reply = process_user_message(sender_id, user_text)
        send_whatsapp_message(sender_id, reply)
    except Exception as e:
        print(f"[ERROR in _process_and_reply] {e}")
        send_whatsapp_message(sender_id, f"[ERROR] An issue occurred while processing your form: {e}")


# 2. WhatsApp Cloud API Incoming Messages (POST)
@app.post("/webhook")
async def receive_whatsapp_message(request: Request):
    """
    Receives incoming WhatsApp messages from Meta, parses payload,
    executes the form automation workflow in a background thread, and replies back via WhatsApp.
    """
    data = await request.json()

    try:
        entry = data.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})
        messages = value.get("messages", [])

        if not messages:
            # Status update or non-message event (e.g. delivered, read)
            return {"status": "ignored_non_message"}

        msg = messages[0]
        sender_id = msg.get("from")
        msg_type = msg.get("type")

        if msg_type != "text":
            send_whatsapp_message(sender_id, "Please send plain text messages with your form details.")
            return {"status": "unsupported_media_type"}

        user_text = msg.get("text", {}).get("body", "").strip()
        print(f"\n[WHATSAPP INCOMING] From: {sender_id} | Body: '{user_text}'")

        # Execute in dedicated worker thread to avoid asyncio loop conflict with Sync Playwright
        loop = asyncio.get_running_loop()
        loop.run_in_executor(_worker_executor, _process_and_reply, sender_id, user_text)

        return {"status": "success"}
    except Exception as e:
        print(f"[WHATSAPP WEBHOOK ERROR] {e}")
        return {"status": "error", "message": str(e)}


# 3. Local Testing Endpoint (Simulates WhatsApp without needing Meta account)
@app.post("/local-test")
def local_test(payload: Dict[str, Any]):
    """
    Endpoint to test multi-turn conversation locally.
    Example payload:
    {
        "user_id": "9876543210",
        "message": "Form: file:///.../form.html\\nName: Ayush\\nPhone: 9876543210"
    }
    """
    user_id = str(payload.get("user_id", "local_user_1"))
    message = str(payload.get("message", "")).strip()

    reply = process_user_message(user_id, message)

    session = get_session(user_id)
    return {
        "user_id": user_id,
        "reply": reply,
        "session_status": session.get("status") if session else "none",
        "missing_fields": session.get("missing_fields") if session else [],
        "user_profile": user_profiles.get(user_id, {})
    }


# 4. Debugging & Session Inspection
@app.get("/sessions")
def list_sessions():
    """Inspect active sessions and user profiles."""
    summary = {}
    for uid, sess in sessions.items():
        summary[uid] = {
            "form_url": sess.get("form_url"),
            "status": sess.get("status"),
            "missing_fields": sess.get("missing_fields"),
            "filled_fields": sess.get("filled_fields"),
            "has_active_browser": sess.get("browser") is not None
        }
    return {
        "active_sessions": summary,
        "user_profiles": user_profiles
    }