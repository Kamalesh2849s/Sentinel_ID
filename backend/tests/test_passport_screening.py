import requests
import time
import os
import json

BASE_URL = "http://127.0.0.1:8000/api"
doc_path = os.path.join(os.path.dirname(__file__), "..", "uploads", "doc_6dc722d2-9d87-4ad1-b672-bda872e21e3d.png")

assert os.path.exists(doc_path), f"File not found: {doc_path}"

with open(doc_path, "rb") as f:
    res = requests.post(f"{BASE_URL}/screenings", files={"document_image": f}, data={"document_type": "passport"})

assert res.status_code == 201, f"Failed create: {res.text}"
screening_id = res.json()["screening_id"]
print(f"Created screening: {screening_id}")

screening = None
for _ in range(40):
    time.sleep(1)
    res = requests.get(f"{BASE_URL}/screenings/{screening_id}")
    screening = res.json()
    status = screening.get("status")
    print(f"  Status: {status}")
    if status not in ["PROCESSING"]:
        break

print("\n=== SCREENING RESULT ===")
print("Status:", screening.get("status"))
print("Risk Score:", screening.get("risk_score"))
print("Risk Object:", json.dumps(screening.get("risk"), indent=2))
print("\nExtracted Document:")
print(json.dumps(screening.get("extracted_document"), indent=2))
print("\nMRZ Result:")
print(json.dumps(screening.get("mrz_result"), indent=2))
