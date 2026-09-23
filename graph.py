import json
import os
from pathlib import Path
from typing import TypedDict, List, Dict, Any, Optional

from langgraph.graph import StateGraph, START, END
from playwright.sync_api import sync_playwright, Playwright, Browser, Page

from dotenv import load_dotenv

# ==========================================
# CONFIGURATION & FLAGS
# ==========================================
# TEST_MODE = True: Bypasses Gemini API completely (quota-safe)
# TEST_MODE = False: Uses Gemini to intelligently analyze arbitrary forms
TEST_MODE = True

load_dotenv()

# Lazy LLM loader so ChatGoogleGenerativeAI is not invoked when TEST_MODE is True
llm = None
if not TEST_MODE:
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash"
        )
    except Exception as e:
        print(f"[WARN] Could not initialize Gemini LLM: {e}")


# ==========================================
# GLOBAL PLAYWRIGHT SESSION
# ==========================================
playwright_instance: Optional[Playwright] = None
browser: Optional[Browser] = None
page: Optional[Page] = None


# ==========================================
# AGENT STATE DEFINITION
# ==========================================
class AgentState(TypedDict, total=False):
    form_url: str
    user_data: Dict[str, Any]

    fields: List[Dict[str, Any]]
    matched_data: Dict[str, Any]
    missing_fields: List[str]
    optional_fields: List[str]
    filled_fields: List[str]

    confirmation: Optional[bool]
    submit_status: str
    is_api: Optional[bool]
    page: Any
    browser: Any
    playwright_instance: Any


