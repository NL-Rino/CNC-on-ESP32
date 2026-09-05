# Nhật ký thay đổi

## v1.11.0 — 2026-09-05

### Căn tâm mâm cặp bằng tay: căn một lần, dùng mãi

Mâm cặp tự định tâm nên ống to hay nhỏ thì đường tâm ống vẫn trùng đường tâm mâm
cặp. **Tâm mâm cặp là hằng số cơ khí của máy, không phải của phôi.** Chạm mỏ vào
bốn mặt ống một lần là xong: sau này thay ống cỡ khác chỉ việc khai lại kích
thước, phần mềm tự tính gốc X và gốc Z mới, không phải căn lại.

Bốn lần chạm, mỗi cặp lấy điểm giữa để khử đúng một sai số:

* **Sườn trái + sườn phải → gốc X.** Béc dày bao nhiêu thì cộng bên này trừ bên
  kia bấy nhiêu, lấy điểm giữa là **đường kính béc tự triệt tiêu** — khỏi đo
  béc. Ống tròn còn khử luôn độ thụt do chạm cao hơn đường tâm, miễn hai bên
  cùng một cao độ Z (lệch quá 1 mm là báo).
* **Đỉnh + đỉnh sau khi xoay 180° → gốc Z.** Ống kẹp lệch lên `e` mm thì quay
  nửa vòng thành lệch xuống `e` mm, cộng lại chia đôi là hết. Còn *hiệu* của hai
  số đó chính là **độ lệch tâm**, in ra để biết mâm cặp có vấn đề không.

Bốn phép soát tự động: đỉnh có chạm gần đường tâm không, hai lần chạm đỉnh có
đúng cách nhau 180° không, hai sườn có cùng cao độ không, và bề rộng đo được có
khớp cỡ ống đã khai không.

### Đặt gốc: X-Z tự động, Y-A bằng tay — chỉ đâu cắt đó

**Đặt gốc X-Z từ tâm kẹp** dùng `G10 L2` (đặt thẳng gốc theo toạ độ máy) chứ
không phải `G10 L20` (lấy chỗ đang đứng làm gốc), nên **mỏ đang ở đâu cũng bấm
được**, không phải rà vào đâu cả. Thêm `G92.1` ở đầu để xoá dịch gốc tạm còn sót.

Hai thứ đổi theo từng lần gá thì để tay, đúng như nên thế: **Đặt gốc Y tại đây**
(rà tới chỗ muốn cắt) và **Đặt gốc A tại đây** (xoay tới góc muốn).

Chế độ dò cạnh tự động vẫn còn nguyên nhưng lùi xuống làm đường phụ.

### Tự siết hành trình theo cỡ ống

Căn xong là phần mềm biết chỗ nào mỏ không bao giờ có việc phải tới:

* trục ngang chỉ chạy trong bán kính ống cộng phần chừa thêm;
* **trục nâng hạ không được xuống dưới 0** — gốc Z ở mặt phôi, xuống dưới là đã
  cắm vào ống ở *mọi* góc xoay;
* trục dọc giới hạn theo chiều dài phôi đã khai.

Sai ở đâu là báo ngay lúc sinh G-code, chưa kịp chạy. Giới hạn **tính lại mỗi
lần gọi** theo cỡ ống đang khai nên đổi ống là tự đổi theo, và luôn **giao với**
hành trình cơ khí chứ không nới rộng quá máy chịu được. Tắt được bằng một ô đánh
dấu.

### Giao diện

Cột trái thẻ Điều khiển giờ **cuộn được** — trước đây trên màn hình máy tính
xách tay là khung dưới cùng bị cắt mất, bấm không tới. Mười hai ô thông số dò
cạnh dời vào hộp thoại riêng cho cột đỡ chật.

### Khác

* Lệnh mới `python -m pipecut clamp` để xem, tính hoặc xoá hồ sơ căn tâm.
* `MachineProfile.effective_travel()` trả về hành trình cơ khí đã giao với vùng
  cỡ ống đang khai cần tới; `Kinematics.check_limits()` dùng nó.
* 28 bài kiểm thử mới, tổng 269.

## v1.10.0 — 2026-09-05

### Dò bằng chính mỏ cắt (ohmic touch-off)

Thêm đường thứ hai để dò cạnh, không cần đầu dò cảm ứng: **kẹp một dây vào đầu
mỏ plasma**, cho Z hạ từ từ tới khi béc chạm phôi là đóng mạch qua chính phôi
(phôi đã nối mát máy cắt). Đầu dò *chính là* mũi cắt nên **mọi số lệch bằng 0** —
gốc Z rơi đúng mặt phôi, không phải đo đạc gì.

Hai đường giờ dùng chung một bộ mã: `arm_steps()` / `disarm_lines()` /
`with_probe_setup()`. Chọn đường nào là chuyện của hồ sơ máy.

**Bốn điều kiện phần cứng, phần mềm chặn hoặc cảnh báo từng cái:**

1. **Máy phải mồi chạm (blowback), không phải mồi cao tần (HF).** Máy HF phát
   xung hàng chục nghìn vôn ở tần số MHz, chạy ngược theo dây dò là cháy bo.
   Cách thử ghi trong hướng dẫn: bấm mồi trong không khí — vẫn ra tia lửa kèm
   tiếng rè rè liên tục là mồi cao tần, phải chuyển sang đầu dò riêng.
2. **Bắt buộc có rơ-le tách dây dò.** Lúc cắt, đầu mỏ mang điện hồ quang
   100–300 V. Phần mềm đóng rơ-le (`M62 P<n>`) khi bắt đầu dò và ngắt
   (`M63 P<n>`) khi xong — **kể cả khi dò lỗi hay bấm dừng giữa chừng**. Khai
   chân ở mục `user_outputs` của tệp cấu hình FluidNC (mẫu `gpio 47`).
3. **Nên cách ly quang chân probe** — ranh giới duy nhất giữa mạch hồ quang và
   con ESP32-S3.
4. **Béc là đồ tiêu hao.** Dò nhanh quá là móp lỗ béc. Phần mềm **từ chối** tốc
   độ dò trên 400 mm/ph ở chế độ này; hồ sơ mẫu để 250 mm/ph rồi dò lại 40.

Phần kiểm tra khai báo cũng từ chối: số lệch khác 0 (đầu dò *là* mỏ, không có
lệch), bật ohmic cùng lúc với đầu đảo, và số ngõ ra ngoài dải 0–7.

**Tắt nguồn cắt luôn là lệnh đầu tiên** của mọi quy trình dò, trước cả lệnh đóng
rơ-le hay xoay đầu đảo.

### Tách tệp cấu hình FluidNC cho S3 thành hai bản

`fluidnc_pipe4axis_s3.yaml` giờ là bản **4 trục dò bằng mỏ cắt**, có thêm mục
`user_outputs` cho rơ-le tách dây. Bản 5 trục có trục đảo chuyển sang tệp riêng
`fluidnc_pipe4axis_s3_dau_do.yaml`.

