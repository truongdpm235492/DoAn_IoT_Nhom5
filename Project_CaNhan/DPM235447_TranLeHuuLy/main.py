# ============================================================
#  NODE 1 - TRAM CAM BIEN (Sensor Node) - ESP32 + MicroPython
#  - DHT22 (GPIO 15): nhiet do
#  - Chiet ap (GPIO 34): gia lap khoi MQ-2
#  - Loc nhieu -> publish MQTT len Adafruit IO (feed: temp, smoke)
#  - Phat hien QUA NHIET / KHOI CAO -> publish NGAY va gui day hon
# ============================================================
import time
import network
import dht
from machine import Pin, ADC
from umqtt.simple import MQTTClient

# ================= CAU HINH (SUA CHO DUNG) =================
WIFI_SSID = "Wokwi-GUEST"          
WIFI_PASS = ""                     

AIO_SERVER = "io.adafruit.com"
AIO_PORT = 1883
AIO_USER = "Lyts"     
AIO_KEY = "aio_tFIS8654si3INGD0flKFNgeLWvIw"          
CLIENT_ID = "esp32-node1-sensor"

FEED_TEMP = "temp"                 # Ten feed (chu thuong)
FEED_SMOKE = "smoke"

PIN_DHT = 15                       # DATA cua DHT22 (pull-up 10k len 3V3)
PIN_SMOKE = 34                     # ADC1 - doc chiet ap

SAMPLE_INTERVAL_MS = 2000          # Chu ky lay mau (DHT22 >= 2s/lan)
PUBLISH_INTERVAL_MS = 10000        # Chu ky gui binh thuong
ALERT_PUBLISH_INTERVAL_MS = 5000   # Chu ky gui khi dang bao dong

TEMP_WINDOW = 5                    # Cua so trung vi cho nhiet do
SMOKE_WINDOW = 3                   # Cua so trung vi cho khoi
ADC_SAMPLES = 20                   # So mau ADC moi lan lay mau
ADC_MAX = 4095

# ---- Nguong canh bao (thong nhat voi nhom / Project 4) ----
TEMP_ALERT = 45.0                  # Qua nhiet khi nhiet do > 45 do C
TEMP_CLEAR = 43.0                  # Het qua nhiet khi < 43 do C (tranh nhap nhay)
SMOKE_ALERT = 60.0                 # Khoi cao khi >= 60 %
SMOKE_CLEAR = 50.0                 # Het khoi cao khi < 50 %
CONFIRM_SAMPLES = 2                # Vuot nguong lien tiep 2 mau (~4 giay) moi bao dong
CLEAR_SAMPLES = 3                  # Binh thuong lien tiep 3 mau (~6 giay) moi tat bao dong
DHT_FAIL_LIMIT = 3                 # Loi DHT22 lien tiep -> bo du lieu nhiet do cu
# ===========================================================

TOPIC_TEMP = "{}/feeds/{}".format(AIO_USER, FEED_TEMP)
TOPIC_SMOKE = "{}/feeds/{}".format(AIO_USER, FEED_SMOKE)

sensor = dht.DHT22(Pin(PIN_DHT))
adc = ADC(Pin(PIN_SMOKE))
adc.atten(ADC.ATTN_11DB)           # Dai do 0 - ~3.3V
adc.width(ADC.WIDTH_12BIT)         # 0 - 4095

temp_buf = []
smoke_buf = []
dht_fail = 0

# Trang thai bao dong
alarm = False
over_count = 0
under_count = 0
last_temp_raw = None
last_smoke_raw = 0.0


# ---------------- LOC NHIEU ----------------
def median(values):
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2


def push(buf, value, size):
    buf.append(value)
    if len(buf) > size:
        buf.pop(0)


def sample_smoke():
    """20 mau ADC, bo 20% thap/cao nhat, lay trung binh -> % (0-100)."""
    raw = []
    for _ in range(ADC_SAMPLES):
        raw.append(adc.read())
        time.sleep_ms(5)
    raw.sort()
    cut = ADC_SAMPLES // 5
    trimmed = raw[cut:ADC_SAMPLES - cut]
    avg = min(sum(trimmed) / len(trimmed), ADC_MAX)
    return avg * 100 / ADC_MAX


def sample_temp():
    """Doc DHT22. Hop le -> nhiet do, loi -> None (dem so lan loi lien tiep)."""
    global dht_fail
    try:
        sensor.measure()
        t = sensor.temperature()
        if -40 <= t <= 80:
            dht_fail = 0
            return t
    except OSError as e:
        print("Loi doc DHT22:", e)
    dht_fail += 1
    if dht_fail >= DHT_FAIL_LIMIT and temp_buf:
        temp_buf.clear()           # Khong gui lai so lieu cu khi cam bien mat tin hieu
        print("CANH BAO: DHT22 mat tin hieu, bo du lieu nhiet do cu")
    return None


