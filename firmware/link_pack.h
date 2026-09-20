// Dong goi / mo goi tin cho che do "nao tu xa" (link/protocol.py).
// Tach khoi .ino de doi chieu duoc bang may: tests/test_firmware.py bien
// dich file nay roi kiem tra tung byte voi ban Python. Offset lech mot byte
// la thu khong the go duoc khi da nam tren xe.
#pragma once
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define LINK_MAGIC0 'C'
#define LINK_MAGIC1 'B'
#define LINK_VER    1
#define LINK_T_STATE 1
#define LINK_T_SCAN  2
#define LINK_T_CMD   3

#define LINK_F_CLIFF_F  (1u<<0)
#define LINK_F_CLIFF_R  (1u<<1)
#define LINK_F_BUMP     (1u<<2)
#define LINK_F_CHARGING (1u<<3)
#define LINK_F_REFLEX   (1u<<4)
// Tiep diem sac dang cham. Khac LINK_F_CHARGING: cham tiep diem chua chac
// co dien (con phai bat tay hong ngoai). Nho bit nay ma xe vua bat nguon
// trong hoc la biet ngay tram cua no o dau, khong can nhin thay gi.
#define LINK_F_ON_DOCK  (1u<<5)

#define LINK_HDR_SIZE   12
#define LINK_STATE_SIZE (LINK_HDR_SIZE + 60)
#define LINK_CMD_SIZE   (LINK_HDR_SIZE + 16)
#define LINK_SCAN_SIZE(n) (LINK_HDR_SIZE + 12 + 2 * (n))

typedef struct {
    float x, y, th;       // odometry
    float v, w;
    float battery;
    // BA mat thu moi kenh: trai, giua, phai. Mot mat chi biet co thay hay
    // khong; ba mat thi ti le cuong do giua chung cho ra HUONG cua den.
    float ir_call[3], ir_dock[3];
    float u_applied_l;    // ga THUC SU vao dong co, khong phai ga duoc yeu cau
    float u_applied_r;
    uint8_t flags;
} link_state_t;

// Tra ve so byte da ghi.
int link_pack_state(uint8_t *buf, uint32_t seq, uint32_t t_ms,
                    const link_state_t *st);
int link_pack_scan(uint8_t *buf, uint32_t seq, uint32_t t_ms,
                   const float *scan_m, int n, float theta, uint32_t t_scan_ms);

// Tra ve 1 neu la goi CMD hop le va *ack_seq khop `expect_seq`.
// expect_seq = 0 nghia la nhan bat ky seq nao.
int link_parse_cmd(const uint8_t *buf, int len, uint32_t expect_seq,
                   float *ul, float *ur, uint32_t *ack_seq, uint8_t *flags);

#ifdef __cplusplus
}
#endif
