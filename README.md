# Xe tự hành 2 bánh — nuôi AI trong mô phỏng trước, phần cứng sau

Mục tiêu: nuôi một bộ não biết **chạy long nhong không rơi khỏi bàn**, **đi tới chỗ
có đèn hồng ngoại gọi**, và **tự tìm trạm sạc khi pin yếu** — huấn luyện hoàn toàn
trong mô phỏng, sau đó nạp xuống ESP32.

Chạy bằng Python 3 + numpy, không cần GPU, không cần thư viện RL nào.

```bash
pip install numpy
python3 tests/test_sim.py                              # kiểm tra mô phỏng
python3 tools/compare.py brains/car_v1.npz             # AI có sẵn vs bộ điều khiển viết tay
python3 -m train.evaluate --policy brains/car_v1.npz --ascii --seed 7   # xem xe chạy
python3 -m train.train --curriculum --jobs 4 --gens 500 --out runs/car  # nuôi lại từ đầu
```

## Bộ não đã nuôi được

`brains/car_v1.npz` — GRU 1.810 tham số, ~830 thế hệ ES. Chấm trên 40 cảnh ngẫu
nhiên, **cùng seed** cho cả hai bên:

| | AI đã học | Viết tay |
|---|---:|---:|
| Điểm | **205** | 22 |
| Rơi khỏi bàn | 2% | 0% |
| Chết vì hết pin | **8%** | 30% |
| Lần tới đèn gọi / tập | **1.88** | 0.20 |
| Pin tự nạp được / tập | **0.185** | 0.007 |
| Quãng đường / tập 45 s | **11.3 m** | 8.2 m |
| Bước va chạm | 13.8 | 0.5 |
| Ô lưới đã đi qua | **9.8** | 3.6 |

AI hơn hẳn ở nhiệm vụ (tìm đèn gọi nhiều gấp 9 lần, tự sạc gấp 26 lần, đi khắp bàn
gấp 3 lần) nhưng **cọ vật cản nhiều hơn** và thỉnh thoảng còn rơi. Muốn xe hiền hơn
thì tăng `w_bump` / `w_fall` trong `sim/env.py` rồi nuôi tiếp:

```bash
python3 -m train.train --stage 3 --resume brains/car_v1.npz --gens 400 --out runs/car2
```

## Chiếc xe trong mô phỏng

| Bộ phận | Mô hình |
|---|---|
| 2 cặp bánh DC trái/phải | điều khiển vi sai, 2 lệnh PWM trong `[-1,1]`, trễ motor 0.12 s, vùng chết PWM, trượt bánh ngẫu nhiên |
| 5 siêu âm | góc **−90°, −45°, 0°, +45°, +90°**, tầm 2 m, chùm tia ±7.5°, nhiễu 1.2 cm, 2% lần đo **mất echo** |
| 2 cảm biến vực | chiếu xuống ở **đầu** và **đuôi** xe (cách tâm 10.5 cm), báo trước khi tâm xe ra tới mép bàn |
| 1 mắt thu hồng ngoại | đặt ở đầu xe, góc thu ±46°, **2 kênh tần số**: kênh GỌI (người dùng gọi xe tới) và kênh TRẠM SẠC |
| Cảm biến pin | mức pin 0..1, hao theo tải động cơ, nạp lại khi đâm đúng hướng vào trạm sạc |

Mép bàn **không** hiện ra trên siêu âm (siêu âm chiếu ngang không thấy hố sâu) —
đúng như ngoài đời. Chỉ 2 cảm biến chiếu xuống cứu được xe.

Chỉ có **một** mắt thu hồng ngoại, nên muốn biết đèn phát từ hướng nào thì xe phải
**xoay và so sánh cường độ theo thời gian**. Vì vậy bộ não là một mạng **GRU có trí
nhớ**, không phải mạng thuần.

## Bộ não và cách nuôi

- `train/policy.py` — GRU nhỏ (~1.8k tham số, mặc định 16 nơ-ron ẩn).
  Vào: 20 số từ cảm biến. Ra: 2 số = ga trái / ga phải.
- `train/es.py` — **Evolution Strategies**: mỗi thế hệ sinh 64 bản đột biến của bộ
  não, cho từng bản sống thử vài tập mô phỏng, rồi dịch bộ gen về phía các bản sống
  tốt. Không cần đạo hàm, chạy song song 4 nhân CPU.
- `train/train.py` — **chương trình học tăng cấp** (`--curriculum`):

  | Cấp | Bài học | Điều kiện lên cấp |
  |---|---|---|
  | 0 | bàn trống: đừng rơi khỏi mép, đi cho rộng | rơi < 10%, đi qua ≥ 14 ô lưới |
  | 1 | thêm vật cản: tránh đụng | thêm va chạm thấp |
  | 2 | đèn gọi bật ngẫu nhiên: tìm và đi tới | ≥ 1 lần tới đích/tập |
  | 3 | pin + trạm sạc: tự đi sạc khi yếu | (cấp cuối) |

Phần thưởng (`sim/env.py`, sửa được hết): rơi khỏi bàn −40, hết pin −25, va chạm
−1.2/bước, tiến gần mục tiêu +14/m, tới đích +40, sạc +150/đơn vị pin, canh đúng
hướng ổ sạc +0.35/bước, đi nhanh +0.6·v, ô lưới mới +6, phạt quay tại chỗ / hao
điện / giật ga.

## Xem xe chạy

```bash
# ngay trên terminal
python3 -m train.evaluate --policy brains/car_v1.npz --ascii --seed 7

# xuất file HTML xem trên trình duyệt (tia siêu âm, pin, IR, vệt bánh xe)
python3 -m train.evaluate --policy brains/car_v1.npz --record demo.json --episodes 5
python3 tools/make_replay.py demo.json viz/replay.html

# bản trang đẹp, kèm đường tiến hoá
python3 tools/make_artifact.py brains/car_v1.npz runs/car/log.csv xe.html
```

## Sang phần cứng (làm sau)

```bash
python3 tools/export_c.py brains/car_v1.npz firmware/policy_weights.h
```

`firmware/brain.c` chạy đúng mạng đó trên ESP32 (~0.2 ms/bước, không cần thư viện
ngoài). Chi tiết chân cắm, thứ tự đọc cảm biến và lớp phản xạ an toàn: xem
`firmware/README.md`. Thiết kế chi tiết + ghi chú sim-to-real: xem `docs/DESIGN.md`.

## Cấu trúc

```
sim/      mô phỏng: thế giới, động lực học xe, cảm biến, phần thưởng, vẽ ASCII
train/    bộ não GRU, ES, vòng huấn luyện, chấm điểm, bộ điều khiển viết tay
brains/   bộ não đã nuôi được
tools/    xuất trọng số ra C, dựng file replay HTML, so sánh
firmware/ mã C chạy bộ não trên ESP32 (phần cứng làm sau)
tests/    kiểm tra mô phỏng
```
