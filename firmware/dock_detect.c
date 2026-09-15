#include <math.h>

#include "dock_detect.h"

#define BAY_OUT       0.40f
#define BAY_DEPTH     0.355f
#define WIDTH_MIN     0.26f
#define WIDTH_MAX     0.52f
#define DEPTH_MIN     0.14f
#define DEPTH_MAX     0.60f
#define BULGE_MAX     0.05f
#define WIDTH_PRE     0.95f
#define SHRINK_ITERS  6
#define BACK_BAND     0.08f
#define BACK_MIN_PTS  5
#define MIN_PTS       6
#define MIN_DIST      0.12f
#define MAX_DIST      3.0f
#define GAP_ABS       0.45f
#define GAP_REL       0.20f
#define PATCH_JUMP    0.06f

static void patch_dropouts(float *r, int n)
{
    float prev = r[0];          // giu ban goc de khong lan truyen diem vua va
    for (int i = 1; i < n - 1; ++i) {
        float cur = r[i];
        if (cur <= 0.0f && prev > 0.0f && r[i + 1] > 0.0f &&
            fabsf(prev - r[i + 1]) < PATCH_JUMP) {
            r[i] = 0.5f * (prev + r[i + 1]);
        }
        prev = cur;
    }
}

static int cut_here(const float *r, int i)
{
    float a = r[i], b = r[i + 1];
    if (a <= 0.0f || b <= 0.0f) return 1;
    float lo = a < b ? a : b;
    return fabsf(b - a) > GAP_ABS + GAP_REL * lo;
}

static void insert_sorted(dock_cand_t *out, int *cnt, const dock_cand_t *c)
{
    int i = *cnt;
    if (i < DOCK_MAX_CAND) {
        ++(*cnt);
    } else if (c->dist >= out[DOCK_MAX_CAND - 1].dist) {
        return;
    } else {
        i = DOCK_MAX_CAND - 1;
    }
    while (i > 0 && out[i - 1].dist > c->dist) {
        out[i] = out[i - 1];
        --i;
    }
    out[i] = *c;
}

