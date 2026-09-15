# Xe tự hành 2 bánh — nuôi AI trong mô phỏng trước, phần cứng sau

Mục tiêu: nuôi một bộ não biết **chạy long nhong không rơi khỏi bàn**, **đi tới chỗ
có đèn hồng ngoại gọi**, và **tự tính xem còn đủ pin để về trạm sạc hay chưa** —
huấn luyện hoàn toàn trong mô phỏng, sau đó nạp xuống ESP32.

Chạy bằng Python 3 + numpy, không cần GPU, không cần thư viện RL nào.

```bash
pip install numpy
python3 tests/test_sim.py                                  # kiểm tra mô phỏng
python3 tests/test_firmware.py                             # bản C khớp bản Python (cần gcc, thiếu thì tự bỏ qua)
python3 tests/test_link.py                                 # robot <-> wifi <-> bộ não
python3 tools/compare.py brains/car_bay_v1.npz              # AI vs bộ điều khiển viết tay
python3 -m train.evaluate --policy brains/car_bay_v1.npz --ascii --seed 7
```

## Trạng thái hiện tại (đọc cái này trước)

Phần **mô phỏng + nhận thức đã xong và đã kiểm chứng**: LiDAR, bộ dò hộc chữ U
(cho ra cả trục), bắt tay hồng ngoại qua khe hẹp, cửa sổ bắt ở miệng hộc, trí nhớ
vị trí + hướng trạm, ước lượng pin — chạy được, có **21 kiểm thử**, và bản C cho
ESP32 đã đối chiếu **trùng khít** bản Python trên 25 cảnh.

Phần **bộ não thì mới xong một nửa, và nửa nào xong thì xong hẳn**:

| | AI đang nuôi | Bộ luật viết tay |
|---|---:|---:|
| **Đi long nhong (không có hộc)** | | |
| Rơi khỏi bàn | **0%** | 0% |
| Quãng đường / tập | **24.5 m** | — |
| **Toàn bộ nhiệm vụ (có hộc, phải tự sạc)** | | |
| Rơi khỏi bàn | 37% | **0%** |
| Chết vì hết pin | 47% | **23%** |
| Lần tự sạc đầy / tập | 0.00 | **0.23** |

Kỹ năng **đi long nhong coi như xong**: 0% rơi, 24.5 m mỗi tập, 40 ô lưới đã đi
qua, chỉ ~30 bước va chạm. Kỹ năng **tự về sạc thì chưa** — và đo ra thì thấy cứ
thêm mấy cái hộc vào là kỹ năng nền cũng hỏng theo (0% rơi → 40–50% rơi).

Điều đó **không** phải do phần thưởng về sạc kéo nó ra mép. Tôi đã đoán vậy hai
lần và cả hai lần đều sai. Phép thử dứt điểm: ghim pin luôn đầy (tức là xoá hẳn
phần thưởng sạc ra khỏi phương trình) rồi thả vào cùng cảnh có hộc — **vẫn rơi
70%**. Thủ phạm là chính mấy cái hộc: chúng đổi hẳn thống kê LiDAR mà chính sách
đã quen ở bậc trước, nên nó phải học lại gần như từ đầu, và 37 thế hệ ở bậc đó
thì chưa đủ.

Chạy tiếp (mỗi thế hệ ~8 giây trên 4 nhân ở stage 2):

```bash
python3 -m train.train --curriculum --resume brains/car_bay_v1.npz \
        --jobs $(nproc) --pop 48 --gens 6000 --min-gens-per-stage 150 \
        --eval-episodes 20 --out runs/bay11
```

Ước chừng cần 1.000–2.000 thế hệ ở stage 2, tức 2–4 giờ trên máy 8 nhân.

### Bốn kẽ hở trong phần thưởng đã tìm và sửa trong phiên này

Đây là phần đáng đọc nhất, vì mấy lỗi này sẽ lặp lại y nguyên trên phần cứng
(chi tiết trong `docs/DESIGN.md` mục 10):

1. **Rơi khỏi bàn rẻ hơn giải thưởng sạc.** Phạt rơi −40, mà đi 2 m về phía trạm
   đã được +28 và giải sạc tới +120. Xe học đúng cái đó: 14/20 lần rơi là **đang
   lúc pin yếu**. Nâng phạt lên −150.
