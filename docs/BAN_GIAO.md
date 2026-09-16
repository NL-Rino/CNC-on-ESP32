# Bàn giao dự án: xe tự hành 2 bánh, LiDAR Camsense, não chạy trên laptop

Tài liệu này đủ để một phiên trò chuyện khác tiếp nhận dự án mà không cần đọc
lại lịch sử. Repo: nhánh `claude/quirky-ritchie-p2hp6z`.

---

## 1. Mục tiêu

Một con xe 2 bánh vi sai **tròn, đường kính 30 cm** chạy trong nhà: đi long
nhong không đâm đồ, tới chỗ có đèn hồng ngoại gọi, và **tự biết lúc nào phải
về trạm sạc** rồi chui vào sạc đầy, xong lại đi tiếp.

Nuôi hoàn toàn trong mô phỏng bằng Python + numpy (không GPU, không thư viện
RL). Chạy thật thì **bộ não nằm trên laptop**, ESP32 chỉ đẩy cảm biến qua wifi
và nhận lệnh ga.

## 2. Phần cứng

| | |
|---|---|
| LiDAR | **Camsense X1/X2**, 3000 điểm/giây, quay 5–8 Hz → ~460 điểm/vòng (0,8°/điểm), tầm 0,12–8 m. Trả về **milimet** qua UART |
| Thân xe | **tròn Ø30 cm**. Tròn nên không có ràng buộc góc khi chui vào khe — đây là lý do bài toán khả thi |
| Bánh | 2 cặp DC vi sai, v_max 0,5 m/s, trễ motor 0,12 s |
| Cảm biến vực | 2 cái chiếu xuống, cách tâm ±14,5 cm (dùng cho mặt bàn / cầu thang) |
| Hồng ngoại | 1 mắt thu ở đầu xe, ±46°, **2 kênh**: đèn gọi và trạm sạc |
| Tiếp điểm sạc | 1 bit "đang nằm trong hộc". Khác với "đang có điện" |
| Odometry | encoder 2 bánh, sai số 2,5% + trôi góc |
| Não | ESP32 ↔ wifi ↔ laptop (UDP). Có sẵn cả chế độ não chạy thẳng trên ESP32 làm dự phòng |

### Trạm sạc: cái hộc chữ U

Ngoài **40×40 cm**, lòng trong **31×31 cm**, vách dày 4,5 cm, **đèn hồng ngoại
gắn giữa thành trong** chiếu thẳng ra cửa. Xe Ø30 cm chui vào chỉ dư 5 mm mỗi bên.

**Bắt buộc phải vát hai góc trong ở miệng.** Đo trong mô phỏng (tắt nhiễu trượt
bánh): miệng thẳng tuột bắt được **±2 mm**, vát 8 cm bắt được **±38 mm**, vát
12 cm ±42 mm. Không vát thì không dẫn động vi sai nào cắm nổi.

Trên bàn/trong nhà còn có **hộc mồi nhử** giống hệt nhưng không phát hồng
ngoại, nên xe buộc phải hỏi IR chứ không chỉ nhìn hình.

## 3. Trạng thái hiện tại — nói thẳng

Chạy 30 cảnh, cùng seed, bậc 3 (có người đi lại):

| | rơi % | hết pin % | sạc/tập | sạc đầy/tập |
|---|---:|---:|---:|---:|
| Bộ luật viết tay (`train/baseline.py`) | **0** | 7 | **0,414** | **0,60** |
| Bộ não đang nuôi (`brains/car_bay_v1.npz`) | 17 | 20 | 0,048 | 0,03 |
| Bộ não + lớp cưỡng ép về sạc | 13 | **7** | 0,125 | 0,03 |

**Bộ não chưa dùng được.** Bộ luật viết tay mới là cái làm trọn quy trình, và
đó là bằng chứng bài toán giải được với đúng bộ cảm biến này. Phần mô phỏng,
nhận thức, đường truyền, giao diện thì **đã xong và có kiểm thử**.

Lý do não chưa xong: thiếu thế hệ, cộng với hai lỗi trong bộ tiến hoá vừa mới
được sửa (mục 6, lỗi l) đã phá hỏng một phiên chạy 5.900 thế hệ.

## 4. Chạy thế nào

```
pip install numpy
python tests/test_sim.py        # 21/21
python tests/test_link.py       # 6/6   robot <-> wifi <-> não
python tests/test_firmware.py   # 5/5   bản C khớp bản Python (cần gcc, thiếu thì bỏ qua)
python tests/test_studio.py     # 7/7   giao diện (cần playwright)
```

**Xưởng làm việc** — xem xe chạy, vẽ nhà, dừng huấn luyện:
```
python -m tools.studio
```

