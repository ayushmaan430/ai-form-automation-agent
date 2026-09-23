from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

llm = ChatGoogleGenerativeAI(
    model="gemini-3.6-flash"
)

def automate_form(form_url, user_data):

    with sync_playwright() as p:

        browser = p.chromium.launch(headless=False)

        page = browser.new_page()
        # form_url = input("Enter form URL: ")

        page.goto(form_url)

        #page.goto("file:///C:/Users/ayush/OneDrive/Attachments/Desktop/form/form.html")

        # User ka data
        # user_data = {
        #     "name": "Ayushmaan Rathore",
        #     "email": "ayushmaan@gmail.com",
        #     "phone": "9876543210",
        #     "city": "Indore",
        #     "gender": "male",
        #     "skills": ["python", "django"],
        #     "feedback": "This is my feedback."
        # }

        # Form ke saare input fields
        

        # for radio button
        inputs = page.locator('input:not([type="radio"])')

        print("Total inputs:", inputs.count())

        city = user_data.get("city")

        missing_fields = []

        # Har input ko inspect karna
        for i in range(inputs.count()):

            field = inputs.nth(i)

            field_type = field.get_attribute("type")
            field_name = field.get_attribute("name")
            placeholder = field.get_attribute("placeholder")

            field_info = {
                "type": field_type,
                "name": field_name,
                "placeholder": placeholder
            }

            prompt = f"""
            Identify what information this form field is asking for.

            Field:
            {field_info}

            Return only one word:
            name, email, phone, age, city, address, gender, unknown
            """

            response = llm.invoke(prompt)

            field_meaning = response.content[0]["text"].strip().lower()
            print("Field:", field_info)
            print("Meaning:", field_meaning)

            #missing_fields = []

            if field_meaning in user_data:
                value = user_data[field_meaning]
                field.fill(value)
                print("Filled:", value)
            else:
                if field.get_attribute("required") is not None:
                    missing_fields.append(field_meaning)
                    print("Missing:", field_meaning)

        # Dropdowns detect karna
        selects = page.locator("select")

        print("Total dropdowns:", selects.count())

        for i in range(selects.count()):

            dropdown = selects.nth(i)

            dropdown_name = dropdown.get_attribute("name")

            print("Dropdown:", dropdown_name)

            options = dropdown.locator("option")

            for j in range(options.count()):

                option = options.nth(j)

                print("Option:", option.inner_text())



        for i in range(selects.count()):

            dropdown = selects.nth(i)

            dropdown.select_option(label=city)

        print("Selected city:", city)


        # Radio button

        radios = page.locator('input[type="radio"]')
        print("Total radio buttons:", radios.count())

        gender = user_data.get("gender")

        if gender:

            for i in range(radios.count()):

                radio = radios.nth(i)

                if radio.get_attribute("value") == gender:

                    radio.check()

                    print("Selected gender:", gender)

                # Checkboxes

        checkboxes = page.locator('input[type="checkbox"]')

        skills = user_data.get("skills", [])

        print("Total checkboxes:", checkboxes.count())

        for i in range(checkboxes.count()):

            checkbox = checkboxes.nth(i)

            value = checkbox.get_attribute("value")

            if value in skills:
                checkbox.check()
                print("Selected skill:", value)




            # Textarea detect karna



        textareas = page.locator("textarea")

        print("Total textareas:", textareas.count())

        for i in range(textareas.count()):

            textarea = textareas.nth(i)

            field_info = {
                "type": "textarea",
                "name": textarea.get_attribute("name"),
                "placeholder": textarea.get_attribute("placeholder")
            }

            print("Textarea:", field_info)

            prompt = f"""
            Identify what information this textarea is asking for.

            Field:
            {field_info}

            Return only one word:
            feedback, summary, address, description, message, unknown
            """

            response = llm.invoke(prompt)

            field_meaning = response.content[0]["text"].strip().lower()

            print("Meaning:", field_meaning)

            if field_meaning in user_data:

                value = user_data[field_meaning]

                textarea.fill(value)

                print("Filled:", value)

            else:

                if textarea.get_attribute("required") is not None:

                    missing_fields.append(field_meaning)

                    print("Missing:", field_meaning)



        # Final form status


        print("\n--- FORM STATUS ---")

        if missing_fields:

            print("Missing required fields:")

            for field in missing_fields:

                print("-", field)

        else:

            print("All required fields are available.")

        return {
            "missing_fields": missing_fields
        }
                    

    # User confirmation

    # confirmation = input("\nType 'Submit Form' to submit: ")

    # if confirmation.strip().lower() == "submit form":

    #     submit_button = page.locator("button[type='submit']")

    #     if submit_button.count() > 0:
    #         submit_button.click()
    #         print("Form submitted successfully")

    # else:
    #     print("Form submission cancelled.")

# browser.close()