Phải tách vì để trục `B` trong cấu hình mà không lắp mô-tơ là **về gốc treo ở chu
kỳ 4**, máy đứng im không báo gì.

Kèm hồ sơ máy mẫu `config/machine_s3_do_bang_mo.json` (4 trục, dò 250 mm/ph, dò
lại 40 mm/ph, nhấc 3 mm, mọi số lệch 0).

## v1.9.0 — 2026-09-04

### Đầu đảo: một mô-tơ xoay giữa mỏ cắt và đầu dò

Đầu dò cảm ứng gắn **lệch 90°** với mỏ cắt trên một trục đảo (khai là trục `B`),
một mô-tơ xoay qua lại đổi đầu nào chúc xuống.

Kiểu này có một cái hay về hình học: **khi mỗi đầu đã chúc xuống thì cả hai nằm
đúng cùng một chỗ theo X và Y**, chỉ khác chiều cao. Nên thường chỉ phải khai
một số duy nhất — *đầu dò thấp hơn mỏ bao nhiêu mm* — thay vì ba số lệch như
kiểu que dò gắn cố định cạnh mỏ.

Phần mềm tự lo trình tự, không phải gõ tay: nâng Z lên cao độ xoay → xoay sang
đầu dò → chờ hết rung → dò → nâng Z → xoay về mỏ cắt.

**Ba chốt an toàn**, mỗi chốt chặn một cách hỏng thật:

1. **Nâng trước rồi mới xoay.** Lúc xoay, đầu dài hơn quét một cung quanh trục
   đảo; không nâng đủ cao là nó quét thẳng vào phôi. Đặt cao độ xoay thấp hơn
   tầm quét là phần mềm báo lỗi, không cho chạy.
2. **Dò lỗi hay bấm dừng giữa chừng thì vẫn tự trả đầu về mỏ cắt.** Bỏ máy lại ở
   tư thế đầu dò chúc xuống là lần cắt sau đâm kim vào phôi. Chuỗi lệnh trả về
   chạy cả khi đã bật cờ dừng.
3. **Mọi chương trình cắt đều mở đầu bằng lệnh đưa đầu đảo về mỏ cắt**, đứng
   trước mọi lệnh bật nguồn cắt. Mất điện xong máy không biết đầu nào đang chúc
   xuống, mà đoán sai là mồi lửa ngay trên đầu dò.

Thêm vai trò trục `swivel`, hồ sơ máy mẫu `config/machine_s3_dau_do.json`, trục
`B` trong tệp cấu hình FluidNC cho S3 (chân 39/40, công tắc về gốc 41, chu kỳ về
gốc 4 — sau khi Z đã nâng), và các ô khai báo trong khung Dò cạnh.

### Ghi chú về kim dò

Cái bán rời gồm **bi ruby + trục sứ** chỉ là *kim dò* (stylus), vặn ren M2.5 vào
thân đầu dò. Bi ruby và trục sứ đều **không dẫn điện** nên bản thân kim không
đóng mạch được — phải mua cả **thân đầu dò cảm ứng**, bên trong mới có tiếp
điểm. Đã ghi rõ trong hướng dẫn và trong tệp cấu hình FluidNC.

Kèm cảnh báo về mức điện áp: đầu dò cảm ứng thường ra tín hiệu 5 V hoặc 12 V,
phải hạ áp hoặc cách ly quang về 3,3 V trước khi vào chân ESP32-S3.

### Khác

* Thêm 9 bài kiểm thử, tổng cộng **230**.

## v1.8.0 — 2026-09-04

### Sửa hai lỗi trong tệp cấu hình FluidNC mẫu

Đối chiếu từng khoá với mã nguồn FluidNC v4.0.4 thì thấy hai lỗi, **cả hai đều
làm máy không chạy được** mà không báo gì:

* **Nguồn cắt khai sai chỗ.** Tôi lồng nó trong một khoá `spindle:`, nhưng
  FluidNC không có khoá đó — nguồn cắt khai ngay ở **gốc tệp**, tên khối chính là
  loại nguồn cắt (`Relay:`, `PWM:`...). Lồng sai là cả khối bị bỏ qua và **mỏ
  không bao giờ kích**.
* **Tên driver động cơ sai.** Tôi ghi `stepstick:`, nhưng tên đăng ký thật là
  `standard_stepper:` — chữ `stepstick` chỉ nằm trong một dòng chú thích của mã
  nguồn. Khai sai là **trục không có chân STEP/DIR nên đứng im**.

Còn một lỗi nhỏ: `pulloff_mm` nằm nhầm trong khối `homing`, đúng ra thuộc về
`motor0`.

FluidNC **lặng lẽ bỏ qua khoá lạ** chứ không dừng, nên cả ba lỗi này đều không
có thông báo gì nếu không chạy `$Config/Validate`. Đã ghi rõ điều đó trong
hướng dẫn.

Thêm `tests/test_firmware_config.py`: 10 bài soát tệp cấu hình theo danh sách
khoá lấy từ chính mã nguồn FluidNC — khoá lạ, tên driver, vị trí nguồn cắt, chân
cấm theo từng dòng chip, chân trùng, trục xoay không được đặt giới hạn hành
trình, Z phải về gốc trước, rơ-le mỏ cắt không được nằm ở chân khởi động.

### Tệp cấu hình ESP32-S3 đầy đủ

Viết lại `firmware/fluidnc_pipe4axis_s3.yaml` cho đủ mọi phần: sinh xung, bộ đệm
nhìn trước, sai số cung và mức phanh ở góc, bốn trục kèm về gốc, nguồn cắt, dò
chạm, công tắc điều khiển ngoài (E-stop / tạm dừng / chạy tiếp), thiết lập lúc
khởi động, và macro.

Khối **nguồn cắt** để riêng một chỗ có đánh dấu rõ, kèm sẵn khối `PWM` cho laser
và `NoSpindle` cho chạy khô — chọn xong nguồn cắt thì mở khối tương ứng.

Thêm chân cho nút DỪNG KHẨN (`gpio 13`), tạm dừng (`gpio 14`) và chạy tiếp
(`gpio 42`), khai kiểu **thường đóng** đúng chuẩn an toàn. Có ghi rõ đây chỉ là
dừng *phần mềm*, vẫn bắt buộc phải có công tắc dừng khẩn **cứng** cắt thẳng
nguồn động lực.

### Que dò riêng đặt cạnh mỏ cắt

Đầu que dò không nằm cùng chỗ với mũi cắt, nên mọi số đo được là đo ở vị trí que
dò. Thêm ba ô khai khoảng lệch (**thấp hơn mỏ bao nhiêu**, **lệch ngang**,
**lệch dọc**); phần mềm quy kết quả về đúng mũi cắt khi đặt gốc.

