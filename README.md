# Xe tự hành 2 bánh — nuôi AI trong mô phỏng trước, phần cứng sau

Mục tiêu: nuôi một bộ não biết **chạy long nhong không rơi khỏi bàn**, **đi tới chỗ
có đèn hồng ngoại gọi**, và **tự tính xem còn đủ pin để về trạm sạc hay chưa** —
huấn luyện hoàn toàn trong mô phỏng, sau đó nạp xuống ESP32.

Chạy bằng Python 3 + numpy, không cần GPU, không cần thư viện RL nào.

```bash
pip install numpy
python3 tests/test_sim.py                                  # kiểm tra mô phỏng
python3 tests/test_firmware.py                             # bản C khớp bản Python
python3 tools/compare.py brains/car_bay_v1.npz              # AI vs bộ điều khiển viết tay
python3 -m train.evaluate --policy brains/car_bay_v1.npz --ascii --seed 7
```

## Trạng thái hiện tại (đọc cái này trước)

Phần **mô phỏng + nhận thức đã xong và đã kiểm chứng**: LiDAR, bộ dò hộc chữ U
(cho ra cả trục), bắt tay hồng ngoại qua khe hẹp, va chạm thân vuông, trí nhớ vị
trí + hướng trạm, ước lượng pin — chạy được, có 20 kiểm thử, và bản C cho ESP32
đã đối chiếu **trùng khít** bản Python trên 25 cảnh.

Phần **bộ não thì đang nuôi dở**. So trên 30 cảnh ngẫu nhiên, cùng seed:

| | AI đang nuôi | Bộ luật viết tay |
|---|---:|---:|
| Điểm | −58 | **171** |
| Rơi khỏi bàn | 53% | **0%** |
| Chết vì hết pin | 13% | **10%** |
| Pin tự nạp được / tập | 0.000 | **0.417** |
| Lần tự sạc đầy / tập | 0.00 | **0.40** |
| Ô lưới đã đi qua | **7.5** | 5.4 |

Nói thẳng: **bộ não hiện chưa dùng được** — nó rơi khỏi bàn hơn nửa số tập. Bộ
luật viết tay (`train/baseline.py`) mới là cái làm trọn quy trình bạn mô tả, và
đó là bằng chứng rằng bài toán **giải được** với đúng bộ cảm biến này.

Vì sao lần này tụt so với bản siêu âm trước: bài đã khó hơn hẳn. Xe từ 18 cm lên
**30 cm** trên cùng cái bàn, phải chui vào khe chỉ hở 5 mm, và đầu vào từ 40 lên
**46 số**. Phiên này chỉ chạy được ~500 thế hệ, mà đường cong còn đang lên rõ
(điểm đánh giá đi từ 30 lên 104 trong 200 thế hệ gần nhất). Chạy tiếp:

```bash
python3 -m train.train --curriculum --resume brains/car_bay_v1.npz \
        --jobs $(nproc) --pop 48 --gens 4000 --min-gens-per-stage 100 \
        --eval-episodes 20 --out runs/bay6
```

Ba điều tôi sẽ làm nếu chạy tiếp, và lý do:

1. **`--eval-episodes 20`** thay vì 8. Với 8 tập, hai lần đánh giá liên tiếp cho
   ra 0% và 75% rơi trên **cùng một bộ trọng số**. Nhiễu đó khiến `best.npz` chọn
   nhầm bộ may mắn chứ không phải bộ giỏi. Đây là lỗi phương pháp, không phải
   thiếu tính toán.
2. **`--pop 48`**. Với 2.150 tham số, quần thể 32 cho gradient quá nhiễu.
3. **Kiên nhẫn ở stage 2.** Chương trình học hiện tại lên cấp khi rơi ≤ 10%, rồi
   stage sau lại rơi ngược lên — dấu hiệu nó lên cấp lúc kỹ năng còn mong manh.

Mỗi thế hệ ~6 giây trên 4 nhân ở stage 2. Ước chừng cần 1.500–2.500 thế hệ nữa,
tức 3–5 giờ trên máy 8 nhân — chạy nền được, không phải ngồi canh.

## Chiếc xe trong mô phỏng

