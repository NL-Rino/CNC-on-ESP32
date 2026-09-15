// Chay bo nao GRU da huan luyen tren ESP32 (float, khong can thu vien ngoai).
// ~2k tham so -> vai chuc KB RAM, mot buoc suy luan < 0.2 ms tren ESP32 240MHz.
#pragma once

#ifdef __cplusplus
extern "C" {
#endif

// Thu tu 20 dau vao PHAI khop voi sim/env.py (OBS_NAMES):
//  0..4  sieu am trai90, trai45, truoc, phai45, phai90  (chia cho 2.0 m)
//  5,6   cam bien vuc truoc / sau                       (0 hoac 1)
//  7,8   hong ngoai kenh GOI: cuong do, co thay khong
//  9,10  hong ngoai kenh TRAM SAC: cuong do, co thay khong
//  11,12 thay doi cuong do hong ngoai (goi, sac) * 8, ket o [-1,1]
//  13,14 muc pin (0..1), co dang yeu pin khong
//  15    van toc / v_max          16  toc do quay / omega_max
//  17,18 lenh dong co buoc truoc (trai, phai)
//  19    dang va cham (0/1)
typedef struct {
    float h[64];   // trang thai an, nho >= BRAIN_HID
} brain_state_t;

void brain_reset(brain_state_t *st);

// obs: mang BRAIN_OBS phan tu. out: 2 phan tu trong [-1,1] (trai, phai).
void brain_step(brain_state_t *st, const float *obs, float *out);

#ifdef __cplusplus
}
#endif
