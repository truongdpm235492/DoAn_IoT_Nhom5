
# DU AN 1 - DOC 4 CAM BIEN VA GUI TRANG THAI CHO DO
# ESP32 + 4 HC-SR04 + 4 LED + MQTT Adafruit IO

import time
import network
from machine import Pin, time_pulse_us
from umqtt.simple import MQTTClient

# =========================
# 1. CAU HINH WIFI
# =========================
WIFI_SSID = "Wokwi-GUEST"
WIFI_PASS = ""

# =========================
# 2. CAU HINH ADAFRUIT IO
# =========================
AIO_HOST = "io.adafruit.com"
AIO_PORT = 1883
AIO_USER = "trgtran"
AIO_KEY = "aio_jRge90vZu2oNPw8vlMOceF3NvXi1"

FEED_CHO = AIO_USER + "/feeds/bai-do-xe"

# =========================
# 3. KHAI BAO CAM BIEN
# =========================
N = 4
NGUONG_CM = 15.0

TRIG = [Pin(p, Pin.OUT) for p in (13, 14, 27, 26)]
ECHO = [Pin(p, Pin.IN) for p in (34, 35, 32, 33)]
LED = [Pin(p, Pin.OUT) for p in (2, 4, 16, 17)]

trang_thai_cu = None
client = None

# =========================
# 4. KET NOI WIFI
# =========================
def wifi_connect():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    if wlan.isconnected():
        print("WiFi da ket noi:", wlan.ifconfig()[0])
        return True

    try:
        wlan.connect(WIFI_SSID, WIFI_PASS)

        for _ in range(40):
            if wlan.isconnected():
                print("WiFi OK:", wlan.ifconfig()[0])
                return True
            time.sleep_ms(500)

    except Exception as e:
        print("Loi WiFi:", repr(e))

    print("Khong ket noi duoc WiFi")
    return False

# =========================
# 5. KET NOI MQTT
# =========================
def connect_mqtt():
    global client

    for lan in range(3):
        c = None

        try:
            cid = "esp32_cam_bien_%d" % time.ticks_ms()

            c = MQTTClient(
                cid,
                AIO_HOST,
                port=AIO_PORT,
                user=AIO_USER,
                password=AIO_KEY,
                keepalive=60
            )

            c.connect()
            client = c

            print("MQTT ket noi thanh cong")
            print("Feed:", FEED_CHO)
            return True

        except Exception as e:
            print("MQTT loi:", repr(e))

            try:
                if c is not None:
                    c.disconnect()
            except Exception:
                pass

            time.sleep(10)

    client = None
    print("Khong ket noi duoc MQTT")
    return False

# =========================
# 6. DOC KHOANG CACH
# =========================
def doc_khoang_cach(i):
    TRIG[i].value(0)
    time.sleep_us(3)

    TRIG[i].value(1)
    time.sleep_us(10)
    TRIG[i].value(0)

    try:
        duration = time_pulse_us(ECHO[i], 1, 30000)
    except Exception:
        return None

    if duration <= 0:
        return None

    return duration * 0.0343 / 2

# =========================
# 7. DOC TRANG THAI 4 VI TRI
# =========================
def doc_trang_thai():
    bits = []

    for i in range(N):
        dist = doc_khoang_cach(i)

        if dist is None:
            # Neu cam bien loi, giu trang thai cu
            # de tranh tu dong bao vi tri trong.
            if trang_thai_cu is not None:
                co_xe = trang_thai_cu[4 + i] == "1"
            else:
                co_xe = False

            print("Canh bao: cam bien", i + 1, "khong doc duoc")

        else:
            co_xe = dist < NGUONG_CM

        LED[i].value(1 if co_xe else 0)
        bits.append("1" if co_xe else "0")

        time.sleep_ms(25)

    return "CHO:" + "".join(bits)

# =========================
# 8. KHOI DONG
# =========================
for led in LED:
    led.value(0)

if not wifi_connect():
    raise RuntimeError("Khong ket noi duoc WiFi")

if not connect_mqtt():
    raise RuntimeError("Kiem tra AIO_USER va AIO_KEY")

trang_thai_cu = None
lan_gui_cuoi = time.ticks_ms()

# =========================
# 9. VONG LAP CHINH
# =========================
while True:
    try:
        trang_thai = doc_trang_thai()
        now = time.ticks_ms()

        # Gui khi trang thai thay doi hoac moi 5 giay
        if (
            trang_thai != trang_thai_cu
            or time.ticks_diff(now, lan_gui_cuoi) >= 5000
        ):
            client.publish(FEED_CHO, trang_thai)

            print("Gui MQTT:", trang_thai)

            trang_thai_cu = trang_thai
            lan_gui_cuoi = now

        time.sleep_ms(200)

    except Exception as e:
        print("Loi doc/gui:", repr(e))

        try:
            if client is not None:
                client.disconnect()
        except Exception:
            pass

        client = None
        time.sleep(5)

        if wifi_connect():
            connect_mqtt()
            trang_thai_cu = None
