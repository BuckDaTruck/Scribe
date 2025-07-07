import os
import time
import uuid
import threading
import subprocess
import datetime
import glob
import requests
import math
import logging
from gpiozero import Button, PWMLED

# === CONFIG ===
DEVICE_ID = "Buckley-Scribe-v1.1"
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
AUDIO_DIR = SCRIPT_DIR
os.makedirs(AUDIO_DIR, exist_ok=True)

UPLOAD_URL = 'https://buckleywiley.com/Scribe/upload2.php'
API_KEY = '@YourPassword123'
BUTTON_HIGHLIGHT = Button(27, bounce_time=0.1)
BUTTON_UPLOAD = Button(17, bounce_time=0.1)
CHUNK_DURATION = 0.5 * 60  # 30 minutes, unused but retained
MAX_UPLOADED = 5
last_upload_time = 0
UPLOAD_DEBOUNCE_SEC = 2.0  # Prevent triggering more than once every 2 seconds

# === LOGGING SETUP ===
LOG_PATH = os.path.join(SCRIPT_DIR, 'scribe.log')
logging.basicConfig(
    filename=LOG_PATH,
    filemode='a',
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    level=logging.INFO
)

def log(message, level='info'):
    print(message)
    getattr(logging, level)(message)

# === LED SETUP ===
led_r = PWMLED(24)
led_g = PWMLED(23)
led_b = PWMLED(22)

def set_led(r=0, g=0, b=0):
    led_r.value = r
    led_g.value = g
    led_b.value = b

def pulse_led(r=0, g=0, b=0, duration=10, delay=0.05):
    stop_event = threading.Event()
    def pulser():
        start = time.time()
        while time.time() - start < duration and not stop_event.is_set():
            t = time.time() * 2
            brightness = (math.sin(t) + 1) / 2
            led_r.value = brightness * r
            led_g.value = brightness * g
            led_b.value = brightness * b
            time.sleep(delay)
        if not stop_event.is_set():
            set_led(0, 0, 0)
    thread = threading.Thread(target=pulser, daemon=True)
    thread.start()
    return stop_event

# === TRIPLE TAP DETECTION / IDLE MODE ===
idle_mode = False
pulse_event = threading.Event()

def idle_led_pulse():
    while not pulse_event.is_set():
        for _ in range(100):
            if pulse_event.is_set(): return
            val = (math.sin(time.time() * 2) + 1) / 2
            led_g.value = val
            led_b.value = 1 - val
            time.sleep(0.05)
        set_led(0, 0, 0)

# === UTILS ===
def quick_flash(r=0, g=0, b=0, duration=0.2):
    set_led(r, g, b)
    time.sleep(duration)
    set_led(0, 0, 0)

def set_error_led():
    set_led(r=1, g=0, b=0)

def startup_sequence():
    log("[SYSTEM] Running startup LED sequence...")
    colors = [
        (1, 0, 0), (1, 0.5, 0), (1, 1, 0), (0, 1, 0),
        (0, 0, 1), (0.29, 0, 0.51), (0.56, 0, 1),
    ]
    for r, g, b in colors:
        set_led(r, g, b)
        time.sleep(0.2)
    set_led(0, 0, 0)
    time.sleep(0.3)
    set_led(1, 1, 1)
    time.sleep(0.2)
    set_led(0, 0, 0)
    log("[SYSTEM] LED sequence complete.")

# === STATE ===
highlight_lock = threading.Lock()
highlighting = []
highlight_led_stop = None
current_csv_path = None
session_id = uuid.uuid4().hex[:8]
session_part = 1

