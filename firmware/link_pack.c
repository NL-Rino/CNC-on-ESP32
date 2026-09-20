#include <string.h>

#include "link_pack.h"

static void put_u16(uint8_t *p, int o, uint16_t v) { memcpy(p + o, &v, 2); }
static void put_u32(uint8_t *p, int o, uint32_t v) { memcpy(p + o, &v, 4); }
static void put_f32(uint8_t *p, int o, float v)    { memcpy(p + o, &v, 4); }
static float get_f32(const uint8_t *p, int o) { float v; memcpy(&v, p + o, 4); return v; }
static uint32_t get_u32(const uint8_t *p, int o) { uint32_t v; memcpy(&v, p + o, 4); return v; }

static int put_header(uint8_t *p, uint8_t type, uint32_t seq, uint32_t t_ms)
{
    p[0] = LINK_MAGIC0;
    p[1] = LINK_MAGIC1;
    p[2] = LINK_VER;
    p[3] = type;
    put_u32(p, 4, seq);
    put_u32(p, 8, t_ms);
    return LINK_HDR_SIZE;
}

int link_pack_state(uint8_t *buf, uint32_t seq, uint32_t t_ms,
                    const link_state_t *st)
{
    int o = put_header(buf, LINK_T_STATE, seq, t_ms);
    put_f32(buf, o +  0, st->x);
    put_f32(buf, o +  4, st->y);
    put_f32(buf, o +  8, st->th);
    put_f32(buf, o + 12, st->v);
    put_f32(buf, o + 16, st->w);
    put_f32(buf, o + 20, st->battery);
    for (int i = 0; i < 3; ++i) {
        put_f32(buf, o + 24 + 4 * i, st->ir_call[i]);
        put_f32(buf, o + 36 + 4 * i, st->ir_dock[i]);
    }
    put_f32(buf, o + 48, st->u_applied_l);
    put_f32(buf, o + 52, st->u_applied_r);
    buf[o + 56] = st->flags;
    buf[o + 57] = 0;
    buf[o + 58] = 0;
    buf[o + 59] = 0;
    return o + 60;
}

int link_pack_scan(uint8_t *buf, uint32_t seq, uint32_t t_ms,
                   const float *scan_m, int n, float theta, uint32_t t_scan_ms)
{
    int o = put_header(buf, LINK_T_SCAN, seq, t_ms);
    put_u16(buf, o + 0, (uint16_t)n);
    put_f32(buf, o + 2, theta);
    put_u32(buf, o + 6, t_scan_ms);
    put_u16(buf, o + 10, 0);                  // 2 byte chen cho thang hang
    int base = o + 12;
    for (int i = 0; i < n; ++i) {
        long mm = 0;
        if (scan_m[i] > 0.0f) {
            mm = (long)(scan_m[i] * 1000.0f + 0.5f);
            if (mm > 65535) mm = 65535;
        }
        put_u16(buf, base + 2 * i, (uint16_t)mm);
    }
    return base + 2 * n;
}

int link_parse_cmd(const uint8_t *buf, int len, uint32_t expect_seq,
                   float *ul, float *ur, uint32_t *ack_seq, uint8_t *flags)
{
    if (len < LINK_CMD_SIZE) return 0;
    if (buf[0] != LINK_MAGIC0 || buf[1] != LINK_MAGIC1 ||
        buf[2] != LINK_VER || buf[3] != LINK_T_CMD) return 0;
    uint32_t ack = get_u32(buf, LINK_HDR_SIZE + 8);
    if (expect_seq != 0 && ack != expect_seq) return 0;
    if (ul) *ul = get_f32(buf, LINK_HDR_SIZE + 0);
    if (ur) *ur = get_f32(buf, LINK_HDR_SIZE + 4);
    if (ack_seq) *ack_seq = ack;
    if (flags) *flags = buf[LINK_HDR_SIZE + 12];
    return 1;
}
