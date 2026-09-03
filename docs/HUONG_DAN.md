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
10. [Nhập biên dạng từ tệp ngoài](#10-nhập-biên-dạng-từ-tệp-ngoài)
11. [Kết nối qua WiFi / mạng LAN](#11-kết-nối-qua-wifi--mạng-lan)
12. [Xử lý sự cố](#12-xử-lý-sự-cố)

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

**Phôi** — chọn hình dạng trước, rồi nhập kích thước tương ứng:

| Hình dạng | Ô cần nhập |
|---|---|
| Ống tròn | Đường kính ngoài |
| Ống hộp vuông | Cạnh ngang (bỏ qua ô cạnh dọc) |
| Ống hộp chữ nhật | Cạnh ngang + cạnh dọc |

Kích thước là thông số quan trọng nhất: mọi phép quy đổi góc ↔ cung đều dựa vào
nó. Hãy **đo bằng thước cặp**, đừng lấy theo tên gọi danh nghĩa (ống "phi 60"
thực tế thường là 60,3 mm; hộp "50" có thể là 49,6 mm).

*Góc lượn* của ống hộp để 0 thì phần mềm tự lấy 2 lần chiều dày thành. Nếu cần
chính xác, đo bán kính góc thật bằng dưỡng rồi nhập vào — sai số góc lượn ảnh
hưởng trực tiếp tới khe hở mỏ cắt khi chạy qua góc.

Dòng chữ dưới bảng cho biết chu vi tính được và **hành trình trục ngang cần
thiết** — đối chiếu với hành trình thật của máy trước khi cắt.

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
| Tốc độ đều cả đường | Cả đường cắt chạy một tốc độ bề mặt duy nhất | Bật khi cắt ống hộp muốn vết cắt đồng đều |
| Qua góc ống hộp | `follow` cắt liền mạch · `pivot` xoay 45° rồi cắt · `index` bỏ qua góc | Xem mục dưới |
| Tắt mỏ khi xoay góc | Chỉ có tác dụng ở chế độ `index` | Tắt thì góc lượn không được cắt |
| Nhấc mỏ khi xoay góc | Nhấc thêm bao nhiêu mm cho an toàn khi xoay | 5-10 mm là đủ |

**Chọn cách vượt góc ống hộp.** Qua cung góc lượn, mâm cặp phải quay 90° trong
một đoạn cung rất ngắn — ống 50×50 góc lượn R6 cần tới ~15 000 độ/phút để giữ
tốc độ cắt 1600 mm/phút, không mâm cặp thường nào làm nổi. Hai lối ra:

* **`follow`** — cắt liền mạch qua góc, phần mềm tự hạ tốc độ xuống mức máy chạy
  được và báo con số cụ thể. Phôi **đứt hẳn**. Đổi lại vết cắt ở góc chậm hơn ở
  mặt phẳng (bật *Tốc độ đều* để đồng đều lại).
* **`pivot`** *(mặc định)* — cắt hết mặt phẳng rồi **dừng, xoay 45° đưa góc bo
  lên đỉnh** (mỏ vẫn đứng đúng chỗ vừa cắt, X và Z bám theo), lúc này cả cung góc
  nằm gọn quanh đỉnh nên **cắt hết cung ở tốc độ chuẩn với trục A đứng yên**, xong
  **xoay nốt 45°** về mặt kế tiếp rồi cắt tiếp. Cắt đủ cả cung góc *và* giữ được
  tốc độ. Đổi lại: hai đầu cung mỏ nghiêng tới 45° nên mặt cắt chỗ đó không vuông
  góc, và tốn thêm 2 điểm mồi mỗi góc (tổng 9 thay vì 1 cho một nhát cắt đứt).
* **`index`** — cắt hết mặt phẳng rồi **dừng cắt: tắt mỏ, nhấc lên, ba trục phối
  hợp giữ mỏ bám đúng góc đó trên phôi trong lúc mâm quay 90°, quay xong hạ
  xuống mồi lại và cắt mặt kế tiếp**. Nhanh gọn nhưng **bốn cung góc lượn không
  được cắt** nên phôi chưa rời hẳn — dùng khi cắt cửa sổ/rãnh trên các mặt, hoặc
  khi chấp nhận bẻ/mài nốt góc.

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

> **Thứ tự cắt.** Mặc định phần mềm **cắt đúng thứ tự trong bảng** — xếp sao thì
> chạy vậy. Dòng chữ dưới bảng luôn hiện thứ tự thật sự sẽ chạy để đối chiếu.
>
> Tích ô *Tự sắp xếp thứ tự cắt* nếu muốn phần mềm tự lo: *vạch dấu → lỗ/rãnh →
> cắt đứt*, các nhát cắt đứt xếp từ đầu tự do vào trong (sau khi cắt đứt thì
> phần phôi phía ngoài rơi ra, không còn gá được nữa).
>
> Khi tự xếp thủ công, nếu có nguyên công nằm **ngoài** một nhát cắt đứt đứng
> trước nó, phần mềm sẽ cảnh báo chứ không tự đổi thứ tự của bạn.

> **Thư viện nguyên công lọc theo phôi.** Khai báo ống hộp thì danh sách không
> hiện *miệng cá* và *lỗ xuyên thành* — hai biên dạng đó là giao của hai mặt trụ,
> chỉ dùng được với ống tròn. Cần lỗ tròn trên mặt ống hộp thì dùng *Lỗ tròn trên
> mặt*.

> **Chọn chỗ vết mồi.** Vết mồi rất xấu và rộng nên nên cho nó rơi vào phần phế
> liệu hoặc chỗ khuất. Ô *Vị trí điểm mồi* (% chu vi biên dạng) xoay điểm bắt đầu
> quanh đường cắt; ô *Phía vào dao* chọn vào từ trong hay ngoài biên dạng kín,
> hoặc lệch về đầu tự do (`plus`) hay về phía mâm cặp (`minus`) với nhát cắt
> quanh phôi.

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
   (ảnh minh hoạ: [ống tròn](mo_phong_may.svg) · [ống hộp](mo_phong_ong_hop.svg)):
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

## 10. Nhập biên dạng từ tệp ngoài

Hình đã vẽ ở phần mềm khác thì nạp thẳng vào, không phải vẽ lại.

### Nạp bằng giao diện

1. Thẻ **Công việc** → **Thêm** → chọn nguyên công **Nhập biên dạng từ tệp**.
2. Bấm **Chọn...** rồi trỏ tới tệp. Phần mềm đọc thử ngay và hiện ngay dưới ô
   mô tả: *"bản vẽ CAD 2D (DXF) · 3 đường (3 khép kín) · tổng 330.0 mm"*.
3. Chỉnh **Dịch dọc ống** và **Dịch theo góc** để đặt hình vào đúng chỗ trên phôi.
4. Sang thẻ **Xem trước** kiểm tra, rồi **Mô phỏng** chạy thử.

Một tệp chứa nhiều đường thì tất cả đều được nạp, đánh số `#1`, `#2`... theo thứ
tự từ đường dài nhất trở xuống.

### Nạp bằng dòng lệnh

```bash
python -m pipecut import ban_ve.dxf                  # xem trong tệp có gì
python -m pipecut import ban_ve.dxf --layers CAT,LO  # chỉ lấy hai lớp này
python -m pipecut import chi_tiet.stl --mesh-tol 0.3
```

### Hiểu từng ô thông số

| Ô | Ý nghĩa |
|---|---|
| **Tệp biên dạng** | Đường dẫn tệp. Ghi đường dẫn tương đối thì tính từ chỗ để tệp công việc |
| **Dịch dọc ống** | Đẩy cả hình chạy dọc phôi, tính bằng mm |
| **Dịch theo góc** | Xoay cả hình quanh phôi, tính bằng độ |
| **Tỉ lệ** | Phóng to / thu nhỏ. Sai đơn vị (bản vẽ vẽ theo cm) thì sửa ở đây |
| **Xoay biên dạng** | Xoay hình **trên tấm trải phẳng** trước khi cuốn lên phôi |
| **Lật** | `u` lật theo chiều dọc ống, `v` lật theo chiều chu vi — dùng khi hình bị ngược |
| **Khép kín** | `auto` là theo đúng tệp gốc; ép `yes`/`no` khi tệp vẽ thiếu nét cuối |
| **Bo góc** | Bo tròn các góc nhọn của hình nhập vào, giúp đường cắt mượt hơn |
| **Lớp cần lấy** | Chỉ dùng với DXF — nhiều lớp cách nhau bằng dấu phẩy, để trống là lấy hết |
| **Trục phôi trong mô hình** | Chỉ dùng với STL/OBJ — để `auto` cho phần mềm tự dò |
| **Xoay mô hình quanh trục** | Chỉ dùng với STL/OBJ — mô hình đang bị xoay bao nhiêu độ thì điền bấy nhiêu |
| **Dung sai bề mặt** | Chỉ dùng với STL/OBJ — sai lệch cho phép để coi một mảnh lưới là còn nằm trên mặt phôi. Lưới thô thì tăng lên |

### Vẽ ở CAM nào cũng được

Cách nhanh nhất nếu đã quen một phần mềm CAM: vẽ biên dạng **trên mặt phẳng**
như cắt tôn tấm rồi xuất G-code hai trục. Quy ước: **X là chiều dọc phôi**,
**Y là chiều theo chu vi**. Phần mềm đọc lại, cuốn lên ống, rồi tự lo phần bốn
trục — CAM không cần biết gì về máy cắt ống.

Chiều dài một vòng chu vi để vẽ cho khớp: ống tròn là `π × đường kính`; ống hộp
là `2×(rộng + cao) − 8×R + 2πR` với `R` là bán kính bo góc. Phần mềm in sẵn số
này khi chạy `python -m pipecut profile`.

### Nạp mô hình 3D (STL/OBJ)

Đưa vào **chi tiết đã cắt xong**, không phải phôi nguyên. Phần mềm so bề mặt mô
hình với tiết diện phôi đã khai báo, phần nào còn nằm trên mặt phôi gốc thì giữ,
ranh giới của phần đó chính là đường cắt.

Nhờ vậy nó không chỉ "nhận dạng rồi để đấy": trục phôi, tâm tiết diện, đường cắt
và toạ độ trải phẳng đều tự tính, rồi đi tiếp đúng dây chuyền bù kerf – vào/ra
dao – chiến lược góc – bù tốc độ như mọi biên dạng khác.

Khai báo phôi phải **đúng với mô hình**, nhất là **bán kính bo góc** của ống hộp.
Khai sai thì phần mềm cảnh báo ngay chứ không lặng lẽ cho ra đường cắt sai:

* *"... mảnh lưới nằm hẳn ngoài mặt phôi đã khai báo"* → phôi khai nhỏ hơn thực
  tế, hoặc mô hình đang tính theo inch (đặt **Tỉ lệ** = 25.4).
* *"... % chu vi tiết diện không có mảnh lưới nào bám vào"* → sai hình dạng tiết
  diện, hay gặp nhất là quên khai bán kính bo góc.
* *"Không thấy phần bề mặt nào ... nằm trên mặt phôi"* → sai kích thước, sai trục
  hoặc lưới quá thô; kiểm tra lại rồi tăng **Dung sai bề mặt**.

> **STEP và IGES chưa đọc được** — đó là định dạng B-rep, dựng lại được phải kèm
> cả một nhân hình học rất nặng. Xuất STL với sai số lưới 0,01–0,05 mm rồi nạp.

---

## 11. Kết nối qua WiFi / mạng LAN

FluidNC có sẵn máy chủ Telnet; phần mềm nói chuyện qua đó y như qua cổng COM.

### Bật WiFi trên ESP32

Nối cổng COM một lần rồi gõ vào ô lệnh ở thẻ **Điều khiển**:

```
$Sta/SSID=ten-wifi-nha-ban
$Sta/Password=mat-khau
$Sta/IPMode=DHCP
$Telnet/Enable=ON
$Telnet/Port=23
$WiFi/Mode=STA
```

Khởi động lại bo, rồi gõ `$Sta/Status` để xem địa chỉ IP máy nhận được.

**Nên đặt IP tĩnh** cho máy (`$Sta/IPMode=Static`, `$Sta/IP=192.168.1.50`,
`$Sta/Gateway=192.168.1.1`, `$Sta/Netmask=255.255.255.0`) để địa chỉ không đổi
sau mỗi lần khởi động.

### Nối từ phần mềm

* **Giao diện:** ô **Cổng / địa chỉ** gõ thẳng `192.168.1.50`, hoặc bấm
  **Dò trong mạng LAN** để phần mềm quét cả dải mạng tìm máy. Ô này gõ được cả
  `192.168.1.50:23` và `fluidnc.local`.
* **Dòng lệnh:**

```bash
python -m pipecut scan                             # dò trong mạng
python -m pipecut send ra.nc --port 192.168.1.50
python -m pipecut run cong_viec.json --port fluidnc.local
```

Thử đường truyền mạng khi chưa có bo mạch:

```bash
python -m pipecut sim ra.nc --serve 2323
python -m pipecut send ra.nc --port 127.0.0.1:2323
```

> **Cắt thật thì nên dùng dây.** WiFi rất tiện để nạp chương trình, theo dõi và
> chỉnh máy. Nhưng xưởng có máy hàn, biến tần, nguồn plasma là môi trường nhiễu
> nặng — mất sóng giữa nhát cắt là hỏng phôi. Dùng WiFi cho khâu chuẩn bị, cắm
> dây cho khâu cắt.

---

## 12. Xử lý sự cố

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Cắt ống hộp bị **cháy/đọng xỉ ở góc lượn** | Tốc độ cắt tụt ở góc vì trục xoay chạm trần tốc độ | Bật *tốc độ đều*, hoặc chuyển sang chế độ `index`, hoặc tăng tốc độ tối đa trục A |
| Cắt ống hộp xong mà **phôi chưa rời** | Đang dùng `index` có tắt mỏ nên bốn cung góc không được cắt | Đây là cảnh báo phần mềm đã báo trước; đổi sang `follow` hoặc tắt tuỳ chọn *Tắt mỏ khi xoay góc* |
| Phần mềm báo *"tốc độ cắt tụt còn ... mm/phút"* | Đúng như trên — máy không quay kịp qua góc | Xem cột trên; nếu chấp nhận được thì bỏ qua, đây là cảnh báo chứ không phải lỗi |
| Cắt ống hộp báo **vượt hành trình trục X** | Trục ngang không đủ dài để chạy hết bề rộng mặt | Cần hành trình ít nhất ±(nửa cạnh − góc lượn); đặt gốc X đúng đường tâm phôi |
| Nguyên công *miệng cá* / *lỗ xuyên* bị bỏ qua | Hai biên dạng này chỉ có nghĩa với ống tròn | Với ống hộp dùng *rãnh*, *tròn trên bề mặt* hoặc *biên dạng trải phẳng* |
| Không thấy cổng COM | Thiếu driver CP2102/CH340 | Cài driver USB-UART của chip trên bo |
| **Dò mạng LAN không thấy máy nào** | ESP32 chưa vào WiFi, khác dải mạng, hoặc chưa bật Telnet | Cắm dây kiểm tra `$Sta/Status`; máy tính và ESP32 phải cùng dải mạng; bật `$Telnet/Enable=ON` |
| **Nối qua WiFi bị đứt giữa chừng** | Sóng yếu hoặc nhiễu từ nguồn plasma/máy hàn | Nạp chương trình qua WiFi thì được, nhưng **lúc cắt hãy cắm dây** |
| **Nhập tệp báo "không nhận ra đuôi tệp"** | Định dạng chưa hỗ trợ (hay gặp: STEP/IGES) | Xuất lại sang DXF (2D) hoặc STL (3D) từ phần mềm CAD |
| **Nạp DXF ra hình quá to hoặc quá nhỏ** | Bản vẽ không khai `$INSUNITS`, hoặc vẽ theo cm/inch | Sửa ô **Tỉ lệ** (cm → 10, inch → 25.4) |
| **Nạp STL báo sai tiết diện** | Khai phôi không khớp mô hình, hay quên bán kính bo góc | Đọc kỹ nội dung cảnh báo — nó chỉ đúng chỗ sai; xem mục 10 |
| **Nạp STL thiếu mất đường cắt** | Lưới quá thô so với dung sai bề mặt | Tăng **Dung sai bề mặt** lên 0,5–1 mm, hoặc xuất lại STL mịn hơn |
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
