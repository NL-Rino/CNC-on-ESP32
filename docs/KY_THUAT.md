# Tài liệu kỹ thuật

Tài liệu này giải thích **tại sao** phần mềm làm như đang làm. Mọi công thức ở
đây đều được kiểm chứng bằng bài kiểm thử trong `tests/`.

## Mục lục

1. [Hệ toạ độ và mặt trụ trải phẳng](#1-hệ-toạ-độ-và-mặt-trụ-trải-phẳng)
2. [Công thức các biên dạng cắt](#2-công-thức-các-biên-dạng-cắt)
3. [Góc trục vát](#3-góc-trục-vát)
4. [Bù bề rộng mạch cắt](#4-bù-bề-rộng-mạch-cắt)
5. [Bài toán tốc độ tổng hợp bốn trục](#5-bài-toán-tốc-độ-tổng-hợp-bốn-trục)
6. [Điều tiết mật độ điểm](#6-điều-tiết-mật-độ-điểm)
7. [Nạp lệnh và giao thức](#7-nạp-lệnh-và-giao-thức)
8. [Hạn chế đã biết](#8-hạn-chế-đã-biết)

---

## 1. Hệ toạ độ và mặt trụ trải phẳng

Phôi là mặt trụ bán kính `R`, quay quanh trục của chính nó. Đầu cắt đứng yên ở
vị trí 12 giờ và chỉ tiến/lùi theo phương bán kính.

Một điểm trên bề mặt được xác định bởi `(x, θ)`:

```
x = toạ độ dọc trục ống (mm)          -> trục X của máy
θ = góc quay của ống (độ)             -> trục A của máy
```

Toàn bộ phần mềm làm việc trên **mặt phẳng trải** `(u, v)`:

```
u = x                    (mm dọc ống)
v = R · θ_rad            (mm theo chu vi)
```

**Vì sao điều này quan trọng.** Trải mặt trụ ra mặt phẳng là một *phép đẳng cự*
(isometry): độ dài đường cong và góc giữa hai đường được bảo toàn **chính xác**,
không phải xấp xỉ. Hệ quả:

* Đo chiều dài đường cắt trên mặt phẳng = chiều dài thật trên ống.
* Bù kerf vuông góc trên mặt phẳng = bù đúng nửa bề rộng mạch trên ống.
* Bo góc bán kính `r` trên mặt phẳng = cung bán kính `r` thật trên bề mặt.
* Dung sai dây cung đo trên mặt phẳng là cận trên của sai số thật.

Ngoài ra `v` biến thiên **liên tục** nên `θ = v/R` cũng liên tục — không bao giờ
có cú nhảy ±180°/±360° giữa hai điểm liền nhau. Trục A vì thế quay một mạch, đây
là điều kiện cần để đường cắt không bị khựng.

---

## 2. Công thức các biên dạng cắt

### 2.1 Mặt phẳng cắt (cắt đứt / cắt vát)

Giao của một mặt phẳng nghiêng góc `α` với mặt trụ là ellipse. Trải phẳng ra nó
trở thành **hình sin thuần tuý**:

```
u(θ) = x₀ + R·tan(α)·cos(θ − φ)
```

`φ` là hướng vát quanh ống. Biên độ `R·tan α` được kiểm chứng ở
`test_cat_vat_cho_bien_do_bang_R_tan_alpha`.

### 2.2 Miệng cá (ống nhánh ôm ống chính)

Ống nhánh bán kính `r` (chính là phôi), ống chính bán kính `R`, hai trục hợp
góc `β`, lệch tâm `e`. Điểm trên mặt ống nhánh ở góc `θ`, cách trục ống chính
một đoạn `t` dọc theo trục nhánh:

```
P = ( t·cosβ − r·cosθ·sinβ ,  r·sinθ + e ,  t·sinβ + r·cosθ·cosβ )
```

Thay vào phương trình ống chính `P_y² + P_z² = R²` và giải theo `t`:

```
          √(R² − (r·sinθ + e)²) − r·cosθ·cosβ
t(θ) =  ─────────────────────────────────────
                      sinβ
```

Toạ độ trên phôi: `u = x_trục − t(θ)`, `v = r·θ`.
Chiều sâu miệng cá (trường hợp `β = 90°`, `e = 0`): `R − √(R² − r²)`.

Điều kiện tồn tại: `r ≤ R` và `|e| + r ≤ R`, phần mềm báo lỗi rõ ràng nếu vi phạm.

### 2.3 Lỗ xuyên thành ống

Đây là *vế còn lại* của cùng bài toán giao tuyến — đường cắt nằm trên ống chính.
Thay `t(θ)` ngược vào `P` cho kết quả rất gọn:

```
P_y = r·sinθ + e
P_z = √(R² − P_y²)
P_x = (P_z·cosβ − r·cosθ) / sinβ
φ   = atan2(P_y, P_z)          (góc quay quanh phôi)
```

Với `β = 90°`, `e = 0` ta được `u ∈ [−r, +r]` và `φ ∈ ±asin(r/R)` — đúng như
trực giác về một lỗ khoan hướng tâm.

Cả hai công thức được kiểm chứng bằng cách dựng lại điểm 3D và kiểm tra nó nằm
**đồng thời trên cả hai mặt trụ** (`test_lo_xuyen_nam_tren_ca_hai_mat_tru`).

### 2.4 Các biên dạng khác

| Biên dạng | Trên mặt phẳng trải |
|---|---|
| Rãnh chữ nhật | hình chữ nhật `L × (R·Δθ)`, bo góc bằng cung tròn |
| Tròn trên bề mặt | đường tròn thật (khác lỗ khoan!) |
| Xoắn ốc | đường **thẳng** — đó là lý do xoắn ốc cắt rất mượt |
| Biên dạng tự do | chép nguyên xi từ tệp CSV/DXF |

---

## 3. Góc trục vát

Với máy 4 trục, trục vát chỉ nghiêng được trong mặt phẳng chứa trục ống và
phương bán kính (nghiêng "tới/lui" dọc ống). Góc cần thiết để mặt cắt vuông góc
với đường cắt chính là **độ dốc dọc trục của đường cắt trên mặt phẳng trải**:

```
tan(γ) = du / dv
```

Kiểm chứng bằng hai trường hợp có đáp số giải tích:

* **Cắt vát mặt phẳng góc α**: `u = x₀ + R·tanα·cos(v/R)` ⟹ `du/dv = −tanα·sin θ`,
  đạt cực đại đúng bằng `α` tại sườn ống (`θ = 90°`) và bằng 0 tại hai điểm cực —
  giống hệt cách thợ đặt mỏ cắt bằng tay.
* **Miệng cá**: cực đại của `atan( r·sinθ·cosθ / √(R² − r²sin²θ) )`; với `r=30`,
  `R=50` là 18.4°, phần mềm cho 17.9° (sai số < 1°, xem bên dưới).

Hai chi tiết kỹ thuật:

* **Ước lượng đạo hàm theo khoảng cách cung**, không theo chỉ số điểm (cửa sổ
  ±1.5 mm), nên mật độ điểm không ảnh hưởng tới góc tính ra.
* **Làm trơn cũng theo khoảng cách cung**: nếu các điểm đã thưa hơn cửa sổ thì
  không làm trơn nữa. Nếu làm trơn theo chỉ số như cách thông thường, đỉnh góc
  vát bị bào mòn (18.4° → 17.1°). Sai số còn lại ~0.5° đến từ việc lấy cát tuyến
  thay cho tiếp tuyến — hoàn toàn nằm trong dung sai cơ khí của một mỏ plasma.

Đoạn vào/ra dao **không** tham gia tính góc vát (nó chạy thuần theo trục nên sẽ
kéo góc lệch hẳn đi); các điểm đó nhận đúng góc vát của điểm cắt kề bên, tức là
trục vát đã vào đúng vị trí từ trước khi mồi.

Khi tâm xoay của cơ cấu nghiêng cách mũi cắt một đoạn `L`, nghiêng góc `γ` làm
mũi cắt dịch đi; phần mềm bù lại:

```
X_lệnh = x + L·sin γ
Z_lệnh = z − L·(1 − cos γ)
```

---

## 4. Bù bề rộng mạch cắt

Tâm tia luôn phải lệch khỏi đường bao danh nghĩa **nửa bề rộng mạch cắt về phía
phần phế liệu**:

| Loại biên dạng | Phía phế liệu | Cách bù |
|---|---|---|
| Lỗ, rãnh (khép kín) | bên trong | bù vào trong nửa kerf |
| Cắt đứt, miệng cá (quấn quanh ống) | phía đầu tự do | bù vuông góc, hướng `+u` |
| Đường hở | không xác định | chỉ bù khi người dùng chỉ định |

Thuật toán bù: dịch từng đoạn theo pháp tuyến rồi lấy giao của các đường đã dịch;
sau đó **cắt bỏ các "tai" tự giao** (dùng kiểm tra bao hình chữ nhật trước nên
vẫn nhanh với vài nghìn điểm).

Với đường quấn quanh ống, trước khi bù phần mềm **nối thêm bản sao tuần hoàn** ở
hai đầu rồi cắt lại sau — nhờ vậy điểm nối vòng được bù đúng như mọi điểm khác,
không bị "gãy" tại chỗ khép kín.

Kiểm chứng: một lỗ ⌀30 với kerf 2 mm cho đường chạy dao dài đúng 28 mm dọc trục
(`test_bu_kerf_thu_nho_lo_dung_nua_be_rong`).

---

## 5. Bài toán tốc độ tổng hợp bốn trục

### Vấn đề

FluidNC/Grbl phân bổ tốc độ theo **quãng đường tổng hợp trong không gian trục**:

```
L_trục = √(ΔX² + ΔY² + ΔZ² + ΔA² + ΔB²)
```

trong đó `ΔA` tính bằng **độ** nhưng lại được cộng như thể là **mm**. Thời gian
chạy một block là `L_trục / F`.

Với ống ⌀60 (R = 30 mm), quay 1 độ tương đương `π·30/180 = 0.524 mm` trên bề mặt.
Vậy nếu ghi `F1600` cố định:

| Đoạn | L_bề_mặt | L_trục | Tốc độ bề mặt thực |
|---|---|---|---|
| chỉ chạy dọc 10 mm | 10.00 | 10.00 | **1600 mm/ph** ✔ |
| chỉ xoay 45° | 23.56 | 45.00 | **838 mm/ph** ✘ (chậm 48%) |
| phối hợp 10 mm + 45° | 25.60 | 46.10 | **889 mm/ph** ✘ |

Trên một đường miệng cá, tỉ lệ giữa hai thành phần thay đổi liên tục, nên tốc độ
bề mặt dao động suốt nhát cắt — đó chính là nguyên nhân "chỗ cháy chỗ non".

### Cách giải

Với mỗi đoạn, tính quãng đường thật của mũi cắt trên bề mặt:

```
L_bề_mặt = √( Δx² + (R_cắt·Δθ_rad)² + Δz² + (L_pivot·Δγ_rad)² )
```

rồi ghi ra:

```
F = v_cắt · L_trục / L_bề_mặt
```

Sau đó kẹp lại theo tốc độ tối đa của **từng trục**:

```
F ≤ max_rate_i · L_trục / |Δ_i|      với mọi trục i
```

và theo trần/sàn tốc độ trong hồ sơ máy.

Kết quả (`test_toc_do_be_mat_khong_doi_moi_ti_le_phoi_hop_truc`): tốc độ bề mặt
bằng đúng giá trị đặt với sai số < 0.5 mm/phút, ở mọi tỉ lệ phối hợp trục — kể cả
trên toàn bộ một đường miệng cá thật.

`R_cắt` lấy theo `feed_radius_mode`: `outer` (mặc định), `mid` (giữa thành ống)
hoặc `inner`. Với ống thành dày, `mid` cho tốc độ sát thực tế hơn.

---

## 6. Điều tiết mật độ điểm

ESP32 xử lý mỗi block G-code mất một khoảng thời gian cố định (đọc UART, phân
tích cú pháp, đưa vào planner). Nếu tốc độ tiêu thụ block vượt khả năng đó,
planner cạn dữ liệu và bộ điều khiển buộc phải giảm tốc — máy giật từng nhịp.

Chuỗi bốn bước:

| Bước | Việc làm | Mục đích |
|---|---|---|
| 1. Lấy mẫu thích nghi | chia đôi đệ quy tới khi sai số dây cung < dung sai | dày ở chỗ cong gắt, thưa ở chỗ gần thẳng |
| 2. Rút gọn (Douglas–Peucker) | bỏ điểm gần thẳng hàng | giảm 30–60% số dòng mà hình dạng vẫn trong dung sai |
| 3. Gộp đoạn ngắn | bỏ đoạn < `min_segment` | tránh chuỗi block li ti làm nghẽn planner |
| 4. Chia đoạn dài | cắt đoạn > `max_segment` | để planner luôn có nhiều block nhìn trước, không phanh gấp |

Bước 3 và 4 nghe có vẻ mâu thuẫn nhưng phục vụ hai vấn đề khác nhau: một bên là
**quá tải xử lý**, một bên là **thiếu tầm nhìn của planner**.

Ngoài ra bo góc (`round_corners`) thay các góc nhọn bằng cung tròn. Góc nhọn buộc
bộ điều khiển phải dừng hẳn vận tốc tại đỉnh (junction deviation ≈ 0); thay bằng
cung tròn thì bốn trục chuyển hướng liên tục.

Bộ hậu xử lý còn rút ngắn dòng lệnh: chỉ ghi từ lệnh nào thay đổi (modal), F chỉ
ghi lại khi lệch quá 4%, số bỏ 0 thừa. Trung bình **17.3 byte/dòng** — ở 115200
baud tương đương khả năng nạp ~660 block/giây, dư sức nuôi planner.

---

## 7. Nạp lệnh và giao thức

### Đếm ký tự (character counting)

Cách gửi–chờ–`ok` từng dòng khiến planner luôn rỗng. Thay vào đó phần mềm cộng
dồn độ dài các dòng đã gửi mà **chưa nhận `ok`**, và chỉ gửi tiếp khi:

```
byte_đang_chờ + len(dòng_mới) + 1  ≤  rx_buffer − 1
```

Đo thực tế trên máy ảo: bộ đệm luôn ở mức **124/127 byte** trong suốt quá trình
chạy — tức là FluidNC lúc nào cũng có sẵn hàng chục block để nhìn trước.

`rx_buffer` mặc định 127 (an toàn cho cả Grbl gốc); FluidNC thật có 255, có thể
tăng lên trong hồ sơ máy nếu muốn.

### Luồng dữ liệu

Ba luồng nền chạy song song, giao diện chỉ đọc sự kiện từ hàng đợi:

```
luồng đọc   ── phân tích từng dòng ──► ok/error  → trả chỗ trong bộ đệm
                                    ├► <...>    → cập nhật DRO, vẽ vị trí mũi cắt
                                    └► ALARM    → dừng chương trình, báo người dùng
luồng ghi   ── chọn dòng kế tiếp (lệnh tay ưu tiên hơn chương trình) ──► cổng COM
luồng hỏi   ── gửi '?' mỗi 200 ms ──►
```

Lệnh thời gian thực (`?`, `!`, `~`, `0x18`, `0x85`, các byte override) được gửi
thẳng, không xếp hàng và không chiếm bộ đệm — đúng theo đặc tả Grbl 1.1.

Khi gặp `error:N` giữa chương trình, phần mềm **dừng ngay** thay vì chạy tiếp:
với máy cắt, chạy tiếp sau một dòng bị từ chối là cách nhanh nhất để hỏng phôi.

---

## 8. Hạn chế đã biết

* **Chỉ xuất G1/G0**, không dùng cung tròn G2/G3. Cung tròn không biểu diễn được
  đường giao tuyến ống trong không gian 4 trục, và với dung sai dây cung đã dùng
  thì lợi ích gần như không có.
* **Không mô hình hoá gia tốc** khi ước tính thời gian — con số hiển thị là cận
  dưới, thực tế lâu hơn 10–30% tuỳ số đoạn ngắn.
* **Máy ảo không mô phỏng gia tốc**, chỉ dùng để kiểm tra logic và luồng lệnh.
* **Trục vát 4 trục không cắt được mặt vát chuẩn ở mọi điểm** của biên dạng phức
  tạp — đó là giới hạn động học, muốn đúng tuyệt đối cần máy 5 trục. Phần mềm cho
  góc tối ưu trong khả năng của bốn trục.
* **Không có điều khiển chiều cao tự động (THC)** — phần mềm đặt Z theo giá trị
  cố định. Nếu phôi cong hoặc ô van nhiều, nên dùng THC phần cứng.
* **Bù kerf cho biên dạng tự cắt nhau nhiều lần** (biên dạng rất phức tạp, kerf
  lớn) có thể còn sót vòng lặp; hãy xem kỹ bản xem trước trước khi cắt.