**Nuôi tiếp** (`--resume` trỏ vào **thư mục**, đừng trỏ vào `best.npz`):
```
python -m train.train --curriculum --resume brains/car_bay_v1.npz --jobs 4 --pop 48 --gens 6000 --min-gens-per-stage 150 --eval-episodes 20 --out runs/bay11
```

**Não chạy trên laptop, robot qua wifi** (hai cửa sổ):
```
python -m link.brain_server --policy brains/car_bay_v1.npz
python -m link.fake_robot --realtime
```

**So sánh / xem nhanh**:
```
python tools/compare.py brains/car_bay_v1.npz
python -m train.evaluate --baseline --ascii --seed 7
```

## 5. Cấu trúc repo

```
sim/
  world.py        mặt bằng, hộc chữ U (Bay/Dock), vật cản, người đi lại (Mover)
  lidar.py        mô hình Camsense: gom đủ 1 vòng mới xử lý, nhiễu, 2% điểm mất
  dock_detector.py  DÒ HỘC — thuật toán hình học, không phải mạng
  perception.py   CHỖ DUY NHẤT dựng 46 số đầu vào. Sim và robot thật đều gọi vào đây
  failsafe.py     cưỡng ép về sạc khi pin thấp
  robot.py        động lực học, odometry, va chạm, tiếp điểm sạc
  sensors.py      cảm biến vực + hồng ngoại
  env.py          vòng reset/step, phần thưởng
  layout.py       đọc/ghi mặt bằng tự vẽ
train/
  policy.py       GRU 46→16→2, numpy thuần
  es.py           Evolution Strategies + Adam(W)
  train.py        vòng huấn luyện, chương trình học 4 bậc, lưu state.npz
  imitate.py      học bắt chước bộ luật viết tay (khởi động nguội)
  baseline.py     BỘ LUẬT VIẾT TAY — mốc so sánh, và bộ lái của lớp cưỡng ép
link/
  protocol.py     gói tin UDP
  brain_server.py não chạy trên laptop
  fake_robot.py   robot giả nói đúng giao thức (thử khi chưa có phần cứng)
firmware/
  dock_detect.c/h bản C của bộ dò hộc — đã đối chiếu khớp bản Python
  link_pack.c/h   đóng gói tin — đã đối chiếu TỪNG BYTE với Python
  robot_link.ino  ESP32 chế độ não-từ-xa
  car_main_skeleton.ino  ESP32 chế độ não-trên-xe (dự phòng)
tools/studio.py   xưởng làm việc (web cục bộ)
```

## 6. Những quyết định quan trọng và lý do

**Bộ dò hộc là thuật toán, không phải mạng.** Cắt vòng quét thành đoạn → nối
hai đầu thành dây cung → đo độ **lõm** (hộc lõm 35 cm, vật đặc lồi ra) → co dây
cung cho hết lồi → **khớp đường thẳng qua thành trong** để lấy trục. Trục lệch
trung vị **2°** thay vì 8,4° nếu lấy từ dây cung. Chạy 133 µs/vòng, port sang C
khớp từng con số.

**Chùm hồng ngoại bị chính hai vách bên bóp lại còn ~±24°.** Đây là hình học tự
nhiên chứ không phải luật viết tay — và nó khiến "phải vòng ra đối diện cửa mới
hỏi được IR" trở thành hệ quả bắt buộc.

**46 đầu vào**: 12 quạt LiDAR, 2 vực, 2×6 ứng viên hộc (vị trí + **trục**),
6 hồng ngoại, 6 trí nhớ trạm (vị trí + **hướng trục**), 3 pin (có **biên an
toàn**), 5 chuyển động. Chi tiết trong `firmware/brain.h`.

**Biên an toàn** = `pin còn − (hao mỗi mét xe TỰ ĐO × quãng đường về × 2,0 + 0,12)`.
Đây là phần "kinh nghiệm" — xe không có bản đồ, chỉ có odometry của chính nó.

**Xe xuất phát TỪ TRONG HỘC SẠC**, đầu hướng vào trong, muốn đi thì phải lùi ra.
Tiếp điểm sạc cho nó biết vị trí trạm ngay từ bước 0.

**Lớp cưỡng ép về sạc** (`sim/failsafe.py`) cắt quyền bộ não khi pin ≤ 15%
**hoặc** biên an toàn về 0, rồi tự lái về bằng bộ luật viết tay. Xe **vẫn nhận
đủ LiDAR và cảm biến** suốt đường về — chỉ đổi người cầm lái.
Số đo: pin 15% chỉ còn **7,9 giây / 2,2 m**, mà phòng rộng 3–3,8 m — nên vế
"hoặc biên an toàn" mới là vế cứu được xe. Chết pin 17% → **4%**.
**KHÔNG bật trong lúc huấn luyện**, bật thì não được cứu mỗi lần và không bao
giờ tự học được.

