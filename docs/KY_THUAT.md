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
8. [Nhập biên dạng từ tệp ngoài](#8-nhập-biên-dạng-từ-tệp-ngoài)
9. [Hạn chế đã biết](#9-hạn-chế-đã-biết)

---

## 1. Hệ toạ độ và mặt trụ trải phẳng

Phôi là mặt trụ bán kính `R`, quay quanh trục của chính nó và **tịnh tiến dọc
theo trục của nó**. Mỏ cắt đứng yên theo phương dọc, chỉ chạy ngang (X) và lên
xuống (Z).

Về mặt toán học, "ống chạy còn mỏ cắt đứng yên" và "mỏ cắt chạy còn ống đứng
yên" là **cùng một bài toán** — chỉ khác hệ quy chiếu. Nhờ vậy toàn bộ phần
hình học không cần biết máy thuộc kiểu nào; chỉ có khung mô phỏng mới quan tâm,
qua trường `layout` trong hồ sơ máy.

Một điểm trên bề mặt được xác định bởi `(x, θ)`:

```
x = toạ độ dọc trục ống (mm)          -> trục Y của máy (ống ra vào)
θ = góc quay của ống (độ)             -> trục A của máy (mâm cặp)
```

Chữ cái trục do **vai trò** trong hồ sơ máy quyết định, không phải do quy ước
cứng trong mã nguồn — đổi vai trò là G-code xuất ra đổi theo.

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

## 1b. Tiết diện phôi và động học cắt vuông góc

Ống tròn là trường hợp đặc biệt dễ chịu: khoảng cách từ tâm tới bề mặt không đổi,
pháp tuyến luôn hướng ra ngoài theo phương bán kính, nên cứ quay trục A là điểm
cần cắt tự nằm đúng dưới mỏ cắt.

Ống hộp thì khác hẳn:

* khoảng cách tâm → bề mặt thay đổi (nửa cạnh ở giữa mặt, lớn hơn ở góc lượn);
* **hướng pháp tuyến cũng thay đổi**: giữ nguyên suốt một mặt phẳng rồi quay
  90° trong một đoạn cung ngắn.

### Điều kiện cắt vuông góc

Muốn mỏ cắt vuông góc với bề mặt tại điểm ``s``, phải xoay phôi sao cho pháp
tuyến tại đó hướng thẳng lên. Gọi ``ψ(s)`` là góc pháp tuyến và ``C(s)`` là điểm
trên biên tiết diện, ta được **phép ánh xạ động học tổng quát**:

```
A(s) = ψ(s)                        (góc trục xoay)
X(s) = thành phần ngang của R(−ψ)·C(s)     (trục ngang)
Z(s) = thành phần cao của R(−ψ)·C(s)       (chiều cao bề mặt)
```

Kiểm chứng ba trường hợp:

| Vị trí | A | X | Z |
|---|---|---|---|
| Ống tròn, mọi nơi | ``s/R`` | **0** | ``R`` (không đổi) |
| Ống hộp, trên mặt phẳng | không đổi | **chạy dọc mặt** | nửa cạnh (không đổi) |
| Ống hộp, qua góc lượn | quay 90° | chạy từ mép này sang mép kia | nhô lên rồi hạ xuống |

Với góc lượn tâm ``K`` bán kính ``r_c``: ``R(−ψ)·C = R(−ψ)·K + r_c·(0,1)``, nghĩa
là mũi cắt vạch một **cung tròn bán kính |K|** trong mặt phẳng (X, Z) - đó là lý
do cả ba trục phải phối hợp qua góc.

Vì ống tròn cho ``X ≡ 0`` và ``Z`` không đổi, cùng một bộ mã chạy đúng cho cả hai
loại phôi mà không cần rẽ nhánh.

### Hệ quả: không được rút gọn điểm một cách ngây thơ

Trên mặt trải phẳng, nhát cắt vuông góc quanh ống hộp là một **đường thẳng**.
Nhưng trong không gian bốn trục nó không hề thẳng. Nếu để bước rút gọn
Douglas–Peucker gộp cả đường thành hai điểm rồi nội suy thẳng, mỏ cắt sẽ đi
xuyên qua góc lượn và **cắm vào phôi**.

Vì vậy sau khi rút gọn, phần mềm còn hai bước bắt buộc với tiết diện không tròn:

1. **Chèn đỉnh tại mọi chỗ đổi hình** (mặt phẳng ↔ góc lượn). Đó chính là nơi độ
   cong nhảy bậc và trục X đạt cực trị.
2. **Chia nhỏ theo sai lệch trong không gian trục**: đo khoảng cách giữa đường đi
   thật của mũi cắt và dây cung nối hai điểm, chia đôi cho tới khi nhỏ hơn dung
   sai. Trên mặt phẳng và với ống tròn, sai lệch bằng 0 nên **không thêm điểm nào**
   - số dòng G-code không tăng vô ích.

Bài kiểm thử ``test_khe_ho_mo_cat_luon_dung_bang_cao_do_cat`` dựng lại vị trí mũi
cắt từ chính G-code, kể cả các điểm **giữa hai lệnh**, rồi đo khe hở tới bề mặt
phôi - đây là bằng chứng máy không cắm vào phôi ở bất cứ đâu.

### Giới hạn cơ khí ở góc lượn

Qua góc lượn, trục A phải quay 90° trong đoạn cung ``π·r_c/2``. Với ống 50×50 góc
lượn R6, đoạn cung chỉ 9,4 mm: giữ tốc độ cắt 1600 mm/phút đòi hỏi trục xoay chạy
**~15 000 độ/phút**, vượt xa khả năng của mọi mâm cặp thông thường.

Đây là giới hạn vật lý, không phải lỗi phần mềm. Phần mềm kẹp tốc độ theo khả
năng thật của từng trục rồi **cảnh báo bằng con số cụ thể**. Hai cách xử lý:

* bật ``uniform_feed`` - cả đường chạy ở một tốc độ bề mặt duy nhất (bằng tốc độ
  chậm nhất), vết cắt đồng đều từ mặt phẳng sang góc lượn, đổi lại lâu hơn;
* hoặc tăng khả năng của trục xoay: giảm tỉ số truyền, tăng điện áp driver, dùng
  động cơ mô-men lớn hơn.

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

| Biên dạng | Trên mặt phẳng trải | Ống hộp |
|---|---|---|
| Rãnh chữ nhật | hình chữ nhật, bo góc bằng cung tròn | ✔ |
| Tròn trên bề mặt | đường tròn thật (khác lỗ khoan!) | ✔ |
| Xoắn ốc | đường **thẳng** — đó là lý do xoắn ốc cắt rất mượt | ✔ |
| Biên dạng tự do | chép nguyên xi từ tệp CSV/DXF | ✔ |
| Cắt đứt / cắt vát | ``u = x0 + tanα · (hình chiếu của điểm lên phương nghiêng)`` | ✔ |
| Miệng cá, lỗ xuyên | công thức giao hai mặt trụ | ✘ chỉ ống tròn |

Công thức cắt vát ở dạng tổng quát đúng cho mọi tiết diện: với ống tròn, hình
chiếu là ``R·cos(θ−roll)`` nên đường cắt trải phẳng là hình sin; với ống hộp, hình
chiếu tuyến tính theo toạ độ điểm nên đường cắt là **thẳng vuông góc trục trên mặt
trên/dưới và chéo trên hai mặt bên** - đúng như nhát cắt vát ống hộp làm bằng tay.

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

## 7b. Mô phỏng máy

`gsim.Playback` đọc chương trình G-code rồi trả lời câu hỏi *"tại giây thứ t,
bốn trục ở đâu"*:

* mỗi dòng thành một đoạn có thời điểm bắt đầu và thời lượng
  (`L/F` cho G1, `max(|Δᵢ|/tốc_độ_tối_đaᵢ)` cho G0, đúng cách Grbl phân bổ);
* vết cắt được ghi theo **toạ độ trên phôi** `(x, θ)`, không phải toạ độ thế
  giới — nhờ vậy vết cắt nằm yên trên mặt ống khi ống trượt và quay;
* mỗi lần mồi lại được đánh dấu `start=True` để không nối nhầm hai lượt cắt rời
  nhau bằng một nét thẳng vắt ngang ống.

Thời gian ước tính hiển thị trên giao diện lấy từ chính bộ diễn giải này, nên
con số ở tab Xem trước và thanh thời gian ở tab Mô phỏng luôn khớp nhau.

Khung vẽ 3D xử lý che khuất bằng cách tô đặc **bao lồi của hai vành đầu ống** —
với mặt trụ thì bao lồi chính là đường bao thật — rồi mới vẽ đè lên những chi
tiết nằm ở nửa mặt hướng về người xem (kiểm tra bằng `pháp_tuyến · hướng_nhìn > 0`).

Khi đang nối máy thật, khung mô phỏng không tự tích luỹ vết cắt từ các báo cáo
trạng thái (chỉ 5 lần/giây, vết sẽ rất thưa) mà **dóng vị trí máy báo về vào
chương trình đã biết**: tìm điểm gần nhất trên quỹ đạo, suy ra thời điểm, rồi
lấy đúng phần vết cắt tương ứng. Việc dò được giới hạn quanh vị trí đã khớp lần
trước nên đường chạy tự cắt nhau cũng không làm hình nhảy lung tung.

---

## 8. Nhập biên dạng từ tệp ngoài

### 8.1 Một cửa duy nhất

Mọi định dạng đều quy về cùng một thứ: danh sách **đường cong phẳng** `Curve2D`.
Sau đó `shapes.flat_pattern` cuốn chúng lên mặt phôi, và từ đó trở đi chúng đi
**đúng dây chuyền của biên dạng tự sinh**:

```
tệp ─► bộ đọc ─► Curve2D(u, v) ─► flat_pattern ─► Contour
                                                    │
        bù kerf ─► vào/ra dao ─► điều tiết điểm ─► chèn điểm gãy ─► làm mịn
        theo tiết diện ─► chiến lược góc ─► động học 4 trục ─► bù tốc độ ─► G-code
```

Nhờ tách bạch như vậy, thêm một định dạng mới chỉ cần viết một hàm trả về
`List[Curve2D]` — không đụng gì tới phần hình học hay động học.

### 8.2 DXF

Đọc thẳng theo cặp *mã nhóm – giá trị* của DXF ASCII, không cần thư viện ngoài.

Cung **bulge** trong `LWPOLYLINE` là chỗ hay bị làm sai nhất: `b = tan(θ/4)` với
`θ` là góc chắn cung. Từ hai đỉnh liên tiếp và `b`:

```
θ  = 4·atan(b)
d  = |P₁ − P₀| / 2
r  = d / sin(θ/2)
h  = d / tan(θ/2)          (khoảng cách từ trung điểm dây tới tâm)
```

`SPLINE` được tính bằng **thuật toán De Boor** trên đúng vector nút mà tệp khai
báo. Nối các điểm điều khiển lại làm đường gấp khúc là sai — chỉ với spline bậc 3
bốn điểm, sai lệch đã tới vài milimét.

`$INSUNITS` được đọc để tự quy về mm (1 = inch, 4 = mm, 5 = cm...).

### 8.3 SVG

Khác biệt so với bản vẽ cơ khí, đã xử lý sẵn:

* **Trục Y hướng xuống** → lật lại cho đúng chiều bản vẽ.
* **Đơn vị là "user unit"**. Nếu thẻ `svg` có `width` kèm đơn vị thật và có
  `viewBox` thì tỉ lệ suy ra chính xác từ hai số đó; không thì lấy 96 dpi.
* `transform` **lồng nhau** qua các nhóm `g` được nhân ma trận đúng thứ tự
  (translate, scale, rotate, matrix, skewX/skewY).
* `rect` có `rx`/`ry` là **bo góc ellipse**, kể cả khi chỉ khai một trong hai
  (chuẩn SVG quy định lấy cái còn lại) và khi khai lớn quá nửa cạnh (bị kẹp lại,
  hình thành ellipse).

### 8.4 G-code phẳng hai trục

Cửa ngõ để dùng **CAM bất kỳ**: vẽ trên mặt phẳng như cắt tôn tấm, xuất G-code
hai trục, phần mềm cuốn lên ống. Quy ước `X` là dọc phôi, `Y` là theo chu vi.

Điểm cần chú ý ở `G2/G3`:

* Kiểu **I/J**: tâm là *offset tương đối* so với điểm đầu, và khi điểm đầu trùng
  điểm cuối thì đó là **cả vòng tròn**, không phải cung 0°.
* Kiểu **R**: có hai tâm thoả mãn. Theo chuẩn, `R > 0` lấy cung **nhỏ** (≤180°),
  `R < 0` lấy cung **lớn**. Tâm chọn theo:

```
sign = +1 nếu (R > 0) trùng với chiều ngược kim đồng hồ, ngược lại −1
tâm  = trung_điểm ± sign · h · pháp_tuyến_đơn_vị,   h = √(R² − d²)
```

`G0` không được coi là đường cắt — nó **tách biên dạng**, đúng như ý đồ của CAM.

### 8.5 Mô hình 3D (STL/OBJ)

Mô hình đưa vào là **chi tiết đã cắt xong**. Bề mặt của nó gồm hai phần: phần
còn nằm trên mặt phôi gốc, và phần mặt cắt mới do dao tạo ra. **Đường cắt chính
là ranh giới giữa hai phần đó.**

Thuật toán không cần thư viện hình học nào:

1. **Khoảng cách có dấu** từ mỗi đỉnh tới biên tiết diện. Ống tròn thì đơn giản
   là `√(x²+y²) − R`. Hộp bo góc dùng công thức SDF chuẩn của hình chữ nhật bo góc:

   ```
   qx = |x| − (hx − rc),   qy = |y| − (hy − rc)
   d  = ‖(max(qx,0), max(qy,0))‖ + min(max(qx,qy), 0) − rc
   ```

   Một biểu thức lo trọn cả ba vùng: ngoài góc, ngoài cạnh, và bên trong.

2. **Tam giác "còn nguyên"** là tam giác có cả ba đỉnh cách mặt phôi không quá
   dung sai bề mặt.

3. **Cạnh biên** là cạnh chỉ thuộc **một** tam giác còn nguyên. Đỉnh được hàn
   theo lưới 0,05 mm trước khi so, nên lưới có bị tách đỉnh cũng không sao.

4. **Nối cạnh biên thành vòng**, rồi đổi mỗi đỉnh sang toạ độ trải phẳng `(u, v)`
   và **gỡ cuộn** `v` để đường cắt không nhảy một vòng chu vi ở mốc 0.

5. Đường nào có điểm đầu và điểm cuối lệch nhau **đúng một chu vi** thì đó là
   đường **quấn trọn vòng** (cắt đứt, vát đầu ống) — đánh dấu `wrap`, khác với
   vòng kín tại chỗ (lỗ, rãnh).

Cách này chịu được lưới thô hay mịn, và **kiểm chứng được**: dựng lưới của một
nhát cắt lượn sóng đã biết trước phương trình rồi cho thuật toán đọc lại, sai
lệch so với phương trình gốc **dưới 1e-6 mm** (xem `tests/test_import.py`).

#### Soát lại việc khai báo phôi

Khai sai tiết diện thì thuật toán vẫn chạy và vẫn ra đường cong — nhưng là đường
sai. Hai phép soát bắt được gần hết các nhầm lẫn thường gặp:

* **Vật liệu nằm hẳn ngoài mặt phôi khai báo** → phôi khai nhỏ hơn thực tế, hoặc
  mô hình đang tính theo inch.
* **Dải chu vi không chỗ nào bám được mặt phôi** (chia chu vi thành 180 ô, đếm ô
  trống) → sai hình dạng tiết diện, hay gặp nhất là quên khai bán kính bo góc
  của ống hộp.

Cả hai đều báo dưới dạng **cảnh báo** chứ không chặn, vì vẫn có trường hợp hợp lệ
(ví dụ một rãnh dài chạy hết thân ống làm trống hẳn một dải chu vi).

#### Vì sao không đọc STEP/IGES

STEP và IGES là **B-rep**: mô tả vật thể bằng các mặt tham số cắt xén lẫn nhau
(NURBS, mặt trụ, mặt xuyến) kèm cây tô-pô cạnh–vòng–mặt. Đọc được chúng nghĩa là
phải mang theo cả một nhân hình học cỡ OpenCASCADE — vài trăm MB, biên dịch nặng,
và vẫn phải giải giao tuyến mặt–mặt. Trong khi đó **mọi phần mềm CAD đều xuất
được STL**, và với sai số lưới 0,01–0,05 mm thì kết quả đủ chính xác hơn hẳn dung
sai của chính máy cắt.

### 8.6 Truyền qua mạng LAN

FluidNC mở sẵn máy chủ **Telnet** ở cổng 23, dùng đúng dòng lệnh và đúng giao
thức `ok`/`error` như cổng nối tiếp. Nhờ vậy `TcpTransport` chỉ cần thay chỗ đọc
ghi byte, còn toàn bộ phần đếm ký tự, phân tích trạng thái và lệnh thời gian thực
giữ nguyên không đổi.

Hai chi tiết phải xử lý:

* **Lệnh thương lượng Telnet (IAC)** — máy chủ có thể gửi các chuỗi bắt đầu bằng
  byte `0xFF`. Phải lọc bỏ, nếu không chúng lẫn vào dòng phản hồi.
* **Gói tin bị chia nhỏ** — TCP không giữ ranh giới dòng, nên phải gom đệm rồi
  mới tách theo `\n`, y như với cổng nối tiếp.

Việc dò máy trong mạng LAN quét cả dải `/24` của địa chỉ máy tính, mỗi địa chỉ
mở kết nối thử với thời gian chờ rất ngắn, chạy song song nhiều luồng.

> **Độ tin cậy.** WiFi rất tiện cho việc nạp chương trình và theo dõi, nhưng
> xưởng cắt là môi trường nhiễu nặng. Mất sóng giữa nhát cắt là hỏng phôi — nên
> dùng WiFi cho khâu chuẩn bị, cắm dây cho khâu cắt.

---

## 9. Hạn chế đã biết

* **Chỉ xuất G1/G0**, không dùng cung tròn G2/G3. Cung tròn không biểu diễn được
  đường giao tuyến ống trong không gian 4 trục, và với dung sai dây cung đã dùng
  thì lợi ích gần như không có.
* **Không mô hình hoá gia tốc** khi ước tính thời gian — con số hiển thị là cận
  dưới, thực tế lâu hơn 10–30% tuỳ số đoạn ngắn.
* **Máy ảo và mô phỏng đều không mô hình hoá gia tốc**, chỉ chạy đều theo F.
  Dùng để kiểm tra hình học, thứ tự nguyên công và va chạm — không dùng để chốt
  thời gian sản xuất.
* **Trục vát 4 trục không cắt được mặt vát chuẩn ở mọi điểm** của biên dạng phức
  tạp — đó là giới hạn động học, muốn đúng tuyệt đối cần máy 5 trục. Phần mềm cho
  góc tối ưu trong khả năng của bốn trục.
* **Không có điều khiển chiều cao tự động (THC)** — phần mềm đặt Z theo giá trị
  cố định. Nếu phôi cong hoặc ô van nhiều, nên dùng THC phần cứng.
* **Ống hộp không cắt được biên dạng miệng cá và lỗ xuyên** - hai bài toán này
  là giao của hai mặt trụ nên chỉ có nghĩa với ống tròn. Với ống hộp hãy dùng
  rãnh, tròn trên bề mặt hoặc biên dạng trải phẳng.
* **Góc nhọn tuyệt đối (bán kính góc lượn = 0) không cắt được**: pháp tuyến đổi
  hướng đột ngột 90°, máy phải xoay tại chỗ. Ống hộp thật luôn có góc lượn nên
  phần mềm mặc định lấy 2 lần chiều dày thành.
* **Bù kerf cho biên dạng tự cắt nhau nhiều lần** (biên dạng rất phức tạp, kerf
  lớn) có thể còn sót vòng lặp; hãy xem kỹ bản xem trước trước khi cắt.
* **Không đọc được STEP/IGES** — xem mục 8.5 để biết vì sao và cách thay thế.
* **DXF chỉ đọc bản ASCII**, không đọc DXF nhị phân. Mọi phần mềm CAD đều xuất
  được DXF ASCII (thường là lựa chọn mặc định).
* **Không đọc chữ (TEXT/MTEXT) trong DXF và SVG** — chữ phải được chuyển thành
  đường nét (*convert to path* / *explode text*) trước khi xuất.
* **Nhập mô hình 3D cần khai đúng tiết diện phôi** — phần mềm cảnh báo khi thấy
  không khớp, nhưng không tự suy ra kích thước phôi thay người dùng.
* **Kết nối WiFi không có cơ chế nối lại giữa chừng**: mất kết nối là chương
  trình dừng. Đây là lựa chọn có chủ ý — nối lại rồi chạy tiếp một nhát cắt dở
  còn nguy hiểm hơn là dừng hẳn.