Ví dụ que thấp hơn mỏ 12 mm: que chạm mặt phôi thì mũi cắt đang ở *trên* mặt
phôi 12 mm, nên gốc Z đặt là **+12** chứ không phải 0.

Khoảng lệch chỉ đổi gốc đặt ra, **không đổi số đo** — có bài kiểm thử giữ đúng
điều này. Trục xoay không bị bù (que đặt lệch chỗ nào thì góc vẫn thế).

Phần mềm chặn trước cấu hình nguy hiểm: khai lệch ngang mà quên khai que thấp
hơn mỏ là báo lỗi ngay, vì khi đó mỏ đâm vào phôi trước khi que kịp chạm.

Hộp thoại xác nhận nhắc rõ phải rà **đầu que dò** (không phải mũi cắt) vào giữa
mặt trên phôi, kèm số lệch đang khai.

### Khác

* Thêm 17 bài kiểm thử, tổng cộng **221**.
* `pyyaml` chỉ dùng cho bài kiểm thử cấu hình và tự bỏ qua khi thiếu — phần mềm
  vẫn không cần thư viện ngoài nào ngoài `pyserial`.

## v1.7.0 — 2026-09-04

### Chế độ dò cạnh: máy tự tìm phôi và đặt gốc toạ độ

Không phải rà tay từng trục rồi đặt gốc bằng mắt nữa. Máy tự dò ra **cả bốn
gốc**: mặt phôi (Z), đường tâm phôi (X), mặt đầu ống (Y), và với ống hộp là cả
góc xoay cho mặt phẳng nằm ngang (A).

**Cần thêm gì:** một tiếp điểm đóng khi mỏ chạm phôi, nối vào chân `probe` của
FluidNC. Với mỏ plasma kích bằng rơ-le thì nên dùng **đầu cắt thả nổi + công tắc
hành trình** — rẻ, bền, không dính gì tới mạch plasma nên không sợ cao tần.

**Cách làm, và vì sao phải khác máy phay:** máy phay dò cạnh bằng cách chạm
ngang vào thành phôi. Máy cắt ống thì mỏ treo thẳng đứng, đâm ngang là gãy mỏ.
Nên ở đây chỉ **dò xuống**: chỗ nào chạm là còn phôi, chỗ nào hụt là hết phôi,
chia đôi giữa hai chỗ đó rồi lặp lại. Từ khoảng tìm 40 mm xuống sai số 0,1 mm
chỉ mất 9 lần dò.

Bốn quy trình, chạy riêng hoặc chạy trọn gói theo thứ tự Z → A → X → Y. Thứ tự
này có lý do: **phải cân mặt trước khi tìm tâm**, vì phôi xoay lệch thì bề ngang
đo được không phải bề ngang thật.

**Nó còn tự soát giúp.** Lúc tìm tâm, phần mềm đo lại bề rộng phôi rồi đối chiếu
với số đã khai: nằm ngoài mọi khả năng của tiết diện thì báo sai kích thước; chỉ
rộng hơn mức "mặt phẳng ngửa lên" thì nói luôn là phôi đang xoay lệch khoảng bao
nhiêu độ. Khai sai kích thước là lỗi âm thầm nguy hiểm nhất — mọi thứ vẫn chạy,
chỉ có đường cắt là sai chỗ.

Kiểm chứng trên phôi ảo đặt lệch tâm 7,35 mm, đầu ống ở 12,4 mm, xoay lệch 6,2°:
đo ra tâm 7,336 · đầu ống 12,373 · nghiêng 6,201°. Sai số dưới 0,03 mm và 0,01°,
đúng bằng dung sai chia đôi đã đặt.

Thêm `python -m pipecut probe`, khung **Dò cạnh** trong thẻ Điều khiển, và một
phôi ảo trong máy ảo để xem trước trình tự dò khi chưa có cảm biến.

**Hai lỗi tự bắt được trong lúc làm:**

* Quãng dò tìm mép tính từ mặt phôi thay vì từ cao độ an toàn, nên dò không tới
  và mép tìm được chỉ là "chỗ mặt tụt quá ngưỡng". Phôi xoay lệch thì hai bên
  tụt không đều nhau, tâm suy ra lệch 1,8 mm. Nay dò tới đúng mép rộng nhất —
  tâm khi đó luôn đúng vì mọi tiết diện ở đây đều đối xứng qua tâm khi quay
  180°. Không đủ quãng dò thì phần mềm báo rõ chứ không lặng lẽ cho số sai.
* Phôi ảo trong máy ảo coi ống rộng bằng bán kính bao ở mọi góc xoay, nên bề
  rộng đo ra sai. Ống hộp 50×50 ngửa mặt phẳng lên chỉ rộng 50 mm, quay 45° cho
  góc chĩa ngang thì rộng tới 65,7 mm. Nay bắn tia thẳng đứng vào biên tiết diện
  đã quay, lấy giao điểm cao nhất.

### Khác

* Thêm `[PRB:...]` vào bộ phân tích giao thức, phân biệt **chạm thật** với **dò
  hụt** — phân biệt được hai cái này là điều kiện tiên quyết để dò cạnh.
* Thông số dò lưu trong hồ sơ máy (mục `probe`).
* Thêm 19 bài kiểm thử, tổng cộng **204**.

## v1.6.0 — 2026-09-04

### Sửa lỗi phôi quay trọn một vòng giữa nhát cắt

Cắt rãnh trên mặt phẳng mà mâm cặp lại quay hẳn 360° rồi quay về — G-code có
`X0 A-360 F4000` ngay giữa đường cắt.

Nguyên nhân nằm ở phép gỡ cuộn góc trong `Section.contact_at`. Với `v` âm cực
nhỏ (kiểu `-8.9e-16`, vụn dấu phẩy động sinh ra khi bù bề rộng mạch cắt), phần
dư `v - lap*chu_vi` bị làm tròn lên **đúng bằng chu vi**; `normal_angle` quy giá
trị đó về 0° của vòng **sau**, trong khi bộ đếm vòng vẫn ở vòng **trước** — lệch
trọn 360°. Lỗi chỉ hiện ra với biên dạng vắt qua mốc chu vi, tức mọi thứ nằm
quanh vị trí 12 giờ.

Nay phần dư chạm mốc được đưa hẳn về 0 và cộng vòng lên cho khớp. Có bài kiểm
thử quét dày quanh mọi bội số của chu vi cho cả ống tròn lẫn ống hộp.

Cùng nguyên nhân, phần vượt góc cũng đổi sang lấy **đại diện góc gần góc quay
hiện tại nhất** thay vì dò theo phép chia dư.

### Đặt đường vào dao riêng cho từng nguyên công

Trước đây chỗ vào dao chỉ đặt được chung ở hồ sơ máy, nên không chỉnh được cho
từng nhát cắt. Nay mỗi nguyên công có riêng khối ô: bật **Tự đặt đường vào dao**
rồi chọn phía vào dao, dời điểm mồi theo % chu vi, kiểu (`arc`/`line`/`none`),
chiều dài, góc và chạy vượt. Tắt thì vẫn dùng thiết lập chung.

