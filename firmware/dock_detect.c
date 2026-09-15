#include <math.h>

#include "dock_detect.h"

#define DOCK_W        0.15f
#define WIDTH_MIN     0.10f
#define WIDTH_MAX     0.25f
#define MAX_DEPTH     0.085f
#define MIN_PTS       4
#define MAX_DIST      3.0f
#define MIN_DIST      0.10f
#define GAP_ABS       0.035f
#define GAP_REL       0.05f
#define PATCH_JUMP    0.06f

static void patch_dropouts(float *r, int n)
{
    for (int i = 1; i < n - 1; ++i) {
        if (r[i] <= 0.0f && r[i - 1] > 0.0f && r[i + 1] > 0.0f &&
            fabsf(r[i - 1] - r[i + 1]) < PATCH_JUMP) {
            r[i] = 0.5f * (r[i - 1] + r[i + 1]);
        }
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
    int start = 0;
    for (int i = 0; i < n; ++i) {
        int end_here = (i == n - 1) || cut_here(scan, i);
        if (!end_here) continue;

        int a = start, b = i + 1;      // doan [a, b)
        start = b;
        if (b - a < MIN_PTS) continue;

        float xa = scan[a] * cos_a[a], ya = scan[a] * sin_a[a];
        float xb = scan[b - 1] * cos_a[b - 1], yb = scan[b - 1] * sin_a[b - 1];
        float ex = xb - xa, ey = yb - ya;
        float width = sqrtf(ex * ex + ey * ey);
        if (width < WIDTH_MIN || width > WIDTH_MAX) continue;

        float cx = 0.5f * (xa + xb), cy = 0.5f * (ya + yb);
        float dist = sqrtf(cx * cx + cy * cy);
        if (dist < MIN_DIST || dist > MAX_DIST) continue;

        float worst = 0.0f;
        for (int k = a; k < b; ++k) {
            float dx = scan[k] * cos_a[k] - xa;
            float dy = scan[k] * sin_a[k] - ya;
            float cross = fabsf(dx * ey - dy * ex);
            if (cross > worst) worst = cross;
        }
        float depth = worst / width;
        if (depth > MAX_DEPTH) continue;

        float ws = 1.0f - fabsf(width - 0.175f) / 0.10f;
        if (ws < 0.0f) ws = 0.0f;
        float ds = 1.0f - 0.4f * (depth / MAX_DEPTH);
        float score = ws * ds;
        if (b - a < MIN_PTS + 2) score *= 0.75f;
        if (score <= 0.05f) continue;

        dock_cand_t c;
        c.bearing = atan2f(cy, cx) + bearing_offset;
        if (c.bearing > (float)M_PI) c.bearing -= 2.0f * (float)M_PI;
        else if (c.bearing < -(float)M_PI) c.bearing += 2.0f * (float)M_PI;
        c.dist = dist;
        c.width = width;
        c.depth = depth;
        c.npts = b - a;
        c.score = score;
        insert_sorted(out, &count, &c);
    }
    return count;
}