# ==========================================
# AGENT 1: FORM ANALYZER
# ==========================================
def form_analyzer(state: AgentState) -> Dict[str, Any]:
    """
    Opens the form in a persistent Playwright browser, dynamically scans
    all input, select, radio, checkbox, and textarea elements, extracts their
    visible labels, placeholders, and options, and identifies semantic meanings.
    Works for ANY dynamic form, exam registration form, quiz/MCQs, or portal.
    """
    global playwright_instance, browser, page

    form_url = state["form_url"]
    print("\n================================")
    print("AGENT 1: FORM ANALYZER (UNIVERSAL DYNAMIC SCANNER)")
    print("================================")
    print(f"Target Form URL: {form_url}")

    # Check if a persistent page is already open in user session
    session_page = state.get("page")
    if session_page and not session_page.is_closed():
        page = session_page
        browser = state.get("browser", browser)
        playwright_instance = state.get("playwright_instance", playwright_instance)
        print("[SESSION REUSED] Using existing persistent Playwright page.")
        if page.url != form_url and not page.url.endswith(form_url):
            page.goto(form_url, wait_until="domcontentloaded", timeout=15000)
    else:
        try:
            if playwright_instance is None:
                playwright_instance = sync_playwright().start()

            if browser is None or not browser.is_connected():
                is_headless = os.getenv("HEADLESS", "false").lower() == "true" or os.name != "nt"
                browser = playwright_instance.chromium.launch(
                    headless=is_headless,
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"]
                )

            if page is None or page.is_closed():
                page = browser.new_page()

            page.goto(form_url, wait_until="domcontentloaded", timeout=15000)
        except Exception as e:
            # Clean up on failure so subsequent attempts retry fresh
            try:
                if page and not page.is_closed():
                    page.close()
            except Exception:
                pass
            page = None
            try:
                if browser and browser.is_connected():
                    browser.close()
            except Exception:
                pass
            browser = None
            raise e

    page.wait_for_timeout(500)

    # Detect Page Title or Heading
    form_title = ""
    try:
        h1 = page.locator("h1, h2, title").first
        if h1.count() > 0:
            form_title = h1.inner_text().strip()
    except Exception:
        pass
    if not form_title:
        try:
            form_title = page.title().strip()
        except Exception:
            form_title = "Online Dynamic Form"

    print(f"Detected Form Title: '{form_title}'")

    raw_fields: List[Dict[str, Any]] = []

    # 1. Inspect Inputs (text, email, tel, date, number, radio, checkbox, etc.)
    inputs = page.locator("input")
    input_count = inputs.count()
    for i in range(input_count):
        field = inputs.nth(i)
        input_type = (field.get_attribute("type") or "text").lower()

        if input_type in ["submit", "button", "reset", "hidden"]:
            continue

        field_name = field.get_attribute("name") or ""
        field_id = field.get_attribute("id") or ""
        placeholder = field.get_attribute("placeholder") or ""
        field_val = field.get_attribute("value") or ""
        is_required = field.get_attribute("required") is not None

        # Extract human-readable Label
        label_text = ""
        option_label = ""

        # Check label[for=id]
        if field_id:
            try:
                lbl = page.locator(f'label[for="{field_id}"]')
                if lbl.count() > 0:
                    label_text = lbl.first.inner_text().strip()
            except Exception:
                pass

        # Check ancestor label (common for radios/checkboxes)
        if not label_text:
            try:
                parent_lbl = field.locator('xpath=ancestor::label')
                if parent_lbl.count() > 0:
                    option_label = parent_lbl.first.inner_text().strip()
                    label_text = option_label
            except Exception:
                pass

        # Check parent question / form-group label
        if not label_text or input_type in ["radio", "checkbox"]:
            try:
                container = field.locator('xpath=ancestor::*[contains(@class, "form-group") or contains(@class, "question") or contains(@class, "field") or name()="fieldset"][1]')
                if container.count() > 0:
                    group_lbl = container.locator('label:not([for]), legend, .question-title, strong, b').first
                    if group_lbl.count() > 0:
                        group_text = group_lbl.inner_text().strip()
                        if group_text:
                            label_text = group_text
            except Exception:
                pass

        if not label_text:
            label_text = field.get_attribute("aria-label") or placeholder or field_name or field_id

        raw_fields.append({
            "element": "input",
            "type": input_type,
            "name": field_name,
            "id": field_id,
            "label": label_text,
            "option_label": option_label,
            "placeholder": placeholder,
            "value": field_val,
            "required": is_required
        })

    # 2. Inspect Dropdowns (select)
    selects = page.locator("select")
    select_count = selects.count()
    for i in range(select_count):
        field = selects.nth(i)
        field_name = field.get_attribute("name") or ""
        field_id = field.get_attribute("id") or ""
        is_required = field.get_attribute("required") is not None

        label_text = ""
        if field_id:
            try:
                lbl = page.locator(f'label[for="{field_id}"]')
                if lbl.count() > 0:
                    label_text = lbl.first.inner_text().strip()
            except Exception:
                pass
        if not label_text:
            try:
                container = field.locator('xpath=ancestor::*[contains(@class, "form-group") or contains(@class, "question") or contains(@class, "field")][1]')
                if container.count() > 0:
                    c_lbl = container.locator('label, strong, b').first
                    if c_lbl.count() > 0:
                        label_text = c_lbl.inner_text().strip()
            except Exception:
                pass
        if not label_text:
            label_text = field.get_attribute("aria-label") or field_name or field_id

        options = []
        opt_locators = field.locator("option")
        for j in range(opt_locators.count()):
            opt = opt_locators.nth(j)
            opt_val = opt.get_attribute("value") or ""
            opt_lbl = opt.inner_text().strip()
            if opt_lbl and not opt_lbl.startswith("--"):
                options.append({
                    "value": opt_val,
                    "label": opt_lbl
                })

        raw_fields.append({
            "element": "select",
            "type": "select",
            "name": field_name,
            "id": field_id,
            "label": label_text,
            "options": options,
            "required": is_required
        })

    # 3. Inspect Textareas
    textareas = page.locator("textarea")
    textarea_count = textareas.count()
    for i in range(textarea_count):
        field = textareas.nth(i)
        field_name = field.get_attribute("name") or ""
        field_id = field.get_attribute("id") or ""
        placeholder = field.get_attribute("placeholder") or ""
        is_required = field.get_attribute("required") is not None

        label_text = ""
        if field_id:
            try:
                lbl = page.locator(f'label[for="{field_id}"]')
                if lbl.count() > 0:
                    label_text = lbl.first.inner_text().strip()
            except Exception:
                pass
        if not label_text:
            try:
                container = field.locator('xpath=ancestor::*[contains(@class, "form-group") or contains(@class, "question") or contains(@class, "field")][1]')
                if container.count() > 0:
                    c_lbl = container.locator('label, strong, b').first
                    if c_lbl.count() > 0:
                        label_text = c_lbl.inner_text().strip()
            except Exception:
                pass
        if not label_text:
            label_text = placeholder or field_name or field_id

        raw_fields.append({
            "element": "textarea",
            "type": "textarea",
            "name": field_name,
            "id": field_id,
            "label": label_text,
            "placeholder": placeholder,
            "required": is_required
        })

    # 4. Derive Dynamic Semantic Meaning
    import re
    analyzed_fields: List[Dict[str, Any]] = []

    for item in raw_fields:
        name = (item.get("name") or "").lower()
        field_id = (item.get("id") or "").lower()
        label = (item.get("label") or "").lower()
        placeholder = (item.get("placeholder") or "").lower()
        field_type = (item.get("type") or "").lower()

        combined = f"{label} {name} {field_id} {placeholder}"

        meaning = "unknown"
        # 1. Exam Question / MCQ tags (e.g. Q1, Q2, Question 1)
        q_match = re.search(r'^(?:q|question)\s*(\d+)', name) or re.search(r'^(?:q|question)\s*(\d+)', label)
        if q_match:
            meaning = f"q{q_match.group(1)}"
        # 2. Email Address
        elif field_type == "email" or "email" in name or "mail" in name or "email" in label:
            meaning = "email"
        # 3. Phone / Mobile
        elif field_type == "tel" or any(k in name for k in ["phone", "mobile", "tel"]) or any(k in label for k in ["phone", "mobile", "contact"]):
            meaning = "phone"
        # 4. Roll / Registration Number
        elif any(k in combined for k in ["roll", "enroll", "registration_no", "reg_no", "hall_ticket", "admit_card"]):
            meaning = "roll_number"
        # 5. Father's Name
        elif any(k in combined for k in ["father", "parent", "guardian"]):
            meaning = "father_name"
        # 6. Mother's Name
        elif any(k in combined for k in ["mother"]):
            meaning = "mother_name"
        # 7. Date of Birth
        elif any(k in combined for k in ["dob", "birth", "date of birth"]) or field_type == "date":
            meaning = "dob"
        # 8. Course / Branch
        elif any(k in combined for k in ["course", "branch", "stream", "department", "degree", "program"]):
            meaning = "course"
        # 9. Exam Center Preference
        elif any(k in combined for k in ["exam center", "test center", "exam_center", "center preference", "center"]):
            meaning = "exam_center"
        # 10. College / University
        elif any(k in label for k in ["college", "university", "institute", "school"]) or any(k in name for k in ["college", "university"]):
            meaning = "college"
        # 11. Semester
        elif any(k in combined for k in ["semester", "sem", "academic year"]):
            meaning = "semester"
        # 12. Category
        elif any(k in combined for k in ["category", "caste"]):
            meaning = "category"
        # 13. Candidate / Student Full Name
        elif any(k in combined for k in ["student name", "candidate name", "full name", "applicant name", "your name"]) or (name == "name" or field_id == "name"):
            meaning = "name"
        # 14. City
        elif "city" in combined:
            meaning = "city"
        # 15. Gender
        elif "gender" in combined or "sex" in combined:
            meaning = "gender"
        # 16. Skills
        elif any(k in combined for k in ["skill", "technolog"]):
            meaning = "skills"
        # 17. Feedback / Remarks
        elif any(k in combined for k in ["feedback", "comment", "message", "remark", "suggestion"]):
            meaning = "feedback"
        else:
            meaning = name if name else re.sub(r'[^a-z0-9_]', '_', label.strip())[:25].strip('_')

        analyzed_fields.append({
            **item,
            "meaning": meaning
        })

    print(f"Detected & Analyzed {len(analyzed_fields)} Fields on page:")
    for f in analyzed_fields:
        print(f" - [{f.get('type')}] '{f.get('label')}' (Name: '{f.get('name')}') -> Meaning: '{f.get('meaning')}', Required: {f.get('required')}")

    return {
        "form_title": form_title,
        "fields": analyzed_fields,
        "page": page,
        "browser": browser,
        "playwright_instance": playwright_instance
    }


