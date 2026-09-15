// Chay bo nao GRU da huan luyen tren ESP32 (float, khong can thu vien ngoai).
// ~2k tham so -> vai chuc KB RAM, mot buoc suy luan < 0.2 ms tren ESP32 240MHz.
#pragma once

#ifdef __cplusplus
extern "C" {
#endif

// Thu tu 46 dau vao PHAI khop voi sim/env.py (OBS_NAMES):
//   0..11  12 quat LiDAR (min khoang cach trong quat, chia 3.0 m, ket o [0,1])
//          quat 0 bat dau tu -180 do, moi quat 30 do, quat 6 la thang truoc mat
//  12,13   cam bien vuc truoc / sau (0 hoac 1)
//  14..25  2 ung vien HOC SAC tu dock_detect(), moi cai 6 so, gan nhat truoc:
//          [co/khong, sin(goc toi cua), cos(goc toi cua), khoang cach / 3.0,
//           sin(goc TRUC hoc), cos(goc TRUC hoc)]
//          Goc truc la huong xe phai quay ve de chui vao thang. Khong co no
//          thi khong the canh vao khe chi ho 5 mm moi ben.
//  26,27   hong ngoai kenh GOI: cuong do, co thay khong
//  28,29   hong ngoai kenh TRAM SAC: cuong do, co thay khong
//  30,31   thay doi cuong do hong ngoai (goi, sac) * 8, ket o [-1,1]
//  32..37  tri nho tram sac theo odometry:
//          [co nho khong, sin(goc), cos(goc), khoang cach / 3.0,
//           sin(huong truc), cos(huong truc)]
//          Nho ca huong truc vi hoc chi chui vao duoc tu mot phia.
//  38      muc pin (0..1)
//  39      co dang yeu pin khong (pin < 0.40)
//  40      BIEN AN TOAN = pin con - pin uoc tinh de ve toi tram, ket o [-1,1]
//          uoc tinh = (pin hao moi met do duoc tu dau chuyen di) * quang duong
//          ve tram * 2.0 + 0.12.  Day la phan "kinh nghiem" cua xe.
//  41      van toc / v_max          42  toc do quay / omega_max
//  43,44   lenh dong co buoc truoc (trai, phai)
//  45      dang va cham (0/1)
typedef struct {
    float h[64];   // trang thai an, nho >= BRAIN_HID
} brain_state_t;

void brain_reset(brain_state_t *st);

// obs: mang BRAIN_OBS phan tu. out: 2 phan tu trong [-1,1] (trai, phai).
void brain_step(brain_state_t *st, const float *obs, float *out);

#ifdef __cplusplus
}
#endif
