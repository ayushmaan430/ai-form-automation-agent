import os
from pathlib import Path
from app import process_user_message
from session_manager import sessions, user_profiles, clear_session

# Resolve local dummy form path
current_dir = Path(__file__).parent.resolve()
form_html_url = (current_dir / "form.html").as_uri()

TEST_USER_ID = "919876543210"

print("==========================================================")
print("TESTING WHATSAPP AGENTIC FORM AUTOMATION MULTI-TURN FLOW")
print(f"Target Form URL: {form_html_url}")
print(f"Test WhatsApp User: {TEST_USER_ID}")
print("==========================================================\n")

# Ensure clean starting state
clear_session(TEST_USER_ID)

# ---------------------------------------------------------
# TURN 1: User sends Form URL + Partial Information
# ---------------------------------------------------------
print("\n>>> [TURN 1] User sends Form URL and partial details...")
msg_turn_1 = f"""
Form: {form_html_url}
Name: Ayushmaan Rathore
Phone: 9876543210
"""
reply_1 = process_user_message(TEST_USER_ID, msg_turn_1)
print(f"\n<<< [WHATSAPP BOT REPLY 1]:\n{reply_1}")

session = sessions.get(TEST_USER_ID)
print(f"\n[SESSION STATE AFTER TURN 1]:")
print(f"Status: {session.get('status')}")
print(f"Filled Fields: {session.get('filled_fields')}")
print(f"Browser Open?: {session.get('page') is not None and not session['page'].is_closed()}")

# ---------------------------------------------------------
# TURN 2: User provides remaining information
# ---------------------------------------------------------
print("\n----------------------------------------------------------")
print(">>> [TURN 2] User provides remaining information...")
msg_turn_2 = """
Email: ayushmaan@gmail.com
City: Indore
Gender: male
Skills: python, django
Feedback: Automated multi-turn WhatsApp test passed!
"""
reply_2 = process_user_message(TEST_USER_ID, msg_turn_2)
print(f"\n<<< [WHATSAPP BOT REPLY 2]:\n{reply_2}")

session = sessions.get(TEST_USER_ID)
print(f"\n[SESSION STATE AFTER TURN 2]:")
print(f"Status: {session.get('status')}")
print(f"Filled Fields: {session.get('filled_fields')}")
print(f"Browser Still Open for Confirmation?: {session.get('page') is not None and not session['page'].is_closed()}")

# ---------------------------------------------------------
# TURN 3: User confirms submission
# ---------------------------------------------------------
print("\n----------------------------------------------------------")
print(">>> [TURN 3] User replies 'Submit Form'...")
msg_turn_3 = "Submit Form"
reply_3 = process_user_message(TEST_USER_ID, msg_turn_3)
print(f"\n<<< [WHATSAPP BOT REPLY 3]:\n{reply_3}")

print("\n----------------------------------------------------------")
print(f"[FINAL PROFILE MEMORY STORED FOR USER {TEST_USER_ID}]:")
print(user_profiles.get(TEST_USER_ID, {}))
print("\nAll turns completed successfully!")
