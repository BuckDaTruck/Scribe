import subprocess
import time
import requests
from gpiozero import Button, PWMLED

# === GPIO SETUP ===
BUTTON_UPLOAD = Button(27, bounce_time=0.1)
led_r = PWMLED(22)
led_g = PWMLED(23)
led_b = PWMLED(24)

# === LED CONTROL ===
def led_color(r=0, g=0, b=0):
    led_r.value = r
    led_g.value = g
    led_b.value = b

def led_pulse(color_fn, duration=5):
    end_time = time.time() + duration
    while time.time() < end_time:
        for v in range(0, 100, 5):
            color_fn(v / 100.0)
            time.sleep(0.01)
        for v in range(100, 0, -5):
            color_fn(v / 100.0)
            time.sleep(0.01)
    led_color(0, 0, 0)

# === BLUETOOTH PAIRING ===
def start_pairing():
    print("[BT] Starting pairing mode...")
    led_color(0.5, 0.5, 0)  # Yellow
    subprocess.run(["bluetoothctl", "discoverable", "on"])
    subprocess.run(["bluetoothctl", "pairable", "on"])
    subprocess.run(["bluetoothctl", "agent", "NoInputNoOutput"])
    subprocess.run(["bluetoothctl", "default-agent"])
    print("[BT] Pairing mode enabled. Connect from your phone now.")
    led_pulse(lambda v: setattr(led_b, 'value', v), duration=30)
    led_color(0, 0, 0)

# === INTERNET TEST ===
def check_internet():
    led_color(0, 0, 1)  # Blue = checking
    try:
        response = requests.get("http://google.com", timeout=5)
        if response.ok:
            print("[NET] Internet reachable via BT.")
            led_color(0, 1, 0)  # Green = success
        else:
            raise Exception("Bad status")
    except:
        print("[NET] Internet check failed.")
        led_color(1, 0, 0)  # Red = fail
    time.sleep(5)
    led_color(0, 0, 0)

# === BUTTON EVENT ===
def on_upload_pressed():
    if time.time() - on_upload_pressed.last_press < 2.0:
        return
    on_upload_pressed.last_press = time.time()

    print("[ACTION] Button pressed. Initiating pairing + internet check.")
    start_pairing()
    check_internet()

on_upload_pressed.last_press = 0
BUTTON_UPLOAD.when_pressed = on_upload_pressed

print("[SYSTEM] Ready. Press button to pair via Bluetooth.")
led_color(0, 0, 0)

while True:
    time.sleep(0.1)