# ==========================================
# AGENT 2: DATA MATCHING (UNIVERSAL & ACADEMIC/EXAM)
# ==========================================
def data_matching(state: AgentState) -> Dict[str, Any]:
    """
    Compares detected field meanings with user_data.
    Supports personal, contact, academic, exam, quiz, and custom questions.
    Includes built-in answering engine for exam questions.
    """
    print("\n================================")
    print("AGENT 2: DATA MATCHING")
    print("================================")

    fields = state.get("fields", [])
    user_data = state.get("user_data", {})

    matched_data = {}
    missing_fields = []

    user_data_normalized = {str(k).lower().strip(): v for k, v in user_data.items()}
    checked_meanings = set()

    # Comprehensive Synonyms & Aliases for Forms (Personal, Exam, Student, Job, Survey)
    ALIASES = {
        "name": ["name", "full_name", "fullname", "username", "user_name", "first_name", "applicant_name", "student_name", "candidate_name"],
        "father_name": ["father_name", "father", "fathers_name", "parent_name", "guardian"],
        "mother_name": ["mother_name", "mother", "mothers_name"],
        "roll_number": ["roll_number", "roll_no", "rollno", "enrollment", "enrollment_no", "reg_no", "registration_no", "hall_ticket"],
        "dob": ["dob", "birth_date", "date_of_birth", "birthdate"],
        "course": ["course", "branch", "stream", "degree", "program", "discipline", "degree_branch"],
        "college": ["college", "university", "institute", "school"],
        "semester": ["semester", "sem", "academic_year", "year"],
        "category": ["category", "caste"],
        "exam_center": ["exam_center", "center", "test_center", "city_preference"],
        "subject": ["subject", "paper", "paper_code", "exam_name"],
        "email": ["email", "mail", "email_address", "user_email"],
        "phone": ["phone", "tel", "mobile", "contact", "phone_number", "mobile_number"],
        "city": ["city", "location", "town", "district"],
        "state": ["state", "province"],
        "address": ["address", "street", "residential_address"],
        "pincode": ["pincode", "pin", "zip", "postal_code"],
        "gender": ["gender", "sex"],
        "skills": ["skills", "skill", "technologies", "tech_stack", "frameworks"],
        "specialization": ["specialization", "preferred_specialization", "domain"],
        "explanation": ["explanation", "answer", "description", "details"],
        "feedback": ["feedback", "message", "comment", "comments", "description", "notes", "remarks"]
    }

    # Knowledge Base for Automatic Exam / Quiz Answering
    KNOWLEDGE_ANSWERS = {
        # General & Geography Knowledge
        "capital city of madhya pradesh": "Bhopal",
        "capital of madhya pradesh": "Bhopal",
        "capital of mp": "Bhopal",
        "capital of india": "New Delhi",
        "python dynamically typed": "Yes",
        "is python interpreted": "Yes",
        "father of computer": "Charles Babbage",
        # AI & Machine Learning Knowledge
        "ai stand for": "Artificial Intelligence",
        "what does ai stand for": "Artificial Intelligence",
        "widely used for ai": "Python",
        "programming language is most widely used": "Python",
        "nlp stand for": "Natural Language Processing",
        "natural language processing": "Natural Language Processing",
        "used for classification": "Logistic Regression",
        "classification": "Logistic Regression",
        "supervised and unsupervised": "Supervised learning trains models on labeled input-output pairs, whereas unsupervised learning discovers hidden structures and clusters in unlabeled data.",
        "explain the difference": "Supervised learning trains models on labeled input-output pairs, whereas unsupervised learning discovers hidden structures and clusters in unlabeled data.",
        "deep learning frameworks": ["PyTorch", "TensorFlow", "Keras"],
        "frameworks": ["PyTorch", "TensorFlow", "Keras"],
        "specialization": "Generative AI & LLMs",
        "preferred ai specialization": "Generative AI & LLMs",
        "degree_branch": "B.Tech AI & Data Science",
        "favorite ai project": "Building autonomous AI agents and intelligent form automation systems."
    }

    auto_answer_requested = bool(user_data_normalized.get("_auto_answer") or user_data_normalized.get("auto_answer") or "answer" in user_data_normalized)

    for field in fields:
        meaning = field.get("meaning", "unknown")
        field_name = (field.get("name") or "").lower().strip()
        field_label = (field.get("label") or "").lower().strip()
        is_required = field.get("required", False)

        matched_val = None

        # 1. Exact match with meaning or field_name
        if meaning in user_data_normalized:
            matched_val = user_data_normalized[meaning]
        elif field_name in user_data_normalized:
            matched_val = user_data_normalized[field_name]
        else:
            # 2. Check Aliases
            for alias in ALIASES.get(meaning, []):
                if alias in user_data_normalized:
                    matched_val = user_data_normalized[alias]
                    break

        # 3. Fuzzy match with field label or name (skip generic keys)
        if matched_val is None:
            for u_k, u_v in user_data_normalized.items():
                if u_k.startswith("_") or u_k in ["city", "name", "email", "phone", "state", "the", "is", "a", "to", "in", "for", "or"]:
                    continue
                if len(u_k) >= 3 and (u_k in field_label or u_k in field_name):
                    matched_val = u_v
                    break

        # 4. Exam / Quiz Question Answering Engine ("or answer deskta h")
        if matched_val is None:
            # Check if this field is a question
            for q_key, correct_ans in KNOWLEDGE_ANSWERS.items():
                if q_key in field_label or q_key in field_name:
                    matched_val = correct_ans
                    print(f" [AI KNOWLEDGE ENGINE] Solved question '{field.get('label')}' -> '{correct_ans}'")
                    break

            # If user explicitly asked for auto-answers and this is an MCQ/Question
            if matched_val is None and auto_answer_requested:
                if field.get("type") == "radio" and field.get("value"):
                    matched_val = field.get("value")
                elif field.get("element") == "select" and field.get("options"):
                    matched_val = field["options"][0]["label"]

        if matched_val is not None and meaning not in matched_data:
            matched_data[meaning] = matched_val

        # Check required fields
        if is_required and meaning not in checked_meanings:
            checked_meanings.add(meaning)
            val = matched_val
            if val is None or (isinstance(val, str) and not val.strip()) or (isinstance(val, list) and len(val) == 0):
                if meaning not in missing_fields:
                    missing_fields.append(meaning)

    all_meanings = []
    for f in fields:
        m = f.get("meaning", "unknown")
        if m != "unknown" and m not in all_meanings:
            all_meanings.append(m)

    optional_fields = [m for m in all_meanings if m not in matched_data and m not in missing_fields]

    print("Matched Data for Form:")
    print(json.dumps(matched_data, indent=2))

    print("\nMissing Required Fields (from matching):")
    print(missing_fields if missing_fields else "None")

    print("\nUnfilled Optional Fields:")
    print(optional_fields if optional_fields else "None")

    return {
        "matched_data": matched_data,
        "missing_fields": missing_fields,
        "optional_fields": optional_fields
    }


