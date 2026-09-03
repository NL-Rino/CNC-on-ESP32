# PipeCut Studio — Phần mềm máy cắt ống 4 trục cho ESP32 / FluidNC

Phần mềm chạy trên máy tính (Windows / Linux / macOS), nói chuyện với bo **ESP32
chạy firmware FluidNC** qua **cổng COM**, để điều khiển máy cắt ống 4 trục:
sinh biên dạng, tính đường chạy dao, xem trước, rồi nạp G-code xuống máy.

Trọng tâm của phần mềm là **đường cắt mượt nhờ bốn trục phối hợp** — xem phần
[Ba trụ cột của độ mượt](#ba-trụ-cột-của-độ-mượt) và
[docs/KY_THUAT.md](docs/KY_THUAT.md).

```
┌──────────────┐   USB / COM   ┌──────────────┐   xung bước   ┌──────────────┐
│ PipeCut      │ ────────────► │ ESP32        │ ────────────► │ Máy cắt ống  │
│ Studio (PC)  │ ◄──────────── │ FluidNC      │               │ X Y Z A      │
└──────────────┘   trạng thái  └──────────────┘               └──────────────┘
```

---

## Máy 4 trục gồm những gì

| Trục | Vai trò | Đơn vị | Ghi chú |
|------|---------|--------|---------|
| **Y** | **ống ra vào** — bàn mang mâm cặp chạy dọc trục ống | mm | phôi tịnh tiến, mỏ cắt đứng yên |
| **A** | **mâm cặp xoay** ống | **độ** | quay vô hạn, không cần về gốc |
| **X** | **mỏ cắt chạy ngang**, vuông góc với trục Y | mm | hoặc dùng làm trục vát mép |
| **Z** | **mỏ cắt lên xuống** | mm | giữ khoảng cách mỏ–phôi |

```
              Z ↕ mỏ cắt lên xuống
              │
        X ↔───┴───  mỏ cắt chạy ngang (vuông góc Y)
              ▼
   ══════════════════════════╗
    ống  ←── Y ──→  quay A   ║ mâm cặp
   ══════════════════════════╝
```

Gốc toạ độ quy ước: **Y0** khi mũi cắt ở đúng mặt đầu phôi, **Z0** khi mũi cắt
chạm mặt ống, **A0** ở vị trí 12 giờ (ngay dưới mỏ cắt), **X0** khi mỏ cắt nằm
đúng trên đường tâm ống.

Vai trò trục khai báo được trong hồ sơ máy, nên nếu máy của bạn là kiểu **xe mỏ
cắt chạy dọc còn ống đứng yên** thì chỉ cần đổi vai trò và đặt
`"layout": "torch_moves"` — phần còn lại của phần mềm không đổi gì.

---

## Làm được những gì

| Nguyên công | Mô tả |
|---|---|
| `cutoff` | Cắt đứt vuông góc hoặc **cắt vát** một góc bất kỳ (làm co, cút) |
| `saddle` | **Miệng cá / yên ngựa** — cắt đầu ống nhánh ôm khít ống chính (chữ T, chữ Y, lệch tâm) |
| `hole` | **Lỗ xuyên thành ống**, hướng tâm hoặc xiên, có lệch tâm |
| `slot` | Cửa sổ / rãnh chữ nhật bo góc, đo theo kích thước thật trên bề mặt |
| `circle` | Đường tròn đo trên bề mặt ống |
| `helix` | Đường xoắn ốc quanh ống |
| `axial` | Đường cắt hoặc vạch dấu dọc thân ống |
| `ring_mark` | Vạch dấu vòng quanh ống |
| `weld_prep` | Vát mép hàn chữ V ở đầu ống |
| `pattern` | Cuốn một **biên dạng phẳng bất kỳ** (từ DXF/SVG/CSV) lên mặt ống |

Hỗ trợ tiến trình: **plasma, laser, oxy-gas, phay, bút vạch dấu**.

---

## Cài đặt

Cần **Python 3.9 trở lên**.

```bash
git clone https://github.com/NL-Rino/CNC-on-ESP32.git
cd CNC-on-ESP32
pip install -r requirements.txt      # chỉ cần pyserial
```

* Giao diện đồ hoạ dùng **Tkinter**, có sẵn trong bản Python cài trên Windows/macOS.
  Trên Linux: `sudo apt install python3-tk`.
* Phần sinh G-code và mô phỏng **không cần thư viện ngoài nào** — chạy được ngay
  bằng Python thuần.

---

## Bắt đầu nhanh (chưa cần phần cứng)

Phần mềm có sẵn **máy ảo FluidNC**, hãy thử trước khi cắm máy thật:

```bash
python -m pipecut ui                       # mở giao diện, chọn cổng "GIA-LAP"
```

Hoặc bằng dòng lệnh:

```bash
python -m pipecut ops                      # xem danh mục nguyên công
python -m pipecut gen examples/vi_du_ong_T.json -o ong_T.nc --svg xem.svg
python -m pipecut gen examples/vi_du_ong_T.json -o ong_T.nc \
       --machine-svg mo-phong.svg --at 75   # chụp mô phỏng ở 75% chương trình
python -m pipecut sim ong_T.nc --speed 20   # chạy thử trên máy ảo
```

Khi đã có máy thật:

```bash
python -m pipecut ports                    # tìm cổng COM của ESP32
python -m pipecut run examples/vi_du_ong_T.json --port COM5
```

Trên Windows có thể nháy đúp `chay_gui.py` để mở giao diện.

---

## Trình tự làm việc trên giao diện

```
1. Máy & Kết nối → 2. Điều khiển → 3. Công việc → 4. Xem trước → 5. Mô phỏng → 6. Chạy
   chọn cổng COM    jog, đặt gốc    thêm nguyên    kiểm tra       xem máy       nạp lệnh,
   khai báo phôi    toạ độ          công, nhập số  hình 2D/3D     chạy thử      theo dõi
```

* **Xem trước** có hai khung nhìn: *trải phẳng* (đo kích thước thật) và *ba chiều*
  (hình dung nhát cắt), zoom bằng con lăn, kéo bằng chuột trái.
  Xem bản mẫu: [docs/vi_du_ong_T.svg](docs/vi_du_ong_T.svg).
![Mô phỏng máy](docs/mo_phong_may.svg)

* **Mô phỏng** dựng lại đúng máy của bạn: đoạn ống dài theo kích thước đã nhập,
  **trượt ra vào** theo trục Y và **quay** theo trục A, mỏ cắt chạy ngang (X) và
  lên xuống (Z), vết cắt đỏ hiện dần trên mặt ống. Chạy được offline — bấm ▶,
  tua tới lui bằng thanh trượt, đổi tốc độ 0,25× đến 20×, kéo chuột để xoay góc
  nhìn. Khi đã nối máy thật, bật *Bám theo máy thật* thì khung này phản chiếu
  đúng vị trí máy đang báo về.
* Trong lúc chạy, vị trí mũi cắt được vẽ **theo thời gian thực** lên bản xem trước,
  dòng G-code đang chạy được tô sáng.
* Nút **DỪNG** gửi feed-hold rồi reset mềm, tắt nguồn cắt ngay lập tức.

---

## Ba trụ cột của độ mượt

Máy cắt ống tự chế hay bị "cắt lúc cháy lúc non, đường cắt gợn sóng". Nguyên nhân
gần như luôn là ba thứ dưới đây, và phần mềm này xử lý cả ba:

### 1. Bù tốc độ tổng hợp cho trục xoay

FluidNC (như Grbl) tính `F` trên **quãng đường tổng hợp trong không gian trục**,
trong đó *độ* của trục A được cộng chung với *mm* của trục X. Ghi `F1600` cố định
thì đoạn chỉ xoay chạy ở 1600 độ/phút — với ống ⌀60 chỉ tương đương **838 mm/phút**
trên bề mặt, chậm hơn 48% so với đoạn chỉ chạy dọc.

Phần mềm tính lại F cho **từng đoạn**:

```
F = v_cắt × L_trục / L_bề_mặt
```

nên tốc độ mũi cắt trên bề mặt ống **luôn không đổi** dù bốn trục phối hợp theo
tỉ lệ nào. Đây là điều kiện đầu tiên để mạch cắt đều.

### 2. Mật độ điểm vừa đủ cho ESP32

Quá nhiều điểm → ESP32 nghẽn, planner hụt hơi, máy giật. Quá ít điểm → đường cong
thành đa giác. Phần mềm rời rạc hoá **thích nghi theo dung sai dây cung**, rồi rút
gọn (Douglas–Peucker), gộp đoạn quá ngắn, chia nhỏ đoạn quá dài. Kết quả: chỗ cong
gắt thì dày điểm, chỗ gần thẳng thì thưa.

### 3. Nạp lệnh theo kiểu đếm ký tự

Không gửi–chờ–`ok` từng dòng (kiểu đó planner không bao giờ nhìn được về phía
trước). Phần mềm luôn giữ bộ đệm nhận của ESP32 **gần đầy** (đo được ~124/127 byte),
để FluidNC lúc nào cũng có 15–30 block phía trước mà làm mượt vận tốc giữa các đoạn.

Ngoài ra: đường cắt được xử lý trên **mặt trụ trải phẳng** — một phép đẳng cự, nên
bù kerf, bo góc và đo chiều dài đều chính xác tuyệt đối; và góc quay biến thiên liên
tục, không bao giờ nhảy ±180°.

---

## Cấu trúc mã nguồn

```
pipecut/
  config.py      hồ sơ máy: trục, phôi, tiến trình, tham số chuyển động
  geom2d.py      hình học 2D: bù đường, bo góc, rút gọn, lấy mẫu thích nghi
  shapes.py      thư viện biên dạng cắt ống (toán giao tuyến mặt trụ)
  toolpath.py    cấu trúc dữ liệu đường chạy dao
  pathops.py     kerf → vào/ra dao → điều tiết điểm → góc trục vát
  kinematics.py  động học 4 trục + bù tốc độ tổng hợp
  gcode.py       hậu xử lý FluidNC (modal, dòng lệnh ngắn)
  gsim.py        diễn giải G-code theo thời gian (cho tab Mô phỏng)
  machinescene.py dựng hình mô phỏng máy (dùng chung cho giao diện và SVG)
  jobs.py        mô tả công việc bằng JSON + danh mục nguyên công
  protocol.py    phân tích phản hồi Grbl/FluidNC, mã lỗi tiếng Việt
  transport.py   cổng COM (pyserial) hoặc máy ảo
  simulator.py   máy ảo FluidNC để thử khi chưa có phần cứng
  controller.py  nạp lệnh đếm ký tự, jog, tạm dừng, dừng khẩn
  svgview.py     xuất bản vẽ xem trước SVG
  cli.py         giao diện dòng lệnh
  ui/            giao diện đồ hoạ Tkinter (kèm khung mô phỏng máy 3D)
config/          hồ sơ máy mẫu (thường, có trục vát, laser)
firmware/        cấu hình FluidNC cho ESP32
examples/        tệp công việc mẫu
docs/            hướng dẫn sử dụng và tài liệu kỹ thuật
tests/           72 bài kiểm thử (chạy bằng thư viện chuẩn)
```

Chạy kiểm thử:

```bash
python -m unittest discover -s tests -t .
```

---

## An toàn

Máy cắt ống dùng plasma/laser/oxy-gas là thiết bị nguy hiểm. Phần mềm chỉ là một
lớp điều khiển — **trách nhiệm an toàn thuộc về người vận hành**:

* Luôn thử trên **máy ảo** hoặc chạy khô (tắt nguồn cắt, nâng Z lên cao) trước.
* Kiểm tra `Giới hạn trục` mà phần mềm báo sau khi sinh G-code.
* Lắp công tắc dừng khẩn cấp **cứng**, cắt trực tiếp nguồn động lực — không phụ
  thuộc vào nút DỪNG trên phần mềm.
* Kẹp phôi chắc chắn; ống dài phải có giá đỡ đầu kia của mâm cặp.
* Hút khói, kính bảo hộ đúng cấp, và nối đất thân máy khi cắt plasma.

---

## Tài liệu

* [docs/HUONG_DAN.md](docs/HUONG_DAN.md) — hướng dẫn lắp đặt, hiệu chỉnh và sử dụng.
* [docs/KY_THUAT.md](docs/KY_THUAT.md) — công thức hình học, thuật toán, giao thức.
* [firmware/fluidnc_pipe4axis.yaml](firmware/fluidnc_pipe4axis.yaml) — cấu hình FluidNC mẫu.
