# PipeCut C — bản thử viết bằng C thuần (Win32 + GDI)

Câu hỏi: *viết lại phần mềm bằng C thuần, chỉ dùng Win32 + GDI có sẵn trong
Windows, không thư viện ngoài, thì có làm được như bản hiện tại không?*

**Làm được.** Thư mục này là bản thử chạy thật, đủ một vòng làm việc: nhập phôi →
thêm nguyên công → sinh G-code → mô phỏng 3D → nối máy (cổng COM hoặc WiFi) →
chạy chương trình. Nó chưa làm được mọi thứ bản Python làm (xem cuối trang), nhưng
những phần khó nhất đã có và đã đối chiếu từng con số với bản Python.

| | Bản Python (PipeCut Studio 1.14) | Bản C này (0.1) |
|---|---|---|
| Tệp phát hành | bộ cài 11,6 MB, bản chạy liền 16,3 MB | **một tệp `PipeCutC.exe` 231 KB** (zip ~180 KB) |
| Cần gì để chạy | tự mang theo Python bên trong | chỉ DLL có sẵn của Windows (user32, gdi32, comctl32, comdlg32, ws2_32, advapi32, shell32, msvcrt) |
| Vẽ một khung 3D (1280×800) | 20–22 ms (Canvas của Tkinter) | **1,2–3,2 ms** trên Windows (máy của GitHub), 5,7 ms trong Wine |
| Lượng mã | ~14 900 dòng Python | ~4 200 dòng C |
| Kiểm thử tự động | 315 bài | tự kiểm `--selftest` + đối chiếu số với bản Python |

## Đã đối chiếu với bản Python

Phần lõi chuyển nguyên công thức từ `pipecut/section.py`, `kinematics.py`,
`planner.py`, rồi so từng số:

* **Tư thế máy khi cắt vuông góc mặt ống** (A, X, Z theo vị trí chu vi): lệch tối
  đa 1,4·10⁻⁸ trên ống tròn D60, D114,3 và các ống hộp 50×50, 80×40 bo 6,
  40×40, 100×50 — kể cả sát mốc 360°.
* **Chiều cao mặt phôi dưới mỏ** theo góc xoay: lệch ≤ 5·10⁻¹⁰.
* **Thời gian chạy tính như FluidNC** (tăng/giảm tốc từng trục, junction deviation,
  hàng đợi 32 khối, dừng hẳn ở M3/M5/G4): **khớp tới micro giây** trên 6 chương
  trình mẫu của bản Python và 2 chương trình do bản C sinh.
* **G-code bản C sinh ra**: sai số tư thế 6·10⁻¹⁴ mm; tốc độ trên mặt ống giữ
  1600 mm/ph (chỉ lệch do làm tròn số và ngưỡng đổi F; qua góc ống hộp tụt còn
  ~375 vì trục A chạm tốc độ tối đa — bản Python cũng vậy, 379); lỗ D20/D16 ra đúng bán kính
  sau bù kerf (9,25 / 7,25 mm, lệch dưới 0,006 mm do chia đoạn).
* **Chạy trên Windows thật** (máy Windows của GitHub, mỗi lần đẩy mã): tự kiểm ra
  đúng các con số trên, 6 ảnh 3D đều vẽ đủ, chụp được cả ba thẻ của cửa sổ.
* **Nạp lệnh qua mạng** tới máy FluidNC ảo của bản Python (`pipecut/simulator.py`):
  gửi đủ 813/813 dòng, **đúng từng ký tự và đúng thứ tự**, máy ảo dừng đúng điểm cuối
  chương trình. Cho máy ảo báo động giữa chừng: bản C dừng ngay, ghi
  "BÁO ĐỘNG 1: Chạm công tắc hành trình cứng…".

## Có gì trong bản thử

**Phôi** — ống tròn, ống hộp vuông / chữ nhật (bo góc tự tính hoặc nhập tay).

**Nguyên công** — cắt đứt (cả cắt xiên), lỗ khoan xuyên ống tròn, lỗ tròn trên
mặt, rãnh chữ nhật bo góc. Có bù kerf, vào dao, chạy vượt. Tự sắp thứ tự như máy
laser cắt ống: làm xong từng chi tiết từ đầu tự do vào, lỗ/rãnh trước nhát cắt đứt
của chính chi tiết đó, trong nhóm thì đi đường gần nhất theo thời gian máy.

**G-code FluidNC** — bù tốc độ tổng hợp cho trục xoay, không trục nào bị ép quá
tốc độ tối đa, dòng lệnh ngắn (chỉ ghi chữ số thay đổi).

**Mô phỏng 3D bằng GDI** — cùng cách dựng với bản Python 1.14: đổ bóng theo ánh
sáng, cột + cần + mỏ cắt đặc, béc đồng, hồ quang sáng khi cắt, đường sắp cắt nét
đứt / đã cắt nét đậm, chữ "hở … mm", bảng toạ độ, ba trục ở góc. Kéo trái để xoay,
kéo phải để dịch, lăn chuột phóng quanh con trỏ, nháy đúp đổi vùng cắt ↔ toàn cảnh.
Thanh trượt thời gian, tốc độ 0,5×–20×; ở thẻ G-code dòng đang chạy được tô sáng.
Vẽ vào bộ nhớ rồi mới chép ra nên không nháy.

