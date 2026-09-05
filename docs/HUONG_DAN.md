# Hướng dẫn sử dụng PipeCut Studio

## Mục lục

1. [Chuẩn bị phần cứng](#1-chuẩn-bị-phần-cứng)
2. [Nạp và cấu hình FluidNC](#2-nạp-và-cấu-hình-fluidnc)
3. [Hiệu chỉnh trục xoay](#3-hiệu-chỉnh-trục-xoay)
4. [Cài đặt phần mềm](#4-cài-đặt-phần-mềm)
5. [Khai báo hồ sơ máy](#5-khai-báo-hồ-sơ-máy)
6. [Đặt gốc toạ độ](#6-đặt-gốc-toạ-độ) — căn tâm mâm cặp một lần, dùng mãi
7. [Tạo công việc](#7-tạo-công-việc)
8. [Chạy chương trình](#8-chạy-chương-trình)
9. [Định dạng tệp công việc](#9-định-dạng-tệp-công-việc)
10. [Nhập biên dạng từ tệp ngoài](#10-nhập-biên-dạng-từ-tệp-ngoài)
11. [Kết nối qua WiFi / mạng LAN](#11-kết-nối-qua-wifi--mạng-lan)
12. [Dò cạnh: máy tự tìm phôi và đặt gốc](#12-dò-cạnh-máy-tự-tìm-phôi-và-đặt-gốc)
13. [Giao diện: nền sáng và nền tối](#13-giao-diện-nền-sáng-và-nền-tối)
14. [Xử lý sự cố](#14-xử-lý-sự-cố)

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

### 2.1 Nạp bản nào

Tải bản phát hành ở https://github.com/bdring/FluidNC/releases — lấy bản gắn nhãn
**Latest** (bản ổn định mới nhất), đừng lấy bản có chữ `pre` ở cuối, đó là bản
thử nghiệm.

Trong tệp nén có nhiều bản firmware khác nhau. **Chọn bản WiFi:**

| Tệp cài | Nạp cái gì | Dùng khi nào |
|---|---|---|
| `install-fs.bat` / `.sh` | Hệ thống tệp + WebUI | **Lần đầu phải chạy cái này**, chỉ một lần |
| `install-wifi.bat` / `.sh` | Firmware bản **WiFi** | **← chọn cái này** |
| `install-bt.bat` / `.sh` | Firmware bản Bluetooth | Chỉ khi muốn điều khiển qua Bluetooth |

**Vì sao phải là bản WiFi:** ESP32 chỉ có **một** bộ thu phát vô tuyến, không
chạy WiFi và Bluetooth cùng lúc được; hai phần mã lại đều rất nặng nên FluidNC
tách hẳn thành hai bản firmware riêng. Nạp bản `bt` thì **mất chức năng nối qua
mạng LAN** của PipeCut Studio.

### Bo của bạn là ESP32 gốc hay ESP32-S3?

Đây là chỗ **rất dễ nạp sai**, vì hai dòng chip dùng firmware khác nhau **và**
bảng chân khác nhau. FluidNC phát hành riêng cho từng dòng:

| Bo | Bản firmware | Tệp cấu hình dùng kèm |
|---|---|---|
| **ESP32-S3** (S3-DevKitC-1...) | `wifi_s3` | [`fluidnc_pipe4axis_s3.yaml`](../firmware/fluidnc_pipe4axis_s3.yaml) |
| **ESP32 gốc** (WROOM-32) | `wifi` | [`fluidnc_pipe4axis.yaml`](../firmware/fluidnc_pipe4axis.yaml) |

Nạp lẫn là **không chạy**: ảnh firmware của hai dòng nạp mã vào những vùng địa
chỉ khác nhau hẳn. Hai tệp cấu hình cũng **không dùng lẫn được** (xem 2.5).

Chưa rõ bo mình là gì thì cắm cáp USB rồi kết nối, FluidNC in ra dòng chào có
tên chip. Hoặc nhìn con nhôm vuông trên bo: chữ *ESP32-WROOM-32* là dòng gốc,
*ESP32-S3-WROOM-1* là S3.

Muốn biết một tệp `.bin` đã tải là bản nào thì gõ:

```bash
esptool.py image_info --version 2 firmware.bin
```

Dòng `Chip ID` và các địa chỉ `Segment` sẽ cho biết ảnh đó dựng cho chip nào.
Trên ESP32-S3, đoạn mã chương trình nạp ở vùng `0x42000000`; trên ESP32 gốc là
`0x400D0000`.

### 2.2 Bo S3 có hai cổng USB - cắm đúng cổng

Trên **ESP32-S3-DevKitC-1** có **hai** cổng USB-C cạnh nhau, dễ cắm lẫn:

| Cổng in chữ | Đi qua đâu | Hiện ra là |
|---|---|---|
| **USB** | USB nối thẳng vào chip S3 (chân 19/20) | Mã nhà sản xuất Espressif `303A:1001` — Linux là `/dev/ttyACM*` |
| **UART** | Chip cầu CP2102 / CH340 | `10C4:...` hoặc `1A86:...` — Linux là `/dev/ttyUSB*` |

Cả hai đều dùng được. `python -m pipecut ports` giờ nhận ra và ghi rõ từng loại:

```
/dev/ttyACM0   USB JTAG/serial debug unit [ESP32-S3 USB gắn trong - cổng USB]
/dev/ttyUSB0   CP2102 USB to UART Bridge [CP2102 - ESP32]
```

Cắm vào cổng **USB** thì tốc độ baud không có ý nghĩa (USB tự thoả thuận), đặt
bao nhiêu cũng chạy. Cắm cổng **UART** thì phải để 115200.

### 2.3 Trình tự nạp

```
1. Cắm ESP32 vào máy tính bằng cáp USB
2. Chạy install-fs      (lần đầu tiên, nạp WebUI vào flash)
3. Chạy install-wifi    (nạp firmware)
4. Mở lại nguồn, nối vào cổng COM để kiểm tra
```

Nếu báo lỗi lúc nạp: mở tệp `install-wifi.bat` bằng notepad, sửa `--baud 921600`
thành `--baud 115200` rồi chạy lại. Cáp USB dài hoặc rẻ tiền hay gây lỗi ở tốc
độ cao.

### 2.4 Nạp tệp cấu hình máy

1. Mở WebUI của FluidNC → **Files** → tải lên
   [`firmware/fluidnc_pipe4axis.yaml`](../firmware/fluidnc_pipe4axis.yaml).
2. Đặt làm cấu hình đang dùng: gõ trong terminal
   `$Config/Filename=fluidnc_pipe4axis.yaml` rồi khởi động lại.
3. Gõ `$Config/Validate` — FluidNC sẽ in ra mọi dòng nó không hiểu. Phải **sạch
   lỗi** mới cấp điện động lực.

> **Vì sao bước `$Config/Validate` quan trọng:** khai sai một khoá thì FluidNC
> **lặng lẽ bỏ qua cả khối** chứ không dừng. Khai nhầm tên driver động cơ là
> trục không có chân STEP/DIR nên đứng im; khai nhầm chỗ nguồn cắt là mỏ không
> bao giờ kích. Cả hai đều không có thông báo gì nếu không chạy Validate.
4. **Đối chiếu chân GPIO** trong tệp YAML với bo mạch thực tế. Xem bảng chân
   tổng hợp ở cuối tệp YAML.

### 2.5 Những chân ESP32-S3 không được dùng

Bản đồ chân của S3 **khác hẳn** ESP32 gốc, nên tệp cấu hình cũng khác:

| Chân | Vấn đề | Hệ quả nếu dùng sai |
|---|---|---|
| **22, 23, 24, 25** | **Không tồn tại trên S3** — Espressif loại hẳn bốn số này | FluidNC báo "Unavailable GPIO" |
| 26–32 | Chip nhớ flash chiếm (CS1, HD, WP, CS0, CLK, MISO, MOSI) | Máy không khởi động |
| 33–37 | PSRAM loại octal chiếm (D4–D7, DQS) — các bo N8R8/N16R8 đều dùng | Máy không khởi động trên bo có PSRAM octal |
| 19, 20 | Cổng USB-Serial-JTAG trên bo | Mất cổng nạp/terminal |
| 43, 44 | TX/RX của UART0 | Mất cổng terminal |
| 0, 3, 45, 46 | Chân quyết định chế độ khởi động | Không nạp được firmware |
| 38, 48 | Đèn LED RGB trên bo DevKitC-1 | Chỉ xung đột với đèn, không nguy hiểm |

**Điểm tốt hơn ESP32 gốc:** S3 không có chân "chỉ vào" nào. Mọi chân dùng được
đều treo được bên trong, nên ba công tắc hành trình ghi `:pu` bình thường và
**không phải hàn điện trở 10k bên ngoài**.

Bảng chân trong `fluidnc_pipe4axis_s3.yaml`: X = 4/5, Y = 6/7, Z = 15/16,
A = 17/18, ENABLE chung = 21, hành trình = 8/9/10, dò chạm = 11, rơ-le = 12.

S3 chỉ có **4 kênh RMT**, vừa đủ cho 4 trục. Nếu FluidNC báo hết kênh RMT thì
đổi `engine: RMT` thành `engine: Timed` trong tệp cấu hình.

Kiểm tra nhanh bằng PipeCut Studio:

```bash
python -m pipecut ports          # tìm cổng COM (CP2102 / CH340 sẽ được đánh dấu)
```

Vào tab **1. Máy & Kết nối**, chọn cổng, bấm **Kết nối**. Dòng chào
`Grbl 1.1f` hoặc `[VER:...FluidNC...]` xuất hiện trong nhật ký là thành công.

### 2.6 Những chân ESP32 gốc không được dùng

Đây là chỗ hay hỏng việc nhất khi tự đặt chân. Không phải chân nào cũng dùng
được như nhau:

| Chân | Vấn đề | Hệ quả nếu dùng sai |
|---|---|---|
| 6, 7, 8, 11 | Nối trực tiếp vào chip nhớ flash | FluidNC báo "Unusable GPIO" |
| **34–39** | **Chỉ vào, KHÔNG có điện trở treo bên trong** | Ghi `:pu` thì FluidNC báo lỗi; công tắc hành trình báo lung tung |
| **12** | Kéo cao lúc khởi động là chọn sai điện áp flash | **ESP32 không khởi động được** |
| 0, 2, 5 | Chân quyết định chế độ khởi động (2 còn nối đèn LED) | Không nạp được firmware; rơ-le có thể đóng lúc bật nguồn |
| 14, 15 | Phát xung PWM ngay khi cấp điện | Động cơ giật, hoặc **mỏ cắt phụt một nhát lúc bật nguồn** |
| 1, 3 | TX/RX của cổng USB | Mất cổng terminal |
| 16, 17 | Một số bo WROVER dùng cho PSRAM | Chạy được trên WROOM nhưng nên tránh cho chắc |

Ba chân hành trình `34/35/36` trong tệp cấu hình **bắt buộc hàn điện trở 10k từ
chân đó lên 3V3**, vì chúng không treo được bên trong.

> **An toàn:** rơ-le nguồn cắt đặt ở `gpio 21` — chân thường, không dính gì tới
> khởi động. Đừng đổi sang 0, 2, 5, 14 hay 15. Dù chọn chân nào cũng nên dùng
> rơ-le **thường hở** và lắp thêm một công tắc cắt tay nối tiếp trên đường mồi
> của nguồn cắt.

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

Mâm cặp **tự định tâm**: ống to hay nhỏ thì đường tâm ống vẫn trùng đường tâm
mâm cặp. Nghĩa là **tâm mâm cặp là hằng số cơ khí của máy**, không phải của
phôi. Căn nó **một lần duy nhất** rồi thôi — sau này thay ống chỉ việc khai lại
kích thước, phần mềm tự tính ra gốc X và gốc Z mới.

Còn hai thứ *có* đổi theo từng lần gá thì để tay:

| Gốc | Ở đâu | Lấy bằng cách nào |
|---|---|---|
| **X** đường tâm ống | tâm mâm cặp | căn một lần, xong tự có |
| **Z** mặt trên phôi | tâm mâm cặp + nửa chiều cao tiết diện | căn một lần, xong tự có |
| **Y** dọc ống | tuỳ lần này đẩy ống vào sâu bao nhiêu | rà tay tới chỗ muốn cắt, bấm |
| **A** góc xoay | tuỳ lần này đặt ống nghiêng bao nhiêu | xoay tay, bấm |

### 6.1 Căn tâm mâm cặp — làm một lần

Thẻ **2. Điều khiển** → khung **Căn tâm mâm cặp** ở cột phải. Bốn lần chạm,
mỗi lần rà mỏ tới nơi rồi bấm **Ghi** (phần mềm lấy **toạ độ máy**, không phải
toạ độ chi tiết — gốc chi tiết còn đổi, tâm mâm cặp thì không).

| | Rà mỏ tới đâu |
|---|---|
| 1 | **Chạm đỉnh ống.** Ống hộp thì xoay cho một mặt phẳng nằm ngang trước. Hạ mỏ xuống đúng giữa mặt trên. |
| 2 | **Chạm sườn trái.** Nâng mỏ, đưa sang trái, hạ xuống ngang thân ống, đẩy X vào tới khi chạm. |
| 3 | **Chạm sườn phải**, hạ xuống **đúng cao độ như lúc chạm sườn trái**. |
| 4 | **Xoay A đúng 180°, chạm đỉnh lần nữa.** |

Bấm **Tính tâm**. Rồi **Lưu hồ sơ máy** (thẻ 1) để lần sau mở phần mềm là có sẵn.

**Vì sao lại là bốn chỗ chứ không phải hai.** Cả hai cặp đều dùng phép *lấy điểm
giữa*, và mỗi phép khử đúng một sai số:

* **Trái + phải → tâm ngang.** Béc dày bao nhiêu thì cộng vào bên này bấy nhiêu
  và trừ đi bên kia bấy nhiêu, lấy điểm giữa là **đường kính béc tự triệt tiêu**
  — không phải đo béc. Với ống tròn còn hay hơn: chạm ở cao độ nào cũng được,
  chỗ chạm thụt vào bao nhiêu thì thụt đều cả hai bên. Điều kiện duy nhất là
  **hai bên cùng một cao độ Z**; lệch quá 1 mm là phần mềm báo.
* **Đỉnh + đỉnh sau nửa vòng → tâm đứng.** Ống kẹp lệch lên `e` mm thì quay nửa
  vòng thành lệch xuống `e` mm, cộng lại chia đôi là hết. **Hiệu** của hai số đó
  chính là độ lệch tâm — phần mềm in ra để biết mâm cặp có vấn đề không.

Phần mềm còn soát giúp: đỉnh có chạm gần đường tâm không, hai lần chạm đỉnh có
đúng cách nhau 180° không, và bề rộng đo được có khớp cỡ ống đã khai không (lệch
nhiều thường là chạm nhầm vào mâm cặp hoặc khai sai cỡ ống).

Làm bằng dòng lệnh cũng được, tiện khi muốn ghi lại số đo:

```bash
python -m pipecut clamp --top 'X123.4,Z-20.6,A0' --left 'X92.4,Z-45.6,A0' \
                        --right 'X154.4,Z-45.6,A0' --top180 'X123.4,Z-20.6,A180' \
                        --save config/machine.json
python -m pipecut clamp        # xem lại hồ sơ căn đang có
```

### 6.2 Trước mỗi lô hàng

1. **Về gốc** (`$H`) nếu máy có công tắc hành trình.
2. Kẹp phôi, mặt đầu ống nhô ra đủ dài.
3. Khai đúng cỡ ống ở thẻ **1. Máy & Kết nối**.
4. Bấm **Đặt gốc X-Z từ tâm kẹp**. **Mỏ đang đứng ở đâu cũng bấm được** — lệnh
   này đặt thẳng gốc theo toạ độ máy (`G10 L2`), không phải "lấy chỗ đang đứng
   làm gốc" (`G10 L20`), nên không phải rà mỏ vào đâu cả.
5. Rà trục **Y** tới đúng chỗ trên ống muốn bắt đầu cắt → **Đặt gốc Y tại đây**.
6. Xoay **A** tới vị trí muốn coi là 0° → **Đặt gốc A tại đây**.

Chỉ đâu cắt đó: bước 5 và 6 là toàn bộ phần phải làm cho mỗi lô.

### 6.3 Máy tự siết hành trình theo cỡ ống

Bật ô **Tự siết hành trình theo cỡ ống** (mặc định bật) thì căn xong là phần mềm
biết luôn chỗ nào mỏ *không bao giờ* có việc phải tới:

* **Trục ngang** chỉ cần chạy trong khoảng bán kính ống cộng phần chừa thêm.
* **Trục nâng hạ** không được xuống dưới 0 — gốc Z ở mặt phôi, xuống dưới là đã
  cắm vào ống ở **mọi góc xoay**.
* **Trục dọc** giới hạn theo chiều dài phôi đã khai.

Sai ở đâu là báo ngay lúc sinh G-code, chưa kịp chạy. Giới hạn **tính lại mỗi
lần** theo cỡ ống đang khai, nên đổi ống to hơn thì nó tự nới ra — không phải
căn lại, cũng không phải sửa hồ sơ máy. Ô **chừa thêm** (mặc định 25 mm) là
khoảng dự phòng cho mồi lửa và dây dẫn mồi.

Giới hạn này **giao với** hành trình cơ khí đã khai ở thẻ Máy chứ không thay
thế: nó chỉ siết chặt hơn, không bao giờ nới rộng ra quá máy chịu được.

### 6.4 Không dùng cách căn thì làm tay như cũ

1. Jog **Y** cho mặt đầu ống nằm đúng dưới mũi cắt.
2. Jog **X** cho mỏ về đúng đường tâm ống.
3. Jog **Z** hạ mũi cắt chạm nhẹ mặt ống (kẹp tờ giấy để cảm nhận).
4. Xoay **A** cho vị trí muốn coi là 0° nằm ngay dưới mũi cắt.
5. Bấm **Đặt gốc chi tiết**.

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

### Đặt đường vào dao riêng cho từng nguyên công

Vết mồi rất xấu và rộng, nên chỗ vào dao phải rơi đúng vào **phần phế liệu**.
Mỗi nhát cắt lại có chỗ hợp lý khác nhau: lỗ thì vào từ trong lòng, cắt đứt thì
vào từ phía đầu tự do, rãnh dài thì tuỳ chỗ kẹp phôi.

Ngoài thiết lập chung ở thẻ **Máy & Kết nối**, mỗi nguyên công còn có riêng khối
ô nhập ở cuối bảng thông số:

| Ô | Ý nghĩa |
|---|---|
| **Tự đặt đường vào dao** | Tắt = dùng thiết lập chung. Bật mới đọc các ô dưới |
| **Vào dao phía nào** | `inside`/`outside` cho biên dạng kín; `plus`/`minus` cho nhát cắt quanh ống (về phía đầu tự do hay phía gốc) |
| **Dời điểm mồi** | Xoay chỗ vào dao quanh biên dạng, tính theo % chu vi — dùng để đưa vết mồi ra giữa cạnh thay vì đúng góc bo |
| **Kiểu vào dao** | `arc` (cung, ít cháy mép nhất), `line` (thẳng), `none` (mồi ngay trên đường cắt) |
| **Chiều dài vào dao** | mm |
| **Góc vào dao** | Chỉ dùng cho kiểu `line` |
| **Chạy vượt** | Chạy quá điểm khép kín cho mạch cắt đứt hẳn |

Đặt ở đây **không ảnh hưởng** các nguyên công khác và cũng không sửa hồ sơ máy.

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

## 12. Dò cạnh: máy tự tìm phôi và đặt gốc

> **Đây là đường phụ.** Với mâm cặp tự định tâm thì [căn tâm một lần ở mục
> 6.1](#6-đặt-gốc-toạ-độ) đã lo xong gốc X và gốc Z rồi, còn gốc Y thì rà tay
> tới đúng chỗ muốn cắt là nhanh nhất. Mục này dành cho ai muốn máy tự tìm
> phôi — cần thêm một cảm biến chạm, đổi lại đo được **cả bốn gốc** kể cả góc
> xoay của ống hộp.

Máy dò ra: mặt phôi (Z), đường tâm phôi (X), mặt đầu ống (Y), và với ống hộp là
cả góc xoay cho mặt phẳng nằm ngang (A).

### Chọn cách dò: hai đường

| | **Dò bằng chính mỏ cắt** *(đơn giản hơn)* | **Đầu dò riêng trên trục đảo** |
|---|---|---|
| Phần cứng thêm | 1 dây kẹp vào béc + 1 rơ-le tách dây | Thân đầu dò cảm ứng + kim dò + 1 mô-tơ + 1 trục |
| Cấu hình FluidNC | `fluidnc_pipe4axis_s3.yaml` (4 trục) | `fluidnc_pipe4axis_s3_dau_do.yaml` (5 trục) |
| Hồ sơ máy | `config/machine_s3_do_bang_mo.json` | `config/machine_s3_dau_do.json` |
| Rủi ro | Điện hồ quang / cao tần chạy ngược vào mạch dò | Không dính gì tới mạch plasma |
| Hao mòn | Béc chạm phôi mỗi lần dò | Không đụng tới béc |

### Dò bằng chính mỏ cắt: phải đọc trước khi đấu dây

Kẹp một dây vào đầu mỏ plasma, cho Z hạ xuống từ từ tới khi béc chạm phôi là
đóng mạch qua chính phôi (phôi đã nối mát máy cắt). Không cần đầu dò riêng.

Đổi lại phải lo phần điện cho đúng. **Bốn việc, không bỏ việc nào:**

**1. Máy plasma của bạn mồi hồ quang kiểu gì?** Đây là câu quyết định.

* **Mồi chạm** (blowback / contact start) — đa số máy cắt rẻ tiền. Béc bị đẩy ra
  để tạo hồ quang, không có xung cao áp. **Kiểu dò này dùng được.**
* **Mồi cao tần** (HF start) — có bộ phóng tia lửa điện, phát xung **hàng chục
  nghìn vôn ở tần số MHz**. Xung đó chạy ngược theo dây dò vào chân vi điều
  khiển là **cháy bo ngay**. Máy HF thì **đừng đấu kiểu này**, chuyển sang
  đường đầu dò riêng.

  *Cách nhận biết:* bấm mồi trong không khí, không chạm phôi. Vẫn ra tia lửa
  xanh lét kèm tiếng rè rè liên tục → mồi cao tần. Không ra gì cả, phải chạm
  phôi mới có hồ quang → mồi chạm.

**2. Bắt buộc có rơ-le tách dây dò.** Dù là máy mồi chạm, lúc cắt đầu mỏ vẫn
mang điện hồ quang 100–300 V. Rơ-le này chỉ nối dây dò vào mỏ **trong lúc dò**,
ngắt hẳn trước khi cắt.

Phần mềm tự lo: `M62 P0` đóng lúc bắt đầu dò, `M63 P0` ngắt khi xong — kể cả khi
dò lỗi hay bấm dừng giữa chừng. Khai chân rơ-le ở mục `user_outputs` trong tệp
cấu hình FluidNC (mẫu để ở `gpio 47`), và điền số ngõ ra vào ô **Ngõ ra rơ-le
dây dò** (mẫu là `0`). Đấu chết không có rơ-le thì để `-1`, nhưng **không nên**.

**3. Nên cách ly quang cho chân probe.** Một con opto rẻ tiền đứng giữa là ranh
giới duy nhất giữa mạch hồ quang và con ESP32-S3.

**4. Béc là đồ tiêu hao.** Chạm nhiều thì móp lỗ, mà lỗ béc móp là mạch cắt hỏng
theo. Để **tốc độ dò chậm** (150–300 mm/ph) và bật **dò hai lần** — lần đầu
nhanh để tìm, lần sau chậm để lấy số chính xác. Phần mềm cảnh báo nếu đặt tốc độ
dò quá 400 mm/ph ở chế độ này.

Trong hồ sơ máy mẫu: dò 250 mm/ph, dò lại 40 mm/ph, nhấc 3 mm sau khi chạm.

Vì đầu dò **chính là mũi cắt** nên mọi số lệch đều bằng 0 — không phải đo đạc gì,
gốc Z rơi đúng mặt phôi.

### Đầu dò riêng trên trục đảo

> **Mua kim dò không đủ.** Cái bán rời gồm **bi ruby + trục sứ** chỉ là *kim dò*
> (stylus), vặn ren M2.5 vào **thân đầu dò**. Bi ruby và trục sứ đều **không dẫn
> điện** — bản thân kim không đóng mạch được. Phải mua cả **thân đầu dò cảm ứng**
> (touch probe body), bên trong có tiếp điểm; kim chỉ là phần mòn thay được.

> **Nguồn nuôi đầu dò:** thường có 3 dây (nguồn, mát, tín hiệu). Nếu tín hiệu ra
> 5 V hay 12 V thì **phải hạ áp hoặc cách ly quang về 3,3 V** trước khi vào chân
> ESP32-S3 — chân S3 không chịu được 5 V.

Đầu dò gắn **lệch 90°** với mỏ cắt trên một trục đảo (trục `B`), một mô-tơ xoay
qua lại đổi đầu nào chúc xuống. Kiểu này có một cái hay về hình học: **khi mỗi
đầu đã chúc xuống thì cả hai nằm đúng cùng một chỗ theo X và Y**, chỉ khác chiều
cao — nên chỉ phải khai một số duy nhất, *đầu dò thấp hơn mỏ bao nhiêu mm*.

Trình tự phần mềm tự làm:

```
tắt mỏ → nâng Z → xoay B sang đầu dò → chờ hết rung
      → dò → nâng Z → xoay B về mỏ cắt
```

**Nâng trước rồi mới xoay** là bắt buộc: lúc xoay, đầu dài hơn quét một cung
quanh trục đảo, không nâng đủ cao là nó quét thẳng vào phôi. Đặt cao độ xoay
thấp hơn tầm quét là phần mềm báo lỗi, không cho chạy.

**Nên lắp công tắc về gốc cho trục đảo** (mẫu để ở `gpio 41`, chu kỳ về gốc 4 —
sau khi Z đã nâng). Không có nó thì sau mỗi lần mất điện phải tự xoay về mỏ cắt
rồi đặt lại gốc trục B bằng tay.

### Ba chốt an toàn, chung cho cả hai đường

1. **Luôn tắt nguồn cắt trước khi dò** — lệnh đầu tiên của mọi quy trình dò.
2. **Dò lỗi hay bấm dừng giữa chừng thì máy vẫn tự về tư thế cắt**: ngắt dây dò,
   trả đầu đảo về mỏ cắt, tắt mỏ lần nữa cho chắc.
3. **Mọi chương trình cắt đều mở đầu bằng lệnh đưa đầu đảo về mỏ cắt**, đứng
   trước mọi lệnh bật nguồn cắt.

Kiểm tra cảm biến trước khi dò lần đầu: gõ `?` ở ô lệnh, lấy tay chạm dây dò (hay
kim dò) vào phôi — dòng trạng thái phải hiện `Pn:P`. Không thấy chữ `P` nghĩa là
chưa nối đúng.

### Vì sao không dò ngang như máy phay

Máy phay dò cạnh bằng cách đưa đầu dò **chạm ngang** vào thành phôi. Máy cắt ống
thì không: mỏ treo thẳng đứng, chỉ đi lên xuống, đâm ngang vào ống là gãy mỏ.

Cách làm ở đây chỉ cần **dò xuống**:

```
dò xuống ở chỗ A  ->  chạm   =>  chỗ này còn phôi
dò xuống ở chỗ B  ->  hụt    =>  chỗ này hết phôi
             chia đôi A-B, dò lại, lặp lại  =>  ra đúng mép
```

Mỗi lần chia đôi khoảng cách còn một nửa, nên từ khoảng tìm 40 mm xuống sai số
0,1 mm chỉ mất 9 lần dò.

### Dùng thế nào

1. Rà mỏ bằng tay vào **khoảng giữa mặt trên phôi**, cách mặt vài chục mm.
2. Thẻ **Điều khiển** → khung **Dò cạnh** → chọn việc cần dò → **Bắt đầu dò**.
3. Xác nhận hộp thoại (nó nhắc lại: nguồn cắt phải tắt).

| Chọn | Máy làm gì | Đặt gốc nào |
|---|---|---|
| Chạm mặt phôi | Hạ xuống chạm mặt trên, dò hai lần cho chính xác | **Z** |
| Tìm tâm phôi | Dò hai mép trái/phải, lấy điểm giữa | **X** |
| Tìm đầu ống | Lùi dọc trục tới khi hết phôi, chia đôi | **Y** |
| Cân mặt phẳng | Đo cao độ hai chỗ trên mặt trên, xoay cho bằng nhau | **A** |
| **Dò trọn gói** | Cả bốn việc, đúng thứ tự Z → A → X → Y | **cả bốn** |

Thứ tự trong "dò trọn gói" có lý do: **phải cân mặt trước khi tìm tâm**, vì phôi
xoay lệch thì bề ngang đo được không phải bề ngang thật.

### Nó còn tự soát giúp

Lúc tìm tâm, phần mềm **đo lại bề rộng phôi** rồi đối chiếu với số đã khai:

* Bề rộng nằm ngoài mọi khả năng của tiết diện đã khai → **kích thước phôi khai
  sai**, báo ngay.
* Bề rộng lớn hơn mức "mặt phẳng ngửa lên" → **phôi đang bị xoay lệch**, phần
  mềm nói luôn lệch khoảng bao nhiêu độ và bảo chạy cân mặt trước.

Khai sai kích thước là lỗi âm thầm nguy hiểm nhất: mọi thứ vẫn chạy, chỉ có
đường cắt là sai chỗ. Đây là chỗ bắt được nó.

### Thử trước khi có cảm biến

Máy ảo có sẵn một phôi ảo, đặt lệch và xoay tuỳ ý, để xem trước trình tự dò:

```bash
python -m pipecut probe all --fake-x 7.35 --fake-y 12.4 --fake-roll 6.2 \
       --start-x 7 --start-y 100 -v
```

Chạy với máy thật thì thay `--port`:

```bash
python -m pipecut probe surface --port 192.168.1.50
python -m pipecut probe all --port COM5 --no-zero   # chỉ đo, không đặt gốc
```

### Thông số dò

Trong hồ sơ máy, mục `probe`:

| Thông số | Ý nghĩa |
|---|---|
| `seek_feed` | Tốc độ dò lần đầu (mm/ph). 300 là vừa |
| `latch_feed` | Tốc độ dò lại lần hai cho chính xác. Càng chậm càng đúng |
| `retract` | Nhấc lên bao nhiêu sau khi chạm |
| `clearance` | Cao độ an toàn khi chạy ngang giữa các điểm dò |
| `max_depth` | **Quãng dò xuống tối đa** — vừa là giới hạn an toàn, vừa quyết định có tới được mép rộng nhất không. Đặt theo hành trình Z dùng được của máy |
| `tolerance` | Dừng chia đôi khi khoảng còn nhỏ hơn số này (mm) |

Nếu `max_depth` không đủ sâu để chạm tới mép rộng nhất, phần mềm **báo rõ** chứ
không lặng lẽ cho ra số sai.

---

## 13. Giao diện: nền sáng và nền tối

Bấm nút **◐ Nền tối / ◐ Nền sáng** ở góc trên bên phải để đổi qua lại. Lựa chọn
được ghi nhớ, lần mở sau tự dùng lại.

Tông màu lấy theo **FreeCAD**: khung nhìn nền chuyển sắc xanh lam, khung điều
khiển xám trung tính, điểm nhấn xanh dương. Phôi và máy trong khung nhìn giữ
màu kim loại ở cả hai chế độ, giống hệt cách FreeCAD hiển thị vật thể.

Màu trong phần mềm đều có nghĩa, không phải trang trí:

| Màu | Ý nghĩa |
|---|---|
| **Đỏ cam** | Đường cắt |
| **Xanh dương** | Đường vạch dấu (không cắt đứt) |
| **Xanh lá** | Đoạn vào dao / ra dao, và điểm mồi |
| **Xám nhạt, nét đứt** | Đoạn chạy không (không cắt) |
| **Nút xanh dương** | Lệnh làm máy chạy: Kết nối, Về gốc, Sinh G-code, Bắt đầu cắt |
| **Nút đỏ** | Lệnh nguy hiểm: Bật nguồn cắt, DỪNG |

Mọi cặp chữ/nền trong cả hai chế độ đều đã soát theo tiêu chuẩn tương phản
**WCAG AA**, nên đọc được cả khi xưởng thiếu sáng lẫn khi nắng chiếu vào màn hình.

Bản vẽ SVG xuất ra cũng theo tông màu đang xem. Ở dòng lệnh thì chỉ định bằng
`--theme`:

```bash
python -m pipecut gen cong_viec.json -o ra.nc --svg xem.svg --theme dark
python -m pipecut ui --theme dark
```

---

## 14. Xử lý sự cố

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
| **Dò cạnh báo "không nhận được kết quả dò"** | FluidNC chưa khai chân probe, hoặc dây cảm biến đứt | Gõ `$Probe/Pin` xem đã khai chưa; gõ `?` rồi gạt tay công tắc, phải thấy `Pn:P` |
| **Dò cạnh báo "dò hết ... mà không chạm gì"** | Mỏ chưa ở trên phôi, hoặc `max_depth` quá ngắn | Rà mỏ vào giữa mặt trên phôi trước; tăng `max_depth` |
| **Dò cạnh ra tâm lệch** | Phôi bị xoay lệch, hoặc quãng dò không tới mép rộng nhất | Chạy **Cân mặt phẳng** trước rồi tìm tâm lại; đọc kỹ cảnh báo phần mềm in ra |
| **Dò xong nhưng bề rộng đo khác số khai** | Kích thước phôi khai sai, hoặc phôi đặt nghiêng | Phần mềm nói rõ là sai kích thước hay chỉ nghiêng — làm theo |
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
