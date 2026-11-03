import time
import network
import dht
from machine import Pin, ADC
from umqtt.simple import MQTTClient
from config import WIFI_SSID, WIFI_PASS, AIO_SERVER, AIO_PORT, AIO_USER, AIO_KEY, GROUP

# ================= PROJECT 1: NODE CẢM BIẾN =================
CLIENT_ID = "esp32-node1-sensor"


def topic(name):
    return "{}/f/{}.{}".format(AIO_USER, GROUP, name)


TOPIC_TEMP = topic("temp")
TOPIC_SMOKE = topic("smoke")
TOPIC_HUM = topic("humidity")

# Adafruit IO bản free: tối đa 30 điểm dữ liệu / phút cho CẢ tài khoản (4 project dùng chung).
# Nên chỉ gửi khi giá trị đổi đủ lớn (tối thiểu cách nhau 5 giây),
# và gửi lại định kỳ 30 giây để dashboard biết cảm biến vẫn sống.
READ_MS = 1000
MIN_GAP_MS = 5000
HEARTBEAT_MS = 30000

sensor = dht.DHT22(Pin(15))
adc = ADC(Pin(34))
adc.atten(ADC.ATTN_11DB)
adc.width(ADC.WIDTH_12BIT)
wlan = network.WLAN(network.STA_IF)


class Feed:
    def __init__(self, topic_name, step):
        self.topic = topic_name
        self.step = step
        self.last = None
        self.last_ms = 0

    def due(self, value, now):
        if self.last is None:
            return True
        age = time.ticks_diff(now, self.last_ms)
        if age >= HEARTBEAT_MS:
            return True
        return age >= MIN_GAP_MS and abs(value - self.last) >= self.step

    def publish(self, client, value, now):
        client.publish(self.topic, str(value))
        self.last = value
        self.last_ms = now


def sample_smoke():
    raw = [adc.read() for _ in range(10)]
    return (sum(raw) / len(raw)) * 100 / 4095


def read_dht():
    try:
        sensor.measure()
        return round(sensor.temperature(), 1), int(round(sensor.humidity()))
    except OSError as e:
        print("[P1 - DHT] Lỗi đọc cảm biến:", e)
        return None, None


def connect_wifi():
    if wlan.isconnected():
        return
    wlan.active(True)
    print("[P1 - WiFi] Đang kết nối WiFi Wokwi-GUEST...")
    wlan.connect(WIFI_SSID, WIFI_PASS)
    t0 = time.ticks_ms()
    while not wlan.isconnected():
        if time.ticks_diff(time.ticks_ms(), t0) > 20000:
            raise OSError("WiFi timeout")
        time.sleep_ms(300)
    print("[P1 - WiFi] Kết nối thành công! IP:", wlan.ifconfig()[0])


def main():
    print("==========================================")
    print("=== PROJECT 1: NODE CẢM BIẾN (START) ===")
    print("==========================================")
    f_temp = Feed(TOPIC_TEMP, 0.5)
    f_smoke = Feed(TOPIC_SMOKE, 2.0)
    f_hum = Feed(TOPIC_HUM, 3)
    client = None
    last_ping = time.ticks_ms()

    while True:
        try:
            connect_wifi()
            if client is None:
                print("[P1 - MQTT] Đang kết nối tới Adafruit IO...")
                client = MQTTClient(CLIENT_ID, AIO_SERVER, port=AIO_PORT, user=AIO_USER,
                                    password=AIO_KEY, keepalive=60)
                client.connect()
                for f in (f_temp, f_smoke, f_hum):
                    f.last = None  # gửi lại ngay sau khi nối lại
                last_ping = time.ticks_ms()
                print("[P1 - MQTT] Đã kết nối thành công!")

            now = time.ticks_ms()
            temp, hum = read_dht()
            smoke = round(sample_smoke(), 1)
            print("[P1 - ĐỌC CẢM BIẾN] Nhiệt độ: {} C | Độ ẩm: {} % | Khói: {} %".format(temp, hum, smoke))

            sent = []
            if temp is not None and f_temp.due(temp, now):
                f_temp.publish(client, temp, now)
                sent.append("temp")
            if f_smoke.due(smoke, now):
                f_smoke.publish(client, smoke, now)
                sent.append("smoke")
            if hum is not None and f_hum.due(hum, now):
                f_hum.publish(client, hum, now)
                sent.append("humidity")
            if sent:
                print("[P1 - PUBLISH] Đã gửi:", ", ".join(sent))

            if time.ticks_diff(now, last_ping) >= 30000:
                client.ping()
                last_ping = now
            time.sleep_ms(READ_MS)
        except Exception as e:
            print("[P1 - ERROR] {} -> tự kết nối lại sau 2s...".format(e))
            try:
                client.disconnect()
            except Exception:
                pass
            client = None
            time.sleep(2)


if __name__ == "__main__":
    main()
