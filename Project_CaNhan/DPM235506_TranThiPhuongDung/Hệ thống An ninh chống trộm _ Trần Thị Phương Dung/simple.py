import usocket as socket
import ustruct as struct
from ubinascii import hexlify

class MQTTException(Exception):
    pass

class MQTTClient:
    def __init__(self, client_id, server, port=0, user=None, password=None, keepalive=0, ssl=False, ssl_params={}):
        if port == 0:
            port = 8883 if ssl else 1883
        self.client_id = client_id
        self.sock = None
        self.server = server
        self.port = port
        self.ssl = ssl
        self.ssl_params = ssl_params
        self.pid = 0
        self.cb = None
        self.user = user
        self.pswd = password
        self.keepalive = keepalive
        self.lw_topic = None
        self.lw_msg = None
        self.lw_qos = 0
        self.lw_retain = False

    def _send_str(self, s):
        self.sock.write(struct.pack("!H", len(s)))
        self.sock.write(s)

    def _recv_len(self):
        n = 0
        sh = 0
        while 1:
            b = self.sock.read(1)
            if not b:
                return None
            b = b[0]
            n |= (b & 0x7f) << sh
            if not (b & 0x80):
                return n
            sh += 7

    def set_callback(self, f):
        self.cb = f

    def connect(self, clean_session=True):
        self.sock = socket.socket()
        addr = socket.getaddrinfo(self.server, self.port)[0][-1]
        self.sock.connect(addr)
        if self.ssl:
            import ussl
            self.sock = ussl.wrap_socket(self.sock, **self.ssl_params)
        msg = bytearray(b"\x10\x00\x00\x04MQTT\x04\x02\x00\x00")
        msg[1] = 10 + 2 + len(self.client_id)
        msg[9] = clean_session << 1
        if self.user is not None:
            msg[1] += 2 + len(self.user) + 2 + len(self.pswd)
            msg[9] |= 0xC0
        if self.keepalive:
            msg[10] |= self.keepalive >> 8
            msg[11] |= self.keepalive & 0xFF
        self.sock.write(msg)
        self._send_str(self.client_id)
        if self.user is not None:
            self._send_str(self.user)
            self._send_str(self.pswd)
        resp = self.sock.read(4)
        assert resp[0] == 0x20 and resp[1] == 0x02
        if resp[3] != 0:
            raise MQTTException(resp[3])
        return resp[2] & 1

    def disconnect(self):
        self.sock.write(b"\xe0\x00")
        self.sock.close()

    def publish(self, topic, msg, retain=False, qos=0):
        pkt = bytearray(b"\x30\x00")
        pkt[0] |= (qos << 1) | retain
        sz = 2 + len(topic) + len(msg)
        if sz >= 2097152:
            raise MQTTException("Message too long")
        while sz > 0x7f:
            pkt.append((sz & 0x7f) | 0x80)
            sz >>= 7
        pkt.append(sz)
        self.sock.write(pkt)
        self._send_str(topic)
        self.sock.write(msg)

    def subscribe(self, topic, qos=0):
        self.pid += 1
        pkt = bytearray(b"\x82\x00\x00\x00")
        sz = 2 + 2 + len(topic) + 1
        pkt[1] = sz
        struct.pack_into("!H", pkt, 2, self.pid)
        self.sock.write(pkt)
        self._send_str(topic)
        self.sock.write(bytes([qos]))
        resp = self.sock.read(5)
        assert resp[0] == 0x90 and resp[2] == (self.pid >> 8) and resp[3] == (self.pid & 0xFF)

    def check_msg(self):
        res = self.sock.read(1)
        if res is None:
            return None
        if res == b"":
            return None
        if res[0] == 0x30:
            sz = self._recv_len()
            topic_len = struct.unpack("!H", self.sock.read(2))[0]
            topic = self.sock.read(topic_len)
            sz -= topic_len + 2
            msg = self.sock.read(sz)
            if self.cb:
                self.cb(topic, msg)
            return True