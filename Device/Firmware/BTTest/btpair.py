import os
import subprocess
import time
import requests
from gpiozero import Button, PWMLED

# === GPIO SETUP ===
BUTTON_UPLOAD = Button(27, bounce_time=0.1)
led_r = PWMLED(22)
led_g = PWMLED(23)
led_b = PWMLED(24)

# === FILE LOCATION ===
MAC_FILE_PATH = "/etc/scribe/phone_mac.conf"

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

# === BT MAC UTILITIES ===
def get_saved_mac():
    if os.path.exists(MAC_FILE_PATH):
        with open(MAC_FILE_PATH, "r") as f:
            return f.read().strip()
    return None

def save_mac(mac):
    with open(MAC_FILE_PATH, "w") as f:
        f.write(mac.strip().upper())

def find_newly_paired_device():
    output = subprocess.getoutput("bluetoothctl paired-devices")
    devices = output.strip().splitlines()
    if not devices:
        return None
    return devices[-1].split()[1]  # Grab MAC from last paired device

def is_mac_paired(mac):
    output = subprocess.getoutput("bluetoothctl paired-devices")
    return mac.upper() in output

# === CONNECTION FLOW ===
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

    new_mac = find_newly_paired_device()
    if new_mac:
        print(f"[BT] Detected new device: {new_mac}")
        save_mac(new_mac)
    else:
        print("[BT] No device paired. Try again.")

def connect_to_phone_pan(mac):
    print(f"[BT] Connecting to {mac}...")
    subprocess.run(["bt-pan", "client", "--wait", mac])

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

# === BUTTON HANDLER ===
def on_upload_pressed():
    if time.time() - on_upload_pressed.last_press < 2.0:
        return
    on_upload_pressed.last_press = time.time()

    print("[ACTION] Button pressed.")
    saved_mac = get_saved_mac()
    if saved_mac and is_mac_paired(saved_mac):
        print(f"[BT] Already paired with {saved_mac}.")
        connect_to_phone_pan(saved_mac)
    else:
        print("[BT] No known paired phone. Entering pairing mode.")
        start_pairing()
        saved_mac = get_saved_mac()
        if saved_mac and is_mac_paired(saved_mac):
            connect_to_phone_pan(saved_mac)
        else:
            print("[BT] Skipping PAN connect. No valid MAC found.")

    check_internet()

on_upload_pressed.last_press = 0
BUTTON_UPLOAD.when_pressed = on_upload_pressed

print("[SYSTEM] Ready. Press button to check BT + Internet.")
led_color(0, 0, 0)

while True:
    time.sleep(0.1)
