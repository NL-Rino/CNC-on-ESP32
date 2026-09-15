# Thiet ke mo phong & huan luyen

## 1. Vi sao mo phong truoc

Xe that chay 1 tap 45 giay; mot the he ES can ~256 tap. Tren may nay mot tap
mat ~75 ms, tuc **1 the he ~5 giay tren 4 nhan**, va 500 the he ~40 phut.
Neu lam tren xe that thi mat 4 thang lien tuc — va moi lan roi khoi ban la
mot lan gay xe. Mo phong khong phai de "cho vui": no la cach duy nhat de
thuat toan tien hoa nay chay duoc.

## 2. The gioi (`sim/world.py`)

- Mat ban hinh chu nhat, kich thuoc **ngau nhien moi tap** 1.8–3.0 m × 1.4–2.4 m.
  Ra khoi bien = roi khoi ban = ket thuc tap, phat −40.
- 1–6 vat can ngau nhien (hop hoac tru).
- Tram sac dat sat mot canh ngau nhien, co **huong cam** — xe phai vao dung
  huong ±51° va dung yen moi nap duoc pin.
- Den goi (kenh IR khac) hien ra o thoi diem ngau nhien (buoc 20–240), o vi tri
  cach xe it nhat 0.6 m, va **tu tat sau 200–500 buoc** neu xe khong toi kip.

Moi thu ngau nhien lai o moi tap (domain randomization) de bo nao khong hoc thuoc
long mot cai ban cu the.

## 3. Dong luc hoc xe (`sim/robot.py`)

```
v_banh(t+1) = v_banh + (u·v_max − v_banh)·dt/(tau+dt) + nhieu_truot
v = (v_trai + v_phai)/2          omega = (v_phai − v_trai)/wheel_base
```

| Tham so | Gia tri | Ghi chu |
|---|---|---|
| `v_max` | 0.60 m/s | toc do banh o PWM 100% |
| `motor_tau` | 0.12 s | do tre dong co — quyet dinh quang duong phanh |
| `deadband` | 0.06 | PWM duoi muc nay banh khong quay |
| `wheel_base` | 0.15 m | |
| `radius` | 0.09 m | dung cho va cham |
| `slip_noise` | 2% | 2 ben khong bao gio bang nhau → xe luon lech |

**Quang duong phanh** tu 0.6 m/s khi dao chieu het ga ≈ 3.3 cm, cong 1 chu ky
dieu khien 50 ms ≈ 3 cm → ~6.5 cm. Cam bien vuc dat cach tam **10.5 cm**, nen
xe *vua du* cuu duoc o toc do toi da. Day la con so quan trong nhat cua toan bo
thiet ke: **neu tren xe that cam bien vuc gan tam hon hoac vong dieu khien cham
hon 50 ms, phai giam `v_max`** — neu khong xe se roi ban du bo nao hoc tot the nao.

## 4. Cam bien (`sim/sensors.py`)

| Cam bien | Mo hinh | Loi that duoc mo phong |
|---|---|---|
| 5 × sieu am | raycast 3 tia trong chum ±7.5°, lay min, tam 2 m | nhieu σ=1.2 cm, **2% mat echo → bao 2 m (trong)**, vung mu 3 cm |
| 2 × cam bien vuc | do cao diem cach tam ±10.5 cm | nhieu σ=3 mm quanh nguong 4.5 cm |
| 1 × mat thu IR | `cuong_do = lobe(goc)·1/(1+(d/0.9)²)`, goc thu ±46°, bi vat can che | nhieu σ=0.03 |
| Pin | hao `0.0016 + 0.0075·tai` / giay | het pin = ket thuc tap, −25 |

Sieu am **khong** thay mep ban: tia chieu ngang di thang ra ngoai va khong co
gi doi ve. Day la ly do phai co 2 cam bien chieu xuong.

Mat thu IR chi co **mot**, nen dau vao khong chua "huong cua den". Bo nao phai
xoay, nho lai cuong do buoc truoc va suy ra huong — vi the co them 2 dau vao
`d_ir` (do chenh lech cuong do so voi buoc truoc) va bo nao la GRU.

## 5. Dau vao/dau ra cua bo nao (20 → 2)

