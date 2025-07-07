import os
import time
import uuid
import threading
import subprocess
import datetime
import requests
import wave
import logging
import math
from gpiozero import Button, PWMLED

# === CONFIG ===
DEVICE_ID        = "Buckley-Scribe-v1.1"
SCRIPT_DIR       = os.path.dirname(os.path.realpath(__file__))
AUDIO_DIR        = SCRIPT_DIR
os.makedirs(AUDIO_DIR, exist_ok=True)

UPLOAD_URL       = 'https://buckleywiley.com/Scribe/upload2.php'
API_KEY          = '@YourPassword123'
BUTTON_HIGHLIGHT = Button(27, bounce_time=0.1)  # green button
BUTTON_UPLOAD    = Button(17, bounce_time=0.1)  # blue button

# audio parameters
SAMPLE_RATE      = 88200
BYTES_PER_SAMPLE = 2    # 16-bit
CHANNELS         = 1
CHUNK_SECONDS    = 1
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
led_r = PWMLED(24)
led_g = PWMLED(23)
led_b = PWMLED(22)

def set_led(r=0, g=0, b=0):
    led_r.value, led_g.value, led_b.value = r, g, b

# State for LED controller
recording_start_time = None
highlight_start       = None
highlight_until       = 0

def led_controller():
    """Background thread: sets LED based on idle/record/highlight state."""
    global recording_start_time, highlight_start, highlight_until

    crossfade_period = 4.0    # seconds for full blue↔green cycle
    pulse_period     = 2.0    # seconds for a full pulse up/down
    refresh_rate     = 0.05   # 50 ms

    while True:
        now = time.time()

        if idle_mode:
            # Highlight override?
            if highlight_start and now < highlight_until:
                # smooth green pulse
                phase     = ((now - highlight_start) % pulse_period) / pulse_period
                brightness = (math.sin(2 * math.pi * phase) + 1) / 2
                set_led(0, brightness, 0)
            else:
                # crossfade blue↔green
                phase = (now % crossfade_period) / crossfade_period
                g_val = phase
                b_val = 1 - phase
                set_led(0, g_val, b_val)

            # Reset recording timer in case we just stopped
            recording_start_time = None

        else:
            # recording mode
            if recording_start_time is None:
                recording_start_time = now

            elapsed = now - recording_start_time
            if elapsed < 5:
                # pulse blue for first 5 seconds
                phase     = (elapsed % pulse_period) / pulse_period
                brightness = (math.sin(2 * math.pi * phase) + 1) / 2
                set_led(0, 0, brightness)
            else:
                # solid green afterwards
                set_led(0, 1, 0)

            # clear any highlight once recording begins
            highlight_until = 0

        time.sleep(refresh_rate)

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
    try:
        while not idle_mode:
            chunk = sox.stdout.read(CHUNK_SIZE)
            if not chunk:
                break

            wf.writeframes(chunk)
            threading.Thread(target=async_upload, args=(chunk,), daemon=True).start()

    finally:
        wf.close()
        arec.terminate()
        sox.terminate()
        log("[STREAM] Stopped.")

# === HIGHLIGHT ===
def on_highlight_pressed():
    global highlight_start, highlight_until
    t0 = datetime.datetime.now() - datetime.timedelta(seconds=10)
    t1 = datetime.datetime.now()
    t2 = t1 + datetime.timedelta(seconds=10)
    csv_entry = f"{t0},{t1},{t2}\n"
    csv_path = os.path.join(AUDIO_DIR, f"{session_id}_Highlights.csv")
    with open(csv_path, 'a') as f:
        f.write(csv_entry)

    # schedule 10s of smooth green-pulsing
    highlight_start = time.time()
    highlight_until = highlight_start + 10

    threading.Thread(
        target=async_upload,
        args=(csv_entry.encode('utf-8'), True),
        daemon=True
    ).start()

# === UPLOAD BUTTON ===
def on_upload_pressed():
    global idle_mode, last_upload_time, session_id
    now = time.time()
    if now - last_upload_time < UPLOAD_DEBOUNCE_SEC:
        return
    last_upload_time = now

    if not idle_mode:
        # stop recording
        idle_mode = True
        log("[UPLOAD] Stopping & sending highlights CSV…")
        on_highlight_pressed()   # send final highlight as CSV
    else:
        # start new recording session
        session_id = uuid.uuid4().hex[:8]
        idle_mode = False
        threading.Thread(target=stream_audio, daemon=True).start()

BUTTON_HIGHLIGHT.when_pressed = on_highlight_pressed
BUTTON_UPLOAD.when_pressed    = on_upload_pressed

# === MAIN ===
if __name__ == "__main__":
    for m in [
      "[SYSTEM] Starting Scribe Recorder…",
      f"[SYSTEM] Device ID: {DEVICE_ID}",
      f"[SYSTEM] Audio Dir: {AUDIO_DIR}",
      f"[SYSTEM] Log File: {LOG_PATH}"
    ]: log(m)

    # Start LED manager
    threading.Thread(target=led_controller, daemon=True).start()

    # small white flash at startup
    set_led(1,1,1)
    time.sleep(0.1)
    set_led(0,0,0)

    # begin streaming immediately
    threading.Thread(target=stream_audio, daemon=True).start()

    # keep main thread alive
    while True:
        time.sleep(1)
