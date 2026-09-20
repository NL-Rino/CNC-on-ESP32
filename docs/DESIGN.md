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

## 3. Bộ dò hộc sạc (`sim/dock_detector.py` ⇄ `firmware/dock_detect.c`)

Trạm sạc là cái **hộc chữ U**: ngoài 40×40 cm, lòng trong 31×31 cm, vách dày
4.5 cm, đèn hồng ngoại giữa thành trong. Xe 30×30 cm chui vừa khít.

1. Vá lại điểm mất lẻ loi.
2. **Cắt vòng quét thành đoạn.** Ngưỡng cắt phải **lớn hơn** độ sâu lòng hộc
   (35.5 cm) — nếu không chính cái hộc sẽ bị cắt làm đôi. Dùng `45 cm + 20%`.
3. **Nối hai đầu đoạn thành dây cung, đo độ lõm.** Hộc lõm vào 35 cm sau dây
   cung; vật đặc thì mọi điểm **lồi ra trước** dây cung. Đó là dấu hiệu phân biệt.
4. **Co dây cung vào cho hết lồi.** Nhìn chéo, cái hộc in bóng thành chữ L: mặt
   ngoài của vách bên lồi hẳn ra trước dây cung nối hai đầu đoạn. Cứ cắt dần đầu
   nào gần chỗ lồi nhất, dây cung sẽ tự lùi về đúng hai mép cửa.
5. **Trục hộc lấy từ mặt thành trong**, không lấy từ dây cung.

Bước 5 là bước quan trọng nhất và cũng là thứ hộp đặc 15 cm ngày trước **không
thể cho được**. Dây cung chỉ có hai điểm đầu, mỗi điểm nhiễu ±2 cm, nên ở cự ly
0.4 m nó cho trục lệch tới 40°. Thành trong thì phẳng và có hàng chục điểm: khớp
một đường thẳng qua chúng cho **trung vị 2°**.

| | dây cung | khớp thành trong |
|---|---|---|
| trục lệch trung vị | 8.4° | **2.0°** |
| 90% dưới | 37.8° | **15.8°** |

Tỉ lệ tìm ra hộc (ở khoảng ±20° quanh trục): **99–100%** trong 0.5 m, 92% ở
0.8 m, 71% ở 1.2 m. Sai số khoảng cách ~3 cm.

Ứng viên được xếp theo **khoảng cách**, không theo điểm giống nhau — vì hộc mồi
nhử cho điểm y hệt trạm thật. Phân biệt là việc của hồng ngoại.

### Một phát hiện chỉ lộ ra khi đo thật

Tia LiDAR quét qua cửa hộc **không** nhảy một phát từ mép vào thành trong. Nó
trượt dọc mặt trong của vách bên, nên khoảng cách lên dần thành bậc thang:

```
0.82 → 0.82 → 0.89 → 1.07 → 1.16 → 1.16 …   (đo ở cự ly 0.8 m)
      mép cửa    mặt trong vách    thành trong
```

Bản đầu tiên tôi viết theo kiểu "tìm mép rồi ghép cặp mở–đóng" — nghe rất hợp lý,
và chỉ đạt **27%**. Mỗi bậc thang đều vượt ngưỡng mép nên nó đẻ ra 3–4 cái "mép"
chồng nhau, và cái nào cũng lệch vào trong. Chuyển sang cắt đoạn rồi đo độ lõm:
**84%**. Bài học: đừng đoán vòng quét trông thế nào, in nó ra mà nhìn.

## 4. Bắt tay hồng ngoại

Đèn hồng ngoại nằm giữa **thành trong** của hộc, chiếu thẳng ra cửa. Chùm phát
của LED là ±40°, nhưng **chính hai vách bên bóp nó lại còn ~±24°** — đây là hình
học tự nhiên, không phải con số tôi đặt ra: mô phỏng dựng đường ngắm qua đúng ba
cái vách đó. Kết quả đo: đứng lệch 20° vẫn thấy, lệch 45° là mất hẳn.

Nghĩa là xe phải **vòng ra đối diện cửa hộc** mới hỏi được hồng ngoại — đúng quy
trình "thấy hình thì quay lại hỏi", nhưng bây giờ nó là hệ quả của hình học chứ
không phải một luật tôi viết tay vào.

`Robot.try_charge()` chỉ nạp điện khi:
- cách **tâm hộc** dưới 10 cm (tức là đã chui hẳn vào trong),
- lệch hướng dưới 17°,
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

## 6. Đầu vào/đầu ra của bộ não (46 → 2)