Ghi đè chỉ áp cho đúng nguyên công đó, không đụng tới hồ sơ máy hay nguyên công
khác.

### Cắt góc gần vuông hơn: chia cung làm nhiều lần xoay

Kiểu `pivot` trước đây luôn xoay **một lần** đưa giữa cung lên đỉnh, nên ở hai
đầu cung mỏ nghiêng tới 45° so với pháp tuyến. Thêm ô **Chia cung góc mấy lần
xoay**: chia làm `k` lần thì độ nghiêng lớn nhất chỉ còn `45/k`.

Đo trên nhát cắt đứt ống 50×50 R6, 1600 mm/phút:

| Chia | Mỏ nghiêng tối đa | Tốc độ cắt | Số lần mồi | Thời gian |
|---|---|---|---|---|
| 1 *(mặc định)* | 45° | 1600 mm/ph | 9 | 29 s |
| 2 | 22,5° | 1600 mm/ph | 13 | 34 s |
| 3 | 15° | 1600 mm/ph | 17 | 38 s |
| 6 | 7,5° | 1600 mm/ph | 29 | 51 s |

Tốc độ cắt không đổi; cái phải trả là **số lần mồi** — mỗi lần xoay là một lần
tắt mỏ rồi mồi lại. Ban đầu tôi định lấy 3 làm mặc định vì tưởng không tốn gì,
nhưng bài kiểm thử cũ bắt được rằng số lần mồi tăng từ 9 lên 17. Mồi là thứ hại
phôi và hao vật tư nhất nên mặc định giữ ở 1.

Khe hở mỏ–phôi giữ đúng 1,600 mm ở mọi cách chia, có bài kiểm thử.

### Bán kính góc lượn ghi 0 không còn gây hiểu nhầm

Ghi 0 nghĩa là "để phần mềm tự lấy" (2 lần chiều dày thành), không phải "góc
nhọn tuyệt đối" — góc nhọn thì pháp tuyến đổi hướng 90° trong quãng đường bằng
0, máy phải xoay tại chỗ, không cắt được. Trước đây phần mềm thay số âm thầm nên
gõ 0 rồi thấy máy báo R6 thì rất dễ tưởng nó bỏ qua.

Nay số thật được **ghi thẳng vào ô nhập**, và dòng mô tả phôi nói rõ "phần mềm
tự lấy vì ô bán kính để 0". Muốn góc nhỏ hơn thì gõ số cụ thể, phần mềm dùng
đúng số đó.

### Khác

* Bỏ hai cục kê tròn trong khung mô phỏng máy — chỉ để làm mốc nhìn, mà nhìn xấu.
* Nhãn phôi trong khung mô phỏng ghi đúng dạng tiết diện: ống hộp ghi `□50×50`
  chứ không ghi `⌀60` như trước.
* Thêm 10 bài kiểm thử. Tổng cộng **185**.

## v1.5.0 — 2026-09-04

### Làm lại toàn bộ giao diện: thêm màu và có nền tối

Trước đây màu nằm rải rác trong sáu tệp, mỗi chỗ tự chọn một kiểu, và chỉ có
một chế độ hiển thị xám nhạt. Nay gom hết vào **một bảng màu duy nhất**
(`pipecut/palette.py`), nên đổi tông hay thêm chế độ mới chỉ phải sửa một chỗ.

Tông màu lấy theo **FreeCAD**: khung nhìn nền chuyển sắc xanh lam đặc trưng,
khung điều khiển xám trung tính, điểm nhấn xanh dương.

* **Nút ◐ ở góc trên bên phải** đổi qua lại nền sáng / nền tối, có ghi nhớ cho
  lần mở sau.
* **Màu có nghĩa chứ không phải trang trí:** đỏ cam là đường cắt, xanh dương là
  vạch dấu, xanh lá là vào/ra dao, xám nét đứt là chạy không. Nút xanh dương là
  lệnh làm máy chạy (Kết nối, Về gốc, Sinh G-code, Bắt đầu cắt), nút đỏ là lệnh
  nguy hiểm (Bật nguồn cắt, DỪNG) — trước đây mọi nút đều xám như nhau.
* **Phôi và máy trong khung nhìn giữ màu kim loại ở cả hai chế độ.** Ban đầu tôi
  cho chúng chạy theo màu nền, sang chế độ tối thì thân ống hoá đen thui không
  nhìn ra hình khối; FreeCAD cũng không đổi màu vật thể theo giao diện.
* **Bản vẽ SVG xuất ra theo đúng tông màu đang xem**, kèm nền chuyển sắc thật
  cho ảnh chụp máy. Ở dòng lệnh chỉ định bằng `--theme light|dark`.

Mọi cặp chữ/nền ở cả hai chế độ đều **đã soát theo tiêu chuẩn tương phản WCAG
AA** (4,5:1 cho chữ, 3:1 cho nét vẽ), và có bài kiểm thử giữ mức đó về sau. Ba
màu bị bắt lỗi ngay trong lúc làm và đã chỉnh lại: chữ mờ ở cả hai chế độ, chữ
trắng trên nút xanh nền sáng, và nét chạy không ở nền sáng. Chữ trên nút màu
giờ tự chọn đen hay trắng theo độ sáng của nền, vì cùng một màu "nguy hiểm"
nhưng ở nền sáng thì đậm còn ở nền tối lại nhạt.

### Sửa lỗi bản xem trước không tự căn khung

Thẻ **Xem trước** luôn hiện biên dạng dồn vào góc trên bên trái, tỉ lệ báo
`0.00 px/mm`. Nguyên nhân: khung vẽ căn khung ngay lúc nạp dữ liệu, mà lúc đó
thẻ chưa hiện nên canvas mới chỉ 1×1 px. Nay căn lại đúng một lần khi khung vẽ
có kích thước thật, và chỉ một lần — để người dùng phóng to hay kéo lệch rồi thì
chỉnh cửa sổ không làm mất khung nhìn họ đang đặt.

Lỗi này có từ trước, không liên quan tới việc đổi màu.

### Khác

* Nhãn cạnh huy hiệu trạng thái không còn lặp lại chữ "Chưa kết nối" nữa mà chỉ
  đường cho người dùng biết làm gì tiếp.
* `pipecut/palette.py` **không nạp Tkinter**, nên phần sinh G-code, xuất SVG và
  các bài kiểm thử vẫn chạy được trên máy không có môi trường đồ hoạ — có bài
  kiểm thử riêng giữ đúng điều này.
* Thêm 11 bài kiểm thử cho bảng màu, trong đó có một bài quét mã nguồn để bắt
  màu cứng lọt ra ngoài bảng màu. Tổng cộng **175**.

