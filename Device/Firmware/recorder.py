import os
import time
import uuid
import threading
import subprocess
import datetime
import glob
import requests
import math
from gpiozero import Button, PWMLED

# === CONFIG ===
DEVICE_ID = hex(uuid.getnode())[-6:]
AUDIO_DIR = '/home/pi/audio'
os.makedirs(AUDIO_DIR, exist_ok=True)

HIGHLIGHT_CSV = os.path.join(AUDIO_DIR, f'highlights_{DEVICE_ID}.csv')
UPLOAD_URL = 'https://buckleywiley.com/Scribe/upload.php'
API_KEY = '@YourPassword123'
BUTTON_HIGHLIGHT = Button(17)
BUTTON_UPLOAD = Button(27)
CHUNK_DURATION = 30 * 60  # 30 minutes
MAX_UPLOADED = 5

# === LED SETUP ===
led_r = PWMLED(22)
led_g = PWMLED(23)
led_b = PWMLED(24)

def set_led(r=0, g=0, b=0):
    led_r.value = r
    led_g.value = g
    led_b.value = b

def pulse_led(r=0, g=0, b=0, duration=10, delay=0.05):
    def pulser():
        start = time.time()
        while time.time() - start < duration:
            t = time.time() * 2
            brightness = (math.sin(t) + 1) / 2
            led_r.value = brightness * r
            led_g.value = brightness * g
            led_b.value = brightness * b
            time.sleep(delay)
        set_led(0, 0, 0)
    threading.Thread(target=pulser, daemon=True).start()

def set_error_led():
    set_led(r=1, g=0, b=0)

# === STATE ===
current_proc = None
highlight_lock = threading.Lock()
highlighting = []

# === AUDIO RECORDING ===
def start_new_recording():
    global current_proc
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M')
    filename = f"recording_{timestamp}_{DEVICE_ID}.wav"
    filepath = os.path.join(AUDIO_DIR, filename)

    print(f"[INFO] Starting recording: {filename}")
    current_proc = subprocess.Popen([
        'arecord', '-D', 'plughw:1,0', '-f', 'S16_LE',
        '-r', '16000', '-c', '1', filepath
    ])
    set_led(r=0, g=1, b=0)  # solid green
    return filepath

# === HIGHLIGHT BUTTON ===
def on_highlight_pressed():
    press_time = datetime.datetime.now()
    start_time = press_time - datetime.timedelta(minutes=2)
    end_time = press_time + datetime.timedelta(minutes=5)

    print(f"[HIGHLIGHT] Start: {start_time}, End: {end_time}")
    with highlight_lock:
        highlighting.append((start_time, press_time, end_time))

    with open(HIGHLIGHT_CSV, 'a') as f:
        f.write(f"{start_time},{press_time},{end_time}\n")

    pulse_led(r=0, g=1, b=0, duration=5*60)  # pulse green for 5 minutes

# === UPLOAD BUTTON ===
def on_upload_pressed():
    print("[UPLOAD] Button pressed.")
    upload_files()

BUTTON_HIGHLIGHT.when_pressed = on_highlight_pressed
BUTTON_UPLOAD.when_pressed = on_upload_pressed

# === FILE UPLOAD ===
def upload_files():
    files = {}

    # Add highlight CSV
    if os.path.exists(HIGHLIGHT_CSV):
        files['data'] = open(HIGHLIGHT_CSV, 'rb')

    # Add un-uploaded recordings
    for path in glob.glob(os.path.join(AUDIO_DIR, f'recording_*_{DEVICE_ID}.wav')):
        if '_uploaded' not in path:
            key = os.path.basename(path)
            files[key] = open(path, 'rb')

    if not files:
        print("[UPLOAD] Nothing to upload.")
        return

    data = {'api_key': API_KEY}
    try:
        print("[UPLOAD] Sending files...")
        pulse_led(r=0, g=0, b=1, duration=10)  # pulse blue
        response = requests.post(UPLOAD_URL, files=files, data=data)
        print(f"[UPLOAD] Response: {response.status_code} - {response.text}")

        if response.status_code == 200:
            for f in files:
                if f != 'data':
                    old = os.path.join(AUDIO_DIR, f)
                    new = old.replace('.wav', '_uploaded.wav')
                    os.rename(old, new)
            cleanup_old_recordings()
    except Exception as e:
        print("[UPLOAD] Failed:", e)
        set_error_led()

# === CLEANUP ===
def cleanup_old_recordings():
    uploaded_files = sorted(glob.glob(os.path.join(AUDIO_DIR, f'*_uploaded.wav')))
    if len(uploaded_files) > MAX_UPLOADED:
        for f in uploaded_files[:-MAX_UPLOADED]:
            print(f"[CLEANUP] Deleting old file: {f}")
            os.remove(f)

# === AUTO-UPLOAD THREAD ===
def auto_uploader():
    while True:
        time.sleep(CHUNK_DURATION)
        upload_files()

# === MAIN LOOP ===
def main():
    print(f"[SYSTEM] Recorder started. Device ID: {DEVICE_ID}")
    threading.Thread(target=auto_uploader, daemon=True).start()

    while True:
        try:
            if current_proc:
                current_proc.terminate()
                current_proc.wait()
            start_new_recording()
            time.sleep(CHUNK_DURATION)
        except Exception as e:
            print("[MAIN] Error:", e)
            set_error_led()
            time.sleep(10)

if __name__ == "__main__":
    main()