```
 0..11  12 quạt LiDAR (chia 3.0 m)          12,13  vực trước, vực sau
14..25  2 ứng viên hộc, mỗi cái 6 số:
        [thấy, sin/cos góc tới cửa, khoảng cách, sin/cos GÓC TRỤC hộc]
26..31  hồng ngoại: gọi, thấy_gọi, sạc, thấy_sạc, Δgọi, Δsạc
32..37  trí nhớ trạm: [có, sin/cos góc, khoảng cách, sin/cos HƯỚNG TRỤC]
38..40  pin, pin_yếu, BIÊN AN TOÀN
41..45  vận tốc, tốc độ quay, ga trái/phải bước trước, va chạm
```

Hai chỗ in hoa là phần mới so với bản hộp đặc. Hộc chỉ chui vào được từ **một
phía**, nên biết nó ở đâu mà không biết nó quay về đâu thì về tới nơi vẫn phải
dò lại từ đầu.

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

**(f) Khe 31 cm cho xe Ø30 cm là bất khả thi nếu không vát mép.** Thân tròn bỏ
được ràng buộc góc (xe vuông cùng cỡ nghiêng 2° đã cần khe 31.0 cm), nhưng vẫn
phải đúng trục trong **±5 mm**. Mà LiDAR ở cự ly cắm cho trục chính xác ~2°, và
2° trên quãng tiếp cận 40 cm là 1.4 cm lệch ngang — **đo tốt hết mức vẫn không đủ**.

Cách sửa là cách mọi đế sạc thật đều dùng: **vát hai góc trong ở miệng**. Đo với
nhiễu trượt bánh tắt: thẳng tuột **±2 mm**, vát 8 cm **±38 mm**, vát 12 cm ±42 mm.
8 cm đã gần kịch trần hình học (lòng miệng 18.5 − bán kính xe 15 = 3.5 cm).

Một cái bẫy trong chính mô hình này: lần đầu tôi cho cái "nêm" nắn xe ở **mọi**
chỗ chạm vách hộc. Kết quả là hộc thẳng tuột cũng bắt được xe lệch 6 cm — vô lý,
vì vách song song với trục thì chặn được xe đi ngang chứ không đẩy được xe sang
bên. Nêm chỉ tồn tại ở đoạn vát. Nó còn biến thành nam châm: xe húc vào **sườn**
hộc cũng bị kéo về trục, tức là đi xuyên qua vách, và lỡ đâm vào hộc mồi nhử thì
bị hút hẳn vào trong rồi kẹt cứng — đó là lý do stage 2 từng rơi bàn 88%.

Bài học: một "mô hình tuân thủ" viết ẩu sẽ âm thầm làm bài toán dễ đi, và bạn chỉ
phát hiện khi ra phần cứng thật. Đặt `BAY_FLARE = 0.0` để xem lại hộc thẳng tuột.

**(g) Rơi khỏi bàn rẻ hơn phần thưởng về sạc.** Phạt rơi −40, trong khi đi 2 m
về phía trạm đã được +28 và giải sạc tới +120. Lao về trạm rồi rơi xuống đất gần
như hoà vốn — và xe học đúng cái đó: stage 2 rơi bàn 65%, trong đó **14/20 lần là
đang lúc pin yếu**, tức đúng lúc phần thưởng đang kéo nó đi. Nâng lên −150, tức
lớn hơn mọi thứ kiếm được trong một tập cộng lại.

**(h) Sửa xong (g) thì xe học cách chết rẻ hơn.** Rơi −150 nhưng hết pin chỉ −60,
nên nó **đứng quay tại chỗ cho hết pin**: rơi 0–5%, hết pin 85–100%, mỗi tập chỉ
đi qua 3 ô lưới. Hai cái chết đều là chết, giá phải bằng nhau → `w_flat` cũng −150.
Kèm theo đó phát hiện phạt quay-tại-chỗ đang **tắt khi có mục tiêu**, mà pin yếu
thì lúc nào cũng có mục tiêu — thành ra xe được quay vòng vòng miễn phí đúng lúc
nó cần đi nhất.

**(i) Miễn phạt va chạm quá rộng thành kẽ hở.** Khe hộc chỉ hở 5 mm mỗi bên nên
xát vách lúc chui vào là đương nhiên, phạt thì xe sẽ học cách không bao giờ vào
sạc. Nhưng tôi miễn cho **mọi** va chạm với vách hộc, kể cả khi xe tì vào *sườn*
hộc. Xe tìm ra ngay: nó nằm lì vào vách **41% số bước**. Giờ chỉ miễn khi xe thật
sự nằm trong lối vào và đang hướng vào trong (`World.in_bay_corridor`). Kiểm chứng
bằng cách tách số va chạm làm hai loại: bộ luật viết tay xát hành lang 611 lần và
húc vật cản thật 2441 lần trên 20 tập — tức định nghĩa hành lang đúng cỡ.