## v1.4.3 — 2026-09-04

### Nhận diện cổng USB gắn trong của ESP32-S3

`pipecut ports` và ô chọn cổng trong giao diện trước đây chỉ biết các chip cầu
USB-UART (CP2102, CH340, FTDI). ESP32-S3 có USB **nối thẳng vào chip** nên hiện
ra dưới mã nhà sản xuất của Espressif, không khớp mẫu nào và bị bỏ trống phần
ghi chú. Nay nhận ra:

* `303A:1001` → "ESP32-S3 USB gắn trong - cổng USB"
* `303A:1002` → "ESP32-S3 USB-OTG"

Việc này có ích thực tế vì bo **S3-DevKitC-1 có hai cổng USB-C cạnh nhau**: cổng
**USB** đi thẳng vào chip (Linux là `/dev/ttyACM*`), cổng **UART** đi qua chip
cầu (`/dev/ttyUSB*`). Cắm sai cổng là không thấy máy, mà trước đây danh sách
cổng không giúp phân biệt được.

### Tự dùng cỡ bộ đệm nhận mà máy tự khai

FluidNC và Grbl 1.1 đều khai số block planner và cỡ bộ đệm nhận ở cuối dòng
`[OPT:...]`, ví dụ `[OPT:VL,16,128]`. Trước đây phần mềm bỏ qua dòng này và luôn
dùng con số dè dặt 127 ghi trong hồ sơ máy. Nay đọc và **nới ra theo số máy
báo** (chỉ nới, không bao giờ thu nhỏ hơn hồ sơ đã khai), nên phần nạp lệnh đếm
ký tự giữ bộ đệm gần đầy đúng mức và planner nhìn trước xa hơn.

Thêm `protocol.parse_options()` kèm kiểm thử, và bốn bài kiểm thử cho phần này.

### Tài liệu

Chuyển **ESP32-S3 thành lựa chọn đứng đầu** trong hướng dẫn và README, thêm mục
2.2 về hai cổng USB của bo S3-DevKitC-1 và cách phân biệt.

## v1.4.2 — 2026-09-04

### Thêm cấu hình FluidNC cho ESP32-S3

Bản đồ chân của ESP32-S3 khác hẳn ESP32 gốc nên tệp cấu hình cũ không dùng lẫn
được. Thêm `firmware/fluidnc_pipe4axis_s3.yaml`, giữ nguyên toàn bộ thông số
chuyển động, chỉ đổi bảng chân:

* **`gpio 22, 23, 24, 25` không tồn tại trên S3** — Espressif loại hẳn bốn số
  này (`SOC_GPIO_VALID_GPIO_MASK` che đúng bốn bit đó). Tệp cấu hình cho ESP32
  gốc dùng `gpio 22` làm chân dò chạm và `gpio 23` làm ENABLE chung, nạp vào S3
  là FluidNC báo "Unavailable GPIO".
* `gpio 26..32` chip nhớ flash chiếm, `gpio 33..37` PSRAM loại octal chiếm — tệp
  cho ESP32 gốc dùng 34/35/36 làm công tắc hành trình nên cũng xung đột.
* Bảng chân mới cho S3: X = 4/5, Y = 6/7, Z = 15/16, A = 17/18, ENABLE chung =
  21, hành trình = 8/9/10, dò chạm = 11, rơ-le = 12.
* S3 **không có chân "chỉ vào"** nên ba công tắc hành trình treo được bên trong,
  không phải hàn điện trở 10k như bên ESP32 gốc.

### Hướng dẫn phân biệt hai dòng chip

Bổ sung mục 2.5 trong hướng dẫn và bảng đối chiếu trong README: bo nào nạp bản
firmware nào (`wifi` cho ESP32 gốc, `wifi_s3` cho S3 — S3 không có bản `bt` vì
không có Bluetooth Classic), dùng tệp cấu hình nào, cách nhận ra bo mình đang
có, và cách kiểm tra một tệp `.bin` đã tải là dựng cho chip nào (`esptool.py
image_info`; mã chương trình nạp ở `0x42000000` là S3, ở `0x400D0000` là gốc).

Ghi rõ S3 chỉ có 4 kênh RMT, vừa đủ 4 trục, hết thì đổi sang `engine: Timed`.

## v1.4.1 — 2026-09-04

### Sửa lỗi chân GPIO trong tệp cấu hình FluidNC mẫu

Đối chiếu lại `firmware/fluidnc_pipe4axis.yaml` với chính mã nguồn FluidNC
(`GPIOPinDetail::GetDefaultCapabilities`) thì thấy bốn lỗi thật, đã sửa:

* **Ba chân hành trình ghi `:pu` trên chân 34/35/36** — nhóm chân 34–39 của ESP32
  là loại *chỉ vào* và **không có điện trở treo bên trong**. FluidNC in ra lỗi
  `does not support :pu attribute`, chân bị bỏ lửng nên công tắc hành trình báo
  lung tung. Nay bỏ `:pu` và ghi rõ phải hàn điện trở 10k lên 3V3 bên ngoài.
* **Rơ-le nguồn cắt đặt ở `gpio 2`** — vừa là chân quyết định chế độ khởi động,
  vừa nối đèn LED trên bo. Nguy hiểm thật sự: mỏ cắt có thể phụt một nhát lúc
  bật nguồn. Đổi sang `gpio 21`, là chân thường.
* **STEP của trục X đặt ở `gpio 12`** — chân này bị kéo cao lúc khởi động là
  ESP32 chọn sai điện áp flash rồi treo hẳn. Đổi sang `gpio 32`.
* **STEP/DIR đặt ở `gpio 14` và `gpio 15`** — hai chân này phát xung PWM ngay khi
  cấp điện. Đổi sang các chân thường.

Bảng chân mới: X = 32/33, Y = 25/26, Z = 27/13, A = 18/19, ENABLE chung = 23,
hành trình = 34/35/36, dò chạm = 22, rơ-le = 21. Đã soát không trùng chân nào và
không còn chân nào thuộc nhóm có vấn đề khi khởi động.

Tiêu đề bo đổi từ "ESP32 DevKit / MKS DLC32" thành "ESP32 DevKit (WROOM-32) + 4
driver rời" cho đúng: MKS DLC32 đẩy xung qua thanh ghi dịch I2S nên phải khai
chân kiểu `I2SO.x` với `engine: I2S_STREAM`, không dùng được `gpio.x` như tệp
này; hơn nữa đó là bo 3 trục, không đủ cho máy 4 trục.

### Hướng dẫn nạp firmware

Thêm mục **2. Nạp và cấu hình FluidNC** đầy đủ trong hướng dẫn và một mục tương
ứng trong README: nạp bản nào (**bản `wifi`, không phải `bt`** — ESP32 chỉ có một
bộ thu phát vô tuyến nên FluidNC tách làm hai bản firmware), trình tự
`install-fs` rồi `install-wifi`, cách xử lý khi nạp lỗi, và bảng đầy đủ những
chân ESP32 không được dùng kèm hệ quả nếu dùng sai.

