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

# Updated endpoint for streaming and CSV uploads
UPLOAD_URL = 'https://buckleywiley.com/Scribe/upload2.php'
API_KEY = '@YourPassword123'
# Button assignments: GPIO17 = blue button (upload/pause), GPIO27 = green button (highlight)
BUTTON_HIGHLIGHT = Button(27, bounce_time=0.1)  # Green button
BUTTON_UPLOAD = Button(17, bounce_time=0.1)     # Blue button
UPLOAD_DEBOUNCE_SEC = 2.0  # Prevent triggering more than once every 2 seconds

# Chunk settings to upload ~4s of audio per upload
SAMPLE_RATE = 88200            # samples per second
BYTES_PER_SAMPLE = 2           # 16-bit audio => 2 bytes
CHUNK_DURATION_SEC = 2         # seconds per chunk
CHUNK_SIZE = SAMPLE_RATE * BYTES_PER_SAMPLE * CHUNK_DURATION_SEC  # bytes per chunk

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

# === IDLE MODE ===
idle_mode = False
pulse_event = threading.Event()

def idle_led_pulse():
    while not pulse_event.is_set():
        for _ in range(100):
            if pulse_event.is_set():
                return
            val = (math.sin(time.time() * 2) + 1) / 2
            led_g.value = val
            led_b.value = 1 - val
            time.sleep(0.05)
        set_led(0, 0, 0)

# === UTILITIES ===
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

# === AUDIO STREAMING ===
def stream_audio():
    # Start pipelined recording and amplification (raw PCM in/out)
    arecord = subprocess.Popen([
        'arecord', '-D', 'plughw:1,0', '-f', 'S16_LE', '-r', str(SAMPLE_RATE), '-c', '1', '-t', 'raw', '-q', '-'
    ], stdout=subprocess.PIPE)
    sox = subprocess.Popen([
        'sox', '-t', 'raw', '-r', str(SAMPLE_RATE), '-e', 'signed', '-b', '16', '-c', '1', '-',
        '-t', 'raw', '-', 'gain', '10'
    ], stdin=arecord.stdout, stdout=subprocess.PIPE)

    while True:
        if idle_mode:
            time.sleep(0.1)
            continue
        # Indicate streaming
        set_led(r=0, g=1, b=0)
        chunk = sox.stdout.read(CHUNK_SIZE)
        if not chunk:
            break
        # Send raw PCM chunk
        files = {'audio_chunk': ('audio.raw', chunk, 'application/octet-stream')}
        data = {'api_key': API_KEY, 'device_id': DEVICE_ID, 'session_id': session_id}
        try:
            r = requests.post(UPLOAD_URL, files=files, data=data)
            log(f"[STREAM] Chunk uploaded, status {r.status_code}")
        except Exception as e:
            log(f"[STREAM] Error uploading chunk: {e}", level='error')
        time.sleep(0.1)

# === HIGHLIGHT HANDLING ===
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
    highlight_led_stop = pulse_led(r=0, g=1, b=0, duration=5*60)

# === CSV UPLOAD ===
def upload_csv():
    global highlight_led_stop
    csvs = glob.glob(os.path.join(AUDIO_DIR, "*.csv"))
    path = csvs[0] if csvs else None
    if not path:
        log("[UPLOAD] No CSV to upload", level='warning')
        return
    with open(path, 'rb') as f:
        files = {'file': f}
        data = {'api_key': API_KEY, 'device_id': DEVICE_ID, 'session_id': session_id}
        try:
            r = requests.post(UPLOAD_URL, files=files, data=data)
            log(f"[UPLOAD] CSV upload status {r.status_code}")
            if r.status_code == 200:
                os.remove(path)
                quick_flash(b=1)
            else:
                quick_flash(r=1)
        except Exception as e:
            log(f"[UPLOAD] CSV upload error: {e}", level='error')

# === UPLOAD BUTTON ===
def on_upload_pressed():
    global idle_mode, last_upload_time, pulse_event
    now = time.time()
    if now - last_upload_time < UPLOAD_DEBOUNCE_SEC:
        log("[UPLOAD] Debounced press ignored.")
        return
    last_upload_time = now

    if not idle_mode:
        log("[UPLOAD] Entering idle mode; uploading CSV and pausing stream.")
        idle_mode = True
        pulse_event.clear()
        threading.Thread(target=idle_led_pulse, daemon=True).start()
        upload_csv()
    else:
        log("[UPLOAD] Resuming streaming.")
        idle_mode = False
        pulse_event.set()
        set_led(0, 0, 0)

BUTTON_HIGHLIGHT.when_pressed = on_highlight_pressed
BUTTON_UPLOAD.when_pressed = on_upload_pressed

# === MAIN LOOP ===
def main():
    global current_csv_path
    # Startup messages and instructions
    print("[SYSTEM] Starting Scribe Recorder...")
    log(f"[SYSTEM] Recorder started. Device ID: {DEVICE_ID}")
    print(f"Device ID: {DEVICE_ID}")
    print(f"Audio Directory: {AUDIO_DIR}")
    print(f"Log file: {LOG_PATH}")
    print("Welcome to the Scribe Audio Recorder!")
    print("Audio will stream continuously in ~4-second raw PCM chunks.")
    print("Press the green button (GPIO27) to mark highlights.")
    print("Press the blue button (GPIO17) to pause streaming and upload highlights CSV, or to resume streaming.")
    print("LED status:")
    print("  Green: Recording/streaming")
    print("  Pulsing Green: Highlight registered")
    print("  Pulsing Green/Blue: Idle mode (waiting, CSV upload)")
    print("  Red: Error")
    print("  White flash: Startup complete")

    current_csv_path = os.path.join(AUDIO_DIR, f"{session_id}_Highlights.csv")

    startup_sequence()
    threading.Thread(target=stream_audio, daemon=True).start()

    while True:
        time.sleep(1)

if __name__ == "__main__":
    main()
