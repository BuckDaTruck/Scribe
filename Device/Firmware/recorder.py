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
DEVICE_ID = hex(uuid.getnode())[-6:]
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
AUDIO_DIR = SCRIPT_DIR
os.makedirs(AUDIO_DIR, exist_ok=True)

UPLOAD_URL = 'https://buckleywiley.com/Scribe/upload.php'
API_KEY = '@YourPassword123'
BUTTON_HIGHLIGHT = Button(17)
BUTTON_UPLOAD = Button(27)
CHUNK_DURATION = 30 * 60  # 30 minutes
MAX_UPLOADED = 5

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
led_r = PWMLED(22)
led_g = PWMLED(23)
led_b = PWMLED(24)

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

def quick_flash(r=0, g=0, b=0, duration=0.2):
    set_led(r, g, b)
    time.sleep(duration)
    set_led(0, 0, 0)

def set_error_led():
    set_led(r=1, g=0, b=0)

def startup_sequence():
    log("[SYSTEM] Running startup LED sequence...")
    colors = [
        (1, 0, 0),   # Red
        (1, 0.5, 0), # Orange
        (1, 1, 0),   # Yellow
        (0, 1, 0),   # Green
        (0, 0, 1),   # Blue
        (0.29, 0, 0.51), # Indigo
        (0.56, 0, 1),    # Violet
    ]
    for r, g, b in colors:
        set_led(r, g, b)
        time.sleep(0.2)
    set_led(0, 0, 0)
    time.sleep(0.3)
    set_led(1, 1, 1)  # white flash
    time.sleep(0.2)
    set_led(0, 0, 0)
    log("[SYSTEM] LED sequence complete.")

# === STATE ===
current_proc = None
highlight_lock = threading.Lock()
highlighting = []
highlight_led_stop = None
session_id = uuid.uuid4().hex[:8]
session_part = 1
current_csv_path = None