**Máy** — cổng COM (tự liệt kê) hoặc địa chỉ WiFi (`192.168.1.50`,
`fluidnc.local`, `host:cổng`, mặc định telnet 23). Nạp lệnh kiểu đếm ký tự (bộ đệm
127 byte), hỏi trạng thái 5 lần/giây, về gốc, mở khoá, nhích 4 trục, đặt gốc Y / A
tại chỗ mỏ đang đứng ("chỉ đâu cắt đó"), chạy / tạm dừng / chạy tiếp / dừng khẩn,
gõ lệnh tay, nhật ký có giải nghĩa mã lỗi và báo động bằng tiếng Việt. Khung 3D có
thể bám theo vị trí máy thật.

**Khác** — mở G-code sẵn có để mô phỏng và gửi, lưu G-code, nhớ thiết lập ở
`%APPDATA%\PipeCutC\settings.ini`.

## Chưa có (bản Python có)

* Nhập bản vẽ DXF / SVG / G-code phẳng / STL-OBJ và thư viện biên dạng (giao tuyến
  ống chữ T, cắt ghép góc, miệng cá…).
* Căn tâm mâm cặp bằng 4 lần chạm, dò cạnh / dò chạm bằng mỏ cắt.
* Chiến lược vượt góc ống hộp (xoay tại góc, mồi lại ở mép), mồi trượt vào đường
  vào dao, chạy không kiểu nhảy ếch có kiểm va chạm (bản C nhấc thẳng lên rồi đi).
* Hồ sơ máy JSON (nhiều kiểu máy, đổi tên trục, trục vát); bản C dùng cố định thông
  số của `config/machine_round.json`.
* Lưu / mở công việc, xuất SVG, giao diện nền tối, máy ảo "GIA-LAP", quét tìm bo
  trong mạng LAN, chỉnh tốc độ khi đang chạy.
* GDI không khử răng cưa nên cạnh đường chéo hơi răng cưa hơn bản Python.

Mỗi mục trên chuyển sang C được, không vướng gì về kỹ thuật — chỉ tốn công: ước
chừng bản C đầy đủ sẽ dài gấp 2–3 lần bản Python, và 315 bài kiểm thử cũng phải
viết lại.

## Dựng

Cần MinGW-w64 (GCC cho Windows), không cần gì khác.

* **Trên Windows:** tải [w64devkit](https://github.com/skeeto/w64devkit/releases)
  (một tệp zip, giải nén là dùng), mở `w64devkit.exe`, rồi:

  ```
  cd đường\dẫn\CNC-on-ESP32\c
  make CC=gcc WINDRES=windres
  ```

  Hoặc dùng MSYS2 (`pacman -S mingw-w64-x86_64-gcc make`), cùng lệnh trên.
* **Trên Linux:** `sudo apt install gcc-mingw-w64-x86-64` rồi `make`.

Ra hai tệp:

* `PipeCutC.exe` — giao diện.
* `pipecutc-cli.exe` — dòng lệnh: `pipecutc-cli gen round 60 ra.nc`,
  `pipecutc-cli gen box 50 50 0 3 ra.nc`, `pipecutc-cli plan ra.nc` (thời gian chạy chia
  theo cắt / chạy không / nâng hạ / xoay / chờ).

Mỗi lần đẩy mã, [GitHub Actions](../.github/workflows/c-win32.yml) dựng lại và
chạy tự kiểm trên máy Windows thật.

## Tự kiểm

```
PipeCutC.exe --selftest THƯ_MỤC
```

Sinh hai chương trình mẫu (ống tròn D60, ống hộp 50×50), ghi số dòng / số lần mồi /
chiều dài cắt / thời gian vào `selftest.txt`, vẽ 6 ảnh 3D (`round_0.bmp`…), đo tốc
độ vẽ rồi thoát. `--shot ẢNH.bmp [0|1|2]` mở cửa sổ ở thẻ đó, chụp lại rồi thoát.
`--connect 127.0.0.1:CỔNG --run` nối máy ảo và chạy luôn chương trình mẫu — chỉ
nhận địa chỉ trên chính máy tính này, **không bao giờ tự chạy máy thật**.

## Mã nguồn

```
src/core.h      kiểu dữ liệu và hàm của phần lõi (chỉ dùng thư viện chuẩn C)
src/section.c   tiết diện ống tròn / hộp, tư thế máy cắt vuông góc mặt ống
src/ops.c       nguyên công -> biên dạng trên mặt trải, bù kerf, vào dao
src/gcode.c     biên dạng -> G-code FluidNC, bù tốc độ, sắp thứ tự
src/planner.c   ước thời gian như bộ lập kế hoạch của FluidNC, trạng thái theo thời gian
src/view3d.c    khung 3D vẽ bằng GDI
src/comm.c      cổng COM / Winsock, nạp lệnh đếm ký tự, đọc trạng thái
src/ui.c        cửa sổ chính (điều khiển chuẩn của Windows)
src/cli.c       pipecutc-cli.exe
res/            biểu tượng, manifest (giao diện Windows hiện đại, DPI), thông tin phiên bản
```