## v1.4.0 — 2026-09-03

### Nhập biên dạng từ bốn nguồn ngoài

Hình đã vẽ ở phần mềm khác thì nạp thẳng vào, không phải vẽ lại. Nguyên công
`pattern` giờ đọc được:

| Định dạng | Đọc được những gì |
|---|---|
| **DXF** | LINE, CIRCLE, ARC, ELLIPSE, LWPOLYLINE *(kể cả cung bulge)*, POLYLINE, SPLINE *(De Boor, đúng vector nút)*; tự quy đơn vị theo `$INSUNITS`; lọc theo lớp |
| **SVG** | `path` đủ lệnh M L H V C S Q T A Z, `rect` *(kể cả bo góc `rx`/`ry`)*, `circle`, `ellipse`, `polyline`, `polygon`, `line`, `transform` lồng nhau |
| **G-code phẳng** | G0/G1/G2/G3 *(cả kiểu I/J lẫn kiểu R, R âm cho cung lớn)*, G90/G91, G20/G21 — cửa ngõ để dùng **CAM bất kỳ** |
| **STL / OBJ** | Mô hình 3D chi tiết đã cắt — tự dò ra đường cắt trên mặt phôi |

Điểm quan trọng: biên dạng nhập vào đi **đúng dây chuyền xử lý của biên dạng tự
sinh** — bù bề rộng mạch cắt, vào/ra dao, bo góc, chèn điểm gãy theo tiết diện,
chiến lược vượt góc ống hộp, bù tốc độ tổng hợp bốn trục. Nạp vào rồi thì không
còn phân biệt hình tự vẽ hay hình nhập nữa.

Một tệp chứa nhiều đường thì nạp hết, mỗi đường thành một biên dạng riêng.

Thêm ô **Xoay biên dạng** và **Lật** (theo chiều dọc ống hoặc chiều chu vi), và
ô **Khép kín** nhận thêm lựa chọn `auto` — theo đúng tệp gốc.

### Nhận mô hình 3D thì tự chỉnh những gì

Không phải "chỉ nhận dạng rồi để đấy". Trình tự tự động: dò trục phôi → dò tâm
tiết diện và bù góc xoay → tách mặt phôi gốc khỏi mặt cắt mới bằng khoảng cách
có dấu → lấy ranh giới giữa hai phần làm đường cắt → trải phẳng và gỡ cuộn →
soát lại việc khai báo phôi → rồi đi tiếp đúng dây chuyền chung.

Đường cắt quấn trọn một vòng quanh phôi (cắt đứt, vát đầu ống) được nhận ra và
đánh dấu riêng, khác với vòng kín tại chỗ (lỗ, rãnh).

Kiểm chứng bằng cách dựng lưới của một nhát cắt lượn sóng đã biết trước phương
trình rồi cho thuật toán đọc lại: sai lệch **dưới 1e-6 mm**.

Khai sai tiết diện phôi thì **cảnh báo rõ chỗ sai** chứ không lặng lẽ cho ra
đường cắt sai — bắt được cả ba nhầm lẫn hay gặp: phôi khai nhỏ quá, quên bán
kính bo góc ống hộp, và nhầm đơn vị inch.

**STEP/IGES vẫn không đọc được** (định dạng B-rep, cần cả một nhân hình học
nặng) — hãy xuất STL với sai số lưới 0,01–0,05 mm.

### Kết nối qua WiFi trong mạng LAN

Nói chuyện với ESP32 qua **Telnet** mà FluidNC mở sẵn (cổng 23), dùng đúng giao
thức `ok`/`error` như cổng COM — nên toàn bộ phần đếm ký tự, phân tích trạng
thái và lệnh thời gian thực giữ nguyên không đổi.

* Ô **Cổng / địa chỉ** trong giao diện gõ thẳng được `192.168.1.50`,
  `192.168.1.50:23` hay `fluidnc.local`; phần mềm tự nhận ra đó là địa chỉ mạng.
* Nút **Dò trong mạng LAN** quét cả dải `/24`, chạy ở luồng riêng nên giao diện
  không đứng.
* `python -m pipecut scan` làm việc tương tự ở dòng lệnh.
* `python -m pipecut sim ra.nc --serve 2323` mở **máy ảo ra cổng mạng**, thử
  trọn đường truyền WiFi khi chưa có bo mạch.

Lọc sẵn lệnh thương lượng Telnet (IAC) và gom đệm gói tin bị chia nhỏ.

> Cắt thật thì vẫn nên cắm dây: WiFi tiện cho khâu chuẩn bị, nhưng xưởng có máy
> hàn, biến tần, nguồn plasma là môi trường nhiễu nặng.

### Khác

* Lệnh mới `python -m pipecut import <tệp>` — xem trong tệp có mấy đường, dài
  bao nhiêu, khổ bao nhiêu, trước khi đưa vào công việc.
* Giao diện: nút **Chọn...** mở hộp thoại lọc sẵn theo định dạng đọc được, và
  đọc thử ngay để hiện nội dung tệp dưới ô mô tả nguyên công.
* Sửa `rect` trong SVG bỏ qua bo góc `rx`/`ry` — trước đây một hình chữ nhật bo
  góc bị đọc thành hình chữ nhật góc vuông.
* Đọc được STL nhị phân có byte thừa ở cuối (một số phần mềm ghi thêm).
* Thêm tệp mẫu: `examples/bien_dang_cua_so.dxf`,
  `examples/bien_dang_trang_tri.svg`, `examples/bien_dang_cam.nc` và công việc
  mẫu `examples/vi_du_nhap_dxf.json`.
* Bổ sung 43 bài kiểm thử (tổng cộng **160**).

## v1.3.0 — 2026-09-03

### Vượt góc ống hộp kiểu "xoay 45 độ" (`corner_mode = "pivot"`) — mặc định mới

Trình tự đúng như thợ làm bằng tay:

1. cắt hết mặt phẳng ở tốc độ chuẩn, trục A đứng yên;
2. **dừng, xoay 45°** đưa góc bo lên đỉnh — mỏ cắt vẫn đứng đúng chỗ vừa cắt
   xong trên phôi, trục ngang và trục Z phối hợp bám theo;
3. cả cung góc giờ nằm gọn quanh đỉnh nên **cắt hết cung ở tốc độ chuẩn với
   trục A đứng yên**;
4. **xoay nốt 45°** về mặt phẳng kế tiếp, mỏ vẫn bám điểm vừa cắt xong;
5. cắt tiếp.

Vì sao giữ được tốc độ: khi góc bo đã ở đỉnh, cắt hết cung 9,4 mm chỉ cần trục
ngang chạy 8,5 mm — trục A không phải quay tí nào. So với cắt liền mạch (trục A
phải quay 90° trong 9,4 mm cung, tức ~15 000 độ/phút) thì đây là trời với vực.

