# Thiết kế mô phỏng & huấn luyện

## 1. Vì sao mô phỏng trước

Xe thật chạy một tập 65 giây; một thế hệ ES cần ~200 tập. Trên máy này một tập
mất ~0.28 s, tức **một thế hệ ~14 giây trên 4 nhân**. Làm trên xe thật thì mỗi
thế hệ mất 3.6 giờ — và mỗi lần rơi khỏi bàn là một lần gãy xe. Mô phỏng không
phải để cho vui: nó là cách duy nhất để thuật toán tiến hoá này chạy được.

## 2. LiDAR Camsense (`sim/lidar.py`)

Theo datasheet: 3000 điểm/giây, quay 5–8 Hz, tầm 0.12–8 m.

| Chi tiết mô phỏng | Giá trị | Vì sao quan trọng |
|---|---|---|
| Điểm mỗi vòng | 3000 / scan_hz ≈ **430–600** | ở 7 Hz là 0.8°/điểm → hộp 15 cm ở 1 m chỉ chiếm ~9 điểm, ở 2 m chỉ còn 4 điểm |
| Chu kỳ quét | 143 ms ở 7 Hz | vòng điều khiển chạy 20 Hz nên **mỗi vòng quét được dùng cho ~3 bước**, dữ liệu luôn cũ |
| Bù góc | xoay theo odometry | xe quay tới 8 rad/s; không bù thì vòng quét cũ chỉ sai hướng tới 69° |
| Nhiễu | 1 cm + 1.2% khoảng cách | |
| Rung góc | 0.23° | |
| Điểm mất | 2% | bề mặt đen, gương, góc tới xiên |

Mỗi lần đủ một vòng thì bắn trọn 430–600 tia trong **một lệnh numpy** (136 µs).
Mảng được bố trí `[số_vật_cản, số_tia]` chứ không phải ngược lại — rút gọn theo
trục 0 nhanh hơn **12 lần** vì dữ liệu nằm liền nhau trong bộ nhớ.

Vào mạng nơ-ron thì 460 điểm được nén thành **12 quạt** (mỗi quạt 30°, lấy giá
trị gần nhất). Phần tinh vi để cho bộ dò hình lo.

**LiDAR không thấy mép bàn.** Tia quét ngang đi thẳng ra ngoài và không có gì
dội về — đúng như ngoài đời. Chỉ hai cảm biến chiếu xuống cứu được xe.

## 3. Bộ dò hình trạm sạc (`sim/dock_detector.py` ⇄ `firmware/dock_detect.c`)

1. Vá lại điểm mất lẻ loi (2% điểm mất cũng đủ cắt vụn hộp 15 cm thành mảnh quá ngắn).
2. Cắt vòng quét thành đoạn: hai điểm kề nhau lệch quá `3.5 cm + 5%` thì thuộc hai vật khác nhau.
3. Giữ đoạn **rộng 10–25 cm** (hộp 15 cm nhìn chéo thấy 2 mặt, rộng tới 21 cm),
   **phẳng** (độ cong ≤ 8.5 cm — góc hộp nhìn chéo nhô ra tối đa 7.5 cm) và **gần hơn 3 m**.

Tỉ lệ tìm ra trạm: ~82% ở 0.4 m, 80% ở 0.6 m, 55% ở 1 m, 39% ở 1.6 m. Nghe thấp
nhưng xe nhận vòng quét mới 7 lần mỗi giây, nên chỉ cần vài giây là gần như chắc chắn thấy.

Ứng viên được xếp theo **khoảng cách**, không theo điểm giống nhau — vì hộp mồi
nhử và góc bàn cho điểm y hệt trạm thật. Phân biệt là việc của hồng ngoại.

## 4. Bắt tay hồng ngoại

Trạm sạc phát hồng ngoại **có hướng** (nửa góc 54°) từ mặt trước. Mắt thu của xe
ở đầu xe, nửa góc 46°. Nghĩa là muốn bắt được tín hiệu thì xe phải **vừa đứng
đúng phía trước trạm, vừa quay đầu về phía trạm** — đúng quy trình "thấy hình thì
quay đầu lại hỏi".

`Robot.try_charge()` chỉ nạp điện khi:
- cách **ổ đậu** (trên trục trạm, cách tâm hộp 20 cm) dưới 11 cm,
- lệch hướng dưới 40°,
- gần như đứng yên (|v| < 0.10 m/s),
- **và** còn nhớ tín hiệu hồng ngoại trong 30 bước gần nhất (1.5 giây).

