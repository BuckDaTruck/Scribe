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
DEVICE_ID      = "Buckley-Scribe-v1.1"
SCRIPT_DIR     = os.path.dirname(os.path.realpath(__file__))
AUDIO_DIR      = SCRIPT_DIR
os.makedirs(AUDIO_DIR, exist_ok=True)

UPLOAD_URL     = 'https://buckleywiley.com/Scribe/upload2.php'
API_KEY        = '@YourPassword123'
BUTTON_HIGHLIGHT = Button(27, bounce_time=0.1)  # green button
BUTTON_UPLOAD    = Button(17, bounce_time=0.1)  # blue button

# stream settings
SAMPLE_RATE    = 88200          # must match arecord/sox
BYTES_PER_SAMPLE = 2            # 16-bit = 2 bytes
CHANNELS       = 1
CHUNK_SECONDS  = 4              # send every 4 seconds
CHUNK_SIZE     = SAMPLE_RATE * BYTES_PER_SAMPLE * CHANNELS * CHUNK_SECONDS  # ~705600 bytes

# ALSA buffer tuning to avoid overruns
ARECORD_BUFFER_SIZE = 1048576  # 1 MB
ARECORD_PERIOD_SIZE = 65536    # 64 KB

last_upload_time = 0
UPLOAD_DEBOUNCE_SEC = 2.0

# === LOGGING SETUP ===
LOG_PATH = os.path.join(SCRIPT_DIR, 'scribe.log')
logging.basicConfig(
    filename=LOG_PATH, filemode='a',
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S', level=logging.INFO
)
def log(msg, level='info'):
    print(msg)
    getattr(logging, level)(msg)

# === LED SETUP ===
led_r = PWMLED(24); led_g = PWMLED(23); led_b = PWMLED(22)
def set_led(r=0,g=0,b=0):
    led_r.value, led_g.value, led_b.value = r, g, b
def quick_flash(r=0,g=0,b=0,duration=0.2):
    set_led(r,g,b); time.sleep(duration); set_led(0,0,0)

# === STATE ===
idle_mode = False
highlight_lock = threading.Lock()
highlighting = []
highlight_led_stop = None
session_id = uuid.uuid4().hex[:8]

# === STREAM & SAVE AUDIO ===
def stream_audio():
    global idle_mode, session_id

    # Prepare local WAV file
    wav_path = os.path.join(AUDIO_DIR, f"{session_id}.wav")
    local_wav = open(wav_path, 'wb')

    # Launch arecord with larger buffers
    arecord_cmd = [
        'arecord',
        '-D', 'plughw:1,0',
        '-f', 'S16_LE',
        '-r', str(SAMPLE_RATE),
        '-c', str(CHANNELS),
        '--buffer-size', str(ARECORD_BUFFER_SIZE),
        '--period-size', str(ARECORD_PERIOD_SIZE),
        '-t', 'raw', '-q', '-'
    ]
    current_arecord = subprocess.Popen(arecord_cmd, stdout=subprocess.PIPE)

    # Amplify and wrap to WAV
    sox_cmd = [
        'sox',
        '-t', 'raw', '-r', str(SAMPLE_RATE), '-e', 'signed', '-b', '16', '-c', str(CHANNELS), '-',
        '-t', 'wav', '-','gain','10'
    ]
    sox_proc = subprocess.Popen(sox_cmd, stdin=current_arecord.stdout, stdout=subprocess.PIPE)

    log("[STREAM] Starting audio stream...", 'info')
    set_led(0,1,0)  # green = streaming

    try:
        while not idle_mode:
            # Blocking read exactly CHUNK_SIZE bytes (≈4s of audio)
            chunk = sox_proc.stdout.read(CHUNK_SIZE)
            if not chunk:
                break

            # 1) Save locally
            local_wav.write(chunk)
            local_wav.flush()

            # 2) Upload chunk
            files = {
                'audio_chunk': ('chunk.wav', chunk, 'audio/wav')
            }
            data = {
                'api_key': API_KEY,
                'device_id': DEVICE_ID,
                'session_id': session_id
            }
            resp = requests.post(UPLOAD_URL, files=files, data=data)
            log(f"[STREAM] Chunk uploaded, status {resp.status_code}")
    finally:
        # clean up
        local_wav.close()
        current_arecord.terminate()
        sox_proc.terminate()
        set_led(0,0,0)
        log("[STREAM] Audio stream stopped.", 'info')

# === HIGHLIGHT BUTTON ===
def on_highlight_pressed():
    global highlight_led_stop
    t0 = datetime.datetime.now() - datetime.timedelta(seconds=10)
    t1 = datetime.datetime.now()
    t2 = t1 + datetime.timedelta(seconds=10)
    with highlight_lock:
        highlighting.append((t0,t1,t2))
    # append CSV
    csv_path = os.path.join(AUDIO_DIR, f"{session_id}_Highlights.csv")
    with open(csv_path, 'a') as f:
        f.write(f"{t0},{t1},{t2}\n")
    # LED pulse
    if highlight_led_stop:
        highlight_led_stop.set()
    highlight_led_stop = threading.Event()
    threading.Thread(target=lambda: pulse_led(0,1,0, duration=5*60), daemon=True).start()

# === UPLOAD BUTTON ===
def on_upload_pressed():
    global idle_mode, last_upload_time, session_id
    now = time.time()
    if now - last_upload_time < UPLOAD_DEBOUNCE_SEC:
        return
    last_upload_time = now

    if not idle_mode:
        # stop streaming, upload CSV
        idle_mode = True
        log("[UPLOAD] Stopping stream & uploading CSV...", 'info')
        # upload CSV
        csv_path = os.path.join(AUDIO_DIR, f"{session_id}_Highlights.csv")
        if os.path.isfile(csv_path):
            with open(csv_path,'rb') as f:
                files = {'file': f}
                data = {'api_key': API_KEY,'device_id':DEVICE_ID,'session_id':session_id}
                resp = requests.post(UPLOAD_URL, files=files, data=data)
                log(f"[UPLOAD] CSV upload status {resp.status_code}")
        quick_flash(0,0,1)
    else:
        # start new session
        session_id = uuid.uuid4().hex[:8]
        idle_mode = False
        threading.Thread(target=stream_audio, daemon=True).start()
        quick_flash(0,1,0)

# bind buttons
BUTTON_HIGHLIGHT.when_pressed = on_highlight_pressed
BUTTON_UPLOAD.when_pressed    = on_upload_pressed

# === MAIN ===
if __name__ == "__main__":
    print("[SYSTEM] Starting Scribe Recorder...")
    log(f"[SYSTEM] Recorder started. Device ID: {DEVICE_ID}")
    print(f"[SYSTEM] Device ID: {DEVICE_ID}")
    print(f"[SYSTEM] Audio Directory: {AUDIO_DIR}")
    print("[SYSTEM] Log file: " + LOG_PATH)
    print("Welcome to the Scribe Audio Recorder!")
    print("Audio recording will start automatically.")
    print("Audio is sent to BuckleyWiley.com for processing.")
    print("Green button: Highlight   Blue button: Stop/Upload CSV or Resume")
    print("LEDs:")
    print("  Green: Streaming audio")
    print("  Pulsing Green: Highlighting")
    print("  Blue flash: CSV upload")
    print("  Off: idle")
    print("  Red: Error")
    print("  White flash: Startup complete")

    # kickoff
    threading.Thread(target=stream_audio, daemon=True).start()

    # keep main alive
    while True:
        time.sleep(1)
