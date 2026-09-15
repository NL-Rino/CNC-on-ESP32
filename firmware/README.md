# Nạp bộ não xuống ESP32 (phần làm sau)

Thư mục này chứa **phần chạy bộ não + phần nhận dạng trạm sạc**, chưa phải
firmware hoàn chỉnh. Mục đích là khi làm phần cứng thì không phải viết lại từ
đầu, và để biết trước phải đo đạc những gì.

## 1. Xuất trọng số

```bash
python3 tools/export_c.py brains/car_v2.npz firmware/policy_weights.h
```

Sinh ra mảng `float` (~3.2k số, ~26 KB Flash). `brain.c` chạy đúng phép toán GRU
như `train/policy.py`. Một bước suy luận ~0.3 ms trên ESP32 240 MHz — thừa sức
chạy vòng 20 Hz.

## 2. Vòng điều khiển 20 Hz

```
LiDAR Camsense đẩy gói UART liên tục
   └─> gom đủ MỘT VÒNG (~150 ms ở 7 Hz)
        └─> dock_detect()  -> tối đa 2 ứng viên hộc chữ U (vị trí + TRỤC)
mỗi 50 ms:
   1. dựng obs[48]  (thứ tự trong brain.h — SAI MỘT Ô LÀ BỘ NÃO ĐIÊN)
   2. brain_step(&st, obs, u)
   3. LỚP PHẢN XẠ AN TOÀN ghi đè u nếu cảm biến vực kêu
   4. xuất PWM cho 2 cặp bánh
```

`dock_detect.c` là bản C của `sim/dock_detector.py` — đã kiểm tra cho **kết quả
trùng khít** với bản Python trên cùng dữ liệu quét (xem `tests/test_firmware.py`).
Sửa một bên mà quên bên kia là bộ não sẽ gặp dữ liệu khác lúc huấn luyện.

## 3. Gợi ý phần cứng

| Khối | Linh kiện | Ghi chú |
|---|---|---|
| LiDAR | **Camsense X1/X2** | UART 115200 8N1, đẩy gói liên tục, mỗi gói vài điểm kèm góc + tốc độ quay. Dùng SDK/driver chính chủ hoặc parser ROS có sẵn. Cấp nguồn động cơ riêng, đừng lấy chung 3V3 với ESP32. Gom đủ một vòng (góc quay qua 360°) rồi mới gọi `dock_detect`. |
| 2 × cảm biến vực | TCRT5000 / E18-D80NK chiếu xuống | đặt cách tâm xe **≥ 14.5 cm** (mép thân xe 30 cm), càng xa càng an toàn. Lấy ngưỡng bằng cách đo giá trị trên mặt bàn vs. không có gì |
| Mắt thu IR | 2 module TSOP khác tần số (TSOP4838 38 kHz cho "gọi", TSOP4856 56 kHz cho trạm sạc) | "cường độ" lấy bằng cách đếm tỉ lệ xung trong 50 ms. Đặt ở đầu xe, có ống che để góc thu ~±45° |
| Trạm sạc | **hộc chữ U**: ngoài 40 × 40 cm, lòng trong 31 × 31 cm, vách dày 4.5 cm. LED IR 56 kHz gắn **giữa thành trong**, chiếu thẳng ra cửa | Ba mặt vách phải phẳng và **không bóng loáng** — LiDAR cần dội về đều thì mới đo được độ lõm và khớp được trục. **Vát hai góc trong ở miệng**: 8 cm đầu nong ra ~37 cm rồi thu về 31 cm. Không có đoạn vát này thì xe 30 cm phải vào đúng ±5 mm và ±1°, tức là bất khả thi — xem `docs/DESIGN.md` mục 10(f) |
| Odometry | encoder 2 bánh (bắt buộc) + IMU (nên có) | không có encoder thì xe không nhớ nổi đường về trạm |
| Đo pin | chia áp + ADC1, lọc trung bình trượt | ADC ESP32 không tuyến tính, nhớ hiệu chỉnh |
| Động cơ | 2 driver TB6612FNG / DRV8833 | LEDC PWM 20 kHz. Hai bánh cùng bên nối song song = 1 kênh |

## 4. Lớp phản xạ an toàn (BẮT BUỘC)

Mạng nơ-ron có thể lỗi. Cảm biến vực phải có đường cắt thẳng, không qua bộ não:

```c
if (cliff_front && u_forward > 0) { u_left = u_right = -0.7f; }
if (cliff_rear  && u_forward < 0) { u_left = u_right = +0.6f; }
if (battery_volt < CUTOFF)        { u_left = u_right = 0; }
```

Lúc huấn luyện **không** bật lớp này, để bộ não tự học sợ mép bàn; lớp này chỉ
là lưới đỡ khi ra đời thật.

## 5. Kiểm tra trước khi thả xe lên bàn

1. Ghi log 48 số `obs` ra Serial và đối chiếu với mô phỏng — đây là cách nhanh
   nhất để phát hiện sai thứ tự hoặc sai chuẩn hoá.
2. Đo lại `v_max`, `motor_tau` thật rồi sửa `sim/robot.py` và huấn luyện lại.
3. Đo dải cường độ IR thật theo góc và khoảng cách, sửa hàm trong `sim/sensors.py`.
4. Kiểm tra `dock_detect` trên dữ liệu quét thật trước khi tin vào nó: in ra
   bearing/dist của ứng viên rồi lấy thước đo lại.
5. Chạy trên sàn (không có vực) trước, rồi mới lên bàn thấp có trải đệm bên dưới.
