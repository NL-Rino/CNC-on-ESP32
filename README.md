# Xe tu hanh 2 banh — mo phong + "nuoi" AI truoc, phan cung sau

Muc tieu: nuoi mot bo nao biet **chay long nhong khong roi khoi ban**, **di toi
cho co den hong ngoai goi**, va **tu tim tram sac khi pin yeu** — huan luyen
hoan toan trong mo phong, sau do nap xuong ESP32.

Toan bo chay bang Python 3 + numpy, khong can GPU, khong can thu vien RL.

```bash
pip install numpy
python3 tests/test_sim.py                      # kiem tra mo phong
python3 -m train.evaluate --baseline --episodes 20   # moc so sanh viet tay
python3 -m train.train --curriculum --jobs 4 --gens 500 --out runs/car
python3 -m train.evaluate --policy runs/car/best.npz --ascii --seed 7
```

## Chiec xe trong mo phong

| Bo phan | Mo hinh |
|---|---|
| 2 cap banh DC trai/phai | dieu khien vi sai, 2 lenh PWM trong `[-1,1]`, co tre motor (tau=0.12s), vung chet PWM, truot banh ngau nhien |
| 5 sieu am | goc **-90°, -45°, 0°, +45°, +90°**, tam 2 m, chum tia ±7.5°, nhieu 1.2 cm, 2% lan do bi **mat echo** |
| 2 cam bien vuc | chieu xuong o **dau** va **duoi** xe (cach tam 10.5 cm), bao truoc khi tam xe ra toi mep ban |
| 1 mat thu hong ngoai | dat o dau xe, goc thu ±46°, **2 kenh tan so**: kenh GOI (nguoi dung goi xe toi) va kenh TRAM SAC |
| Cam bien pin | muc pin 0..1, hao theo tai dong co, nap lai khi cam dung tram sac |

Mep ban **khong** hien ra tren sieu am (sieu am chieu ngang khong thay ho sau) —
dung nhu ngoai doi. Chi 2 cam bien chieu xuong cuu duoc xe.

Chi co **mot** mat thu hong ngoai, nen muon biet den phat tu huong nao thi xe
phai **xoay va so sanh cuong do theo thoi gian**. Vi vay bo nao la mot mang
**GRU co tri nho**, khong phai mang thuan.

## Bo nao va cach "nuoi"

- `train/policy.py` — GRU nho (~1.8k tham so, mac dinh 16 no-ron an).
  Vao: 20 so tu cam bien. Ra: 2 so = ga trai / ga phai.
- `train/es.py` — **Evolution Strategies**: moi the he sinh 64 ban sao dot bien
  cua bo nao, cho tung ban song thu vai tap mo phong, roi dich bo gen ve phia
  cac ban song tot. Khong can dao ham, chay song song 4 nhan CPU.
- `train/train.py` — **chuong trinh hoc tang cap** (`--curriculum`):

  | Cap | Bai hoc | Dieu kien len cap |
  |---|---|---|
  | 0 | ban trong: dung roi khoi mep, di cho rong | roi < 10%, di qua >= 14 o luoi |
  | 1 | them vat can: tranh dung | them va cham thap |
  | 2 | den goi bat ngau nhien: tim va di toi | >= 1 lan toi dich/tap |
  | 3 | pin + tram sac: tu di sac khi yeu | (cap cuoi) |

Phan thuong (`sim/env.py`, doi duoc het): roi khoi ban −40, het pin −25, va cham
−1.2/buoc, tien gan muc tieu +14/m, toi dich +40, sac +150/don vi pin, di nhanh
+0.6·v, o luoi moi +6, phat quay tai cho / hao dien / giat ga.

## Xem xe chay

```bash
# ngay tren terminal
python3 -m train.evaluate --policy runs/car/best.npz --ascii --seed 7

# xuat file HTML xem tren trinh duyet (co tia sieu am, pin, IR, duong da di)
python3 -m train.evaluate --policy runs/car/best.npz --record demo.json --episodes 5
python3 tools/make_replay.py demo.json viz/replay.html
```

## Sang phan cung (lam sau)

```bash
python3 tools/export_c.py runs/car/best.npz firmware/policy_weights.h
```

`firmware/brain.c` chay dung mang do tren ESP32 (~0.2 ms/buoc, khong can thu
vien ngoai). Chi tiet chan cam, thu tu doc cam bien va lop phan xa an toan:
xem `firmware/README.md`. Thiet ke chi tiet + ghi chu sim-to-real:
xem `docs/DESIGN.md`.

## Cau truc

```
sim/     mo phong: the gioi, dong luc hoc xe, cam bien, phan thuong, ve ASCII
train/   bo nao GRU, ES, vong huan luyen, cham diem, bo dieu khien viet tay
tools/   xuat trong so ra C, dung file replay HTML
firmware/ ma C chay bo nao tren ESP32 (phan cung lam sau)
tests/   kiem tra mo phong
```