| Bộ phận | Mô hình |
|---|---|
| **LiDAR Camsense X1/X2** | 3000 điểm/giây, quay 5–8 Hz → ~460 điểm mỗi vòng (0.8°/điểm), tầm 0.12–8 m. Mỗi vòng mất ~150 ms nên dữ liệu luôn cũ hơn thực tế 3 chu kỳ điều khiển; có nhiễu, rung góc, 2% điểm mất. Xoay bù theo odometry để vòng quét cũ vẫn chỉ đúng hướng |
| 2 cặp bánh DC trái/phải | điều khiển vi sai, 2 lệnh PWM trong `[-1,1]`, trễ motor 0.12 s, vùng chết PWM, trượt bánh ngẫu nhiên |
| Thân xe | **tròn, đường kính 30 cm**. Tròn dễ hơn vuông rất nhiều khi chui vào hộc: chỉ cần đúng trục trong phạm vi vài mm, **không có ràng buộc góc quay** — xe vuông cùng cỡ nghiêng 2° đã cần khe 31.0 cm |
| 2 cảm biến vực | chiếu xuống ở **đầu** và **đuôi** xe (cách tâm 14.5 cm) |
| 1 mắt thu hồng ngoại | ở đầu xe, góc thu ±46°, **2 kênh tần số**: kênh GỌI và kênh TRẠM SẠC |
| Odometry | encoder 2 bánh, sai số đường kính 2.5% + trôi góc → trí nhớ vị trí trạm sạc mờ dần |
| Cảm biến pin | mức pin 0..1, hao theo tải động cơ |

**LiDAR không thấy được mép bàn** — tia quét ngang, hố sâu không dội gì về. Chỉ 2
cảm biến chiếu xuống cứu được xe. Đây là ràng buộc quan trọng nhất của cả thiết kế.

## Trạm sạc: cái hộc chữ U

Trạm sạc là một cái **hộc** để xe chui hẳn vào: ngoài **40 × 40 cm**, lòng trong
**31 × 31 cm**, vách dày 4.5 cm, **đèn hồng ngoại nằm giữa thành trong** chiếu
thẳng ra cửa. Trên bàn còn vài cái hộc **giống hệt** nhưng không phát hồng ngoại.

Hình chữ U cho LiDAR nhiều hơn hẳn một cái hộp đặc: nó cho biết cả **trục** của
trạm, tức hướng xe phải quay về để chui vào thẳng.

1. `sim/dock_detector.py` cắt vòng quét thành đoạn, nối hai đầu thành dây cung rồi
   đo độ **lõm**: hộc lõm vào 35 cm, vật đặc thì lồi ra trước. Rồi khớp một đường
   thẳng qua **thành trong** để lấy trục — trung vị lệch **2°**.
2. Xe **vòng ra đối diện cửa hộc**, canh thẳng trục, rồi xem mắt hồng ngoại có bắt
   được tín hiệu kênh trạm sạc không. Chùm phát của LED là ±40° nhưng **hai vách
   bên bóp nó lại còn ~±24°**, nên đứng chéo là không thấy gì. Đó là lý do phải
   vòng ra đối diện — hình học bắt buộc thế, không phải luật tôi viết thêm.
3. Có tín hiệu thì **cam kết chui vào** và cứ thế mà vào. **Không có bắt tay hồng
   ngoại thì không đóng điện** — trạm thật cũng vậy.

Bước 3 phải "cam kết" chứ không được tính lại từng bước: khi đã vào trong, điểm
đợi trước cửa nằm **sau lưng** xe, nên nếu bước nào cũng hỏi "mình có đang đứng
đúng chỗ đợi không" thì xe sẽ lùi ra rồi vào, lùi ra rồi vào mãi. Tôi mất một
vòng gỡ lỗi vì đúng chuyện này.

### Khe 5 mm và đoạn vát ở miệng — chỗ cần bạn quyết

Xe tròn Ø30 cm, lòng hộc 31 cm. Thân tròn bỏ được hẳn ràng buộc góc — quay thế
nào cũng lọt, miễn đúng trục. Nhưng đúng trục trong **±5 mm** thì vẫn quá chặt:
LiDAR ở cự ly cắm cho trục chính xác ~2°, mà 2° trên quãng tiếp cận 40 cm đã là
1.4 cm lệch ngang.

Nên tôi thêm thứ mọi đế sạc thật đều có: **vát hai góc trong ở miệng hộc**. 8 cm
đầu nong ra 37 cm rồi thu dần về 31 cm — kích thước ngoài vẫn đúng 40 × 40 cm của
bạn. Đo trong mô phỏng, tắt nhiễu trượt bánh để lấy con số sạch:

| miệng hộc | cửa sổ bắt |
|---|---:|
| thẳng tuột (`BAY_FLARE = 0`) | **±2 mm** |
| vát 8 cm | **±38 mm** |
| vát 12 cm | ±42 mm |

Gấp gần **20 lần**, và 8 cm đã gần kịch trần hình học (lòng miệng 18.5 cm trừ bán
kính xe 15 cm = 3.5 cm). Nếu đóng thật, tôi khuyên hoặc vát như vậy, hoặc nới lòng
trong lên ~34 cm. Đặt `BAY_FLARE = 0.0` trong `sim/world.py` để xem lại bản thẳng.