**(j) Đặt trạm sạc sát mép bàn là phá chính manh mối của xe.** LiDAR quét ngang
nên **không thấy mép bàn**; xe chỉ có thể đoán mép qua "quạt này trống trơn".
Đặt một khối 40 cm ngay tại mép là làm hỏng đúng cái manh mối đó. Đo: chính sách
đạt 4% rơi ở stage 1 tụt xuống **70% rơi** ở stage 2 **ngay cả khi ghim pin đầy**
(tức là loại hẳn phần thưởng về sạc ra khỏi phương trình) — nên thủ phạm là cái
hộc chứ không phải phần thưởng. Đã lùi hộc vào 25 cm khỏi mép.

Cách đo đáng nhớ hơn cả kết luận: muốn biết A hay B gây ra lỗi thì **tắt hẳn B
đi rồi đo lại**, đừng ngồi suy luận. Tôi đã đoán sai thủ phạm hai lần liền trước
khi làm phép thử ghim-pin-đầy này.

**(k) `best.npz` không dùng để chạy tiếp được.** Nó chỉ được ghi khi điểm đánh
giá phá kỷ lục, nên đến thế hệ 6000 mà kỷ lục lập từ 1744 thì nó vẫn ghi
`gen=1744`. Người dùng `--resume` từ đó và mất sạch phần giữa. Giờ có `state.npz`
ghi **mọi thế hệ, không điều kiện**, chứa cả sigma, động lượng Adam và bộ sinh
số ngẫu nhiên — nạp lại thì thế hệ tiếp theo sinh ra trùng khít.

Bài học: một file tên là "tốt nhất" không phải là "mới nhất", và trộn hai khái
niệm đó vào một file là cách chắc chắn để mất việc của người khác.

**(l) Một phiên 5.900 thế hệ tự huỷ, vì hai lỗi trong chính bộ tiến hoá.** Chạy
tới thế hệ 7578 rồi mở ra xem: bộ não trả về **đúng `(+1.0, +1.0)` với mọi đầu
vào, độ lệch 0.0000** — tanh bão hoà hoàn toàn. `|theta|` trung bình phình từ
1,5 lên 2,2, đỉnh 10,1. Dấu hiệu trong log lẽ ra phải thấy từ sớm:
`fit -149.0 (max -149.0)` — cả 48 cá thể **điểm giống hệt nhau**, vì khi tanh
đã dính trần thì đổi trọng số không đổi hành vi.

Hai nguyên nhân, cả hai đều là lỗi của tôi:

1. **Weight decay cộng thẳng vào gradient.** Adam chuẩn hoá gradient nên nó
   chuẩn hoá luôn cả số hạng ghìm — đúng lúc cần ghìm nhất thì ghìm không nổi.
   Đây chính là lý do AdamW tồn tại. Đã tách rời: `theta *= 1 - lr*wd` sau
   bước Adam. Thử: dưới sức ép giảm, `|theta|` 3,0 → 0,08.
2. **Điểm bằng nhau vẫn sinh ra gradient.** `argsort` của một dãy bằng nhau
   trả về đúng thứ tự chỉ số, nên cá thể chỉ số chẵn luôn "thắng" cá thể lẻ —
   ES nhận một gradient **có hệ thống từ hư không** và đi lang thang. Giờ dải
   điểm ~0 thì trả về vector 0.

Điều đẹp là hai bản sửa ghép lại thành cơ chế tự thoát: bão hoà → điểm bằng
nhau → gradient 0 → weight decay kéo trọng số xuống → hết bão hoà → điểm lại
phân hoá. Kèm theo đó là dòng cảnh báo trong log, để lần sau không ai đốt
hàng nghìn thế hệ mà không biết gì.

**(m) Ba lỗi cảm biến chỉ lộ ra khi đổi sang căn nhà lớn.** Mặt bàn 3 m che
được chúng; căn nhà 10 m thì không.

1. **Ba mắt hồng ngoại lắp ngược.** `IR_MAT[0] = -1.15` là mắt bên *phải*
   nhưng tôi đặt tên nó là `L`, nên công thức `(L-R)` đảo dấu và xe **lái ra
   xa đèn**. Đo được: xe săn đèn 400 bước liền mà chưa bao giờ tới gần hơn
   1,8 m. Một dấu trừ.