# === AUDIO STREAMING ===
def stream_audio():
    """
    Continuously record, amplify, and stream audio chunks to the server.
    """
    # arecord -> sox pipeline
    arecord = subprocess.Popen([
        'arecord', '-D', 'plughw:1,0', '-f', 'S16_LE', '-r', '88200', '-c', '1', '-t', 'raw', '-q', '-'
    ], stdout=subprocess.PIPE)
    sox = subprocess.Popen([
        'sox', '-t', 'raw', '-r', '16000', '-e', 'signed', '-b', '16', '-c', '1', '-',
        '-t', 'wav', '-', 'gain', '10'
    ], stdin=arecord.stdout, stdout=subprocess.PIPE)

    while True:
        if idle_mode:
            time.sleep(0.1)
            continue
        chunk = sox.stdout.read(1024)
        if not chunk:
            break
        files = {'audio_chunk': ('audio.wav', chunk, 'audio/wav')}
        data = {'api_key': API_KEY, 'device_id': DEVICE_ID, 'session_id': session_id}
        try:
            r = requests.post(UPLOAD_URL, files=files, data=data)
            log(f"[STREAM] Chunk upload status: {r.status_code}")
        except Exception as e:
            log(f"[STREAM] Error uploading chunk: {e}", level='error')
        time.sleep(0.1)

# === HIGHLIGHT BUTTON ===
def on_highlight_pressed():
    global highlight_led_stop, current_csv_path
    press_time = datetime.datetime.now()
    start_time = press_time - datetime.timedelta(seconds=10)
    end_time = press_time + datetime.timedelta(seconds=10)

    log(f"[HIGHLIGHT] Start: {start_time}, End: {end_time}")
    with highlight_lock:
        highlighting.append((start_time, press_time, end_time))
    if current_csv_path:
        with open(current_csv_path, 'a') as f:
            f.write(f"{start_time},{press_time},{end_time}\n")
    if highlight_led_stop:
        highlight_led_stop.set()
        set_led(r=0, g=1, b=0)
    highlight_led_stop = pulse_led(r=0, g=1, b=0, duration=5*60)

# === CSV UPLOAD ===
def upload_csv():
    global highlight_led_stop
    csvs = glob.glob(os.path.join(AUDIO_DIR, "*.csv"))
    path = csvs[0] if csvs else None
    if not path:
        log("[UPLOAD] No CSV to upload", level='warning')
        return
    files = {'file': open(path, 'rb')}
    data = {'api_key': API_KEY, 'device_id': DEVICE_ID, 'session_id': session_id}
    try:
        r = requests.post(UPLOAD_URL, files=files, data=data)
        log(f"[UPLOAD] CSV status: {r.status_code}")
        if r.status_code == 200:
            os.remove(path)
            quick_flash(b=1)
        else:
            quick_flash(r=1)
    except Exception as e:
        log(f"[UPLOAD] CSV upload error: {e}", level='error')
    finally:
        files['file'].close()

# === UPLOAD BUTTON ===
def on_upload_pressed():
    global idle_mode, last_upload_time, pulse_event
    now = time.time()
    if now - last_upload_time < UPLOAD_DEBOUNCE_SEC:
        log("[UPLOAD] Debounced press ignored.")
        return
    last_upload_time = now

    if not idle_mode:
        # enter idle
        log("[UPLOAD] Entering idle mode; uploading CSV.")
        idle_mode = True
        pulse_event.clear()
        threading.Thread(target=idle_led_pulse, daemon=True).start()
        upload_csv()
    else:
        # resume streaming
        log("[UPLOAD] Resuming streaming.")
        idle_mode = False
        pulse_event.set()
        set_led(0,0,0)

BUTTON_HIGHLIGHT.when_pressed = on_highlight_pressed
BUTTON_UPLOAD.when_pressed = on_upload_pressed

# === MAIN LOOP ===
def main():
    global current_csv_path
    print("[SYSTEM] Starting Scribe Recorder...")
    log(f"[SYSTEM] Recorder started. Device ID: {DEVICE_ID}")
    current_csv_path = os.path.join(AUDIO_DIR, f"{session_id}_Highlights.csv")

    startup_sequence()
    threading.Thread(target=stream_audio, daemon=True).start()

    while True:
        time.sleep(1)

if __name__ == "__main__":
    main()
