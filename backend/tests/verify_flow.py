import requests
import time
import os
import json

BASE_URL = "http://127.0.0.1:8000/api"

# Pick a document image from uploads
uploads_dir = os.path.join(os.path.dirname(__file__), "..", "uploads")
doc_files = [f for f in os.listdir(uploads_dir) if f.startswith("doc_") and f.endswith(".jpg") and not f.endswith("_preprocessed.png")]
doc_path = os.path.join(uploads_dir, doc_files[0]) if doc_files else None

person_files = [f for f in os.listdir(uploads_dir) if f.startswith("person_") and f.endswith(".jpg")]
person_path = os.path.join(uploads_dir, person_files[0]) if person_files else None

print(f"[TEST SETUP] Using doc_path: {doc_path}")
print(f"[TEST SETUP] Using person_path: {person_path}")

assert doc_path and os.path.exists(doc_path), "No doc image found"

# ── TEST 1 & 2: Create screening WITHOUT person verification ──────────────────
print("\n=== RUNNING TEST 1 & 2: Create screening without person verification ===")
with open(doc_path, "rb") as f:
    res = requests.post(f"{BASE_URL}/screenings", files={"document_image": f}, data={"document_type": "passport"})

assert res.status_code == 201, f"Failed create: {res.text}"
create_data = res.json()
screening_id = create_data["screening_id"]
print(f"[TEST 1] Screening created: id={screening_id}, status={create_data['status']}")

# Poll until background processing of document is complete
print("[TEST 2] Polling screening until document processing completes...")
screening = None
for _ in range(30):
    time.sleep(1)
    res = requests.get(f"{BASE_URL}/screenings/{screening_id}")
    screening = res.json()
    status = screening.get("status")
    print(f"  Current status: {status}, risk_score: {screening.get('risk_score')}, risk_status: {screening.get('risk', {}).get('status')}")
    if status != "PROCESSING":
        break

print("\n--- Document Processing Finished ---")
print(f"Final Status: {screening.get('status')}")
print(f"Risk Score: {screening.get('risk_score')} (MUST BE None/null, NOT 0!)")
print(f"Risk object: {json.dumps(screening.get('risk'), indent=2)}")
print(f"Extracted Document Fields: {list(screening.get('extracted_document', {}).keys()) if screening.get('extracted_document') else 'None'}")
print(f"MRZ Detected: {screening.get('mrz_result', {}).get('mrz_detected') if screening.get('mrz_result') else 'None'}")
print(f"Identity Verification Status: {screening.get('identity_verification', {}).get('status') if screening.get('identity_verification') else 'None'}")

# Assertions for TEST 1 & 2
assert screening["risk_score"] is None, f"FAIL: risk_score should be None, but got {screening['risk_score']}"
assert screening["risk"]["status"] == "pending", f"FAIL: risk.status should be pending, got {screening['risk']['status']}"
assert screening["risk"]["score"] is None, f"FAIL: risk.score should be None, got {screening['risk']['score']}"
assert screening["status"] == "PENDING", f"FAIL: screening status should be PENDING, got {screening['status']}"
assert screening.get("extracted_document") is not None, "FAIL: extracted_document should be populated"
print("[TEST 1 & 2 PASSED] Incomplete screening has risk_score=None, risk_status=pending, and extracted document fields!")

# ── TEST 3 & 4: Complete Person Verification via Camera/Photo ────────────────
if person_path and os.path.exists(person_path):
    print("\n=== RUNNING TEST 3 & 4: Complete Person Verification ===")
    with open(person_path, "rb") as pf:
        id_res = requests.post(
            f"{BASE_URL}/screenings/{screening_id}/identity/verify",
            files=[("frames", ("person.jpg", pf.read(), "image/jpeg"))],
            data={"is_upload": "true"}
        )
    print(f"Verify response status: {id_res.status_code}")
    id_data = id_res.json()
    print(f"Identity Result: {json.dumps(id_data, indent=2)}")

    # Fetch updated screening
    res = requests.get(f"{BASE_URL}/screenings/{screening_id}")
    s_updated = res.json()
    print("\n--- Updated Screening After Identity Verification ---")
    print(f"Screening Status: {s_updated.get('status')}")
    print(f"Risk Score: {s_updated.get('risk_score')}")
    print(f"Risk Level: {s_updated.get('risk', {}).get('level')}")
    print(f"Risk Status: {s_updated.get('risk', {}).get('status')}")
    print(f"Reasons count: {len(s_updated.get('risk', {}).get('reasons', []))}")
    if s_updated.get('risk', {}).get('reasons'):
        print(f"First reason: {s_updated['risk']['reasons'][0]}")

    assert s_updated["risk_score"] is not None, "FAIL: risk_score should be calculated numeric score"
    assert s_updated["risk"]["status"] == "completed", "FAIL: risk.status should be completed"
    assert isinstance(s_updated["risk_score"], (int, float)), "FAIL: risk_score must be a number"
    for r in s_updated["risk"]["reasons"]:
        assert "signal" in r, "Reason must have signal"
        assert "result" in r, "Reason must have result"
        assert "impact" in r, "Reason must have impact"
    print("[TEST 3 & 4 PASSED] Final risk score successfully calculated with deterministic signals!")

    # ── TEST 5: Refresh/Re-fetch Result ──────────────────────────────────────────
    print("\n=== RUNNING TEST 5: Verify Persistence on Refresh ===")
    res_refresh = requests.get(f"{BASE_URL}/screenings/{screening_id}")
    s_refreshed = res_refresh.json()
    assert s_refreshed["risk_score"] == s_updated["risk_score"], "FAIL: Persisted score does not match"
    assert s_refreshed["risk"]["score"] == s_updated["risk"]["score"], "FAIL: Persisted risk object score does not match"
    print(f"[TEST 5 PASSED] Score {s_refreshed['risk_score']} successfully persisted and verified on reload!")

print("\nALL VERIFICATION TESTS COMPLETED SUCCESSFULLY!")