**Lớp phản xạ an toàn phải nằm trên ESP32.** Từ lúc cảm biến vực kêu đến lúc
tâm xe qua mép là 290 ms, trừ 120 ms phanh còn **170 ms** — một cú nghẽn wifi
ăn hết. Khác lớp cưỡng ép ở trên: cái đó chỉ là "ai lái xe", chậm hơn nhiều.

**Robot phải báo lại ga THỰC SỰ đã chạy**, không phải ga được yêu cầu. Lệnh
bước trước là 1 trong 46 đầu vào; khi phản xạ an toàn đè lệnh mà không báo lại
thì trạng thái GRU trên laptop trôi khỏi thực tế đúng lúc xe đang gặp chuyện.

## 7. Nhật ký lỗi — những thứ sẽ cắn lại

Chi tiết đầy đủ trong `docs/DESIGN.md` mục 10. Tóm tắt những cái đắt nhất:

- **(g)** Rơi khỏi bàn phạt −40 trong khi đi 2 m về trạm được +28 → xe học cách
  lao về trạm rồi rơi. 14/20 lần rơi là đang lúc pin yếu. Nâng lên −150.
- **(h)** Sửa xong (g) thì nó học cách chết rẻ hơn: đứng quay tại chỗ cho hết
  pin. Hai cái chết phải cùng giá.
- **(i)** Miễn phạt va chạm với vách hộc quá rộng → xe nằm lì vào vách **41%**
  số bước. Chỉ miễn khi thật sự đang trong lối vào.
- **(j)** Đặt trạm sạc sát mép bàn phá chính manh mối của xe (LiDAR không thấy
  mép, xe đoán mép bằng "quạt này trống trơn").
- **(k)** `best.npz` **không dùng để chạy tiếp được** — nó chỉ ghi khi phá kỷ
  lục, nên đến thế hệ 6000 vẫn ghi `gen=1744`. Dùng `state.npz` / trỏ vào thư mục.
- **(l)** Một phiên 5.900 thế hệ tự huỷ: `weight_decay` cộng thẳng vào gradient
  bị Adam chuẩn hoá luôn → trọng số phình → **tanh bão hoà, não trả về (+1,+1)
  với mọi đầu vào**. Cộng với `rank_transform` sinh gradient từ hư không khi cả
  quần thể điểm bằng nhau. Cả hai đã sửa (AdamW tách rời + trả vector 0).
- **Sim từng khử nhoè vòng quét bằng GÓC THẬT** — thứ robot thật không có. Phải
  lấy hiệu hai số **cùng một hệ** thì phần trôi mới triệt tiêu.

**Cách làm việc đáng giữ**: muốn biết A hay B gây lỗi thì **tắt hẳn B rồi đo
lại**, đừng ngồi suy luận. Trong dự án này tôi đoán sai thủ phạm 3 lần liên tiếp
trước khi chịu làm phép thử.

## 8. Còn lại phải làm

1. **Nuôi tiếp bộ não** — việc chính. ES đã sửa xong hai lỗi ở (l), chạy lại từ
   `brains/car_bay_v1.npz`. Ước chừng cần 1.500–2.500 thế hệ ở bậc 2–3.
   Nếu thấy dòng `!! ... diem GIONG HET nhau` lặp lại liên tục thì dừng ngay —
   đó là dấu hiệu bão hoà.
2. **Tăng số tập mỗi cá thể** từ 3 lên 5–8 (`--episodes`). Chấm điểm bằng 3 tập
   là chấm gần như ngẫu nhiên; đây là chỗ đáng tiêu tính toán nhất.
3. **Phần cứng** — chưa làm gì. `firmware/robot_link.ino` có đủ khung, cần viết
   các hàm đọc cảm biến thật và điền `WIFI_SSID` / `BRAIN_IP`.
4. Chưa có: sạc theo lịch, nhiều tầng, bản đồ bền giữa các lần chạy.

## 9. Máy của chủ dự án

Laptop i5-7200U (2 nhân / 4 luồng), Intel HD 620, Windows, lệnh là `python`
(không phải `python3`). **GPU không giúp được gì** ở đây: numpy không dùng GPU,
và mô phỏng là chuỗi phép tính nhỏ nối tiếp nên riêng tiền chuyển dữ liệu đã
đắt hơn. Mô phỏng đã được tối ưu 628 → 150 µs/bước (gấp 4,2 lần) bằng cách bỏ
`builtin max()` và duyệt trên tuple rút sẵn — thử numpy hoá thì **chậm hơn gấp
đôi**. Một thế hệ ~4,5 giây ở đây, ~9–11 giây trên máy đó.
