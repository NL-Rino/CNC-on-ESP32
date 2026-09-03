# Nhật ký thay đổi

## v1.0.1 — 2026-09-03

Bản phát hành đầu tiên dùng được đầy đủ của **PipeCut Studio**: phần mềm máy
tính điều khiển máy cắt ống 4 trục chạy ESP32 + FluidNC qua cổng COM.

### Bố trí trục

Khớp với máy có **phôi ống tự tịnh tiến**:

| Trục | Vai trò | Đơn vị |
|---|---|---|
| **Y** | ống ra vào (bàn mang mâm cặp chạy dọc trục ống) | mm |
| **A** | mâm cặp xoay ống | độ |
| **X** | mỏ cắt chạy ngang, vuông góc trục Y | mm |
| **Z** | mỏ cắt lên xuống | mm |

Vai trò trục khai báo trong hồ sơ máy, đổi được sang kiểu **xe mỏ cắt chạy còn
ống đứng yên** bằng `"layout": "torch_moves"`.

### Sinh biên dạng

10 nguyên công, toán giao tuyến suy trực tiếp từ phương trình mặt trụ:
cắt đứt/cắt vát, miệng cá (chữ T, chữ Y, lệch tâm), lỗ xuyên thành ống
(hướng tâm hoặc xiên), rãnh/cửa sổ bo góc, tròn trên bề mặt, xoắn ốc,
đường dọc thân ống, vạch dấu vòng, vát mép hàn, và biên dạng trải phẳng
tự do nạp từ DXF/CSV.

### Đường cắt mượt nhờ bốn trục phối hợp

* **Bù tốc độ tổng hợp** — FluidNC cộng *độ* của trục xoay chung với *mm* của
  trục thẳng khi chia `F`. Phần mềm tính lại F cho từng đoạn theo
  `F = v_cắt × L_trục / L_bề_mặt`, giữ **tốc độ mũi cắt trên bề mặt ống không
  đổi** ở mọi tỉ lệ phối hợp trục (đo được sai số < 0,5 mm/phút).
* **Điều tiết mật độ điểm** — lấy mẫu thích nghi theo dung sai dây cung, rút gọn
  Douglas–Peucker, gộp đoạn quá ngắn, chia đoạn quá dài.
* **Nạp lệnh đếm ký tự** — giữ bộ đệm ESP32 luôn gần đầy (đo được 124/127 byte)
  để planner luôn có hàng chục block nhìn trước.
* Mọi xử lý làm trên **mặt trụ trải phẳng** (phép đẳng cự) nên bù kerf, bo góc
  và đo chiều dài đều chính xác tuyệt đối; góc quay biến thiên liên tục, không
  bao giờ nhảy ±180°.

### Giao diện

Sáu tab theo trình tự làm việc: Máy & Kết nối → Điều khiển → Công việc →
Xem trước → **Mô phỏng** → Chạy.

* **Mô phỏng 3D** dựng lại đúng máy thật: đoạn ống dài theo kích thước nhập vào,
  trượt ra vào và quay dưới mỏ cắt, vết cắt đỏ hiện dần trên phôi. Chạy offline,
  tua tới lui, tốc độ 0,25×–20×, xoay/dịch/phóng bằng chuột, xuất ảnh SVG.
  Khi nối máy thật, khung này bám theo vị trí máy báo về.
* Điều khiển tay có jog theo vai trò trục, DRO, về gốc, đặt gốc chi tiết,
  bảng nhật ký giao tiếp và ô gõ lệnh trực tiếp.
* Chạy chương trình có thanh tiến độ, tô sáng dòng đang chạy, tạm dừng
  (feed hold) và dừng khẩn.

### Công cụ khác

* **Máy ảo FluidNC** dựng sẵn: dùng thử toàn bộ phần mềm khi chưa có phần cứng
  (chọn cổng `GIA-LAP`).
* **CLI** đầy đủ: `ports`, `ops`, `gen`, `preview`, `sim`, `send`, `run`, `demo`.
* Xuất bản vẽ xem trước SVG (trải phẳng + hình chiếu trục đo, ẩn nét khuất).
* Ba hồ sơ máy mẫu, cấu hình FluidNC cho ESP32, bốn tệp công việc mẫu.
* Mã lỗi và báo động Grbl/FluidNC dịch sang tiếng Việt.

### Kiểm thử

72 bài kiểm thử chạy bằng thư viện chuẩn (`python -m unittest discover -s tests -t .`),
gồm bài dựng lại điểm 3D để kiểm tra biên dạng giao tuyến nằm đồng thời trên cả
hai mặt trụ, và bài đo tốc độ bề mặt trên toàn bộ một đường miệng cá.

### Yêu cầu

Python 3.9 trở lên. Chỉ cần `pyserial` khi nối cổng COM thật; phần sinh G-code và
mô phỏng chạy bằng thư viện chuẩn. Giao diện dùng Tkinter (có sẵn cùng Python trên
Windows/macOS; Linux cài thêm `python3-tk`).
