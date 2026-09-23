import os
import re
import json
from typing import Dict, Any, Tuple, Optional, List

CITIES = [
    "indore", "bhopal", "ujjain", "dewas", "delhi", "mumbai", "pune", 
    "bangalore", "bengaluru", "hyderabad", "chennai", "kolkata", "jaipur", 
    "lucknow", "ahmedabad", "patna", "chandigarh", "surat", "gwalior", "jabalpur"
]

SKILLS_LIST = [
    "python", "django", "ml", "machine learning", "ai", "artificial intelligence",
    "data science", "react", "javascript", "java", "c++", "c#", "html", "css",
    "node", "sql", "aws", "docker"
]

COURSES_LIST = [
    "b.tech cs", "b.tech it", "b.tech computer science", "b.tech", "bca", "mca",
    "m.tech", "b.sc", "bsc", "msc", "m.sc", "b.com", "bcom", "mba", "bba"
]

FEEDBACK_PHRASES = [
    "no comment", "no comments", "none", "nil", "na", "n/a", "nothing", 
    "all good", "good", "great", "awesome", "satisfactory", "kuch nahi", 
    "no feedback", "none of above", "test"
]


def parse_whatsapp_message(text: str, missing_fields: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Universal entity & intent parser for WhatsApp form automation.
    Handles:
    - Normal Forms, Dynamic Forms, University Exam Forms, Quiz/MCQ Forms
    - Auto-answer intents ('solve', 'auto answer', etc.)
    - Alphanumeric Roll numbers, Courses, Question answers, Key-Values, and Free text.
    """
    cleaned = text.strip()
    lower_text = cleaned.lower()

    # 0. Check for Greeting / Initial Start intent
    greetings = [
        "hi", "hello", "hey", "namaste", "start", "shuru", "shuru karo", 
        "hii", "helo", "yo", "good morning", "good evening", "namaskar"
    ]
    if lower_text in greetings:
        return {
            "intent": "greeting",
            "form_url": None,
            "user_data": {}
        }

    # 1. Check for Reset / Restart intent
    if lower_text in ["reset", "start over", "restart", "new form", "clear"]:
        return {
            "intent": "reset",
            "form_url": None,
            "user_data": {}
        }

    # 2. Check for Confirmation intent
    confirm_phrases = [
        "submit form", "submit", "yes", "yes, submit", "confirm",
        "proceed", "submit kr do", "submit kar do", "yes submit", "ok submit",
        "btn_submit", "btn_confirm", "ha", "haan", "done", "ok", "kardo", "send"
    ]
    if lower_text in confirm_phrases:
        return {
            "intent": "confirm",
            "form_url": None,
            "user_data": {}
        }

    # 3. Check for Cancellation intent
    cancel_phrases = [
        "no", "cancel", "don't submit", "dont submit", "abort",
        "stop", "mat karo", "cancel form", "reject", "nahi", "nahin", "ruk jao",
        "btn_cancel", "btn_abort"
    ]
    if lower_text in cancel_phrases:
        return {
            "intent": "cancel",
            "form_url": None,
            "user_data": {}
        }

    user_data: Dict[str, Any] = {}

    # Check for Auto-Answer / Solve intent for Exam / Quiz Forms
    auto_solve_keywords = [
        "auto answer", "solve", "solve exam", "exam solve", "answer them", 
        "answers fill", "answers bhar do", "all answers", "solve form", 
        "answers de do", "answer do", "auto solve", "answer deskta"
    ]
    if any(kw in lower_text for kw in auto_solve_keywords):
        user_data["_auto_answer"] = True

    # 4. Extract Form URL (if present)
    form_url = None
    url_match = re.search(r'(https?://[^\s]+|file:///[^\s]+)', cleaned, re.IGNORECASE)
    if url_match:
        raw_matched_url = url_match.group(1).strip()
        form_url = raw_matched_url.rstrip('*_`"\'\n\r ').strip()

    working_text = cleaned
    if url_match:
        working_text = working_text.replace(raw_matched_url, "")
    working_text = re.sub(r'(?i)\bform\s*:\s*', '', working_text)

    # 5. Extract Direct Email
    email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', working_text)
    if email_match:
        user_data["email"] = email_match.group(0).strip()
        working_text = working_text.replace(email_match.group(0), " ")

    # 6. Extract Direct Indian / 10-digit Phone Number
    phone_match = re.search(r'(?:(?:\+|0{0,2})91[\s-]?)?\b([6-9]\d{9})\b', working_text)
    if phone_match:
        user_data["phone"] = phone_match.group(1).strip()
        working_text = working_text.replace(phone_match.group(0), " ")

    # 7. Extract Roll Number (e.g. 0827CS201045 or CS2024001)
    roll_match = re.search(r'\b(\d{2,4}[A-Za-z]{2,6}\d{2,8})\b', working_text)
    if roll_match and "roll_number" not in user_data:
        user_data["roll_number"] = roll_match.group(1).strip()
        working_text = working_text.replace(roll_match.group(0), " ")

    # 8. Extract Explicit Key-Value Pairs
    lines = [l.strip() for l in working_text.split("\n") if l.strip()]
    unmatched_lines = []

    for line in lines:
        kv_match = re.match(r'^([^:=]+)[:=]\s*(.+)$', line)
        if kv_match:
            key = kv_match.group(1).strip().lower()
            val = kv_match.group(2).strip()

            # Academic & Exam keys
            if "roll" in key or "enroll" in key or "reg" in key:
                key = "roll_number"
            elif "father" in key:
                key = "father_name"
            elif "mother" in key:
                key = "mother_name"
            elif "course" in key or "branch" in key:
                key = "course"
            elif "center" in key or "exam_center" in key:
                key = "exam_center"
            elif "subject" in key or "paper" in key:
                key = "subject"
            elif "sem" in key:
                key = "semester"
            # Exam Questions (Q1, Q2, etc.)
            elif re.match(r'^(?:q|question)\s*(\d+)$', key):
                q_num = re.match(r'^(?:q|question)\s*(\d+)$', key).group(1)
                key = f"q{q_num}"
            # Standard keys
            elif "name" in key:
                key = "name"
            elif "mail" in key:
                key = "email"
            elif "phone" in key or "mobile" in key:
                key = "phone"
            elif "city" in key:
                key = "city"
            elif "gender" in key:
                key = "gender"
            elif "skill" in key:
                key = "skills"
            elif "feedback" in key or "comment" in key or "msg" in key:
                key = "feedback"

            if "," in val and key in ["skills", "technologies", "hobbies"]:
                user_data[key] = [item.strip() for item in val.split(",") if item.strip()]
            else:
                user_data[key] = val
        else:
            unmatched_lines.append(line)

    # 9. Check unmatched lines for direct values
    still_unmatched = []
    for line in unmatched_lines:
        line_lower = line.lower().strip()
        matched = False

        # 9a. Direct Course match (e.g. B.Tech CS, BCA, MCA)
        for c in COURSES_LIST:
            if re.search(r'\b' + re.escape(c) + r'\b', line_lower):
                user_data["course"] = c.upper() if len(c) <= 4 else c.title()
                matched = True
                break
        if matched:
            continue

        # 9b. Direct City / Center match
        for city in CITIES:
            if re.search(r'\b' + re.escape(city) + r'\b', line_lower):
                # If exam_center is expected, or default to city
                if missing_fields and "exam_center" in missing_fields and "exam_center" not in user_data:
                    user_data["exam_center"] = city.capitalize()
                elif "city" not in user_data:
                    user_data["city"] = city.capitalize()
                matched = True
                break
        if matched:
            continue

        # 9c. Direct Feedback / Comment match
        for fb in FEEDBACK_PHRASES:
            if fb in line_lower:
                user_data["feedback"] = line.strip()
                matched = True
                break
        if matched:
            continue

        # 9d. Direct Gender match
        gender_match = re.search(r'\b(male|female|other)\b', line_lower)
        if gender_match and "gender" not in user_data:
            user_data["gender"] = gender_match.group(1).lower()
            matched = True
            continue

        # 9e. Direct Skills match
        found_skills = []
        for skill in SKILLS_LIST:
            if re.search(r'\b' + re.escape(skill) + r'\b', line_lower):
                found_skills.append(skill)
        if found_skills:
            user_data.setdefault("skills", [])
            for s in found_skills:
                if s not in user_data["skills"]:
                    user_data["skills"].append(s)
            matched = True
            continue

        still_unmatched.append(line)

    # 10. Context-Aware Sequential Matching for Missing Fields
    if still_unmatched and missing_fields:
        unfilled_needed = [f for f in missing_fields if f not in user_data]
        for line in still_unmatched:
            clean_line = line.strip()
            if not clean_line:
                continue

            if unfilled_needed:
                target_field = unfilled_needed.pop(0)
                # Format name nicely
                if target_field in ["name", "father_name", "mother_name"]:
                    user_data[target_field] = clean_line.title()
                else:
                    user_data[target_field] = clean_line
            elif "name" not in user_data and re.match(r'^[A-Za-z\s]{2,40}$', clean_line):
                user_data["name"] = clean_line.title()
    elif still_unmatched:
        # If no missing_fields context, fallback to person name if looks like a name
        for line in still_unmatched:
            clean_line = line.strip()
            if "name" not in user_data and re.match(r'^[A-Za-z\s]{2,40}$', clean_line):
                if clean_line.lower() not in ["form", "link", "submit", "test", "demo", "none", "auto answer", "solve"]:
                    user_data["name"] = clean_line.title()
                    break

    return {
        "intent": "form_data",
        "form_url": form_url,
        "user_data": user_data
    }