int dock_detect(float *scan, const float *cos_a, const float *sin_a, int n,
                float bearing_offset, dock_cand_t *out)
{
    patch_dropouts(scan, n);

    int count = 0;
    int seg = 0;
    for (int i = 0; i < n; ++i) {
        if (i != n - 1 && !cut_here(scan, i)) continue;

        int a = seg, b = i + 1;        // doan [a, b)
        seg = b;
        if (b - a < MIN_PTS) continue;

        // --- loc so bo theo hai dau doan ---
        float xa = scan[a] * cos_a[a], ya = scan[a] * sin_a[a];
        float xb = scan[b - 1] * cos_a[b - 1], yb = scan[b - 1] * sin_a[b - 1];
        float ex = xb - xa, ey = yb - ya;
        float w0 = sqrtf(ex * ex + ey * ey);
        if (w0 < WIDTH_MIN || w0 > WIDTH_PRE) continue;
        float c0x = 0.5f * (xa + xb), c0y = 0.5f * (ya + yb);
        float d0 = sqrtf(c0x * c0x + c0y * c0y);
        if (d0 < MIN_DIST || d0 > MAX_DIST) continue;

        // --- co day cung vao cho het loi (xem chu thich ban Python) ---
        float wdt = 0.0f, mx = 0.0f, my = 0.0f, nx = 0.0f, ny = 0.0f;
        float x0 = 0.0f, y0 = 0.0f;
        int ok = 0;
        for (int it = 0; it < SHRINK_ITERS; ++it) {
            x0 = scan[a] * cos_a[a];
            y0 = scan[a] * sin_a[a];
            ex = scan[b - 1] * cos_a[b - 1] - x0;
            ey = scan[b - 1] * sin_a[b - 1] - y0;
            wdt = sqrtf(ex * ex + ey * ey);
            if (wdt < WIDTH_MIN || b - a < MIN_PTS) break;
            mx = x0 + 0.5f * ex;
            my = y0 + 0.5f * ey;
            nx = -ey / wdt;
            ny = ex / wdt;
            if (nx * mx + ny * my < 0.0f) { nx = -nx; ny = -ny; }

            int j = 0;
            float worst = 0.0f;
            for (int k = a; k < b; ++k) {
                float d = (scan[k] * cos_a[k] - x0) * nx +
                          (scan[k] * sin_a[k] - y0) * ny;
                if (k == a || d < worst) { worst = d; j = k - a; }
            }
            if (worst >= -BULGE_MAX) { ok = 1; break; }
            if (j * 2 < b - a) a += j; else b = a + j + 1;
        }
        if (!ok || wdt < WIDTH_MIN || wdt > WIDTH_MAX) continue;

        float dmax = 0.0f;
        for (int k = a; k < b; ++k) {
            float d = (scan[k] * cos_a[k] - x0) * nx +
                      (scan[k] * sin_a[k] - y0) * ny;
            if (k == a || d > dmax) dmax = d;
        }
        if (dmax < DEPTH_MIN || dmax > DEPTH_MAX) continue;
        float dist = sqrtf(mx * mx + my * my);
        if (dist < MIN_DIST || dist > MAX_DIST) continue;

        // --- truc hoc: khop duong thang qua lop diem sau nhat (thanh trong) ---
        double sx = 0.0, sy = 0.0;
        int nb = 0;
        for (int k = a; k < b; ++k) {
            float d = (scan[k] * cos_a[k] - x0) * nx +
                      (scan[k] * sin_a[k] - y0) * ny;
            if (d > dmax - BACK_BAND) {
                sx += scan[k] * cos_a[k];
                sy += scan[k] * sin_a[k];
                ++nb;
            }
        }
        if (nb >= BACK_MIN_PTS) {
            double bx = sx / nb, by = sy / nb;
            double sxx = 0.0, syy = 0.0, sxy = 0.0;
            for (int k = a; k < b; ++k) {
                float d = (scan[k] * cos_a[k] - x0) * nx +
                          (scan[k] * sin_a[k] - y0) * ny;
                if (d <= dmax - BACK_BAND) continue;
                double ux = scan[k] * cos_a[k] - bx;
                double uy = scan[k] * sin_a[k] - by;
                sxx += ux * ux; syy += uy * uy; sxy += ux * uy;
            }
            double ang = 0.5 * atan2(2.0 * sxy, sxx - syy);
            float fx = (float)(-sin(ang)), fy = (float)cos(ang);
            if (fx * mx + fy * my < 0.0f) { fx = -fx; fy = -fy; }
            nx = fx; ny = fy;
        }

        float ws = 1.0f - fabsf(wdt - BAY_OUT) / 0.16f;
        if (ws < 0.0f) ws = 0.0f;
        float ds = 1.0f - fabsf(dmax - BAY_DEPTH) / 0.24f;
        if (ds < 0.0f) ds = 0.0f;
        float score = ws * ds;
        if (score <= 0.05f) continue;

        dock_cand_t c;
        c.bearing = atan2f(my, mx) + bearing_offset;
        c.yaw = atan2f(ny, nx) + bearing_offset;
        if (c.bearing > (float)M_PI) c.bearing -= 2.0f * (float)M_PI;
        else if (c.bearing < -(float)M_PI) c.bearing += 2.0f * (float)M_PI;
        if (c.yaw > (float)M_PI) c.yaw -= 2.0f * (float)M_PI;
        else if (c.yaw < -(float)M_PI) c.yaw += 2.0f * (float)M_PI;
        c.dist = dist;
        c.width = wdt;
        c.depth = dmax;
        c.npts = b - a;
        c.score = score;
        insert_sorted(out, &count, &c);
    }
    return count;
}