```
 0..4  sieu am trai90 trai45 truoc phai45 phai90   (chia 2.0 m)
 5,6   vuc truoc, vuc sau                          (0/1)
 7,8   IR kenh GOI: cuong do, co thay              9,10  IR kenh SAC: cuong do, co thay
11,12  thay doi cuong do IR (goi, sac)             13,14 muc pin, co dang yeu pin
15,16  van toc, toc do quay (chuan hoa)            17,18 lenh dong co buoc truoc
19     dang va cham
```

Ra: `tanh` → `(ga_trai, ga_phai)` trong `[-1,1]`, nhan thang vao PWM 2 cap banh.

Bo nao **chi** nhin thay tung nay — dung bang tin hieu phan cung that se co.
Thong tin "toan tri" (vi tri that cua den goi, cua tram sac) chi dung trong
**phan thuong** luc huan luyen, khong bao gio di vao dau vao.

## 6. Phan thuong (`sim/env.py`, lop `EnvConfig`)

| Khoan | He so | Y nghia |
|---|---|---|
| `w_fall` | −40 | roi khoi ban, ket thuc tap |
| `w_flat` | −25 | het pin, ket thuc tap |
| `w_bump` | −1.2/buoc | dang cham vat can |
| `w_cliff` | −0.8/buoc | cam bien vuc keu ma van tien ve phia do |
| `w_progress` | +14/m | tien gan muc tieu dang hoat dong |
| `w_arrive` | +40 | vao trong 0.25 m cua den goi |
| `w_dock` / `w_charge` | +15 / +150·ΔPin | cam trung tram sac / luong pin nap duoc |
| `w_speed` | +0.6·v | chay long nhong: thuong di toi |
| `w_novel` | +6 / o luoi 0.3 m moi | thuong **di cho moi** — neu khong xe se chi chay vong tron |
| `w_spin`, `w_energy`, `w_smooth` | −0.25, −0.008, −0.04 | phat quay tai cho, hao dien, giat ga |

Thuong "di cho moi" va thuong "di nhanh" chi tinh khi **khong co muc tieu nao**
dang bat — nho vay xe khong bo nhiem vu de di lang thang cho diem.

Co ban `--curriculum` vi thuong o cap 2–3 rat **thua**: neu tha ngay vao bai
day du, ES gan nhu khong bao gio tinh co tim ra tram sac. Cap 0 day "song sot",
cap 1 day "ne", roi moi den "tim".

## 7. Vi sao Evolution Strategies chu khong phai PPO

1. Phan thuong thua va co nho (POMDP): GRU + ES khong can lan truyen nguoc
   qua thoi gian, nen it cho sai hon nhieu.
2. 4 nhan CPU, khong GPU: ES song song gan nhu tuyen tinh, moi worker chi can
   gui ve **mot so** (diem cua ca the).
3. Bo nao chi ~1.8k tham so — dung ngay vung ES manh nhat.

Chi tiet: lay mau doi xung (`+εσ`, `−εσ`) de khu phuong sai, chuan hoa theo
**thu hang** de mot tap may man khong lam lech ca the he, Adam + weight decay,
va **dung chung seed cho ca quan the trong moi the he** (common random numbers)
— neu khong, ES chi dang so sanh do may cua tung tap chu khong phai do gioi.

## 8. Tu mo phong ra doi that

Nhung cho gan nhu chac chan lech, can do lai tren xe that roi sua trong
`sim/robot.py` / `sim/sensors.py` va huan luyen lai (vai chuc phut):

1. `v_max`, `motor_tau`, `deadband` — do bang cach cho xe chay 1 m va quay video.
2. Chu ky vong dieu khien. HC-SR04 doc tuan tu 5 cai co the ton 5×30 ms = 150 ms,
   qua cham. Phai doc xen ke (mot cai moi chu ky) hoac dung loai I2C/TOF.
3. Nguong cam bien vuc thuc te, va do tre cua no.
4. Dac tuyen cuong do IR that: bit den lai, do gia tri ADC/so xung theo goc va
   khoang cach, roi thay ham `lobe·atten`.
5. Duong cong xa pin that (Li-ion khong tuyen tinh).

Meo: giu **nhieu trong mo phong hoi lon hon doi that**. Bo nao quen song trong
moi truong "ban" se chiu duoc moi truong sach, chieu nguoc lai thi khong.