Điều kiện cuối là bắt tay thật: trạm sạc thật cũng không đóng điện khi chưa nhận
đúng mã.

## 5. Trí nhớ và "kinh nghiệm"

Xe không có bản đồ. Nó giữ 3 con số, tất cả đều dựng được trên phần cứng thật:

- **Vị trí trạm theo odometry**: mỗi lần hồng ngoại xác nhận (hoặc vừa cắm sạc),
  ghi lại điểm đó trong hệ toạ độ odometry của chính xe. Odometry có sai số đường
  kính bánh 2.5% và trôi góc 0.01 rad/s → trí nhớ mờ dần, gặp lại đèn thì làm mới.
- **Hao pin mỗi mét** `e_per_m`: lọc trung bình trượt của (pin đã tụt / quãng đường đã đi).
- **Biên an toàn** = `pin − (e_per_m × quãng_đường_về × 1.5 + 0.06)`, kẹp về [−1, 1].

Biên an toàn là một đầu vào của mạng. Âm nghĩa là "về ngay không thì chết giữa đường".

## 6. Đầu vào/đầu ra của bộ não (40 → 2)

```
 0..11  12 quạt LiDAR (chia 3.0 m)          12,13  vực trước, vực sau
14..21  2 ứng viên hộp 15 cm: [thấy, sin, cos, khoảng cách]
22..27  hồng ngoại: gọi, thấy_gọi, sạc, thấy_sạc, Δgọi, Δsạc
28..31  trí nhớ vị trí trạm: [có, sin, cos, khoảng cách]
32..34  pin, pin_yếu, BIÊN AN TOÀN
35..39  vận tốc, tốc độ quay, ga trái/phải bước trước, va chạm
```

Ra: `tanh` → `(ga_trái, ga_phải)`. Bộ não **chỉ** nhìn thấy từng này. Thông tin
toàn tri (vị trí thật của trạm, của đèn gọi) chỉ dùng trong **phần thưởng**.

## 7. Phần thưởng (`sim/env.py`, lớp `EnvConfig`)

| Khoản | Hệ số | Ý nghĩa |
|---|---|---|
| `w_fall` / `w_flat` | −40 / −25 | rơi khỏi bàn / hết pin, kết thúc tập |
| `w_bump` / `w_cliff` | −1.5 / −0.8 mỗi bước | chạm vật cản / cảm biến vực kêu mà vẫn tiến tới |
| `w_progress` | +14/m | tiến gần mục tiêu đang hoạt động |
| `w_arrive` | +40 | vào trong 0.25 m của đèn gọi |
| `w_dock` / `w_charge` / `w_full` | +15 / +150·ΔPin / +25 | cắm được / lượng pin nạp / **sạc đầy** |
| `w_align` | +0.35/bước | đã gần ổ đậu và quay đúng hướng, có thưởng riêng cho việc dừng lại |
| `w_speed` / `w_novel` | +0.6·v / +6 mỗi ô lưới mới | đi long nhong: nhanh và **đi chỗ mới** |
| `w_spin`, `w_energy`, `w_smooth` | −0.25, −0.008, −0.04 | quay tại chỗ, hao điện, giật ga |

Pin yếu thì trạm sạc được **ưu tiên hơn đèn gọi** — đừng chết giữa đường vì ham đi chơi.
Sạc đầy xong thì lưới "đã đi qua" được xoá: bắt đầu vòng tuần tra mới.

## 8. Học bắt chước trước, tiến hoá sau

Bộ não có 1.934 tham số. ES mò từ đầu mất hàng trăm thế hệ chỉ để tìm ra phản xạ
"thấy vực thì lùi" — đã đo: sau 100 thế hệ vẫn rơi 25–50% số tập.

Nhưng ta **đã có** một bộ luật chạy được (`train/baseline.py`). Nên:

1. `train/imitate.py` cho mạng học theo bộ luật đó. Mục tiêu dày đặc (mỗi bước
   đều có đáp án) và **không phải chạy mô phỏng lại** — chỉ chạy mạng trên tập dữ
   liệu đã ghi, 16 tập song song bằng phép nhân ma trận. ~1 giây/thế hệ.
2. Rồi `train/train.py` tiến hoá tiếp từ đó, lúc này mới dùng phần thưởng thật.

Giáo viên phải **tất định** (`deterministic=True`): nếu cùng một tình huống mà lúc
thì queo trái lúc thì queo phải thì học sinh chỉ học được trung bình của hai cái
đó — tức là đi thẳng vào vật cản.

