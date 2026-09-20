"""Dinh dang goi tin giua robot (ESP32) va bo nao (laptop), qua UDP.

Vi sao UDP chu khong phai TCP: vong dieu khien chay 20 Hz va chi quan tam
du lieu MOI NHAT. TCP gap mat goi se dung lai de gui lai goi cu - dung cai
ma ta khong muon: mot goi cam bien tre 300 ms con te hon la mat han no.

Ba loai goi:
  STATE  robot -> nao, 20 Hz, 72 byte   (odometry, pin, vuc, 6 mat IR, ga)
  SCAN   robot -> nao,  7 Hz, ~886 byte (mot vong quet LiDAR)
  CMD    nao -> robot, 20 Hz, 28 byte   (ga trai/phai)

Tat ca little-endian de khoi phai doi byte tren ESP32 (cung little-endian).
Ben C xem firmware/robot_link.ino - HAI BEN PHAI GIU GIONG NHAU.
"""
import struct

MAGIC = b"CB"
VERSION = 1
PORT = 4210

T_STATE = 1
T_SCAN = 2
T_CMD = 3

HDR = struct.Struct("<2sBBII")        # magic, ver, type, seq, t_ms
# ox oy oth v omega batt, ir_call[3], ir_dock[3], ul_ap ur_ap, co
# BA mat thu moi kenh (trai, giua, phai). Mot mat thi chi biet co thay hay
# khong chu khong biet den o dau; ba mat thi ti le cuong do cho ra huong.
# ul_ap/ur_ap la ga THUC SU vao dong co, khong phai ga bo nao vua yeu cau.
# Hai so nay khac nhau moi khi lop phan xa an toan can thiep hoac watchdog
# cat dien - va bo nao phai biet dieu do, vi "lenh buoc truoc" la mot trong
# 46 dau vao cua no. Thieu no thi trang thai GRU tren laptop se troi khoi
# thuc te dung luc robot dang gap chuyen.
STATE = struct.Struct("<14fB3x")
SCAN = struct.Struct("<HfI2x")        # so diem, goc luc quet, thoi diem quet
CMD = struct.Struct("<2fIB3x")        # ga trai, ga phai, seq da xu ly, co

F_CLIFF_F = 1 << 0
F_CLIFF_R = 1 << 1
F_BUMP = 1 << 2
F_CHARGING = 1 << 3
F_REFLEX = 1 << 4      # robot dang tu xu ly phan xa an toan, bo qua lenh
F_ON_DOCK = 1 << 5     # tiep diem sac dang cham (dang nam trong hoc).
                       # Khac F_CHARGING: cham tiep diem chua chac co dien,
                       # con phai bat tay hong ngoai da. Nho bit nay ma xe
                       # vua bat nguon trong hoc la biet tram o dau ngay.
F_CMD_CHARGE_OK = 1 << 0


def _hdr(kind, seq, t_ms):
    return HDR.pack(MAGIC, VERSION, kind, seq & 0xFFFFFFFF, t_ms & 0xFFFFFFFF)


def parse(buf):
    """Tra ve (loai, seq, t_ms, phan than) hoac None neu goi khong hop le."""
    if len(buf) < HDR.size:
        return None
    magic, ver, kind, seq, t_ms = HDR.unpack_from(buf, 0)
    if magic != MAGIC or ver != VERSION:
        return None
    return kind, seq, t_ms, buf[HDR.size:]


# ------------------------------------------------------------------- STATE
def pack_state(seq, t_ms, odo, v, omega, battery, ir, flags, u_applied=(0.0, 0.0)):
    """ir = [[goi_trai, goi_giua, goi_phai], [sac_trai, sac_giua, sac_phai]]."""
    return _hdr(T_STATE, seq, t_ms) + STATE.pack(
        odo[0], odo[1], odo[2], v, omega, battery,
        ir[0][0], ir[0][1], ir[0][2], ir[1][0], ir[1][1], ir[1][2],
        u_applied[0], u_applied[1], flags)


def unpack_state(body):
    (ox, oy, oth, v, w, batt, c0, c1, c2, d0, d1, d2,
     ula, ura, flags) = STATE.unpack_from(body, 0)
    return {"odo": (ox, oy, oth), "v": v, "omega": w, "battery": batt,
            "ir": [[c0, c1, c2], [d0, d1, d2]], "u_applied": (ula, ura),
            "cliff": (1.0 if flags & F_CLIFF_F else 0.0,
                      1.0 if flags & F_CLIFF_R else 0.0),
            "bumped": bool(flags & F_BUMP),
            "charging": bool(flags & F_CHARGING),
            "on_dock": bool(flags & F_ON_DOCK),
            "reflex": bool(flags & F_REFLEX)}


# -------------------------------------------------------------------- SCAN
def pack_scan(seq, t_ms, ranges_m, scan_theta, t_scan_ms):
    """Khoang cach gui bang uint16 don vi MILIMET: 1 mm du min so voi nhieu
    thuc te 1-3 cm cua Camsense, ma chi ton nua so byte so voi float32.
    0 = khong co tia phan hoi."""
    n = len(ranges_m)
    out = bytearray(_hdr(T_SCAN, seq, t_ms))
    out += SCAN.pack(n, scan_theta, t_scan_ms & 0xFFFFFFFF)
    mm = bytearray(2 * n)
    struct.pack_into("<%dH" % n, mm, 0,
                     *[min(65535, int(r * 1000.0 + 0.5)) if r > 0.0 else 0
                       for r in ranges_m])
    out += mm
    return bytes(out)


def unpack_scan(body):
    n, scan_theta, t_scan_ms = SCAN.unpack_from(body, 0)
    off = SCAN.size
    if len(body) < off + 2 * n:
        return None
    mm = struct.unpack_from("<%dH" % n, body, off)
    return {"n": n, "scan_theta": scan_theta, "t_scan_ms": t_scan_ms, "mm": mm}


# --------------------------------------------------------------------- CMD
def pack_cmd(seq, t_ms, u_left, u_right, ack_seq, flags=0):
    return _hdr(T_CMD, seq, t_ms) + CMD.pack(
        float(u_left), float(u_right), ack_seq & 0xFFFFFFFF, flags)


def unpack_cmd(body):
    ul, ur, ack, flags = CMD.unpack_from(body, 0)
    return {"u": (ul, ur), "ack_seq": ack, "flags": flags}


def sizes(n_points=432):
    return {"STATE": HDR.size + STATE.size,
            "SCAN": HDR.size + SCAN.size + 2 * n_points,
            "CMD": HDR.size + CMD.size}
