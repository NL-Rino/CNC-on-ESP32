// Tim tram sac (hop 15 x 15 cm) trong mot vong quet LiDAR.
// Ban C cua sim/dock_detector.py - GIU HAI BEN GIONG NHAU, neu sua mot ben
// ma quen ben kia thi bo nao se gap du lieu khac luc huan luyen.
#pragma once
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define DOCK_MAX_CAND 2   // phai bang MAX_CAND trong sim/dock_detector.py

typedef struct {
    float bearing;   // rad, 0 = thang truoc mat xe
    float dist;      // m
    float width;     // m, be rong doan do duoc
    float depth;     // m, do cong so voi day cung
    int   npts;
    float score;     // 0..1, cang gan 15 cm va cang phang thi cang cao
} dock_cand_t;

// scan: mang `n` khoang cach (m) theo goc tang dan tu -pi den +pi,
//       0 nghia la khong co tia phan hoi. Ham CO SUA mang nay (va diem mat).
// cos_a/sin_a: bang cos/sin cua tung goc, tinh san mot lan luc khoi dong.
// out: toi da DOCK_MAX_CAND ung vien, GAN NHAT truoc.
// Tra ve so ung vien tim duoc.
int dock_detect(float *scan, const float *cos_a, const float *sin_a, int n,
                float bearing_offset, dock_cand_t *out);

#ifdef __cplusplus
}
#endif
