from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
load_dotenv()

llm=ChatGoogleGenerativeAI(model="gemini-3.6-flash")

field = {
    "type": "text",
    "name": "name",
    "placeholder": ""
}

prompt = f"""
You are a form field identification agent.

Identify what information this form field is asking for.

Field:
{field}

Return only one word from:
name, email, phone, age, city, address, gender, unknown
"""

response = llm.invoke(prompt)

print("Field meaning:", response.content)