Đo trên cùng một nhát cắt đứt ống 50×50×3, góc lượn R6, đặt 1600 mm/phút:

| `corner_mode` | Tốc độ cắt | Dài cắt | Điểm mồi | Thời gian |
|---|---|---|---|---|
| `follow` | 377 – 1600 *(tụt ở góc)* | 194,7 mm *(đủ)* | 1 | 18 s |
| `index` | 1600 đều | 159,1 mm *(thiếu 4 cung góc)* | 5 | 23 s |
| **`pivot`** | **1600 đều** | **194,7 mm (đủ)** | 9 | 29 s |

Đánh đổi của `pivot`: ở hai đầu cung, mỏ nghiêng tới 45° so với pháp tuyến nên
mặt cắt chỗ đó không vuông góc; và tốn thêm 2 điểm mồi mỗi góc.

Khe hở mỏ–phôi được kiểm chứng giữ đúng 1,600 ± 0,001 mm trên toàn bộ đường
chạy của cả ba chế độ.

### Khác

* Sửa cách tính chiều dài cắt: không cộng phần trục Z nhấp nhô theo mặt phôi
  nữa — đó là chuyển động của mỏ trong không gian, còn vết cắt chỉ tiến theo bề
  mặt. Trước đây chiều dài cắt ống hộp bị thổi phồng ~20%.
* Hồ sơ máy mặc định chuyển sang `pivot`; thêm `config/machine_box_pivot.json`.
* Kiểm thử tăng từ 109 lên **117 bài**, trong đó có bài kiểm tra trục A đứng yên
  suốt pha cắt cung, mỗi lần xoay đúng 45°, và mỏ giữ nguyên một điểm trên phôi
  trong lúc xoay.

## v1.2.0 — 2026-09-03

### Thứ tự cắt: giữ đúng như người dùng xếp

Trước đây phần mềm **tự sắp xếp lại** thứ tự cắt mà không có cách nào tắt, nên
xếp đúng thứ tự trong bảng rồi máy vẫn cắt theo thứ tự khác. Nay:

* mặc định **giữ nguyên thứ tự trong bảng**, không tự đổi;
* có ô *Tự sắp xếp thứ tự cắt* trên giao diện để bật khi cần;
* dòng chữ dưới bảng luôn hiện **thứ tự cắt thật sự** sẽ chạy;
* nếu tự xếp mà có nguyên công nằm ngoài một nhát cắt đứt phía trước, phần mềm
  **cảnh báo** (lúc đó phần phôi đó đã rơi ra) chứ không tự ý đổi thứ tự.

### Thư viện nguyên công lọc theo dạng phôi

Máy chỉ cắt ống hộp thì không cần thấy *miệng cá* và *lỗ xuyên thành* — hai
biên dạng đó là bài toán giao hai mặt trụ, chỉ có nghĩa với ống tròn. Danh sách
thêm nguyên công nay tự lọc theo hình dạng phôi đang khai báo, và hồ sơ máy mặc
định `config/machine_default.json` đã chuyển sang **ống hộp**
(`config/machine_round.json` dành cho máy cắt ống tròn).

### Điều khiển vào dao

Thêm hai thông số để chọn chỗ vết mồi rơi vào:

* **Vị trí điểm mồi** (`lead_start`, % chu vi biên dạng) — xoay điểm bắt đầu
  quanh biên dạng, ví dụ đưa vết mồi vào giữa một cạnh thay vì đúng góc bo, hoặc
  chuyển nhát cắt đứt sang bắt đầu ở mặt khác;
* **Phía vào dao** (`lead_side`) — `inside`/`outside` với biên dạng kín,
  `plus`/`minus` với nhát cắt quanh phôi (mồi lệch về đầu tự do hay về mâm cặp).

### Chế độ dừng cắt — xoay góc — cắt tiếp (ống hộp)

`corner_mode = "index"`: cắt hết một mặt phẳng thì **tắt mỏ, nhấc lên, ba trục
phối hợp giữ mỏ bám đúng góc đó trên phôi trong lúc mâm quay 90°, quay xong hạ
xuống mồi lại rồi cắt mặt kế tiếp**. Nhờ vậy tốc độ cắt trên mặt phẳng luôn đúng
như đặt, không bị trục xoay kéo tụt ở góc.

Đổi lại bốn cung góc lượn không được cắt nên phôi chưa rời hẳn — phần mềm cảnh
báo rõ. Đặt `corner_torch_off = false` thì mỏ vẫn cháy suốt lúc xoay nên cắt
luôn cả góc. Hồ sơ mẫu: `config/machine_box_index.json`.

### Khác

* Sửa lỗi mỏ cắt hạ xuống cao độ cắt **trước khi** quay xong ở chế độ index
  (cắm vào thành phôi 0,13 mm).
* Pha xoay góc được vẽ bằng nét đứt trong hai khung xem trước (vì không cắt).
* Kiểm thử tăng từ 92 lên **109 bài**.

## v1.1.0 — 2026-09-03

### Hỗ trợ ống hộp (vuông và chữ nhật)

Trước đây phôi luôn là ống tròn. Nay khai báo được **hình dạng tiết diện**:
ống tròn nhập đường kính, ống hộp nhập cạnh ngang (và cạnh dọc nếu là hộp chữ
nhật) cùng bán kính góc lượn.

Mỏ cắt **luôn vuông góc với bề mặt phôi** ở mọi loại tiết diện. Phần mềm xoay
trục A sao cho pháp tuyến chỗ đang cắt hướng thẳng lên, dùng trục X đưa mỏ cắt
tới đúng vị trí trên mặt, và trục Z bù chênh cao ở góc lượn:

| Vị trí | A | X | Z |
|---|---|---|---|
| Ống tròn, mọi nơi | quay đều | 0 | không đổi |
| Ống hộp, trên mặt phẳng | đứng yên | chạy dọc mặt | không đổi |
| Ống hộp, qua góc lượn | xoay 90° | bám cung | nhô lên rồi hạ xuống |

Với ống tròn, phép ánh xạ tự rút gọn về X = 0 và Z không đổi, nên hành vi cắt
ống tròn **không đổi một chút nào** so với bản trước.

### Sửa lỗi quan trọng đi kèm

* **Không rút gọn điểm một cách ngây thơ nữa.** Trên mặt trải phẳng, nhát cắt
  quanh ống hộp là đường thẳng, nhưng trong không gian bốn trục thì không:
  nội suy thẳng sẽ cho mỏ cắt cắm vào góc lượn. Nay phần mềm chèn đỉnh tại mọi
  chỗ đổi hình (mặt phẳng ↔ góc lượn) và chia nhỏ theo sai lệch đo trong không
  gian trục. Trên mặt phẳng và với ống tròn, sai lệch bằng 0 nên không thêm
  điểm thừa nào.