2. **Sửa xong (1) thì xe học cách chết rẻ hơn**: đứng quay tại chỗ cho hết pin
   (rơi 0%, hết pin 85%, mỗi tập đi qua 3 ô). Hết pin cũng là chết → cũng −150.
3. **Phạt quay-tại-chỗ đang tắt khi có mục tiêu**, mà pin yếu thì lúc nào cũng
   có mục tiêu — xe được quay vòng vòng miễn phí đúng lúc nó cần đi nhất.
4. **Miễn phạt va chạm với vách hộc quá rộng.** Định miễn cho việc xát vách lúc
   chui vào (khe hở 5 mm, xát là đương nhiên), nhưng lỡ miễn cả lúc xe tì vào
   *sườn* hộc. Xe nằm lì vào vách **41% số bước**.

## Bộ não chạy trên laptop, robot nối qua wifi

ESP32 chỉ làm ba việc: đọc cảm biến, đẩy lên laptop, nhận lại lệnh ga. Toàn bộ
bộ dò hộc và mạng nơ-ron chạy trên máy bạn.

```bash
# trên laptop
python3 -m link.brain_server --policy brains/car_bay_v1.npz

# thử toàn bộ đường đi khi chưa có phần cứng (robot giả nói đúng giao thức)
python3 -m link.fake_robot --realtime
```

Đo trên loopback: **20 Hz đều**, bộ não xử lý **0,5 ms** trong ngân sách 50 ms
mỗi chu kỳ, khứ hồi 0,8 ms. Một vòng quét LiDAR đầy đủ gói lại còn **888 byte**
(khoảng cách nén về milimet — mịn hơn nhiễu thật của Camsense cả chục lần), tức
**6 KB/s** ở 7 Hz. Băng thông không phải vấn đề.

### Ba thứ phải làm đúng, nếu không sẽ hỏng âm thầm

**1. Lớp phản xạ an toàn phải nằm trên ESP32.** Từ lúc cảm biến vực kêu đến lúc
tâm xe qua mép là **290 ms**; trừ 120 ms quãng đường phanh còn **170 ms** dự địa.
Một cú nghẽn wifi ăn hết chừng đó. Nên `robot_link.ino` tự lùi khi cảm biến vực
kêu, bất kể bộ não đang nghĩ gì, và tự dừng bánh nếu 150 ms không có lệnh mới.

**2. Robot phải báo lại ga *thực sự* đã chạy, không phải ga được yêu cầu.** Lệnh
bước trước là một trong 46 đầu vào của bộ não. Khi phản xạ an toàn đè lệnh mà
robot không báo lại, trạng thái GRU trên laptop sẽ trôi khỏi thực tế — đúng vào
lúc xe đang gặp chuyện. Đây là lỗi tôi mắc phải và chỉ lộ ra nhờ phép đối chiếu
quan sát: lệch **1.6** ở trường `prev_u_right`.

**3. Dựng quan sát phải dùng chung một đoạn mã.** `sim/perception.py` là chỗ duy
nhất biến tín hiệu cảm biến thành 46 số; cả mô phỏng lẫn `brain_server` đều gọi
vào đó. Có hai phép kiểm tra giữ cho nó không trôi:

| kiểm tra | kết quả |
|---|---|
| Quan sát trên laptop vs. mô phỏng tự tính, 220 bước | lệch tối đa **3.6e-3** (đúng bằng sai số làm tròn 1 mm) |
| Gói tin `link_pack.c` vs. `link/protocol.py` | **trùng từng byte** |

Cái thứ hai đáng giá hơn vẻ ngoài của nó: offset byte lệch một chữ là thứ không
thể gỡ khi đã nằm trên xe.

### Một lỗi cũ lộ ra khi tách mã

Bản mô phỏng cũ khử nhoè vòng quét LiDAR bằng **góc thật** của xe — thứ robot
thật không hề có. Khi chuyển sang dùng odometry thì tỉ lệ cắm sạc tụt từ 0.33
xuống 0.10 mỗi tập. Nguyên nhân: tôi lấy `scan_theta` ở hệ góc-thật trừ đi góc
odometry, ra đúng bằng **lượng trôi tích luỹ**. Khử nhoè chỉ cần biết xe quay bao
nhiêu *trong một vòng quét* (~143 ms), nên phải lấy hiệu hai số **cùng một hệ**
thì phần trôi mới triệt tiêu. Sửa xong, kết quả trở lại 0.32.

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
