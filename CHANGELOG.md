# Nhật ký thay đổi

## v1.2.0 — 2026-09-03

### Thứ tự cắt: giữ đúng như người dùng xếp

Trước đây phần mềm **tự sắp xếp lại** thứ tự cắt mà không có cách nào tắt, nên
xếp đúng thứ tự trong bảng rồi máy vẫn cắt theo thứ tự khác. Nay:

* mặc định **giữ nguyên thứ tự trong bảng**, không tự đổi;
* có ô *Tự sắp xếp thứ tự cắt* trên giao diện để bật khi cần;
* dòng chữ dưới bảng luôn hiện **thứ tự cắt thật sự** sẽ chạy;
* nếu tự xếp mà có nguyên công nằm ngoài một nhát cắt đứt phía trước, phần mềm
  **cảnh báo** (lúc đó phần phôi đó đã rơi ra) chứ không tự ý đổi thứ tự.

### Thư viện nguyên công lọc theo dạng phôi

Máy chỉ cắt ống hộp thì không cần thấy *miệng cá* và *lỗ xuyên thành* — hai
biên dạng đó là bài toán giao hai mặt trụ, chỉ có nghĩa với ống tròn. Danh sách
thêm nguyên công nay tự lọc theo hình dạng phôi đang khai báo, và hồ sơ máy mặc
định `config/machine_default.json` đã chuyển sang **ống hộp**
(`config/machine_round.json` dành cho máy cắt ống tròn).

### Điều khiển vào dao

Thêm hai thông số để chọn chỗ vết mồi rơi vào:

* **Vị trí điểm mồi** (`lead_start`, % chu vi biên dạng) — xoay điểm bắt đầu
  quanh biên dạng, ví dụ đưa vết mồi vào giữa một cạnh thay vì đúng góc bo, hoặc
  chuyển nhát cắt đứt sang bắt đầu ở mặt khác;
* **Phía vào dao** (`lead_side`) — `inside`/`outside` với biên dạng kín,
  `plus`/`minus` với nhát cắt quanh phôi (mồi lệch về đầu tự do hay về mâm cặp).

### Chế độ dừng cắt — xoay góc — cắt tiếp (ống hộp)

`corner_mode = "index"`: cắt hết một mặt phẳng thì **tắt mỏ, nhấc lên, ba trục
phối hợp giữ mỏ bám đúng góc đó trên phôi trong lúc mâm quay 90°, quay xong hạ
xuống mồi lại rồi cắt mặt kế tiếp**. Nhờ vậy tốc độ cắt trên mặt phẳng luôn đúng
như đặt, không bị trục xoay kéo tụt ở góc.

Đổi lại bốn cung góc lượn không được cắt nên phôi chưa rời hẳn — phần mềm cảnh
báo rõ. Đặt `corner_torch_off = false` thì mỏ vẫn cháy suốt lúc xoay nên cắt
luôn cả góc. Hồ sơ mẫu: `config/machine_box_index.json`.

### Khác

* Sửa lỗi mỏ cắt hạ xuống cao độ cắt **trước khi** quay xong ở chế độ index
  (cắm vào thành phôi 0,13 mm).
* Pha xoay góc được vẽ bằng nét đứt trong hai khung xem trước (vì không cắt).
* Kiểm thử tăng từ 92 lên **109 bài**.

## v1.1.0 — 2026-09-03

### Hỗ trợ ống hộp (vuông và chữ nhật)

Trước đây phôi luôn là ống tròn. Nay khai báo được **hình dạng tiết diện**:
ống tròn nhập đường kính, ống hộp nhập cạnh ngang (và cạnh dọc nếu là hộp chữ
nhật) cùng bán kính góc lượn.

Mỏ cắt **luôn vuông góc với bề mặt phôi** ở mọi loại tiết diện. Phần mềm xoay
trục A sao cho pháp tuyến chỗ đang cắt hướng thẳng lên, dùng trục X đưa mỏ cắt
tới đúng vị trí trên mặt, và trục Z bù chênh cao ở góc lượn:

| Vị trí | A | X | Z |
|---|---|---|---|
| Ống tròn, mọi nơi | quay đều | 0 | không đổi |
| Ống hộp, trên mặt phẳng | đứng yên | chạy dọc mặt | không đổi |
| Ống hộp, qua góc lượn | xoay 90° | bám cung | nhô lên rồi hạ xuống |

Với ống tròn, phép ánh xạ tự rút gọn về X = 0 và Z không đổi, nên hành vi cắt
ống tròn **không đổi một chút nào** so với bản trước.

### Sửa lỗi quan trọng đi kèm

* **Không rút gọn điểm một cách ngây thơ nữa.** Trên mặt trải phẳng, nhát cắt
  quanh ống hộp là đường thẳng, nhưng trong không gian bốn trục thì không:
  nội suy thẳng sẽ cho mỏ cắt cắm vào góc lượn. Nay phần mềm chèn đỉnh tại mọi
  chỗ đổi hình (mặt phẳng ↔ góc lượn) và chia nhỏ theo sai lệch đo trong không
  gian trục. Trên mặt phẳng và với ống tròn, sai lệch bằng 0 nên không thêm
  điểm thừa nào.
* **Sửa cú nhảy 360° của trục A** khi đường cắt đi qua mốc 0 trên ống hộp.
* **Sửa ước tính thời gian** trong tab Xem trước (trước đây bỏ sót các đoạn
  nâng/hạ trục Z).

### Cảnh báo và chế độ tốc độ đều

Qua góc lượn, trục A phải quay 90° trong đoạn cung rất ngắn — ống 50×50 góc lượn
R6 cần tới ~15 000 độ/phút để giữ tốc độ cắt 1600 mm/phút. Đây là giới hạn cơ
khí, không phải lỗi. Phần mềm kẹp tốc độ theo khả năng thật của từng trục và
**cảnh báo bằng con số cụ thể**. Bật `uniform_feed` để cả đường chạy ở một tốc
độ bề mặt duy nhất — chậm hơn nhưng vết cắt đồng đều từ mặt phẳng sang góc lượn.

### Khác

* Nguyên công *miệng cá* và *lỗ xuyên thành* chỉ áp dụng cho ống tròn (là bài
  toán giao hai mặt trụ); với ống hộp phần mềm báo rõ lý do thay vì cắt sai.
* Định vị theo góc (`theta`) nay tính theo **hướng nhìn từ tâm**, nên "rãnh ở
  90 độ" nằm đúng giữa mặt bên của ống hộp chứ không rơi vào mép.
* Hồ sơ máy mới `config/machine_box.json`, ví dụ `examples/vi_du_ong_hop.json`.
* Trục ngang mặc định lấy hành trình đối xứng (−100…100 mm) quanh đường tâm phôi.
* CLI nhận `--profile` ở cả trước lẫn sau tên lệnh con, thêm `--shape`,
  `--width`, `--height`.
* Bộ kiểm thử tăng từ 72 lên **92 bài**, trong đó có bài dựng lại vị trí mũi cắt
  từ chính G-code (kể cả các điểm giữa hai lệnh) để chứng minh khe hở mỏ–phôi
  luôn đúng bằng cao độ cắt.

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