def take_samples():
    """Lay mau, dua vao bo loc, cap nhat gia tri tuc thoi cho phat hien bao dong."""
    global last_temp_raw, last_smoke_raw
    t = sample_temp()
    last_temp_raw = t
    if t is not None:
        push(temp_buf, t, TEMP_WINDOW)
    last_smoke_raw = sample_smoke()
    push(smoke_buf, last_smoke_raw, SMOKE_WINDOW)


def filtered_values():
    t = round(median(temp_buf), 1) if temp_buf else None
    s = round(median(smoke_buf), 1) if smoke_buf else None
    return t, s


# ---------------- PHAT HIEN QUA NHIET / KHOI ----------------
def update_alarm():
    """Cap nhat trang thai bao dong. Tra ve True neu VUA chuyen sang bao dong."""
    global alarm, over_count, under_count
    temp_hot = last_temp_raw is not None and last_temp_raw > TEMP_ALERT
    smoke_hot = last_smoke_raw >= SMOKE_ALERT
    temp_ok = last_temp_raw is None or last_temp_raw < TEMP_CLEAR
    smoke_ok = last_smoke_raw < SMOKE_CLEAR

    just_started = False
    if temp_hot or smoke_hot:
        over_count += 1
        under_count = 0
    elif temp_ok and smoke_ok:
        under_count += 1
        over_count = 0
    # (o giua nguong bao dong va nguong tat: giu nguyen bo dem)

    if not alarm and over_count >= CONFIRM_SAMPLES:
        alarm = True
        just_started = True
        reasons = []
        if temp_hot:
            reasons.append("QUA NHIET {} C".format(last_temp_raw))
        if smoke_hot:
            reasons.append("KHOI CAO {:.1f} %".format(last_smoke_raw))
        print("!!! BAO DONG: " + " + ".join(reasons))
    elif alarm and under_count >= CLEAR_SAMPLES:
        alarm = False
        print("--- Het bao dong, tro lai che do binh thuong")
    return just_started


def values_to_send():
    """Khi bao dong: gui gia tri moi nhat (khong tre). Binh thuong: gia tri da loc."""
    t, s = filtered_values()
    if alarm:
        if last_temp_raw is not None:
            t = round(last_temp_raw, 1)
        s = round(last_smoke_raw, 1)
    return t, s


# ---------------- KET NOI ----------------
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    if wlan.active() and wlan.isconnected():
        return True
    wlan.active(False)
    time.sleep_ms(300)
    wlan.active(True)
    time.sleep_ms(300)

    print("Dang ket noi WiFi", end="")
    wlan.connect(WIFI_SSID, WIFI_PASS)
    for _ in range(15):
        if wlan.isconnected():
            break
        print(".", end="")
        time.sleep(1)
    print()

    if wlan.isconnected():
        print("WiFi OK:", wlan.ifconfig()[0])
        return True
    print("Khong ket noi duoc WiFi (status = {})".format(wlan.status()))
    return False


def connect_mqtt():
    client = MQTTClient(CLIENT_ID, AIO_SERVER, port=AIO_PORT,
                        user=AIO_USER, password=AIO_KEY, keepalive=60)
    client.connect()
    print("MQTT OK:", AIO_SERVER)
    return client


def publish_data(client, temp, smoke):
    if temp is not None:
        client.publish(TOPIC_TEMP, str(temp))
    if smoke is not None:
        client.publish(TOPIC_SMOKE, str(smoke))


# ---------------- CHUONG TRINH CHINH ----------------
def main():
    print("=== NODE 1 - SENSOR NODE ===")

    if AIO_USER.startswith("YOUR_") or AIO_KEY.startswith("YOUR_"):
        print("CANH BAO: chua dien AIO_USER / AIO_KEY - se khong gui duoc len Adafruit IO")

    while not connect_wifi():
        time.sleep(3)

    client = None

    take_samples()
    last_sample = time.ticks_ms()
    last_publish = time.ticks_ms()

    while True:
        now = time.ticks_ms()
        force_publish = False

        # 1) Lay mau + kiem tra bao dong
        if time.ticks_diff(now, last_sample) >= SAMPLE_INTERVAL_MS:
            last_sample = now
            take_samples()
            if update_alarm():
                force_publish = True       # Vua bao dong -> gui NGAY

        # 2) Publish dinh ky (nhanh hon khi dang bao dong)
        interval = ALERT_PUBLISH_INTERVAL_MS if alarm else PUBLISH_INTERVAL_MS
        if force_publish or time.ticks_diff(now, last_publish) >= interval:
            last_publish = now
            temp, smoke = values_to_send()
            print("[{}] Temp: {} C | Smoke: {} %".format(
                "BAO DONG" if alarm else "BINH THUONG", temp, smoke))

            try:
                if client is None:
                    client = connect_mqtt()
                publish_data(client, temp, smoke)
                print("Da publish len Adafruit IO")
            except Exception as e:
                print("Loi MQTT:", e)
                try:
                    if client:
                        client.disconnect()
                except Exception:
                    pass
                client = None
                connect_wifi()

        time.sleep_ms(100)


if __name__ == "__main__":
    main()