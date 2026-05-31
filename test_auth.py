import os
import requests
from dotenv import load_dotenv

load_dotenv()
key = os.getenv("GEMINI_API_KEY")

if not key:
    print("Error: GEMINI_API_KEY not found in environment!")
    exit(1)

print(f"Testing key starting with: {key[:10]}... (length {len(key)})")

payload = {
    "contents": [{"parts": [{"text": "Hello, respond with the word 'OK'."}]}]
}

# Test 1: Query Parameter (v1)
url1 = f"https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent?key={key}"
try:
    r1 = requests.post(url1, json=payload)
    print("\n--- Test 1 (Query Parameter /v1) ---")
    print("Status:", r1.status_code)
    print("Response:", r1.text[:300])
except Exception as e:
    print("Test 1 error:", e)

# Test 2: x-goog-api-key Header (v1)
url2 = "https://generativelanguage.googleapis.com/v1/models/gemini-2.5-flash:generateContent"
headers2 = {
    "x-goog-api-key": key,
    "Content-Type": "application/json"
}
try:
    r2 = requests.post(url2, json=payload, headers=headers2)
    print("\n--- Test 2 (x-goog-api-key Header /v1) ---")
    print("Status:", r2.status_code)
    print("Response:", r2.text[:300])
except Exception as e:
    print("Test 2 error:", e)

# Test 3: Query Parameter (v1beta)
url3 = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}"
try:
    r3 = requests.post(url3, json=payload)
    print("\n--- Test 3 (Query Parameter /v1beta) ---")
    print("Status:", r3.status_code)
    print("Response:", r3.text[:300])
except Exception as e:
    print("Test 3 error:", e)

# Test 4: Bearer Token Auth (v1)
headers4 = {
    "Authorization": f"Bearer {key}",
    "Content-Type": "application/json"
}
try:
    r4 = requests.post(url2, json=payload, headers=headers4)
    print("\n--- Test 4 (Bearer Token Auth /v1) ---")
    print("Status:", r4.status_code)
    print("Response:", r4.text[:300])
except Exception as e:
    print("Test 4 error:", e)
