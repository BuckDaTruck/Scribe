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

UPLOAD_URL = 'https://buckleywiley.com/Scribe/upload.php'
API_KEY = '@YourPassword123'
BUTTON_HIGHLIGHT = Button(17, bounce_time=0.1)
BUTTON_UPLOAD = Button(27, bounce_time=0.1)
CHUNK_DURATION = .5 * 60  # 30 minutes
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

# === AUDIO RECORDING ===
def start_new_recording():
    global current_arecord_proc, current_lame_proc, session_part, current_csv_path
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    print(f"Session ID {session_id}")
    filename = f"part {session_part:04}.opus"
    filepath = os.path.join(AUDIO_DIR, filename)
    current_csv_path = os.path.join(AUDIO_DIR, f"{session_id}_Highlights.csv")
    session_part += 1

    log(f"[INFO] Starting opus recording: {filename}")
    current_arecord_proc = subprocess.Popen([
        'arecord', '-D', 'plughw:1,0', '-f', 'S16_LE', '-r', '88200', '-c', '1',
        '-t', 'raw', '-q', '-',
    ], stdout=subprocess.PIPE)

    sox_proc = subprocess.Popen([
    'sox', '-t', 'raw', '-r', '16000', '-e', 'signed', '-b', '16', '-c', '1', '-',  # raw PCM input
    '-t', 'raw', '-', 'gain', '10'  # actual amplification
    ], stdin=current_arecord_proc.stdout, stdout=subprocess.PIPE)

    current_lame_proc = subprocess.Popen([
    'opusenc', '--raw', '--raw-rate', '88200', '--raw-chan', '1', '-', filepath
    ], stdin=sox_proc.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    sox_proc.stdout.close()
    current_arecord_proc.stdout.close()
    set_led(r=0, g=1, b=0)
    return filepath
#opus works Finally
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

    highlight_led_stop = pulse_led(r=0, g=1, b=0, duration=5 * 60)

# === UPLOAD BUTTON ===
def on_upload_pressed():
    global idle_mode, pulse_event, last_upload_time, session_id, session_part
    now = time.time()

    # Manual debounce protection
    if now - last_upload_time < UPLOAD_DEBOUNCE_SEC:
        log("[UPLOAD] Ignored: Debounced repeated press.")
        return
    last_upload_time = now

    if not idle_mode:
        log("[UPLOAD] Upload button pressed. Stopping and entering idle mode.")
        if current_arecord_proc:
            current_arecord_proc.terminate()
            current_arecord_proc.wait()
        if current_lame_proc:
            current_lame_proc.terminate()
            current_lame_proc.wait()
        upload_files()
        idle_mode = True
        pulse_event.clear()
        pulse_event = threading.Event()
        threading.Thread(target=idle_led_pulse, daemon=True).start()
    else:
        log("[UPLOAD] Upload button pressed. Starting new recording session.")
        pulse_event.set()  # stop pulsing
        set_led(0, 0, 0)
        idle_mode = False
        session_id = uuid.uuid4().hex[:8]
        session_part = 1
        start_new_recording()


BUTTON_HIGHLIGHT.when_pressed = on_highlight_pressed
BUTTON_UPLOAD.when_pressed = on_upload_pressed

# === FILE UPLOAD ===
def upload_files(skip_file=None):
    global highlight_led_stop
    files_to_upload = []

    log("[UPLOAD] Looking for .opus and .csv files in: " + AUDIO_DIR)
    time.sleep(1.0)

    for ext in ('*.opus', '*.csv'):
        files_to_upload.extend(glob.glob(os.path.join(AUDIO_DIR, ext)))

    if not files_to_upload:
        log("[UPLOAD] Nothing to upload.")
        return

    multipart = {
        'api_key': API_KEY,
        'device_id': DEVICE_ID,
        'session_id': session_id
    }
    file_handles = {}

    try:
        for path in files_to_upload:
            if skip_file and os.path.samefile(path, skip_file):
                continue
            basename = os.path.basename(path)
            file_handles[basename] = open(path, 'rb')

        if highlight_led_stop:
            highlight_led_stop.set()
            highlight_led_stop = None

        log(f"[UPLOAD] Uploading {len(file_handles)} files...")
        upload_led_pulse = pulse_led(r=0, g=0, b=1, duration=999)

        response = requests.post(UPLOAD_URL, files=file_handles, data=multipart)
        log(f"[UPLOAD] Response: {response.status_code} - {response.text}")

        if upload_led_pulse:
            upload_led_pulse.set()
        set_led(0, 0, 0)

        if response.status_code == 200:
            for path in files_to_upload:
                try:
                    # Skip deletion if this file is the current recording
                    if skip_file and os.path.samefile(path, skip_file):
                        continue
                    os.remove(path)
                    log(f"[UPLOAD] Deleted uploaded file: {path}")
                except Exception as e:
                    log(f"[UPLOAD] Could not delete file {path}: {e}", level='error')
            quick_flash(b=1)
        else:
            quick_flash(r=1)
            log("[UPLOAD] Server error during file upload.", level='error')

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
        #upload_files()

def startup_cleanup_upload():
    log("[STARTUP] Checking for leftover recordings to upload...")

    upload_files()
    

# === MAIN LOOP ===
def main():
    global idle_mode
    print("[SYSTEM]Starting Scribe Recorder...")
    log(f"[SYSTEM] Recorder started. Device ID: {DEVICE_ID}")
    print(f"[SYSTEM]Device ID: {DEVICE_ID}")
    print(f"[SYSTEM]Audio Directory: {AUDIO_DIR}")
    print("[SYSTEM]Log file: " + LOG_PATH)
    print("Welcome to the Scribe Audio Recorder!")
    print("Audio recording will start automatically.")
    print("Audio is sent to BuckleyWiley.com for processing.")
    print("Press the highlight button to mark highlights.")
    print("Press the upload button to stop/start recording and upload.")
    print("The LEDS will indicate status.")
    print("Green: Recording")
    print("Pulsing Green: Highlighting")
    print("Pulsing Blue: Uploading")
    print("Pulsing Green/Blue: Idle mode")
    print("Red: Error")
    print("White flash: Startup complete")

    startup_sequence()
    startup_cleanup_upload()
    threading.Thread(target=auto_uploader, daemon=True).start()

    start_new_recording()
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
                # Determine the file that is about to be written
                current_file_path = os.path.join(AUDIO_DIR, f"part {session_part:04}.opus")

                # Start new recording BEFORE killing old ones
                start_new_recording()

                # Kill old processes in background
                if current_arecord_proc:
                    current_arecord_proc.terminate()
                    threading.Thread(target=current_arecord_proc.wait, daemon=True).start()
                if current_lame_proc:
                    current_lame_proc.terminate()
                    threading.Thread(target=current_lame_proc.wait, daemon=True).start()

                # Upload all files except the one that's currently being recorded
                threading.Thread(target=lambda: upload_files(skip_file=current_file_path), daemon=True).start()


        except Exception as e:
            log(f"[MAIN] Error: {e}", level='error')
            set_error_led()
            time.sleep(10)

if __name__ == "__main__":
    main()