* **Sửa cú nhảy 360° của trục A** khi đường cắt đi qua mốc 0 trên ống hộp.
* **Sửa ước tính thời gian** trong tab Xem trước (trước đây bỏ sót các đoạn
  nâng/hạ trục Z).

### Cảnh báo và chế độ tốc độ đều

Qua góc lượn, trục A phải quay 90° trong đoạn cung rất ngắn — ống 50×50 góc lượn
R6 cần tới ~15 000 độ/phút để giữ tốc độ cắt 1600 mm/phút. Đây là giới hạn cơ
khí, không phải lỗi. Phần mềm kẹp tốc độ theo khả năng thật của từng trục và
**cảnh báo bằng con số cụ thể**. Bật `uniform_feed` để cả đường chạy ở một tốc
độ bề mặt duy nhất — chậm hơn nhưng vết cắt đồng đều từ mặt phẳng sang góc lượn.

### Khác

* Nguyên công *miệng cá* và *lỗ xuyên thành* chỉ áp dụng cho ống tròn (là bài
  toán giao hai mặt trụ); với ống hộp phần mềm báo rõ lý do thay vì cắt sai.
* Định vị theo góc (`theta`) nay tính theo **hướng nhìn từ tâm**, nên "rãnh ở
  90 độ" nằm đúng giữa mặt bên của ống hộp chứ không rơi vào mép.
* Hồ sơ máy mới `config/machine_box.json`, ví dụ `examples/vi_du_ong_hop.json`.
* Trục ngang mặc định lấy hành trình đối xứng (−100…100 mm) quanh đường tâm phôi.
* CLI nhận `--profile` ở cả trước lẫn sau tên lệnh con, thêm `--shape`,
  `--width`, `--height`.
* Bộ kiểm thử tăng từ 72 lên **92 bài**, trong đó có bài dựng lại vị trí mũi cắt
  từ chính G-code (kể cả các điểm giữa hai lệnh) để chứng minh khe hở mỏ–phôi
  luôn đúng bằng cao độ cắt.

## v1.0.1 — 2026-09-03

Bản phát hành đầu tiên dùng được đầy đủ của **PipeCut Studio**: phần mềm máy
tính điều khiển máy cắt ống 4 trục chạy ESP32 + FluidNC qua cổng COM.

### Bố trí trục

Khớp với máy có **phôi ống tự tịnh tiến**:

| Trục | Vai trò | Đơn vị |
|---|---|---|
| **Y** | ống ra vào (bàn mang mâm cặp chạy dọc trục ống) | mm |
| **A** | mâm cặp xoay ống | độ |
| **X** | mỏ cắt chạy ngang, vuông góc trục Y | mm |
| **Z** | mỏ cắt lên xuống | mm |

Vai trò trục khai báo trong hồ sơ máy, đổi được sang kiểu **xe mỏ cắt chạy còn
ống đứng yên** bằng `"layout": "torch_moves"`.

### Sinh biên dạng

10 nguyên công, toán giao tuyến suy trực tiếp từ phương trình mặt trụ:
cắt đứt/cắt vát, miệng cá (chữ T, chữ Y, lệch tâm), lỗ xuyên thành ống
(hướng tâm hoặc xiên), rãnh/cửa sổ bo góc, tròn trên bề mặt, xoắn ốc,
đường dọc thân ống, vạch dấu vòng, vát mép hàn, và biên dạng trải phẳng
tự do nạp từ DXF/CSV.

### Đường cắt mượt nhờ bốn trục phối hợp

* **Bù tốc độ tổng hợp** — FluidNC cộng *độ* của trục xoay chung với *mm* của
  trục thẳng khi chia `F`. Phần mềm tính lại F cho từng đoạn theo
  `F = v_cắt × L_trục / L_bề_mặt`, giữ **tốc độ mũi cắt trên bề mặt ống không
  đổi** ở mọi tỉ lệ phối hợp trục (đo được sai số < 0,5 mm/phút).
* **Điều tiết mật độ điểm** — lấy mẫu thích nghi theo dung sai dây cung, rút gọn
  Douglas–Peucker, gộp đoạn quá ngắn, chia đoạn quá dài.
* **Nạp lệnh đếm ký tự** — giữ bộ đệm ESP32 luôn gần đầy (đo được 124/127 byte)
  để planner luôn có hàng chục block nhìn trước.
* Mọi xử lý làm trên **mặt trụ trải phẳng** (phép đẳng cự) nên bù kerf, bo góc
  và đo chiều dài đều chính xác tuyệt đối; góc quay biến thiên liên tục, không
  bao giờ nhảy ±180°.

### Giao diện

Sáu tab theo trình tự làm việc: Máy & Kết nối → Điều khiển → Công việc →
Xem trước → **Mô phỏng** → Chạy.

* **Mô phỏng 3D** dựng lại đúng máy thật: đoạn ống dài theo kích thước nhập vào,
  trượt ra vào và quay dưới mỏ cắt, vết cắt đỏ hiện dần trên phôi. Chạy offline,
  tua tới lui, tốc độ 0,25×–20×, xoay/dịch/phóng bằng chuột, xuất ảnh SVG.
  Khi nối máy thật, khung này bám theo vị trí máy báo về.
* Điều khiển tay có jog theo vai trò trục, DRO, về gốc, đặt gốc chi tiết,
  bảng nhật ký giao tiếp và ô gõ lệnh trực tiếp.
* Chạy chương trình có thanh tiến độ, tô sáng dòng đang chạy, tạm dừng
  (feed hold) và dừng khẩn.

### Công cụ khác

* **Máy ảo FluidNC** dựng sẵn: dùng thử toàn bộ phần mềm khi chưa có phần cứng
  (chọn cổng `GIA-LAP`).
* **CLI** đầy đủ: `ports`, `ops`, `gen`, `preview`, `sim`, `send`, `run`, `demo`.
* Xuất bản vẽ xem trước SVG (trải phẳng + hình chiếu trục đo, ẩn nét khuất).
* Ba hồ sơ máy mẫu, cấu hình FluidNC cho ESP32, bốn tệp công việc mẫu.
* Mã lỗi và báo động Grbl/FluidNC dịch sang tiếng Việt.

### Kiểm thử

72 bài kiểm thử chạy bằng thư viện chuẩn (`python -m unittest discover -s tests -t .`),
gồm bài dựng lại điểm 3D để kiểm tra biên dạng giao tuyến nằm đồng thời trên cả
hai mặt trụ, và bài đo tốc độ bề mặt trên toàn bộ một đường miệng cá.

### Yêu cầu

Python 3.9 trở lên. Chỉ cần `pyserial` khi nối cổng COM thật; phần sinh G-code và
mô phỏng chạy bằng thư viện chuẩn. Giao diện dùng Tkinter (có sẵn cùng Python trên
Windows/macOS; Linux cài thêm `python3-tk`).
