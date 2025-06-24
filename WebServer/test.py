import requests
import os

# === Configuration ===
API_KEY = '@YourPassword123'
UPLOAD_URL = 'https://buckleywiley.com/Scribe/upload.php'  # ← Replace with your real domain

# Paths to test files
mp3_path = 'WebServer/test/sample12.mp3'
csv_path = 'WebServer/test/highlights.csv'

# === Check files exist ===
if not os.path.exists(mp3_path):
    print(f"Error: MP3 file not found: {mp3_path}")
    exit(1)

if not os.path.exists(csv_path):
    print(f"Error: CSV file not found: {csv_path}")
    exit(1)

# === Upload ===
files = {
    'file1': open(mp3_path, 'rb'),
    'file2': open(csv_path, 'rb'),
}
data = {
    'api_key': API_KEY
}

try:
    response = requests.post(UPLOAD_URL, files=files, data=data)
    print(f"Status: {response.status_code}")
    print("Response:\n", response.text)
except Exception as e:
    print("Upload failed:", e)
