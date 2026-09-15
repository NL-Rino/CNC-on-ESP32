# Xe tự hành 2 bánh — nuôi AI trong mô phỏng trước, phần cứng sau

Mục tiêu: nuôi một bộ não biết **chạy long nhong không rơi khỏi bàn**, **đi tới chỗ
có đèn hồng ngoại gọi**, và **tự tính xem còn đủ pin để về trạm sạc hay chưa** —
huấn luyện hoàn toàn trong mô phỏng, sau đó nạp xuống ESP32.

Chạy bằng Python 3 + numpy, không cần GPU, không cần thư viện RL nào.

```bash
pip install numpy
python3 tests/test_sim.py                                  # kiểm tra mô phỏng
python3 tests/test_firmware.py                             # bản C khớp bản Python
python3 tools/compare.py brains/car_lidar_v2.npz           # AI vs bộ điều khiển viết tay
python3 -m train.evaluate --policy brains/car_lidar_v2.npz --ascii --seed 7
```

## Trạng thái hiện tại (đọc cái này trước)

Phần **mô phỏng + nhận thức đã xong và đã kiểm chứng**: LiDAR, bộ dò hộp 15 cm,
bắt tay hồng ngoại, trí nhớ vị trí trạm, ước lượng pin — tất cả chạy được, có
kiểm thử, và bản C cho ESP32 đã đối chiếu trùng khít bản Python.

Phần **bộ não thì mới nuôi được một nửa**. So trên 30 cảnh ngẫu nhiên, cùng seed:

| | AI đã học | Bộ luật viết tay |
|---|---:|---:|
| Rơi khỏi bàn | 7% | **0%** |
| Bước va chạm | **19.8** | 107 |
| Quãng đường / tập 65 s | **16.6 m** | 10.2 m |
| Lần tới đèn gọi / tập | 0.27 | **0.47** |
| Pin tự nạp được / tập | 0.000 | **0.258** |
| Lần tự sạc đầy / tập | 0.00 | **0.20** |
| Chết vì hết pin | 60% | **7%** |

Nói thẳng: bộ não hiện **biết đi long nhong, né vật cản và gần như không rơi khỏi
bàn**, nhưng **chưa học xong phần tự về trạm sạc** — nó vẫn chết vì hết pin 60%
số tập. Bộ luật viết tay (`train/baseline.py`) mới là cái làm trọn quy trình, và
đó cũng là bằng chứng rằng bài toán giải được với đúng bộ cảm biến này.

Lý do đơn giản là **thiếu thế hệ**: đổi từ 5 siêu âm sang LiDAR làm đầu vào tăng
từ 20 lên 40 số, mạng từ 1.810 lên 1.934 tham số, và bài khó hơn hẳn (phải nhận
hình, quay đầu hỏi hồng ngoại, rồi mới cắm). Máy chạy phiên này chỉ kịp ~550 thế
hệ. Chạy tiếp trên máy bạn:

```bash
python3 -m train.train --stage 3 --resume brains/car_lidar_v2.npz \
        --jobs $(nproc) --gens 2000 --out runs/car3
```

Mỗi thế hệ ~14 giây trên 4 nhân. Cần khoảng 500–1000 thế hệ nữa cho phần sạc,
tức 2–4 giờ trên máy 8 nhân — và chạy nền được, không phải ngồi canh.

## Chiếc xe trong mô phỏng

| Bộ phận | Mô hình |
|---|---|
| **LiDAR Camsense X1/X2** | 3000 điểm/giây, quay 5–8 Hz → ~460 điểm mỗi vòng (0.8°/điểm), tầm 0.12–8 m. Mỗi vòng mất ~150 ms nên dữ liệu luôn cũ hơn thực tế 3 chu kỳ điều khiển; có nhiễu, rung góc, 2% điểm mất. Xoay bù theo odometry để vòng quét cũ vẫn chỉ đúng hướng |
| 2 cặp bánh DC trái/phải | điều khiển vi sai, 2 lệnh PWM trong `[-1,1]`, trễ motor 0.12 s, vùng chết PWM, trượt bánh ngẫu nhiên |
| 2 cảm biến vực | chiếu xuống ở **đầu** và **đuôi** xe (cách tâm 10.5 cm) |
| 1 mắt thu hồng ngoại | ở đầu xe, góc thu ±46°, **2 kênh tần số**: kênh GỌI và kênh TRẠM SẠC |
| Odometry | encoder 2 bánh, sai số đường kính 2.5% + trôi góc → trí nhớ vị trí trạm sạc mờ dần |
| Cảm biến pin | mức pin 0..1, hao theo tải động cơ |

**LiDAR không thấy được mép bàn** — tia quét ngang, hố sâu không dội gì về. Chỉ 2
cảm biến chiếu xuống cứu được xe. Đây là ràng buộc quan trọng nhất của cả thiết kế.

## Trạm sạc: thấy hình → quay đầu hỏi hồng ngoại → mới vào

Trạm sạc là một **hộp 15 × 15 cm thật** nằm trên bàn. Trên bàn còn có vài **hộp mồi
nhử cùng kích thước** không phát hồng ngoại. Quy trình đúng như vậy mới cắm được:

1. `sim/dock_detector.py` cắt vòng quét LiDAR thành từng đoạn, giữ lại đoạn **rộng
   10–25 cm và phẳng** → ứng viên. Hộp mồi nhử và góc bàn cũng lọt qua bước này.
2. Xe quay đầu về phía ứng viên và xem **mắt hồng ngoại có bắt được tín hiệu kênh
   trạm sạc không**. Trạm chỉ phát về phía trước mặt nó, nên phải vừa đứng đúng phía
   vừa quay đầu về đó mới bắt được.
3. Có tín hiệu thì vào **ổ đậu** (cách tâm hộp 20 cm, đúng trên trục), dừng lại,
   canh hướng. **Không có bắt tay hồng ngoại thì không đóng điện** — trạm thật cũng vậy.

Đây là thuật toán hình học thuần, không phải mạng nơ-ron, nên chuyển sang C chạy
trên ESP32 được: `firmware/dock_detect.c` cho **kết quả trùng khít** bản Python.

## "Kinh nghiệm những lần trước" để tự đoán lúc phải về

Xe không được cho biết bản đồ hay toạ độ. Nó tự dựng ba thứ:

- **Trí nhớ vị trí trạm**: mỗi lần hồng ngoại xác nhận (hoặc cắm sạc xong), xe ghi
  lại chỗ đó theo hệ odometry của chính nó. Odometry trôi dần nên trí nhớ mờ đi,
  thấy lại đèn thì mới làm mới được.
- **Hao pin mỗi mét**: đo thẳng từ chuyến đi hiện tại (pin đã tụt / quãng đường đã đi).
- **Biên an toàn** = `pin còn − (hao mỗi mét × quãng đường về trạm × 1.5 + 0.06)`.
  Đây là một trong 40 đầu vào của bộ não: âm nghĩa là "về ngay không thì chết giữa đường".

Sạc thì sạc **đầy** rồi mới đi tiếp — có thưởng riêng cho việc đó, và mỗi lần sạc đầy
xong thì lưới "đã đi qua" được xoá, coi như bắt đầu vòng tuần tra mới.

## Bộ não và cách nuôi

- `train/policy.py` — GRU nhỏ: **40 đầu vào → 12 nơ-ron ẩn → 2 số ga**, 1.934 tham số.
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
