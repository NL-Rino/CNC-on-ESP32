"""Cuong ep ve tram sac khi pin xuong qua thap.

Bo nao hoc duoc thi tot, nhung mot bo nao chua hoc xong ma het pin giua nha
la mot cuc gach 30 cm nam giua loi di. Lop nay chay TREN MAY TINH (trong
link/brain_server.py), doc cung mot vector quan sat, va khi pin cham nguong
thi no CAT quyen dieu khien cua bo nao roi tu lai xe ve.

Ba diem quan trong:

  - Xe VAN nhan du LiDAR va moi cam bien trong suot duong ve. Day khong phai
    che do mu; chi la nguoi cam lai doi tu mang no-ron sang bo luat cung.
  - Khong phai lop phan xa an toan. Phan xa vuc nam tren ESP32 vi no phai
    tra loi trong 170 ms. Cai nay chi la chuyen "ai lai xe", cham hon nhieu,
    nen nam tren may tinh cung duoc.
  - KHONG bat trong luc huan luyen. Bat thi bo nao duoc cuu moi lan, va no
    se khong bao gio hoc cach tu ve.
"""
from sim.perception import OBS_NAMES
from train.baseline import ReactiveController

NGUONG = 0.15           # san cung: pin cham muc nay la cat quyen, bat ke gi
NHA_KHI_DAY = 0.92      # sac toi day thi tra quyen lai cho bo nao
I_BATT = OBS_NAMES.index("battery")
I_MARGIN = OBS_NAMES.index("return_margin")


def mac_dinh(threshold=NGUONG, seed=0):
    """Lop cuong ep dung san, da noi dung chi so trong vector quan sat."""
    return Failsafe(I_BATT, threshold, seed, I_MARGIN)


class Failsafe:
    """Boc quanh mot ham act(obs). Goi y het, nhung co the doi nguoi lai.

    Cat quyen khi MOT TRONG HAI dieu sau xay ra:

      - Pin xuong duoi `threshold` (mac dinh 15%). Day la san cung.
      - BIEN AN TOAN xuong 0: pin con khong du de ve tram nua, theo chinh
        muc hao moi met ma xe do duoc tu dau chuyen di.

    Dieu thu hai moi la cai dung. Do thuc te: pin 15% chi con 7,9 giay chay
    ga day, tuc **2,2 m** - trong khi phong rong 3-3,8 m. Doi den 15% moi
    quay dau thi tu goc xa nhat la khong ve kip, chua ke con phai tim va
    canh truc. Bien an toan thi tu noi rong ra theo khoang cach: dung ngay
    canh tram thi no cham 12%, o goc xa 3 m thi no cham tu 39%.
    """

    def __init__(self, i_batt, threshold=NGUONG, seed=0, i_margin=None):
        self.i_batt = i_batt          # chi so muc pin trong vector quan sat
        self.i_margin = i_margin      # chi so bien an toan (None = khong dung)
        self.threshold = threshold
        self.home = ReactiveController(seed, force_low=True)
        self.reset()

    def reset(self):
        self.home.reset()
        self.taken = False
        self.steps_taken = 0
        self.trips = 0
        self.batt_prev = 1.0

    def act(self, obs, policy_act):
        """Tra ve ((ga_trai, ga_phai), dang_cuong_ep)."""
        batt = float(obs[self.i_batt])
        charging = batt > self.batt_prev + 1e-6
        self.batt_prev = batt

        if not self.taken:
            # "Chua he cam sac" the hien ngay o muc pin: neu da cam duoc thi
            # pin da len roi, khong the con o muc nay.
            het_bien = (self.i_margin is not None
                        and float(obs[self.i_margin]) <= 0.0)
            if (batt <= self.threshold or het_bien) and not charging:
                self.taken = True
                self.trips += 1
                self.home.reset()
        elif charging and batt >= NHA_KHI_DAY:
            self.taken = False            # sac gan day roi, tra lai bo nao

        if self.taken:
            self.steps_taken += 1
            return self.home.act(obs), True
        return policy_act(obs), False
