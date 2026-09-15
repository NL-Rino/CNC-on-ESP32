# Nap bo nao xuong ESP32 (phan lam sau)

Thu muc nay chua **phan chay bo nao**, chua phai firmware hoan chinh. Muc dich
la de khi lam phan cung thi khong phai viet lai tu dau, va de biet truoc phai
do dac nhung gi.

## 1. Xuat trong so

```bash
python3 tools/export_c.py runs/car/best.npz firmware/policy_weights.h
```

Sinh ra mang `float` (~1.8k so, ~15 KB Flash). `brain.c` + `brain.h` chay dung
phep toan GRU nhu trong `train/policy.py`. Mot buoc suy luan ~0.2 ms tren
ESP32 240 MHz — thua suc chay vong 20 Hz.

## 2. Vong dieu khien 20 Hz

```
moi 50 ms:
  1. doc cam bien  -> dung mang obs[20] (thu tu trong brain.h, DUNG doi)
  2. brain_step(&st, obs, u)
  3. LOP PHAN XA AN TOAN (xem muc 4) co quyen ghi de u
  4. xuat PWM cho 2 cap banh
```

Thu tu 20 dau vao phai khop tuyet doi voi `sim/env.py` (`OBS_NAMES`) va phai
chuan hoa giong het: sieu am chia 2.0 m va ket o [0,1], cam bien vuc la 0/1,
pin 0..1, van toc chia `v_max`, `d_ir = (ir − ir_truoc) × 8` ket o [-1,1].
**Sai mot o la bo nao dien.**

## 3. Goi y phan cung

| Khoi | Linh kien | Ghi chu |
|---|---|---|
| 5 × sieu am | HC-SR04 | doc **xen ke** — moi chu ky trigger 1–2 cai, giu gia tri cu cho cac cai con lai. Doc tuan tu ca 5 ton toi 150 ms, qua cham cho vong 20 Hz. Muon nhanh/gon hon: VL53L0X (I2C, 3 ms). |
| 2 × cam bien vuc | TCRT5000 / e18-d80nk chieu xuong | dat cach tam xe >= 10.5 cm, cang xa cang an toan. Lay nguong bang cach do gia tri tren mat ban vs. khong co gi. |
| Mat thu IR | 2 module TSOP khac tan so (vd TSOP4838 38 kHz cho "goi", TSOP4856 56 kHz cho tram sac) | "Cuong do" lay bang cach dem ti le xung trong 50 ms, hoac dung photodiode + ADC. Dat o dau xe, nen co ong che de goc thu ~±45°. |
| Do pin | chia ap + ADC1 | loc trung binh truot; nho hieu chinh vi ADC ESP32 khong tuyen tinh. |
| Dong co | 2 driver (TB6612FNG / DRV8833) | LEDC PWM 20 kHz. Hai banh cung ben noi song song = 1 kenh. |

## 4. Lop phan xa an toan (BAT BUOC)

Mang no-ron co the loi. Cam bien vuc phai co duong cat thang, khong qua bo nao:

```c
if (cliff_front && u_forward > 0) { u_left = u_right = -0.7f; }  // lui ngay
if (cliff_rear  && u_forward < 0) { u_left = u_right = +0.6f; }
if (battery_volt < CUTOFF)        { u_left = u_right = 0; }      // cuu pin
```

Luc huan luyen **khong** bat lop nay, de bo nao tu hoc so mep ban; lop nay chi
la luoi do khi ra doi that.

## 5. Kiem tra truoc khi tha xe len ban

1. Cho xe chay tren san (khong co vuc) truoc, xem no co ne vat can khong.
2. Do lai `v_max`, `motor_tau` that roi sua `sim/robot.py` va huan luyen lai.
3. Dat ban thap + trai dem ben duoi trong vai chuc lan chay dau.
4. Ghi log 20 so obs ra Serial, doi chieu voi mo phong — day la cach nhanh nhat
   de phat hien sai thu tu hoac sai chuan hoa.
