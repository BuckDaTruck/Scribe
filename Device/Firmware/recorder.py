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
DEVICE_ID        = "Buckley-Scribe-v1.2"#stable
SCRIPT_DIR       = os.path.dirname(os.path.realpath(__file__))
AUDIO_DIR        = SCRIPT_DIR
os.makedirs(AUDIO_DIR, exist_ok=True)

UPLOAD_URL       = 'http://172.20.10.12:3000/api/audio/upload'
API_KEY          = '@YourPassword123'
BUTTON_HIGHLIGHT = Button(27, bounce_time=0.1)
BUTTON_UPLOAD    = Button(17, bounce_time=0.1)

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
chunk_counter       = 0

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
crossfade_start_time  = time.time()

# === LED CONTROLLER ===
def led_controller():
    global recording_start_time, highlight_start, highlight_until, crossfade_start_time

    crossfade_period = 4.0    # seconds for full blue↔green cycle
    pulse_period     = 2.0    # pulse period for highlights and blue pulses
    refresh_rate     = 0.05   # 50 ms update

    while True:
        now = time.time()

        if idle_mode:
            # end any highlight
            highlight_until = 0
            # smooth crossfade idle between blue and green and back
            phase = ((now - crossfade_start_time) % crossfade_period) / crossfade_period
            g_val = 0.5 * (1 - math.cos(2 * math.pi * phase))
            b_val = 0.5 * (1 + math.cos(2 * math.pi * phase))
            set_led(0, g_val, b_val)
            recording_start_time = None

        else:
            # Highlight override during recording
            if highlight_start and now < highlight_until:
                phase      = ((now - highlight_start) % pulse_period) / pulse_period
                brightness = (math.sin(2 * math.pi * phase) + 1) / 2
                set_led(0, brightness, 0)

            else:
                # Recording mode without highlight or after highlight expired
                if recording_start_time is None:
                    recording_start_time = now
                    # reset fade when returning to idle later
                    crossfade_start_time = now
                elapsed = now - recording_start_time
                if elapsed < 5:
                    # blue pulse for first 5s
                    phase      = (elapsed % pulse_period) / pulse_period
                    brightness = (math.sin(2 * math.pi * phase) + 1) / 2
                    set_led(0, 0, brightness)
                else:
                    # solid green afterwards
                    set_led(0, 1, 0)

        time.sleep(refresh_rate)

# === UPLOAD WORKER ===
chunk_counter = 0

def async_upload(chunk_bytes, is_csv=False):
    global chunk_counter
    
    if is_csv:
        # Skip CSV uploads for now - focus on audio
        log("[UPLOAD] Skipping CSV upload (not implemented for new API)")
        return
    
    chunk_counter += 1
    
    # Convert bytes to list of integers for the API
    audio_data = list(chunk_bytes)
    
    payload = {
        "userId": DEVICE_ID,
        "timestamp": int(time.time() * 1000),
        "audioData": audio_data,
        "chunkId": f"{session_id}-chunk-{chunk_counter}",
        "sessionId": session_id
    }
    
    try:
        resp = requests.post(
            UPLOAD_URL, 
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        if resp.status_code != 200:
            log(f"[UPLOAD][ERROR] {resp.status_code}: {resp.text}", 'error')
        else:
            response_data = resp.json()
            log(f"[UPLOAD] Success: {response_data.get('message', 'OK')}")
            print(f"Audio chunk {chunk_counter} uploaded.")
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

    arec = subprocess.Popen([
        'arecord', '-D', 'plughw:1,0',
        '-f', 'S16_LE', '-r', str(SAMPLE_RATE), '-c', str(CHANNELS),
        '--buffer-size', str(ARECORD_BUFFER_SIZE),
        '--period-size', str(ARECORD_PERIOD_SIZE),
        '-t', 'raw', '-q', '-'
    ], stdout=subprocess.PIPE)

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
    # record timestamps
    t0 = datetime.datetime.now() - datetime.timedelta(seconds=10)
    t1 = datetime.datetime.now()
    t2 = t1 + datetime.timedelta(seconds=10)
    entry = f"{t0},{t1},{t2}\n"
    csv_path = os.path.join(AUDIO_DIR, f"{session_id}_Highlights.csv")
    with open(csv_path, 'a') as f:
        f.write(entry)
    # immediate upload of full CSV
    try:
        with open(csv_path, 'rb') as f:
            csv_bytes = f.read()
        threading.Thread(target=async_upload, args=(csv_bytes, True), daemon=True).start()
    except Exception as e:
        log(f"[HIGHLIGHT][ERROR] CSV upload failed: {e}", 'error')
    # start highlight pulse
    highlight_start = time.time()
    highlight_until = highlight_start + 10

# === UPLOAD BUTTON ===
def on_upload_pressed():
    global idle_mode, last_upload_time, session_id, crossfade_start_time, chunk_counter
    now = time.time()
    if now - last_upload_time < UPLOAD_DEBOUNCE_SEC:
        return
    last_upload_time = now

    if not idle_mode:
        idle_mode = True
        crossfade_start_time = now
        log("[UPLOAD] Stopping recording…")
    else:
        session_id = uuid.uuid4().hex[:8]
        chunk_counter = 0  # Reset chunk counter for new session
        idle_mode = False
        threading.Thread(target=stream_audio, daemon=True).start()

# === SETUP BUTTONS & MAIN ===
BUTTON_HIGHLIGHT.when_pressed = on_highlight_pressed
BUTTON_UPLOAD.when_pressed    = on_upload_pressed

if __name__ == "__main__":
    for m in [
        "[SYSTEM] Starting Scribe Recorder…",
        f"[SYSTEM] Device ID: {DEVICE_ID}",
        f"[SYSTEM] Audio Dir: {AUDIO_DIR}",
        f"[SYSTEM] Log File: {LOG_PATH}"
    ]:
        log(m)
        print(m)

    instructions = [
        "[SYSTEM] Instructions:",
        "[SYSTEM] - Press the Green Highlight button to mark a 10-second highlight in the recording.",
        "[SYSTEM] - Press the Blue Upload button to toggle between recording and idle mode.",
        "[SYSTEM] LED Behavior:",
        "[SYSTEM] - Idle Mode: Smooth crossfade between blue and green.",
        "[SYSTEM] - Recording Mode: Blue pulse for the first 5 seconds, then solid green.",
        "[SYSTEM] - Highlight: Green pulse for 10 seconds.",
        "[SYSTEM] Upload Server:",
        f"[SYSTEM] - Audio chunks are uploaded to: {UPLOAD_URL}"
    ]

    for line in instructions:
        log(line)
        print(line)

    # start LED controller
    threading.Thread(target=led_controller, daemon=True).start()

    # flash to show startup
    set_led(1,1,1)
    time.sleep(0.1)
    set_led(0,0,0)

    # start audio streaming
    threading.Thread(target=stream_audio, daemon=True).start()

    # keep main alive
    while True:
        time.sleep(1)
