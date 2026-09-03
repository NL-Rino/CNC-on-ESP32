# Hướng dẫn sử dụng PipeCut Studio

## Mục lục

1. [Chuẩn bị phần cứng](#1-chuẩn-bị-phần-cứng)
2. [Nạp và cấu hình FluidNC](#2-nạp-và-cấu-hình-fluidnc)
3. [Hiệu chỉnh trục xoay](#3-hiệu-chỉnh-trục-xoay)
4. [Cài đặt phần mềm](#4-cài-đặt-phần-mềm)
5. [Khai báo hồ sơ máy](#5-khai-báo-hồ-sơ-máy)
6. [Đặt gốc toạ độ](#6-đặt-gốc-toạ-độ)
7. [Tạo công việc](#7-tạo-công-việc)
8. [Chạy chương trình](#8-chạy-chương-trình)
9. [Định dạng tệp công việc](#9-định-dạng-tệp-công-việc)
10. [Xử lý sự cố](#10-xử-lý-sự-cố)

---

## 1. Chuẩn bị phần cứng

Cấu hình cơ khí tối thiểu cho máy cắt ống 4 trục:

| Bộ phận | Yêu cầu |
|---|---|
| Mâm cặp xoay (A) | Nối với động cơ bước qua hộp giảm tốc (6:1 tới 20:1). Tỉ số càng lớn, mô-men giữ càng khoẻ và góc quay càng mịn |
| Bàn chạy dọc (Y) | Mang cả mâm cặp và phôi ống, tịnh tiến ra vào. Vitme bi hoặc thanh răng, hành trình ≥ chiều dài phôi |
| Trục Z | Mỏ cắt lên xuống, hành trình 100–150 mm |
| Trục X | Mỏ cắt chạy ngang, vuông góc với trục Y — hoặc dùng làm cơ cấu nghiêng để vát mép |
| Giá đỡ phôi | Con lăn đỡ đầu ống phía ngoài mâm cặp — **bắt buộc** với ống dài |
| Bo mạch | ESP32 (DevKit, MKS DLC32, FluidNC v2...) + driver bước |

> **Lưu ý về độ đảo.** Ống thép hộp/tròn thường không tròn tuyệt đối và hay bị
> cong. Độ đảo của phôi ảnh hưởng trực tiếp tới khoảng cách mỏ–phôi. Nếu cắt
> plasma, nên có bộ điều khiển chiều cao (THC) hoặc chọn ống thẳng.

---

## 2. Nạp và cấu hình FluidNC

1. Nạp firmware FluidNC vào ESP32 theo hướng dẫn chính thức
   (http://wiki.fluidnc.com).
2. Mở WebUI của FluidNC → **Files** → tải lên
   [`firmware/fluidnc_pipe4axis.yaml`](../firmware/fluidnc_pipe4axis.yaml).
3. Đặt làm cấu hình đang dùng: gõ trong terminal
   `$Config/Filename=fluidnc_pipe4axis.yaml` rồi khởi động lại.
4. **Đối chiếu chân GPIO** trong tệp YAML với bo mạch thực tế trước khi cấp điện
   động lực.

Kiểm tra nhanh bằng PipeCut Studio:

```bash
python -m pipecut ports          # tìm cổng COM (CP2102 / CH340 sẽ được đánh dấu)
```

Vào tab **1. Máy & Kết nối**, chọn cổng, bấm **Kết nối**. Dòng chào
`Grbl 1.1f` hoặc `[VER:...FluidNC...]` xuất hiện trong nhật ký là thành công.

---

## 3. Hiệu chỉnh trục xoay

> **Trục dọc ống ở máy này là Y, không phải X** — vì chính phôi ống tịnh tiến
> chứ không phải xe mang mỏ cắt. Trục X dành cho chuyển động ngang của mỏ cắt.

Trục A tính bằng **độ**, nên `steps_per_mm` của nó chính là **số xung mỗi độ**:

```
steps_per_deg = (xung_mỗi_vòng_động_cơ × vi_bước × tỉ_số_truyền) / 360
```

Ví dụ: động cơ 1.8° (200 xung/vòng), vi bước 1/8, hộp giảm tốc 6:1

```
(200 × 8 × 6) / 360 = 26.667 xung/độ
```

**Kiểm chứng thực tế** (bắt buộc làm một lần):

1. Vạch dấu một điểm trên ống và trên thân máy cho trùng nhau.
2. Trong tab **2. Điều khiển**, đặt bước xoay `90` độ, bấm `+A` bốn lần.
3. Nếu ống quay đúng một vòng và hai vạch trùng lại → đúng.
4. Nếu lệch: `steps_per_deg_mới = steps_per_deg_cũ × 360 / góc_quay_thực`.

Làm tương tự với trục Y (ống ra vào): cho chạy 100 mm, đo bằng thước cặp khoảng
dịch chuyển thật của ống.

---

## 4. Cài đặt phần mềm

```bash
pip install -r requirements.txt     # chỉ cần pyserial
python -m pipecut ui                # mở giao diện
```

Linux cần thêm `sudo apt install python3-tk`.
Linux/macOS cần quyền truy cập cổng: `sudo usermod -a -G dialout $USER` rồi đăng
nhập lại.

**Hãy thử với cổng `GIA-LAP` (máy ảo) trước.** Máy ảo mô phỏng đầy đủ bộ đệm,
hàng đợi chuyển động và báo cáo trạng thái của FluidNC, nên bạn dựng được cả quy
trình mà không cần cắm máy.

---

## 5. Khai báo hồ sơ máy

Tab **1. Máy & Kết nối** có ba nhóm thông số:

**Phôi ống** — đường kính ngoài, chiều dày, chiều dài. Đường kính là thông số
quan trọng nhất: mọi phép quy đổi góc ↔ cung đều dựa vào nó. Hãy **đo bằng thước
cặp**, đừng lấy theo tên gọi danh nghĩa (ống "phi 60" thực tế có thể là 60.3 mm).

**Tiến trình cắt**

| Thông số | Ý nghĩa | Gợi ý cho plasma |
|---|---|---|
| Bề rộng mạch cắt (kerf) | Bề rộng vết cắt thực tế | 1.2–2.0 mm; đo bằng cách cắt thử |
| Tốc độ cắt | Tốc độ **trên bề mặt ống** | Theo bảng của nguồn plasma |
| Cao độ cắt | Khoảng cách mỏ–phôi khi cắt | 1.5–2.0 mm |
| Cao độ mồi | Khi mồi hồ quang | Gấp ~2.5 lần cao độ cắt |
| Thời gian mồi | Chờ hồ quang xuyên thủng | 0.3–0.8 s tuỳ chiều dày |
| Vào dao | Đoạn dẫn để vết mồi không rơi vào chi tiết | 3–5 mm |
| Chạy vượt | Chạy quá điểm khép kín cho đứt hẳn | 1–2 mm |

**Chuyển động & làm mượt**

| Thông số | Ý nghĩa | Ảnh hưởng |
|---|---|---|
| Dung sai dây cung | Sai số cho phép khi bẻ đường cong thành đoạn thẳng | Nhỏ → mịn hơn nhưng nhiều lệnh hơn. 0.03–0.1 mm là hợp lý |
| Đoạn ngắn nhất | Gộp các đoạn ngắn hơn giá trị này | Tăng lên nếu máy bị **giật cục** |
| Đoạn dài nhất | Chia nhỏ đoạn dài | Giảm xuống nếu máy **phanh gấp** ở cuối đoạn dài |
| Trần tốc độ | Giới hạn F ghi ra | Chặn trên an toàn |
| Góc vát tối đa | Giới hạn cơ khí của trục vát | Đặt đúng khả năng máy |
| Tâm xoay tới mũi cắt | Khoảng cách từ tâm nghiêng tới mũi cắt | Để phần mềm bù toạ độ khi nghiêng |

Bấm **Áp dụng thông số** rồi **Lưu hồ sơ máy...** để dùng lại lần sau.

---

## 6. Đặt gốc toạ độ

Thứ tự chuẩn trước mỗi lô hàng:

1. **Về gốc** (`$H`) nếu máy có công tắc hành trình.
2. Kẹp phôi vào mâm cặp, mặt đầu ống nhô ra đủ dài.
3. Jog trục **Y** (ống ra vào) cho tới khi **mặt đầu ống nằm đúng dưới mũi cắt**.
4. Jog trục **X** cho mỏ cắt về **đúng đường tâm ống** (nhìn từ đầu ống: mũi cắt
   thẳng hàng với đỉnh ống).
5. Jog trục **Z** hạ mũi cắt xuống **chạm nhẹ mặt ống** (kẹp tờ giấy để cảm nhận).
6. Xoay trục **A** sao cho vị trí muốn coi là 0° nằm **ngay dưới mũi cắt**.
7. Bấm **Đặt gốc chi tiết** — lúc này Y0 ở mặt đầu ống, X0 trên đường tâm,
   Z0 ở mặt ống, A0 tại 12 giờ.

Toàn bộ toạ độ trong tệp công việc đều đo từ gốc này: `x` là khoảng cách từ mặt
đầu ống (ra lệnh cho trục Y), `theta` là góc quay tính từ vị trí 12 giờ (trục A).

---

## 7. Tạo công việc

Tab **3. Công việc**:

1. Chọn loại nguyên công trong danh sách → bấm **Thêm**.
2. Chọn nguyên công trong bảng → nhập thông số ở khung bên phải (mỗi ô có chú
   thích ngay cạnh). Mỗi lần đổi số, đường chạy dao được tính lại ngay.
3. Dùng **Lên / Xuống** để đổi thứ tự, **Bật/tắt** để tạm bỏ qua một nguyên công.
4. **Lưu...** thành tệp `.json` để dùng lại.

> **Thứ tự cắt tự động.** Phần mềm luôn sắp xếp lại: *vạch dấu → lỗ/rãnh → cắt
> đứt*, và các nhát cắt đứt được xếp từ đầu tự do vào trong. Lý do: sau khi cắt
> đứt thì phần ống phía ngoài rơi ra, không còn gá được nữa.

Vài lưu ý theo từng nguyên công:

* **Miệng cá (`saddle`)** — `Chuẩn đo` quyết định ý nghĩa của ô `Vị trí gót`:
  `heel` là điểm còn dài nhất (dễ đo nhất khi cầm thước), `toe` là đáy miệng cá,
  `axis` là giao điểm hai đường tâm ống.
* **Lỗ (`hole`)** — đây là lỗ do *ống nhánh hoặc mũi khoan xuyên qua*, nên khi
  trải phẳng nó **không tròn**. Nếu bạn muốn một hình tròn đúng nghĩa trên bề mặt
  thì dùng `circle`.
* **Biên dạng tự do (`pattern`)** — tệp CSV hai cột `u,v` (mm): `u` dọc ống, `v`
  theo chu vi. Xuất từ CAD ra DXF rồi đổi sang CSV, hoặc tự sinh bằng script.
  Xem [`examples/bien_dang_ngoi_sao.csv`](../examples/bien_dang_ngoi_sao.csv).

---

## 8. Chạy chương trình

1. Tab **4. Xem trước** — kiểm tra hình dạng ở cả hai khung nhìn. Dòng thống kê
   cho biết chiều dài cắt, số điểm mồi, số dòng lệnh và thời gian ước tính.
2. Tab **5. Mô phỏng** — bấm ▶ để xem lại toàn bộ hành trình trên mô hình máy
   (xem ảnh minh hoạ: [docs/mo_phong_may.svg](mo_phong_may.svg)):
   ống trượt ra vào và quay, mỏ cắt chạy ngang và lên xuống, vết cắt đỏ hiện dần.
   Đây là bước phát hiện va chạm và sai gốc toạ độ **trước khi** đụng tới phôi thật.
   Kéo chuột trái để xoay góc nhìn, chuột phải để dịch, lăn chuột để phóng to.
   Thanh trượt cho phép tua tới đúng thời điểm cần soi kỹ, nút **Xuất ảnh...**
   lưu lại khung hình đang xem thành tệp SVG để in kèm phiếu công nghệ.
3. Tab **6. Chạy** — bấm **BẮT ĐẦU CẮT**, xác nhận hộp thoại kiểm tra an toàn.
4. Trong lúc chạy:
   * thanh tiến độ và dòng G-code đang chạy được tô sáng;
   * vị trí mũi cắt hiện lên bản xem trước;
   * tab **Mô phỏng** (bật *Bám theo máy thật*) phản chiếu đúng tư thế máy đang
     báo về, kèm phần vết cắt đã hình thành tới thời điểm đó;
   * **Tạm dừng** gửi feed-hold (máy dừng êm, giữ nguyên vị trí, có thể chạy tiếp);
   * **DỪNG** gửi feed-hold rồi reset mềm — nguồn cắt tắt ngay.

**Chạy khô lần đầu:** tắt nguồn plasma/laser, nâng cao độ an toàn lên 40–50 mm,
cho chạy hết chương trình và quan sát. Đây là cách rẻ nhất để phát hiện sai gốc
toạ độ hoặc va chạm.

---

## 9. Định dạng tệp công việc

Tệp `.json` đơn giản, sửa bằng tay cũng được:

```json
{
  "name": "ong-nhanh-chu-T",
  "notes": "Ống D60 nối vào ống chính D114.3",
  "optimize_order": true,
  "operations": [
    { "type": "ring_mark", "enabled": true, "params": { "x": 40.0 } },
    { "type": "hole", "enabled": true,
      "params": { "diameter": 25.0, "x": 90.0, "theta": 0.0, "angle": 90.0, "offset": 0.0 } },
    { "type": "saddle", "enabled": true,
      "params": { "main_diameter": 114.3, "angle": 90.0, "x": 260.0, "reference": "heel" } }
  ]
}
```

Xem toàn bộ tham số của từng loại:

```bash
python -m pipecut ops
```

Sinh hàng loạt bằng script (ví dụ cắt 20 ống theo kích thước trong bảng tính):

```python
from pipecut.config import MachineProfile
from pipecut.jobs import Job
from pipecut.gcode import build_program

profile = MachineProfile.load("config/machine_default.json")
for i, (chieu_dai, goc) in enumerate([(300, 30), (450, 45), (600, 22.5)]):
    job = Job(name=f"chi-tiet-{i}")
    job.add("cutoff", x=chieu_dai, angle=goc)
    toolpath, _ = job.build_toolpath(profile)
    build_program(profile, toolpath).save(f"chi-tiet-{i}.nc")
```

---

## 10. Xử lý sự cố

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không thấy cổng COM | Thiếu driver CP2102/CH340 | Cài driver USB-UART của chip trên bo |
| Kết nối được nhưng không phản hồi | Sai baud, hoặc ESP32 đang khởi động | Đặt 115200; chờ 2 giây sau khi mở cổng |
| `Lỗi 9` khi bắt đầu chạy | Máy đang khoá do báo động | Bấm **Mở khoá ($X)**, tìm nguyên nhân báo động |
| `BÁO ĐỘNG 2` | Toạ độ vượt hành trình mềm | Kiểm tra dòng "Giới hạn trục" sau khi sinh G-code |
| Máy **giật cục** khi cắt đường cong | Quá nhiều đoạn siêu ngắn | Tăng *Đoạn ngắn nhất* lên 0.4–0.6 mm, tăng *Dung sai dây cung* lên 0.08 mm |
| Máy **phanh gấp** ở đoạn thẳng dài | Đoạn quá dài, planner không có gì nhìn trước | Giảm *Đoạn dài nhất* xuống 4–5 mm |
| Mạch cắt **rộng hẹp không đều** quanh chu vi | Chưa bù tốc độ tổng hợp (dùng phần mềm khác), hoặc sai đường kính ống | Đo lại đường kính; phần mềm này bù tự động |
| Cắt **thiếu/thừa kích thước đúng bằng một lượng cố định** | Sai bề rộng mạch cắt | Cắt thử một ô vuông, đo, cập nhật ô *Bề rộng mạch cắt* |
| Lỗ bị **méo về một phía** | Gốc A không nằm ở 12 giờ | Đặt lại gốc theo mục 6 |
| Ống **trượt trong mâm cặp** khi tăng tốc | Mô-men không đủ | Giảm gia tốc trục A trong YAML, tăng lực kẹp, dùng tỉ số truyền lớn hơn |
| Góc quay bị **cộng dồn** rất lớn (A = 3000°) | Bình thường — trục xoay quay vô hạn | Nếu muốn gọn, bật `rotary_rewind` trong hồ sơ máy |

Vẫn chưa xong? Chạy chương trình trên **máy ảo** ở tốc độ x20 và đọc nhật ký —
mọi dòng gửi đi và nhận về đều hiện ở đó.