2. **Mô hình suy giảm hồng ngoại quá gắt.** `1/(1+(d/0.9)²)` cho cường độ
   0,048 ở 4 m — dưới cả ngưỡng "có thấy" 0,05. Khai báo tầm 6 m nhưng thực
   tế 3,5 m; xe đi ngang cách đèn 3 m vẫn không thấy gì. Đổi mẫu số sang 2,5:
   tỉ lệ nhìn thấy 0,3% → 10% số bước.
3. **Con quay chưa hiệu chuẩn.** 0,010 rad/s = 0,57°/s, nghe nhỏ, nhưng
   chuyến đi 150 giây thì lệch **86°** — trí nhớ vị trí trạm sai tới 2,7 m và
   xe không còn tìm được đường về. Đổi sang 0,0015 rad/s (0,086°/s), là mức
   của MPU6050 **đã hiệu chuẩn**. Với nhà to và chuyến đi 5 phút thì hiệu
   chuẩn con quay là bắt buộc, không phải tuỳ chọn.

Điểm chung của cả ba: chúng đều "chạy được" trên mặt bàn nhỏ. Sai số tuyến
tính theo thời gian và khoảng cách thì chỉ lộ ra khi cho nó thời gian và
khoảng cách.

**(n) Một mắt hồng ngoại không cho biết hướng.** Đây không phải lỗi mà là
giới hạn vật lý tôi đã bỏ qua: với một mắt, xe chỉ biết "có thấy đèn", nên
cách duy nhất là đi thẳng rồi hy vọng. Đo: tới được 0,2/5 đèn. Ba mắt đặt ở
−66°, 0°, +66° thì tỉ lệ cường độ giữa chúng cho ra góc — đúng cách robot hút
bụi thật dò hướng về trạm. Cái giá là vector quan sát 46 → 50 số.

Bài học chung: khi agent **không** học được một kỹ năng, đừng tăng số thế hệ. Hãy
đo xem nó thật sự đi tới đâu và dừng lại ở đâu — gần như lần nào nguyên nhân cũng
là hai khoản thưởng đang kéo ngược nhau.

## 10b. Tốc độ mô phỏng: chỗ nghẽn không nằm ở chỗ tôi tưởng

Mô phỏng từng chạy **628 µs/bước**. Tôi đoán chỗ nghẽn là phép bắn tia LiDAR
nên định chuyển nó sang numpy/GPU. Đo ra thì thủ phạm là `dist_to_point`:
**342 nghìn lần gọi cho 6.400 bước** — vòng lặp Python qua ~30 vật cản, gọi
2,4 lần mỗi bước từ hàm tính va chạm.

Thử numpy hoá hàm đó: **chậm hơn gấp đôi** (12,2 µs so với 6,7 µs). Với vài
chục vật cản thì chi phí gọi numpy lớn hơn chính phép tính. Cái ăn tiền lại là
thứ tầm thường hơn nhiều: duyệt trên tuple đã rút sẵn thay vì thuộc tính đối
tượng, và bỏ `builtin max()` (620 nghìn lần gọi) đổi thành lệnh rẽ nhánh.

Kết quả **628 → 150 µs/bước, nhanh gấp 4,2 lần**, đối chiếu 5000 điểm với bản
cũ lệch tối đa 2e-16. Một thế hệ huấn luyện từ 8–10 giây xuống 4,5 giây.

Bài học: đo trước khi tối ưu, và đo lại sau khi tối ưu — cả hai lần tôi đều
đoán sai.

## 11. Từ mô phỏng ra đời thật

1. `v_max`, `motor_tau`, `deadband` — đo bằng cách cho xe chạy 1 m và quay video.
   **Quãng đường phanh phải nhỏ hơn khoảng cách từ tâm xe tới cảm biến vực**
   (mô phỏng: ~5.5 cm phanh so với 14.5 cm cảm biến).
5. **Cửa sổ bắt ở miệng hộc**: đẩy xe vào từ nhiều độ lệch ngang khác nhau, đo
   xem lệch tới đâu thì vẫn vào lọt. Mô phỏng nói ±38 mm với đoạn vát 8 cm.
2. Chu kỳ gom một vòng LiDAR thật (phụ thuộc tốc độ quay thật, 5–8 Hz).
3. Ngưỡng cảm biến vực thực tế và độ trễ của nó.
4. Đặc tuyến cường độ IR thật: bịt đèn lại, đo giá trị theo góc và khoảng cách.
5. Đường cong xả pin thật (Li-ion không tuyến tính).

Mẹo: giữ **nhiễu trong mô phỏng hơi lớn hơn đời thật**. Bộ não quen sống trong môi
trường "bẩn" sẽ chịu được môi trường sạch, chiều ngược lại thì không.
