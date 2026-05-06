"""Test worksheet generation endpoint with teacher account."""
import requests
import sys

BASE = "http://127.0.0.1:8000"
EMAIL = "test1@gmail.com"
PASSWORD = "123456789aA!"

print("=" * 70)
print("TESTING WORKSHEET GENERATION ENDPOINT")
print("=" * 70)
print()

# Step 1: Login
print(f"1. Logging in as {EMAIL}...")
try:
    login_response = requests.post(
        f"{BASE}/api/v1/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        timeout=10
    )
    if login_response.status_code != 200:
        print(f"   ❌ Login failed!")
        print(f"   Status: {login_response.status_code}")
        print(f"   Response: {login_response.text}")
        sys.exit(1)
    
    token = login_response.json()["access_token"]
    print(f"   ✅ Login successful")
except Exception as e:
    print(f"   ❌ Login failed: {e}")
    sys.exit(1)

print()

# Step 2: Get content packs to use for worksheet generation
print("2. Getting content packs...")
try:
    packs_response = requests.get(
        f"{BASE}/api/v1/admin/content-packs?is_active=true",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10
    )
    if packs_response.status_code != 200:
        print(f"   ❌ Failed to get content packs!")
        print(f"   Status: {packs_response.status_code}")
        print(f"   Response: {packs_response.text}")
        sys.exit(1)
    
    packs = packs_response.json()
    if not packs:
        print("   ❌ No content packs available!")
        sys.exit(1)
    
    pack_id = packs[0].get('id')
    pack_name = packs[0].get('name')
    print(f"   ✅ Found {len(packs)} content packs")
    print(f"   Using pack: {pack_name} (ID: {pack_id})")
except Exception as e:
    print(f"   ❌ Error: {e}")
    sys.exit(1)

print()

# Step 3: Test worksheet generation endpoint
print("3. Testing worksheet generation endpoint...")
print(f"   URL: {BASE}/api/v1/worksheets/generate")
print(f"   Method: POST")
print()

request_data = {
    "pack_id": pack_id,
    "topic_text": "Introduction to fractions",
    "grade": "6",
    "subject": "Mathematics",
    "num_questions": 5,
    "difficulty_mix": {
        "easy": 0.4,
        "medium": 0.4,
        "hard": 0.2
    },
    "question_types": ["mcq", "short_answer"]
}

print(f"   Request data:")
print(f"   - Pack ID: {pack_id}")
print(f"   - Topic: {request_data['topic_text']}")
print(f"   - Grade: {request_data['grade']}")
print(f"   - Subject: {request_data['subject']}")
print(f"   - Questions: {request_data['num_questions']}")
print()

try:
    generate_response = requests.post(
        f"{BASE}/api/v1/worksheets/generate",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        },
        json=request_data,
        timeout=60  # Worksheet generation might take time
    )
    
    print(f"   Status Code: {generate_response.status_code}")
    print()
    
    if generate_response.status_code == 200:
        worksheet = generate_response.json()
        print(f"   ✅ SUCCESS! Worksheet generated!")
        print(f"   Worksheet ID: {worksheet.get('id')}")
        print(f"   Questions: {len(worksheet.get('questions', []))}")
        print(f"   Topic: {worksheet.get('topic_text')}")
    elif generate_response.status_code == 403:
        print(f"   ❌ FORBIDDEN - Authorization failed!")
        print(f"   Response: {generate_response.text}")
        print()
        print("   This means the endpoint requires specific roles.")
        print("   Checking route configuration...")
    elif generate_response.status_code == 401:
        print(f"   ❌ UNAUTHORIZED - Authentication failed!")
        print(f"   Response: {generate_response.text}")
    else:
        print(f"   ❌ FAILED!")
        print(f"   Response: {generate_response.text}")
        
except requests.exceptions.Timeout:
    print(f"   ⏱️  Request timed out (worksheet generation takes time)")
    print(f"   This might be normal if the endpoint is processing.")
except Exception as e:
    print(f"   ❌ Error: {e}")
    if hasattr(e, 'response') and e.response:
        print(f"   Status: {e.response.status_code}")
        print(f"   Response: {e.response.text}")

print()
print("=" * 70)
print("TEST COMPLETE")
print("=" * 70)