Bộ dò là thuật toán hình học thuần, không phải mạng nơ-ron, nên chuyển sang C chạy
trên ESP32 được: `firmware/dock_detect.c` cho **kết quả trùng khít** bản Python
trên 25 cảnh ngẫu nhiên (`tests/test_firmware.py`).

## "Kinh nghiệm những lần trước" để tự đoán lúc phải về

Xe không được cho biết bản đồ hay toạ độ. Nó tự dựng ba thứ:

- **Trí nhớ vị trí trạm**: mỗi lần hồng ngoại xác nhận (hoặc cắm sạc xong), xe ghi
  lại chỗ đó theo hệ odometry của chính nó. Odometry trôi dần nên trí nhớ mờ đi,
  thấy lại đèn thì mới làm mới được.
- **Hao pin mỗi mét**: đo thẳng từ chuyến đi hiện tại (pin đã tụt / quãng đường đã đi).
- **Hướng trục của trạm**: nhớ luôn, vì hộc chỉ chui vào được từ một phía. Biết nó
  ở đâu mà không biết nó quay về đâu thì về tới nơi vẫn phải dò lại từ đầu.
- **Biên an toàn** = `pin còn − (hao mỗi mét × quãng đường về trạm × 2.0 + 0.12)`.
  Đây là một trong 46 đầu vào của bộ não: âm nghĩa là "về ngay không thì chết giữa
  đường". Hệ số 2.0 chứ không phải 1.0 vì đường về không thẳng — còn phải vòng ra
  trước cửa hộc rồi canh trục.

Sạc thì sạc **đầy** rồi mới đi tiếp — có thưởng riêng cho việc đó, và mỗi lần sạc đầy
xong thì lưới "đã đi qua" được xoá, coi như bắt đầu vòng tuần tra mới.

## Bộ não và cách nuôi

- `train/policy.py` — GRU nhỏ: **46 đầu vào → 16 nơ-ron ẩn → 2 số ga**, ~3.000 tham số.
  Phải có trí nhớ vì chỉ có một mắt hồng ngoại và vòng quét LiDAR thì cũ 150 ms.
- `train/imitate.py` — **học bắt chước trước**: cho mạng học theo bộ điều khiển viết
  tay (mục tiêu dày đặc, mỗi bước đều có đáp án, không phải chạy mô phỏng lại). Mò từ
  đầu bằng tiến hoá thuần thì mất hàng trăm thế hệ chỉ để tìm ra phản xạ "thấy vực thì lùi".
- `train/es.py` + `train/train.py` — **Evolution Strategies**: mỗi thế hệ sinh 64 bản
  đột biến, cho từng bản sống thử vài tập, rồi dịch bộ gen về phía các bản sống tốt.
  Có chương trình học tăng cấp 4 mức (`--curriculum`) cho ai muốn nuôi lại từ đầu.

```bash
python3 -m train.imitate --episodes 20 --steps 500 --gens 400 --hidden 12 --out runs/bc.npz
python3 -m train.train --stage 3 --resume runs/bc.npz --jobs 4 --gens 400 --out runs/car
```

## Xem xe chạy

```bash
python3 -m train.evaluate --policy brains/car_lidar_v2.npz --ascii --seed 7
python3 -m train.evaluate --policy brains/car_lidar_v2.npz --record demo.json --episodes 5
python3 tools/make_replay.py demo.json viz/replay.html
python3 tools/make_artifact.py brains/car_lidar_v2.npz runs/car/log.csv xe.html
```

## Sang phần cứng (làm sau)

```bash
python3 tools/export_c.py brains/car_lidar_v2.npz firmware/policy_weights.h
```

`firmware/brain.c` chạy đúng mạng đó trên ESP32, `firmware/dock_detect.c` chạy đúng bộ
dò hình. Chi tiết chân cắm, cách gom gói UART của Camsense và lớp phản xạ an toàn:
xem `firmware/README.md`. Thiết kế chi tiết + nhật ký gỡ lỗi: `docs/DESIGN.md`.

## Cấu trúc

```
sim/      mô phỏng: thế giới, xe, LiDAR, bộ dò hình trạm sạc, cảm biến, phần thưởng
train/    bộ não GRU, học bắt chước, ES, vòng huấn luyện, bộ điều khiển viết tay
brains/   bộ não đã nuôi được
tools/    xuất trọng số ra C, dựng file replay HTML, so sánh
firmware/ mã C chạy bộ não + bộ dò hình trên ESP32 (phần cứng làm sau)
tests/    kiểm tra mô phỏng và đối chiếu bản C với bản Python
```
