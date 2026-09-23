import time
from typing import Dict, Any, Optional
from playwright.sync_api import Playwright, Browser, Page

# In-memory storage for active user conversational sessions
# Format:
# sessions[user_id] = {
#     "form_url": str,
#     "user_data": dict,
#     "missing_fields": list,
#     "filled_fields": list,
#     "status": str,  # "ready_to_analyze", "waiting_for_data", "waiting_for_confirmation", "submitted", "cancelled"
#     "playwright_instance": Playwright,
#     "browser": Browser,
#     "page": Page,
#     "updated_at": float
# }
sessions: Dict[str, Dict[str, Any]] = {}

# In-memory persistent profile memory per user (e.g. phone number)
# Automatically remembers basic details (name, email, phone, city, etc.) across different forms
# user_profiles[user_id] = { "name": "...", "email": "...", ... }
user_profiles: Dict[str, Dict[str, Any]] = {}


def get_session(user_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves an active session for a given user ID."""
    return sessions.get(user_id)


def get_user_profile(user_id: str) -> Dict[str, Any]:
    """Returns the remembered profile data for a user."""
    return user_profiles.setdefault(user_id, {})


def update_user_profile(user_id: str, new_data: Dict[str, Any]):
    """Saves or updates basic user information in their profile memory."""
    profile = user_profiles.setdefault(user_id, {})
    for k, v in new_data.items():
        if v is not None and str(v).strip():
            profile[str(k).lower()] = v


def create_or_update_session(user_id: str, form_url: Optional[str] = None, user_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Creates a new session or updates an existing one, merging user data and profile memory."""
    if user_id not in sessions:
        # Load any existing profile memory
        profile_data = dict(get_user_profile(user_id))
        if user_data:
            profile_data.update(user_data)

        sessions[user_id] = {
            "user_id": user_id,
            "form_url": form_url or "",
            "user_data": profile_data,
            "fields": [],
            "matched_data": {},
            "missing_fields": [],
            "filled_fields": [],
            "status": "ready_to_analyze",
            "playwright_instance": None,
            "browser": None,
            "page": None,
            "updated_at": time.time()
        }
    else:
        session = sessions[user_id]
        if form_url:
            session["form_url"] = form_url
        if user_data:
            session["user_data"].update(user_data)
        session["updated_at"] = time.time()

    # Also update user profile memory with newly provided data
    if user_data:
        update_user_profile(user_id, user_data)

    return sessions[user_id]


def close_session_browser(user_id: str):
    """Safely closes the persistent Playwright browser session for a user."""
    session = sessions.get(user_id)
    if not session:
        return

    browser = session.get("browser")
    pw = session.get("playwright_instance")

    if browser:
        try:
            browser.close()
        except Exception:
            pass

    if pw:
        try:
            pw.stop()
        except Exception:
            pass

    session["browser"] = None
    session["page"] = None
    session["playwright_instance"] = None


def clear_session(user_id: str):
    """Cleans up and removes an active session."""
    close_session_browser(user_id)
    sessions.pop(user_id, None)
