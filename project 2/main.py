import time
import network
from machine import Pin, PWM, Timer
from umqtt.simple import MQTTClient
from config import WIFI_SSID, WIFI_PASS, AIO_SERVER, AIO_PORT, AIO_USER, AIO_KEY, GROUP

# ============ PROJECT 2: TRẠM CHỮA CHÁY & THÔNG GIÓ ============
# Nhận lệnh từ Project 4 (Control Room):
#   emergency_status : SAFE / SMOKE / FIRE / TEST   (cũng hiểu ON/1/TRUE = FIRE, OFF = SAFE)
#   manual-vent      : ON / OFF  (nút mở cửa thông gió)
# Bảng điều khiển:
#   SAFE            -> tất cả tắt
#   HOT             -> quạt + cửa thông gió (làm mát; không còi, không bơm)
#   SMOKE           -> quạt + cửa thông gió + còi (bơm TẮT)   (cửa ra vào do Project 3)
#   FIRE / TEST     -> quạt + cửa thông gió + còi + bơm
#   manual-vent ON  -> CHỈ cửa thông gió
# Gửi trạng thái thật của thiết bị lên Adafruit (chỉ khi thay đổi) để dashboard hiển thị.


def topic(name):
    return "{}/f/{}.{}".format(AIO_USER, GROUP, name)


T_EMERGENCY = topic("emergency_status")
T_MANUAL = topic("manual-vent")
T_FAN = topic("fan-state")
T_VENT = topic("vent-state")
T_PUMP = topic("pump-state")
T_ALARM = topic("alarm-state")


def parse_mode(value):
    v = value.strip().upper()
    if v in ("FIRE", "ON", "1", "TRUE"):
        return "FIRE"
    if v == "TEST":
        return "TEST"
    if v == "SMOKE":
        return "SMOKE"
    if v == "HOT":
        return "HOT"
    return "SAFE"


def is_on(value):
    return value.strip().upper() in ("ON", "1", "TRUE")


class StepperMotor:
    PHASES = ((1, 0, 1, 0), (0, 1, 1, 0), (0, 1, 0, 1), (1, 0, 0, 1))

    def __init__(self, pin_numbers, step_ms, sense_pin):
        self.pins = tuple(Pin(n, Pin.OUT, value=0) for n in pin_numbers)
        self.step_ms = step_ms
        self.sense = Pin(sense_pin, Pin.IN, Pin.PULL_DOWN)
        self.requested = False
        self.running = False
        self.index = 0
        self.last_step = time.ticks_ms()

    def set_running(self, requested):
        self.requested = bool(requested)

    def service(self):
        running = self.requested and bool(self.sense.value())
        now = time.ticks_ms()
        if not running:
            if self.running:
                for pin in self.pins:
                    pin.value(0)
            self.running = False
            return
        self.running = True
        if time.ticks_diff(now, self.last_step) >= self.step_ms:
            self.last_step = now
            phase = self.PHASES[self.index]
            self.index = (self.index + 1) & 3
            for pin, level in zip(self.pins, phase):
                pin.value(level)


