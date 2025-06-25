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

# === TRIPLE TAP DETECTION ===
last_tap_time = 0
tap_count = 0
idle_mode = False
pulse_thread = None
pulse_event = threading.Event()

def idle_led_pulse():
    while not pulse_event.is_set():
        for i in range(100):
            if pulse_event.is_set(): return
            val = (math.sin(time.time() * 2) + 1) / 2
            led_g.value = val
            led_b.value = 1 - val
            time.sleep(0.05)
        set_led(0, 0, 0)


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
    set_led(1, 1, 1)
    time.sleep(0.2)
    set_led(0, 0, 0)
    log("[SYSTEM] LED sequence complete.")

# === STATE ===
current_arecord_proc = None
current_lame_proc = None
highlight_lock = threading.Lock()
highlighting = []
highlight_led_stop = None
session_id = uuid.uuid4().hex[:8]
session_part = 1
current_csv_path = None

# === AUDIO RECORDING ===
def start_new_recording():
    global current_arecord_proc, current_lame_proc, session_part, current_csv_path
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    filename = f"Scribe_v1.1_{DEVICE_ID}_{timestamp}_session{session_id}_part{session_part}.mp3"
    filepath = os.path.join(AUDIO_DIR, filename)
    current_csv_path = filepath.replace('.mp3', '.csv')
    session_part += 1

    log(f"[INFO] Starting MP3 recording: {filename}")
    current_arecord_proc = subprocess.Popen([
        'arecord', '-D', 'plughw:1,0', '-f', 'S16_LE', '-r', '88200', '-c', '1',
        '-t', 'raw', '-q', '-',
    ], stdout=subprocess.PIPE)

    current_lame_proc = subprocess.Popen([
        'lame', '-r', '--resample', '16', '--preset', 'standard', '--scale', '10', '-', filepath
    ], stdin=current_arecord_proc.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    current_arecord_proc.stdout.close()
    set_led(r=0, g=1, b=0)
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
        set_led(r=0, g=1, b=0)

    highlight_led_stop = pulse_led(r=0, g=1, b=0, duration=5 * 60)

# === UPLOAD BUTTON ===
def on_upload_pressed():
    global tap_count, last_tap_time, idle_mode, pulse_event

    now = time.time()
    if now - last_tap_time > 1.0:
        tap_count = 1
    else:
        tap_count += 1
    last_tap_time = now

    if tap_count == 3:
        log("[UPLOAD] Triple tap detected. Stopping recording and entering idle mode.")
        if current_arecord_proc:
            current_arecord_proc.terminate()
            current_arecord_proc.wait()
        if current_lame_proc:
            current_lame_proc.terminate()
            current_lame_proc.wait()
        upload_files()
        idle_mode = True
        pulse_event.clear()
        threading.Thread(target=idle_led_pulse, daemon=True).start()
    elif tap_count == 1:
        log("[UPLOAD] Single tap: normal upload and resume.")
        if current_arecord_proc:
            current_arecord_proc.terminate()
            current_arecord_proc.wait()
        if current_lame_proc:
            current_lame_proc.terminate()
            current_lame_proc.wait()
        upload_files()
        if not idle_mode:
            start_new_recording()

BUTTON_HIGHLIGHT.when_pressed = on_highlight_pressed
BUTTON_UPLOAD.when_pressed = on_upload_pressed

# === FILE UPLOAD ===
def upload_files():
    global highlight_led_stop
    files_to_upload = []

    log("[UPLOAD] Looking for .mp3 and .csv files in: " + AUDIO_DIR)
    time.sleep(1.0)  # Give time for filesystem flush

    # Find all mp3 and csv files
    for ext in ('*.mp3', '*.csv'):
        files_to_upload.extend(glob.glob(os.path.join(AUDIO_DIR, ext)))

    if not files_to_upload:
        log("[UPLOAD] Nothing to upload.")
        return

    multipart = {'api_key': API_KEY}
    file_handles = {}

    try:
        for path in files_to_upload:
            basename = os.path.basename(path)
            file_handles[basename] = open(path, 'rb')

        if highlight_led_stop:
            highlight_led_stop.set()
            highlight_led_stop = None

        set_led(r=0, g=0, b=1)  # Blue = uploading
        log(f"[UPLOAD] Uploading {len(file_handles)} files...")
        response = requests.post(UPLOAD_URL, files=file_handles, data=multipart)
        log(f"[UPLOAD] Response: {response.status_code} - {response.text}")

        if response.status_code == 200:
            for path in files_to_upload:
                try:
                    os.remove(path)
                    log(f"[UPLOAD] Deleted uploaded file: {path}")
                except Exception as e:
                    log(f"[UPLOAD] Could not delete file {path}: {e}", level='error')
            quick_flash(b=1)
        else:
            quick_flash(r=1)
            log("[UPLOAD] Server error during file upload.", level='error')

        set_led(0, 0, 0)

    except Exception as e:
        quick_flash(r=1)
        log(f"[UPLOAD] Exception: {e}", level='error')
        set_error_led()
    finally:
        for fh in file_handles.values():
            fh.close()

# === AUTO-UPLOAD THREAD ===
def auto_uploader():
    while True:
        time.sleep(CHUNK_DURATION)
        upload_files()

def startup_cleanup_upload():
    log("[STARTUP] Checking for leftover recordings to upload...")

    upload_files()

# === MAIN LOOP ===
def main():
    global idle_mode
    log(f"[SYSTEM] Recorder started. Device ID: {DEVICE_ID}")
    startup_sequence()
    startup_cleanup_upload()
    threading.Thread(target=auto_uploader, daemon=True).start()

    filepath = start_new_recording()
    while True:
        try:
            if idle_mode:
                time.sleep(1)
                continue

            start_time = time.time()
            while time.time() - start_time < CHUNK_DURATION:
                time.sleep(1)
                if idle_mode:
                    break

            if not idle_mode:
                if current_arecord_proc:
                    current_arecord_proc.terminate()
                    current_arecord_proc.wait()
                if current_lame_proc:
                    current_lame_proc.terminate()
                    current_lame_proc.wait()
                upload_files()
                start_new_recording()

        except Exception as e:
            log(f"[MAIN] Error: {e}", level='error')
            set_error_led()
            time.sleep(10)

if __name__ == "__main__":
    main()
