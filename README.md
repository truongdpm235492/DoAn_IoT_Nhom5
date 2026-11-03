# Hệ thống giám sát môi trường xưởng thực phẩm thông minh

Đồ án môn **Internet of Things (IoT)** – Khoa Công nghệ Thông tin, Trường Đại học An Giang.
Giảng viên hướng dẫn: Ths. Huỳnh Lý Thanh Nhàn.

Hệ thống giám sát nhiệt độ, độ ẩm và nồng độ khói trong xưởng sản xuất thực phẩm, tự động phân loại mức nguy hiểm, điều khiển thiết bị xử lý và **cảnh báo sớm đa kênh** (tại chỗ, Telegram, Web). Toàn bộ chạy trên trình mô phỏng **Wokwi**.

## Thành viên

| STT | Họ tên | MSSV |
| --- | --- | --- |
| 1 | ... | ... |
| 2 | ... | ... |
| 3 | ... | ... |
| 4 | ... | ... |
| 5 | ... | ... |

## Kiến trúc

Bốn vi điều khiển ESP32 (MicroPython), mỗi cái là một dự án Wokwi riêng, giao tiếp với nhau qua **Adafruit IO** bằng MQTT. Trang web quản lý đọc dữ liệu qua REST API.

| Nút | Vai trò | Thiết bị chính |
| --- | --- | --- |
| Project 1 | Nút cảm biến | DHT22, biến trở giả lập khói. Gửi `temp`, `smoke`, `humidity` |
| Project 2 | Trạm chữa cháy và thông gió | Relay quạt/bơm + động cơ bước, servo cửa thông gió, còi |
| Project 3 | Cửa ra vào (sơ tán) | Servo cửa, nút bấm, LED đỏ/xanh |
| Project 4 | Phòng điều khiển | OLED, công tắc Test, công tắc cửa thông gió, còi. **Nơi duy nhất ra quyết định**, gửi Telegram |

Nguyên tắc: chỉ Project 4 phân loại kịch bản và ghi vào feed `emergency_status`; Project 2 và 3 chỉ đọc feed này rồi điều khiển thiết bị.

## Feed trên Adafruit IO

Tất cả nằm trong group `doannhom` (tổng 7 feed, nằm trong giới hạn 10 feed của tài khoản miễn phí). Chủ đề MQTT: `<tên_tài_khoản>/f/doannhom.<tên_feed>`

| Feed | Bên ghi | Ý nghĩa |
| --- | --- | --- |
| `temp` | Project 1 | Nhiệt độ (°C) |
| `humidity` | Project 1 | Độ ẩm (%) |
| `smoke` | Project 1 | Nồng độ khói (%), thang 0 - 100 |
| `emergency_status` | Project 4 | `SAFE` / `HOT` / `SMOKE` / `FIRE` / `TEST` |
| `manual-vent` | Project 4 | `ON` / `OFF`: mở cửa thông gió thủ công |
| `vent-cmd` | Web | `ON` / `OFF`: lệnh mở cửa thông gió từ web |
| `test-cmd` | Web | `ON` / `OFF`: lệnh test cảnh báo từ web |

## Ngưỡng và kịch bản

| Đại lượng | Vào cảnh báo | Thoát cảnh báo |
| --- | --- | --- |
| Nhiệt độ | từ 45 °C | dưới 43 °C |
| Khói | từ 60 % | dưới 50 % |

Thứ tự ưu tiên (Project 4 xét từ trên xuống): **TEST** → **FIRE** (khói và nhiệt cùng vượt) → **SMOKE** (chỉ khói) → **HOT** (chỉ nhiệt) → **SAFE**.

## Cấu trúc thư mục

```
.
├── project1_sensor/         # Nút cảm biến
├── project2_fire_vent/      # Trạm chữa cháy và thông gió
├── project3_door/           # Cửa ra vào
├── project4_control_room/   # Phòng điều khiển
│   ├── main.py
│   ├── config.example.py    # Mẫu cấu hình (copy thành config.py)
│   └── diagram.json         # Sơ đồ mạch Wokwi
├── dashboard/
│   └── dashboard.html       # Trang web quản lý (một tệp)
└── docs/                    # Báo cáo và hình ảnh
```

## Hướng dẫn cài đặt và chạy

1. Tạo tài khoản **Adafruit IO**, tạo group tên `doannhom`, lấy **AIO Key**.
2. Tạo bot Telegram qua **@BotFather**, lấy **token** và **chat ID**.
3. Trong mỗi thư mục dự án, copy `config.example.py` thành `config.py` rồi điền thông tin thật. **Không commit `config.py`** (đã nằm trong `.gitignore`).
4. Trên Wokwi, tạo 4 dự án ESP32 MicroPython. Dán `main.py`, `config.py` và `diagram.json` của từng dự án vào dự án tương ứng.
5. Chạy theo thứ tự: **Project 4 → Project 2 → Project 3 → Project 1** (Project 4 tạo các feed lệnh trước).
6. Mở `dashboard/dashboard.html` bằng trình duyệt, nhập tên tài khoản và AIO Key ở phần Cấu hình, bấm **Lưu và kết nối**.
7. Kéo biến trở (khói) và nhiệt độ DHT22 trong Wokwi để tạo từng kịch bản.

## Liên kết dự án Wokwi

- Project 1: <dán link>
- Project 2: <dán link>
- Project 3: <dán link>
- Project 4: <dán link>

## Hạn chế

Hệ thống chỉ chạy mô phỏng trên Wokwi: khói giả lập bằng biến trở, nhiệt độ và độ ẩm từ DHT22 mô phỏng; chưa kiểm nghiệm với cảm biến và thiết bị công suất thật.