# === AUDIO RECORDING ===
def start_new_recording():
    global current_proc, session_part, current_csv_path
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    filename = f"Scribe_v1.1_{DEVICE_ID}_{timestamp}_session{session_id}_part{session_part}.mp3"
    filepath = os.path.join(AUDIO_DIR, filename)
    current_csv_path = filepath.replace('.mp3', '.csv')
    session_part += 1

    log(f"[INFO] Starting MP3 recording: {filename}")
    current_proc = subprocess.Popen([
        'arecord', '-D', 'plughw:1,0', '-f', 'S16_LE', '-r', '16000', '-c', '1',
        '-t', 'raw', '-q', '-',
    ], stdout=subprocess.PIPE)

    # Pipe raw audio to LAME to encode to MP3
    mp3_proc = subprocess.Popen([
        'lame', '-r', '-s', '16', '-', filepath
    ], stdin=current_proc.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    current_proc.stdout.close()  # allow arecord to receive a SIGPIPE if lame exits
    current_proc = mp3_proc

    set_led(r=0, g=1, b=0)  # solid green
    return filepath


# === HIGHLIGHT BUTTON ===
def on_highlight_pressed():
    global highlight_led_stop, current_csv_path
    press_time = datetime.datetime.now()
    start_time = press_time - datetime.timedelta(minutes=2)
    end_time = press_time + datetime.timedelta(minutes=5)

    log(f"[HIGHLIGHT] Start: {start_time}, End: {end_time}")
    with highlight_lock:
        highlighting.append((start_time, press_time, end_time))

    if current_csv_path:
        with open(current_csv_path, 'a') as f:
            f.write(f"{start_time},{press_time},{end_time}\n")

    if highlight_led_stop:
        highlight_led_stop.set()

    highlight_led_stop = pulse_led(r=0, g=1, b=0, duration=5 * 60)

# === UPLOAD BUTTON ===
def on_upload_pressed():
    global current_proc
    log("[UPLOAD] Button pressed.")

    # Stop current recording
    if current_proc:
        log("[UPLOAD] Terminating current recording...")
        current_proc.terminate()
        current_proc.wait()
        current_proc = None

    # Upload the finished file
    upload_files()

    # Start a new recording
    log("[UPLOAD] Starting new recording after upload.")
    start_new_recording()


BUTTON_HIGHLIGHT.when_pressed = on_highlight_pressed
BUTTON_UPLOAD.when_pressed = on_upload_pressed

# === FILE UPLOAD ===
def upload_files():
    global highlight_led_stop
    files = {}

    log("[UPLOAD] Looking for files in: " + AUDIO_DIR)

    # Collect CSVs
    csv_paths = glob.glob(os.path.join(AUDIO_DIR, f"Scribe_v1.1_*_{DEVICE_ID}_*.csv"))
    for csv_path in csv_paths:
        log(f"[UPLOAD] Found CSV: {csv_path}")
        files[os.path.basename(csv_path)] = open(csv_path, 'rb')

    # Collect WAVs that are not marked uploaded
    wav_paths = glob.glob(os.path.join(AUDIO_DIR, f"Scribe_v1.1_*_{DEVICE_ID}_*.mp3"))
    for path in wav_paths:
        if '_uploaded' not in path:
            log(f"[UPLOAD] Found WAV: {path}")
            files[os.path.basename(path)] = open(path, 'rb')

    if not files:
        log("[UPLOAD] Nothing to upload.")
        return

    data = {'api_key': API_KEY}
    try:
        log("[UPLOAD] Sending files...")

        if highlight_led_stop:
            highlight_led_stop.set()
            highlight_led_stop = None

        set_led(r=0, g=0, b=1)  # solid blue for upload
        response = requests.post(UPLOAD_URL, files=files, data=data)
        log(f"[UPLOAD] Response: {response.status_code} - {response.text}")

        if response.status_code == 200:
            for f in files:
                if f.endswith('.mp3'):
                    old = os.path.join(AUDIO_DIR, f)
                    new = old.replace('.mp3', '_uploaded.mp3')
                    os.rename(old, new)
            cleanup_old_recordings()
            quick_flash(b=1)
            log(f"[UPLOAD] Uploaded files: {list(files.keys())}")
        else:
            quick_flash(r=1)
            log("[UPLOAD] Server error", level='error')

        set_led(0, 0, 0)
    except Exception as e:
        quick_flash(r=1)
        log(f"[UPLOAD] Failed: {e}", level='error')
        set_error_led()


# === CLEANUP ===
def cleanup_old_recordings():
    uploaded_files = sorted(glob.glob(os.path.join(AUDIO_DIR, f'*_uploaded.mp3')))
    if len(uploaded_files) > MAX_UPLOADED:
        for f in uploaded_files[:-MAX_UPLOADED]:
            log(f"[CLEANUP] Deleting old file: {f}")
            os.remove(f)

# === AUTO-UPLOAD THREAD ===
def auto_uploader():
    while True:
        time.sleep(CHUNK_DURATION)
        upload_files()
def startup_cleanup_upload():
    log("[STARTUP] Checking for leftover recordings to upload...")

    leftover_wavs = glob.glob(os.path.join(AUDIO_DIR, f"Scribe_v1.1_*_{DEVICE_ID}_*.mp3"))
    leftover_csvs = glob.glob(os.path.join(AUDIO_DIR, f"Scribe_v1.1_*_{DEVICE_ID}_*.csv"))

    files = {}

    for path in leftover_csvs:
        if not path.endswith("_uploaded.csv"):
            log(f"[STARTUP] Found leftover CSV: {path}")
            files[os.path.basename(path)] = open(path, 'rb')

    for path in leftover_wavs:
        if not path.endswith("_uploaded.mp3"):
            log(f"[STARTUP] Found leftover mp3: {path}")
            files[os.path.basename(path)] = open(path, 'rb')

    if not files:
        log("[STARTUP] No leftover files to upload.")
        return

    try:
        set_led(0, 0, 1)  # Solid blue
        data = {'api_key': API_KEY}
        log("[STARTUP] Uploading leftover files...")
        response = requests.post(UPLOAD_URL, files=files, data=data)
        log(f"[STARTUP] Upload response: {response.status_code} - {response.text}")

        if response.status_code == 200:
            # Delete successfully uploaded files
            for f in list(files.keys()):
                full_path = os.path.join(AUDIO_DIR, f)
                log(f"[STARTUP] Deleting uploaded file: {full_path}")
                try:
                    os.remove(full_path)
                except Exception as e:
                    log(f"[STARTUP] Error deleting file: {e}", level='error')
            quick_flash(b=1)
        else:
            log("[STARTUP] Server error during upload.", level='error')
            quick_flash(r=1)

        set_led(0, 0, 0)
    except Exception as e:
        log(f"[STARTUP] Upload failed: {e}", level='error')
        quick_flash(r=1)
        set_error_led()

# === MAIN LOOP ===
def main():
    global current_proc
    log(f"[SYSTEM] Recorder started. Device ID: {DEVICE_ID}")
    startup_sequence()
    startup_cleanup_upload()
    threading.Thread(target=auto_uploader, daemon=True).start()

    while True:
        try:
            if current_proc:
                current_proc.terminate()
                current_proc.wait()
            start_new_recording()
            time.sleep(CHUNK_DURATION)
        except Exception as e:
            log(f"[MAIN] Error: {e}", level='error')
            set_error_led()
            time.sleep(10)

if __name__ == "__main__":
    main()