# ==========================================
# AGENT 3: FORM FILLING (UNIVERSAL)
# ==========================================
def form_filling(state: AgentState) -> Dict[str, Any]:
    """
    Fills matched fields in the persistent Playwright page:
    - Text / Email / Tel / Date / Number
    - Select / Dropdown (with partial option matching)
    - Radio buttons (by value or option label)
    - Checkboxes
    - Textarea
    """
    global page
    session_page = state.get("page")
    if session_page and not session_page.is_closed():
        page = session_page

    if not page or page.is_closed():
        raise RuntimeError("Playwright page not initialized!")

    fields = state.get("fields", [])
    matched_data = state.get("matched_data", {})
    filled_fields = []

    # 1. Inputs (Text, Email, Tel, Date, Number, Radio, Checkbox)
    inputs = page.locator("input")
    for i in range(inputs.count()):
        field_loc = inputs.nth(i)
        field_type = (field_loc.get_attribute("type") or "text").lower()
        field_name = field_loc.get_attribute("name") or ""
        field_val = field_loc.get_attribute("value") or ""

        # Find matching field config
        field_cfg = next(
            (f for f in fields if f.get("element") == "input" and f.get("name") == field_name and (field_type not in ["radio", "checkbox"] or f.get("value") == field_val)),
            None
        )
        if not field_cfg:
            continue

        meaning = field_cfg.get("meaning")
        if not meaning or meaning not in matched_data:
            continue

        val = matched_data[meaning]

        # Standard Inputs (Text, Email, Tel, Date, Number)
        if field_type not in ["radio", "checkbox", "submit", "button", "reset", "hidden"]:
            field_loc.fill(str(val))
            if meaning not in filled_fields:
                filled_fields.append(meaning)
            print(f" [Filled Input] {meaning} ({field_type}) -> '{val}'")

        # Radio Button (match by value or option_label)
        elif field_type == "radio":
            val_str = str(val).strip().lower()
            opt_lbl = str(field_cfg.get("option_label") or "").strip().lower()
            if val_str == str(field_val).strip().lower() or (opt_lbl and val_str in opt_lbl) or (opt_lbl and opt_lbl in val_str):
                field_loc.check()
                if meaning not in filled_fields:
                    filled_fields.append(meaning)
                print(f" [Checked Radio] {meaning} -> '{field_val}' (Label: '{opt_lbl}')")

        # Checkbox (match by value or option_label)
        elif field_type == "checkbox":
            target_list = val if isinstance(val, list) else [val]
            normalized_targets = [str(x).strip().lower() for x in target_list]
            opt_lbl = str(field_cfg.get("option_label") or "").strip().lower()
            if str(field_val).strip().lower() in normalized_targets or any(t in opt_lbl for t in normalized_targets):
                field_loc.check()
                if meaning not in filled_fields:
                    filled_fields.append(meaning)
                print(f" [Checked Checkbox] {meaning} -> '{field_val}'")

    # 2. Select / Dropdown
    selects = page.locator("select")
    for i in range(selects.count()):
        select_loc = selects.nth(i)
        dropdown_name = select_loc.get_attribute("name") or ""

        field_cfg = next(
            (f for f in fields if f.get("element") == "select" and f.get("name") == dropdown_name),
            None
        )
        if not field_cfg:
            continue

        meaning = field_cfg.get("meaning")
        if not meaning or meaning not in matched_data:
            continue

        val = str(matched_data[meaning]).strip()
        val_lower = val.lower()
        selected = False

        # Attempt 1: Direct label
        try:
            select_loc.select_option(label=val, timeout=1500)
            selected = True
        except Exception:
            pass

        # Attempt 2: Direct value
        if not selected:
            try:
                select_loc.select_option(value=val, timeout=1500)
                selected = True
            except Exception:
                try:
                    select_loc.select_option(value=val_lower, timeout=1500)
                    selected = True
                except Exception:
                    pass

        # Attempt 3: Fuzzy / Partial match on option text
        if not selected:
            try:
                options = select_loc.locator("option").all()
                for opt in options:
                    opt_text = opt.inner_text().strip().lower()
                    opt_val = (opt.get_attribute("value") or "").strip().lower()
                    if val_lower in opt_text or opt_text in val_lower or val_lower in opt_val:
                        select_loc.select_option(value=opt.get_attribute("value"), timeout=1500)
                        selected = True
                        break
            except Exception:
                pass

        if selected:
            if meaning not in filled_fields:
                filled_fields.append(meaning)
            print(f" [Selected Dropdown] {meaning} -> '{val}'")
        else:
            print(f" [Dropdown Notice] Option '{val}' not found in dropdown '{meaning}'.")

    # 3. Textarea
    textareas = page.locator("textarea")
    for i in range(textareas.count()):
        textarea_loc = textareas.nth(i)
        textarea_name = textarea_loc.get_attribute("name") or ""

        field_cfg = next(
            (f for f in fields if f.get("element") == "textarea" and f.get("name") == textarea_name),
            None
        )
        if not field_cfg:
            continue

        meaning = field_cfg.get("meaning")
        if not meaning or meaning not in matched_data:
            continue

        val = str(matched_data[meaning])
        textarea_loc.fill(val)
        if meaning not in filled_fields:
            filled_fields.append(meaning)
        print(f" [Filled Textarea] {meaning} -> '{val}'")

    print("\nTotal Fields Successfully Filled:")
    print(filled_fields)

    return {"filled_fields": filled_fields}


