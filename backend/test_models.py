import time
import google.generativeai as genai
import config

genai.configure(api_key=config.GEMINI_API_KEY, transport="rest")

for name in [
    "gemini-flash-lite-latest",
    "gemini-3.1-flash-lite",
    "gemini-flash-latest",
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
]:
    t = time.time()
    try:
        r = genai.GenerativeModel(name).generate_content(
            "Say hello in one word.", request_options={"timeout": 20}
        )
        print("OK  ", name, round(time.time() - t, 1), "s ->", r.text.strip())
    except Exception as e:
        print("FAIL", name, round(time.time() - t, 1), "s ->", str(e)[:110])