## 9. Vì sao Evolution Strategies chứ không phải PPO

1. Phần thưởng thưa và có nhớ (POMDP): GRU + ES không cần lan truyền ngược qua
   thời gian, ít chỗ sai hơn nhiều.
2. 4 nhân CPU, không GPU: ES song song gần như tuyến tính, mỗi worker chỉ gửi về
   **một số**.
3. Bộ não ~2k tham số — đúng ngay vùng ES mạnh nhất.

Chi tiết: lấy mẫu đối xứng (`+εσ`, `−εσ`), chuẩn hoá theo **thứ hạng**, Adam +
weight decay, và **dùng chung seed cho cả quần thể trong mỗi thế hệ** — nếu không,
ES chỉ đang so sánh độ may của từng tập chứ không phải độ giỏi.

## 10. Nhật ký nuôi: những lỗi khiến xe không học được

Đều là lỗi *thiết kế phần thưởng / môi trường*, không phải lỗi thuật toán — và
đều sẽ lặp lại y hệt trên phần cứng thật.

**(a) Bộ điều khiển viết tay rung tại chỗ.** Nhiễu cảm biến làm nó đổi hướng queo
mỗi 50 ms nên xe đứng một chỗ lắc qua lắc lại. Sửa bằng cách **cam kết** một hướng
trong ~0.5 giây. Mạng GRU tự giải quyết việc này bằng trạng thái ẩn, nhưng firmware
viết tay thì phải có hysteresis.

**(b) Bắt xe lùi vào trạm sạc.** Ban đầu hướng cắm quay vào trong bàn, tức xe phải
lùi vào ổ — trong khi mắt thu hồng ngoại nằm ở **đầu** xe. Xe cắm trong trạng thái
mù hoàn toàn. Đổi thành đâm đầu vào.

**(c) Đích sạc đặt đúng vào toạ độ trạm.** Khó thấy nhất. Trạm cách mép bàn 9 cm,
nên phần thưởng "tiến gần trạm" kéo xe ra tận mép — cảm biến vực kêu, phản xạ tránh
vực (đã học ở cấp 0) đẩy xe ra, hai thứ triệt tiêu nhau. Đo đạc cho thấy xe **đến
cách trạm 1–2 cm** nhưng góc lệch 70–150°. Sửa: đích là **ổ đậu** cách tâm trạm
20 cm về phía trong bàn, cộng một điểm tiếp cận cách 55 cm để xe vào thẳng trục.

**(d) Tập quá ngắn nên pin không quan trọng.** Với tập 45 giây và pin bắt đầu
0.2–0.9, hầu hết tập kết thúc khi pin vẫn còn — xe không có lý do gì để học đi sạc.
Sửa: tập dài 65 giây, tăng tốc độ hao pin, một nửa số tập bắt đầu với pin yếu sẵn.

**(e) Đổi sang LiDAR làm mạng phình ra.** 16 quạt + 3 ứng viên = 48 đầu vào →
3.154 tham số, ES học chậm hẳn. Nén còn 12 quạt + 2 ứng viên = 40 đầu vào →
1.934 tham số. Bài học: với ES, mỗi đầu vào thừa đều phải trả giá bằng thế hệ.

Bài học chung: khi agent **không** học được một kỹ năng, đừng tăng số thế hệ. Hãy
đo xem nó thật sự đi tới đâu và dừng lại ở đâu — gần như lần nào nguyên nhân cũng
là hai khoản thưởng đang kéo ngược nhau.

## 11. Từ mô phỏng ra đời thật

1. `v_max`, `motor_tau`, `deadband` — đo bằng cách cho xe chạy 1 m và quay video.
   **Quãng đường phanh phải nhỏ hơn khoảng cách từ tâm xe tới cảm biến vực**
   (mô phỏng: ~6.5 cm phanh so với 10.5 cm cảm biến).
2. Chu kỳ gom một vòng LiDAR thật (phụ thuộc tốc độ quay thật, 5–8 Hz).
3. Ngưỡng cảm biến vực thực tế và độ trễ của nó.
4. Đặc tuyến cường độ IR thật: bịt đèn lại, đo giá trị theo góc và khoảng cách.
5. Đường cong xả pin thật (Li-ion không tuyến tính).

Mẹo: giữ **nhiễu trong mô phỏng hơi lớn hơn đời thật**. Bộ não quen sống trong môi
trường "bẩn" sẽ chịu được môi trường sạch, chiều ngược lại thì không.
