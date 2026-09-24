import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Force headless=False for local visual execution
os.environ["HEADLESS"] = "false"

from graph import app as graph_app


def run_local_interactive():
    print("\n" + "=" * 60)
    print("🚀 AUTONOMOUS AI FORM AUTOMATION AGENT (LOCAL MODE)")
    print("=" * 60)
    print("Is mode me Live Chrome Browser aapki screen par khulega")
    print("aur AI form ko aapki aankhon ke samne auto-fill karega!\n")

    # 1. Ask for URL
    default_form = "https://ai-form-automation-agents.onrender.com/google_exam_form.html"
    print(f"👉 Enter ANY Form URL (HTTP / HTTPS / Local HTML):")
    print(f"   [Default: {default_form}]")
    url_input = input("   URL: ").strip()
    target_url = url_input if url_input else default_form

    # Handle local file paths cleanly if user passes a local file
    if target_url.endswith(".html") and not target_url.startswith("http"):
        if os.path.exists(target_url):
            target_url = f"file:///{os.path.abspath(target_url).replace('\\', '/')}"

    # 2. Ask for Candidate Details
    print("\n📝 Enter Candidate Details:")
    name = input("   Full Name [Ayushmaan Rathore]: ").strip() or "Ayushmaan Rathore"
    email = input("   Email [ayush@example.com]: ").strip() or "ayush@example.com"
    roll = input("   Roll Number [2026CS101]: ").strip() or "2026CS101"
    college = input("   College Name [Oriental College of Technology]: ").strip() or "Oriental College of Technology"
    gender = input("   Gender [Male]: ").strip() or "Male"

    # 3. Ask for Auto-Answer
    auto_ans = input("\n🤖 Auto-solve Exam MCQs & Questions with AI? (Y/n) [Y]: ").strip().lower()
    auto_answer = auto_ans != "n"

    user_data = {
        "name": name,
        "email": email,
        "roll_number": roll,
        "college": college,
        "gender": gender,
        "_auto_answer": auto_answer
    }

    print("\n" + "-" * 60)
    print(f"🌐 Launching Live Chromium Browser for: {target_url}")
    print("-" * 60)

    # 4. Invoke LangGraph multi-agent flow
    initial_state = {
        "form_url": target_url,
        "user_data": user_data,
        "fields": [],
        "matched_data": {},
        "missing_fields": [],
        "filled_fields": [],
        "confirmation": None,
        "is_api": False,  # Local mode asks confirmation via terminal
        "submit_status": ""
    }

    try:
        final_state = graph_app.invoke(initial_state)

        print("\n" + "=" * 60)
        status = final_state.get("submit_status")
        if status == "submitted":
            print("🎉 SUCCESS: Form was filled and submitted successfully!")
        elif status == "aborted_by_user":
            print("❌ Form submission was cancelled by user.")
        else:
            print(f"ℹ️ Finished with status: {status}")
        print("=" * 60 + "\n")

    except Exception as e:
        print(f"\n❌ Error during form execution: {e}")


if __name__ == "__main__":
    run_local_interactive()