class FireVentNode:
    def __init__(self):
        self.fan = Pin(26, Pin.OUT, value=0)
        self.pump = Pin(27, Pin.OUT, value=0)
        self.fan_motor = StepperMotor((19, 21, 22, 23), 10, 32)
        self.pump_motor = StepperMotor((13, 14, 16, 17), 20, 33)
        self.servo = PWM(Pin(18), freq=50)
        self.buzzer = PWM(Pin(25), freq=2000, duty_u16=0)

        self.mode = "SAFE"      # SAFE / SMOKE / FIRE / TEST (do Project 4 quyết định)
        self.manual = False     # nút mở cửa thông gió
        self.fan_on = False
        self.vent_on = False
        self.pump_on = False
        self.alarm_on = False
        self.full = False
        self._buz = False

        self.motor_timer = Timer(1)
        self.motor_timer.init(period=10, mode=Timer.PERIODIC, callback=lambda t: self.service_motors())
        self.apply()

    def apply(self):
        full = self.mode in ("FIRE", "TEST")
        smoke = self.mode == "SMOKE"
        hot = self.mode == "HOT"                       # nhiệt cao, khói thường: quạt + cửa gió để làm mát
        self.full = full
        self.fan_on = full or smoke or hot
        self.vent_on = full or smoke or hot or self.manual   # nút thủ công: chỉ cửa thông gió
        self.pump_on = full                            # bơm chỉ bật khi cháy / test
        self.alarm_on = full or smoke

        self.fan.value(1 if self.fan_on else 0)
        self.pump.value(1 if self.pump_on else 0)
        time.sleep_ms(2)
        self.fan_motor.set_running(self.fan_on)
        self.pump_motor.set_running(self.pump_on)

        pulse_us = 500 + (90 if self.vent_on else 0) * 2000 // 180
        self.servo.duty_u16(pulse_us * 65535 // 20000)

        if not self.alarm_on:
            self.set_buzzer(False)

        print("[P2] mode={} manual={} | Quạt:{} | Cửa gió:{} | Bơm:{} | Còi:{}".format(
            self.mode, self.manual,
            "BẬT" if self.fan_on else "TẮT", "MỞ" if self.vent_on else "ĐÓNG",
            "BẬT" if self.pump_on else "TẮT", "BẬT" if self.alarm_on else "TẮT"))

    def set_buzzer(self, on):
        if on != self._buz:
            self._buz = on
            self.buzzer.duty_u16(32768 if on else 0)

    def tick_buzzer(self):
        if not self.alarm_on:
            return
        now = time.ticks_ms()
        period = 400 if self.full else 1000   # cháy: bíp nhanh, khói: bíp chậm
        self.set_buzzer((now % period) < 200)

    def service_motors(self):
        self.fan_motor.service()
        self.pump_motor.service()

    def states(self):
        return ((T_FAN, self.fan_on), (T_VENT, self.vent_on), (T_PUMP, self.pump_on), (T_ALARM, self.alarm_on))

    def on_message(self, tpc, payload):
        t = tpc.decode("utf-8") if isinstance(tpc, bytes) else str(tpc)
        v = payload.decode("utf-8") if isinstance(payload, bytes) else str(payload)
        print("[P2 - RECV MQTT]", t, "->", v)
        if t == T_EMERGENCY:
            self.mode = parse_mode(v)
        elif t == T_MANUAL:
            self.manual = is_on(v)
        else:
            return
        self.apply()


wlan = network.WLAN(network.STA_IF)


def connect_wifi():
    if wlan.isconnected():
        return
    wlan.active(True)
    wlan.connect(WIFI_SSID, WIFI_PASS)
    t0 = time.ticks_ms()
    while not wlan.isconnected():
        if time.ticks_diff(time.ticks_ms(), t0) > 20000:
            raise OSError("WiFi timeout")
        time.sleep_ms(300)


#def publish_states(client, node, last):
    #for tpc, value in node.states():
        #if last.get(tpc) != value:
            #client.publish(tpc, "ON" if value else "OFF")
            #last[tpc] = value


def main():
    print("=== PROJECT 2: TRẠM CHỮA CHÁY & THÔNG GIÓ (START) ===")
    node = FireVentNode()
    client = None
    last = {}
    last_ping = time.ticks_ms()
    while True:
        try:
            connect_wifi()
            if client is None:
                client = MQTTClient("esp32-node2-{}".format(time.ticks_ms()), AIO_SERVER, port=AIO_PORT,
                                    user=AIO_USER, password=AIO_KEY, keepalive=60)
                client.set_callback(node.on_message)
                client.connect()
                client.subscribe(T_EMERGENCY)
                client.subscribe(T_MANUAL)
                client.publish(T_EMERGENCY + "/get", b"")   # lấy giá trị mới nhất trên cloud
                client.publish(T_MANUAL + "/get", b"")
                last.clear()                                # gửi lại trạng thái sau khi nối lại
                last_ping = time.ticks_ms()
                print("[P2 - MQTT] Đã kết nối Adafruit IO")

            client.check_msg()
            node.tick_buzzer()
            #publish_states(client, node, last)

            now = time.ticks_ms()
            if time.ticks_diff(now, last_ping) >= 30000:
                client.ping()
                last_ping = now
            time.sleep_ms(20)
        except Exception as e:
            print("[P2 - ERROR] {} -> tự kết nối lại sau 2s...".format(e))
            try:
                client.disconnect()
            except Exception:
                pass
            client = None
            time.sleep(2)


if __name__ == "__main__":
    main()