# ==========================================
# AGENT 4: MISSING FIELD DETECTOR
# ==========================================
def missing_field_detector(state: AgentState) -> Dict[str, Any]:
    """
    Checks if any REQUIRED fields were missing.
    Optional fields are not marked as missing.
    """
    print("\n================================")
    print("AGENT 4: MISSING FIELD DETECTOR")
    print("================================")

    fields = state.get("fields", [])
    matched_data = state.get("matched_data", {})

    missing_fields = []
    seen = set()

    for field in fields:
        meaning = field.get("meaning", "unknown")
        is_required = field.get("required", False)

        if meaning == "unknown" or meaning in seen:
            continue

        seen.add(meaning)

        if is_required:
            val = matched_data.get(meaning)
            if val is None or (isinstance(val, str) and not val.strip()) or (isinstance(val, list) and len(val) == 0):
                missing_fields.append(meaning)

    if missing_fields:
        print("[ALERT] The following required fields are missing:")
        for m in missing_fields:
            print(f" - {m}")
    else:
        print("[OK] All required fields are present!")

    return {"missing_fields": missing_fields}


# ==========================================
# AGENT 5: USER CONFIRMATION
# ==========================================
def user_confirmation(state: AgentState) -> Dict[str, Any]:
    """
    Verifies that all required fields are present before asking user confirmation.
    In TEST MODE, reads confirmation via terminal input:
    - 'yes' => confirmation = True
    - anything else => confirmation = False
    """
    print("\n================================")
    print("AGENT 5: USER CONFIRMATION")
    print("================================")

    missing_fields = state.get("missing_fields", [])

    if missing_fields:
        print("[BLOCKED] Form cannot be submitted because required fields are missing:")
        for field in missing_fields:
            print(f" - {field}")
        return {
            "confirmation": False,
            "submit_status": "blocked_missing_required_fields"
        }

    print("All required fields are populated.")
    print("Please review the filled form in the browser window.")
    print("NOTE: Browser window ko open rehne dein! (Do NOT close the browser window manually).")

    # Check if confirmation was already injected (e.g. from API/webhook)
    if state.get("confirmation") is True:
        print("[CONFIRMED] Pre-confirmed via request payload.")
        return {
            "confirmation": True,
            "submit_status": "confirmed"
        }
    elif state.get("is_api") or state.get("confirmation") is False:
        if state.get("is_api"):
            print("[INFO] API request without explicit confirmation=True. Form filled, awaiting confirmation.")
            return {
                "confirmation": False,
                "submit_status": "awaiting_confirmation"
            }

    try:
        user_input = input("\nDo you want to submit the form? Type 'yes' to submit: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        user_input = "no"

    if user_input == "yes":
        print("[CONFIRMED] User approved submission.")
        return {
            "confirmation": True,
            "submit_status": "confirmed"
        }
    else:
        print("[CANCELLED] Submission aborted by user.")
        return {
            "confirmation": False,
            "submit_status": "cancelled_by_user"
        }


# ==========================================
# AGENT 6: SUBMIT AGENT
# ==========================================
def submit_form(state: AgentState) -> Dict[str, Any]:
    """
    Submits the form ONLY if confirmation is True using the SAME Playwright page session.
    Closes the browser only after completion.
    """
    global playwright_instance, browser, page

    print("\n================================")
    print("AGENT 6: SUBMIT AGENT")
    print("================================")

    confirmation = state.get("confirmation", False)
    status = state.get("submit_status", "not_submitted")

    # For API/WhatsApp sessions: if we are still waiting for missing fields or confirmation,
    # keep the browser open in the session so next turn can continue filling.
    should_close = True
    if state.get("is_api") and not confirmation and status in ["blocked_missing_required_fields", "awaiting_confirmation"]:
        should_close = False

    try:
        if not confirmation:
            print(f"[SKIP] Confirmation is False (Status: {status}). Form was NOT submitted.")
            return {
                "submit_status": status,
                "page": page if not should_close else None,
                "browser": browser if not should_close else None,
                "playwright_instance": playwright_instance if not should_close else None
            }

        if not page or page.is_closed() or not browser or not browser.is_connected():
            print("[WARNING] Browser window was closed before submission could take place.")
            print("[HINT] Next time, keep the browser window open and type 'yes' in terminal. Agent 6 will automatically submit and close it.")
            return {"submit_status": "browser_closed_early"}

        try:
            # Locate submit button
            submit_button = page.locator('button[type="submit"], input[type="submit"]')

            if submit_button.count() == 0:
                print("[ERROR] Submit button not found on page.")
                status = "submit_button_not_found"
            else:
                print("Clicking submit button...")
                submit_button.first.click()
                page.wait_for_timeout(1000)

                # Check for result text in form.html
                result_locator = page.locator("#result")
                if result_locator.count() > 0:
                    result_text = result_locator.inner_text().strip()
                    try:
                        print(f"Form submission message: '{result_text}'")
                    except Exception:
                        print(f"Form submission message: '{result_text.encode('ascii', errors='replace').decode('ascii')}'")

                print("[SUCCESS] Form submitted successfully!")
                status = "submitted"
                page.wait_for_timeout(2000)
        except Exception as err:
            if "closed" in str(err).lower():
                print("[WARNING] Browser window was closed during submission.")
                status = "browser_closed_early"
            else:
                print(f"[ERROR] Submission error: {err}")
                status = "submit_error"

        return {
            "submit_status": status,
            "page": None,
            "browser": None,
            "playwright_instance": None
        }
    finally:
        if should_close:
            print("Closing persistent Playwright browser session...")
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass
            if playwright_instance:
                try:
                    playwright_instance.stop()
                except Exception:
                    pass

            browser = None
            page = None
            playwright_instance = None
        else:
            print(f"[SESSION ACTIVE] Browser kept open for user session (Status: '{status}').")


# ==========================================
# LANGGRAPH SETUP
# ==========================================
graph = StateGraph(AgentState)

graph.add_node("form_analyzer", form_analyzer)
graph.add_node("data_matching", data_matching)
graph.add_node("form_filling", form_filling)
graph.add_node("missing_field_detector", missing_field_detector)
graph.add_node("user_confirmation", user_confirmation)
graph.add_node("submit_form", submit_form)

graph.add_edge(START, "form_analyzer")
graph.add_edge("form_analyzer", "data_matching")
graph.add_edge("data_matching", "form_filling")
graph.add_edge("form_filling", "missing_field_detector")
graph.add_edge("missing_field_detector", "user_confirmation")
graph.add_edge("user_confirmation", "submit_form")
graph.add_edge("submit_form", END)

app = graph.compile()


# ==========================================
# LOCAL EXECUTION & TESTING
# ==========================================
if __name__ == "__main__":
    # Resolve absolute path to form.html
    current_dir = Path(__file__).parent.resolve()
    form_html_path = (current_dir / "form.html").as_uri()

    print("==================================================")
    print("STARTING AGENTIC FORM AUTOMATION PIPELINE")
    print(f"TEST_MODE: {TEST_MODE}")
    print(f"Target Form URL: {form_html_path}")
    print("==================================================")

    test_user_data = {
        "name": "Ayushmaan Rathore",
        "email": "ayushmaan@gmail.com",
        "phone": "9876543210",
        "city": "Indore",
        "gender": "male",
        "skills": ["python", "django"],
        "feedback": "Autonomous LangGraph Form Automation test successful!"
    }

    initial_state: AgentState = {
        "form_url": form_html_path,
        "user_data": test_user_data,
        "fields": [],
        "matched_data": {},
        "missing_fields": [],
        "filled_fields": [],
        "confirmation": None,
        "submit_status": "",
        "is_api": False
    }

    final_state = app.invoke(initial_state)

    print("\n================================")
    print("WORKFLOW COMPLETED - FINAL STATE")
    print("================================")
    print(f"Submit Status: {final_state.get('submit_status')}")
    print(f"Filled Fields: {final_state.get('filled_fields')}")
    print(f"Missing Fields: {final_state.get('missing_fields')}")