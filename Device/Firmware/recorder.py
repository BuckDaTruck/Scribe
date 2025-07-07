import os
import time
import uuid
import threading
import subprocess
import datetime
import requests
import wave
import logging
from gpiozero import Button, PWMLED

# === CONFIG ===
DEVICE_ID        = "Buckley-Scribe-v1.1"
SCRIPT_DIR       = os.path.dirname(os.path.realpath(__file__))
AUDIO_DIR        = SCRIPT_DIR
os.makedirs(AUDIO_DIR, exist_ok=True)

UPLOAD_URL       = 'https://buckleywiley.com/Scribe/upload2.php'
API_KEY          = '@YourPassword123'
BUTTON_HIGHLIGHT = Button(27, bounce_time=0.1)  # green
BUTTON_UPLOAD    = Button(17, bounce_time=0.1)  # blue

# audio parameters
SAMPLE_RATE      = 88200
BYTES_PER_SAMPLE = 2    # 16-bit
CHANNELS         = 1
CHUNK_SECONDS    = 1    # ← now 1s
CHUNK_SIZE       = SAMPLE_RATE * BYTES_PER_SAMPLE * CHANNELS * CHUNK_SECONDS

# ALSA tuning
ARECORD_BUFFER_SIZE = 2 * 1048576   # 2 MB
ARECORD_PERIOD_SIZE = 131072        # 128 KB

UPLOAD_DEBOUNCE_SEC = 2.0
last_upload_time    = 0
idle_mode           = False
session_id          = uuid.uuid4().hex[:8]

# === LOGGING ===
LOG_PATH = os.path.join(SCRIPT_DIR, 'scribe.log')
logging.basicConfig(
    filename=LOG_PATH, filemode='a',
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    level=logging.INFO
)
def log(msg, level='info'):
    print(msg)
    getattr(logging, level)(msg)

# === LEDs ===
led_r = PWMLED(24); led_g = PWMLED(23); led_b = PWMLED(22)
def set_led(r=0,g=0,b=0):
    led_r.value, led_g.value, led_b.value = r, g, b
def quick_flash(r,g,b,duration=0.2):
    set_led(r,g,b); time.sleep(duration); set_led(0,0,0)

def pulse_led(r,g,b, duration=300, interval=0.5):
    """Continuously pulse the LED for `duration` seconds."""
    end = time.time() + duration
    while time.time() < end:
        set_led(r,g,b)
        time.sleep(interval)
        set_led(0,0,0)
        time.sleep(interval)

# === UPLOAD WORKER ===
def async_upload(chunk_bytes, is_csv=False):
    files = {}
    if is_csv:
        files['file'] = ('highlights.csv', chunk_bytes, 'text/csv')
    else:
        files['audio_chunk'] = ('chunk.raw', chunk_bytes, 'audio/raw')
    data = {'api_key': API_KEY, 'device_id': DEVICE_ID, 'session_id': session_id}
    try:
        resp = requests.post(UPLOAD_URL, files=files, data=data, timeout=10)
        if resp.status_code != 200:
            log(f"[UPLOAD][ERROR] {resp.status_code}: {resp.text}", 'error')
        else:
            log(f"[UPLOAD] Success {resp.status_code}")
    except Exception as e:
        log(f"[UPLOAD][EXCEPTION] {e}", 'error')

# === STREAMING ===
def stream_audio():
    global idle_mode, session_id

    wav_path = os.path.join(AUDIO_DIR, f"{session_id}.wav")
    wf = wave.open(wav_path, 'wb')
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(BYTES_PER_SAMPLE)
    wf.setframerate(SAMPLE_RATE)

    # arecord → raw PCM
    arec = subprocess.Popen([
        'arecord', '-D', 'plughw:1,0',
        '-f', 'S16_LE', '-r', str(SAMPLE_RATE), '-c', str(CHANNELS),
        '--buffer-size', str(ARECORD_BUFFER_SIZE),
        '--period-size', str(ARECORD_PERIOD_SIZE),
        '-t', 'raw', '-q', '-'
    ], stdout=subprocess.PIPE)

    # sox gain → raw PCM
    sox = subprocess.Popen([
        'sox',
        '-t', 'raw', '-r', str(SAMPLE_RATE),
        '-e', 'signed-integer', '-b', '16', '-c', str(CHANNELS), '-',
        '-t', 'raw', '-',
        'gain', '10'
    ], stdin=arec.stdout, stdout=subprocess.PIPE)

    log("[STREAM] Starting audio…")
    set_led(0,1,0)

    try:
        while not idle_mode:
            chunk = sox.stdout.read(CHUNK_SIZE)
            if not chunk:
                break

            # write PCM to our WAV
            wf.writeframes(chunk)

            # upload in background
            threading.Thread(target=async_upload, args=(chunk,), daemon=True).start()

    finally:
        wf.close()
        arec.terminate()
        sox.terminate()
        set_led(0,0,0)
        log("[STREAM] Stopped.")

# === HIGHLIGHT ===
def on_highlight_pressed():
    t0 = datetime.datetime.now() - datetime.timedelta(seconds=10)
    t1 = datetime.datetime.now()
    t2 = t1 + datetime.timedelta(seconds=10)
    csv_path = os.path.join(AUDIO_DIR, f"{session_id}_Highlights.csv")
    entry = f"{t0},{t1},{t2}\n"
    with open(csv_path, 'a') as f:
        f.write(entry)

    # upload CSV in background
    threading.Thread(
        target=async_upload,
        args=(entry.encode('utf-8'), True),
        daemon=True
    ).start()

    # pulse green for 5 min
    threading.Thread(target=lambda: pulse_led(0,1,0, duration=300), daemon=True).start()

# === UPLOAD BUTTON ===
def on_upload_pressed():
    global idle_mode, last_upload_time, session_id
    now = time.time()
    if now - last_upload_time < UPLOAD_DEBOUNCE_SEC:
        return
    last_upload_time = now

    if not idle_mode:
        idle_mode = True
        log("[UPLOAD] Stopping & sending highlights CSV…")
        on_highlight_pressed()   # reuse CSV upload
        quick_flash(0,0,1)
    else:
        session_id = uuid.uuid4().hex[:8]
        idle_mode = False
        threading.Thread(target=stream_audio, daemon=True).start()
        quick_flash(0,1,0)

BUTTON_HIGHLIGHT.when_pressed = on_highlight_pressed
BUTTON_UPLOAD.when_pressed    = on_upload_pressed

# === MAIN ===
if __name__ == "__main__":
    setup_msgs = [
      "[SYSTEM] Starting Scribe Recorder…",
      f"[SYSTEM] Device ID: {DEVICE_ID}",
      f"[SYSTEM] Audio Dir: {AUDIO_DIR}",
      f"[SYSTEM] Log File: {LOG_PATH}"
    ]
    for m in setup_msgs:
        log(m)
    quick_flash(1,1,1, duration=0.1)  # white flash
    threading.Thread(target=stream_audio, daemon=True).start()

    while True:
        time.sleep(1)
