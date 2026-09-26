/* Lập kế hoạch chuyển động đúng như Grbl/FluidNC - chuyển từ pipecut/planner.py.
 *   - tốc độ danh định: F (hoặc tốc độ chạy nhanh với G0), không trục nào vượt max_rate
 *   - gia tốc khối: trục yếu nhất theo đúng hướng đi
 *   - tốc độ qua điểm nối: công thức junction deviation
 *   - bộ đệm nhìn trước có hạn (planner_blocks), lệnh M3/M5/G4/G10 bắt dừng hẳn */
#include <ctype.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
#include "core.h"

const char *CAT_NAMES_VI[NCAT] = {"cắt", "chạy không", "nhấc/hạ mỏ", "hạ mỏ chậm",
                                  "xoay/đi chậm", "chờ (mồi, tắt)"};

typedef struct {
    int line;
    double len, unit[NAX], v_nom, accel, v_junc;
    int cat, sync, dwell;
    double dwell_t;
    double a[NAX], b[NAX];
    int torch, rapid;
} Blk;

void plan_free(Plan *p) { free(p->mv); memset(p, 0, sizeof *p); }

static double limit_by_axes(const double lim[NAX], const double u[NAX])
{
    double best = 1e300;
    for (int i = 0; i < NAX; i++)
        if (fabs(u[i]) > 1e-12 && lim[i] > 0 && lim[i] / fabs(u[i]) < best) best = lim[i] / fabs(u[i]);
    return best < 1e299 ? best : 0.0;
}

static double trap_time(double L, double v0, double v1, double vc, double a)
{
    if (L <= 0) return 0;
    double da = (vc * vc - v0 * v0) / (2 * a), dd = (vc * vc - v1 * v1) / (2 * a);
    if (da < 0) da = 0;
    if (dd < 0) dd = 0;
    if (da + dd <= L) return (vc - v0) / a + (vc - v1) / a + (L - da - dd) / vc;
    double vp = sqrt((2 * a * L + v0 * v0 + v1 * v1) / 2.0);
    if (vp < v0) vp = v0;
    if (vp < v1) vp = v1;
    double t = (vp - v0) / a + (vp - v1) / a;
    return t > 0 ? t : 0;
}

/* quãng đường đã đi sau thời gian t trong khối hình thang */
static double trap_dist(double t, double L, double v0, double v1, double vc, double a)
{
    double da = (vc * vc - v0 * v0) / (2 * a), dd = (vc * vc - v1 * v1) / (2 * a);
    if (da < 0) da = 0;
    if (dd < 0) dd = 0;
    double vp = vc;
    if (da + dd > L) {
        vp = sqrt((2 * a * L + v0 * v0 + v1 * v1) / 2.0);
        da = (vp * vp - v0 * v0) / (2 * a);
        dd = (vp * vp - v1 * v1) / (2 * a);
    }
    double ta = (vp - v0) / a, tc = (L - da - dd) / (vp > 0 ? vp : 1);
    if (tc < 0) tc = 0;
    if (t <= ta) return v0 * t + 0.5 * a * t * t;
    if (t <= ta + tc) return da + vp * (t - ta);
    double td = t - ta - tc;
    double s = da + vp * tc + vp * td - 0.5 * a * td * td;
    return s > L ? L : s;
}

int plan_program(const char *gcode, const Machine *m, Plan *out)
{
    memset(out, 0, sizeof *out);
    double rates[NAX], acc[NAX];
    for (int i = 0; i < NAX; i++) { rates[i] = m->max_rate[i] / 60.0; acc[i] = m->accel[i]; }

    int cap = 1024, nb = 0;
    Blk *bl = (Blk *)malloc((size_t)cap * sizeof *bl);
    double pos[NAX] = {0, 0, 0, 0};
    int rapid = 1, absolute = 1, torch = 0, sync_pending = 1;
    double feed = 0;
    int line_no = 0;
    const char *p = gcode;
    char buf[512];
    while (*p) {
        size_t k = 0;
        while (*p && *p != '\n' && k < sizeof buf - 1) buf[k++] = *p++;
        buf[k] = 0;
        while (*p && *p != '\n') p++;
        if (*p == '\n') p++;
        line_no++;
        /* bỏ chú thích (...) và ;... */
        char txt[512];
        size_t t = 0;
        int paren = 0;
        for (size_t i = 0; buf[i]; i++) {
            char ch = buf[i];
            if (ch == '(') { paren = 1; continue; }
            if (ch == ')') { paren = 0; continue; }
            if (ch == ';') break;
            if (!paren) txt[t++] = (char)toupper((unsigned char)ch);
        }
        txt[t] = 0;
        double tgt[NAX];
        memcpy(tgt, pos, sizeof tgt);
        int moved = 0, is_dwell = 0;
        double dwell = -1;
        for (size_t i = 0; i < t;) {
            char L = txt[i];
            if (L < 'A' || L > 'Z') { i++; continue; }
            char *end;
            double val = strtod(txt + i + 1, &end);
            if (end == txt + i + 1) { i++; continue; }
            i = (size_t)(end - txt);
            if (L == 'G') {
                int code = (int)floor(val * 10 + 0.5);
                if (code == 0) rapid = 1;
                else if (code == 10) rapid = 0;
                else if (code == 900) absolute = 1;
                else if (code == 910) absolute = 0;
                else if (code == 40) is_dwell = 1;
                if (code % 10 == 0) {
                    int g = code / 10;
                    if (g == 4 || g == 10 || g == 28 || g == 30 || g == 92 || g == 53) sync_pending = 1;
                }
            } else if (L == 'M') {
                int code = (int)floor(val + 0.5);
                if (code == 3 || code == 4) torch = 1;
                else if (code == 5 || code == 2 || code == 30) torch = 0;
                if (code == 3 || code == 4 || code == 5 || code == 7 || code == 8 || code == 9 ||
                    (code >= 62 && code <= 65)) sync_pending = 1;
            } else if (L == 'F') {
                feed = val > 1 ? val : 1;
            } else if (L == 'P' && is_dwell) {
                dwell = val > 0 ? val : 0;
            } else {
                int ax = L == 'X' ? AX_X : L == 'Y' ? AX_Y : L == 'Z' ? AX_Z : L == 'A' ? AX_A : -1;
                if (ax >= 0) { tgt[ax] = absolute ? val : pos[ax] + val; moved = 1; }
            }
        }
        if (nb + 1 >= cap) { cap *= 2; bl = (Blk *)realloc(bl, (size_t)cap * sizeof *bl); }
        if (is_dwell) {
            if (dwell > 0) {
                Blk *b = &bl[nb++];
                memset(b, 0, sizeof *b);
                b->line = line_no; b->dwell = 1; b->dwell_t = dwell; b->sync = 1; b->cat = CAT_DWELL;
                b->torch = torch;
                memcpy(b->a, pos, sizeof pos); memcpy(b->b, pos, sizeof pos);
            }
            sync_pending = 1;
            continue;
        }
        if (!moved) continue;
        double d[NAX], len = 0;
        for (int i = 0; i < NAX; i++) { d[i] = tgt[i] - pos[i]; len += d[i] * d[i]; }
        len = sqrt(len);
        if (len < 1e-9) { memcpy(pos, tgt, sizeof pos); continue; }
        Blk *b = &bl[nb++];
        memset(b, 0, sizeof *b);
        b->line = line_no; b->len = len;
        for (int i = 0; i < NAX; i++) b->unit[i] = d[i] / len;
        double rr = limit_by_axes(rates, b->unit);
        b->v_nom = rapid ? rr : (feed / 60.0 < rr ? feed / 60.0 : rr);
        if (b->v_nom < 1e-6) b->v_nom = 1e-6;
        b->accel = limit_by_axes(acc, b->unit);
        if (b->accel < 1e-6) b->accel = 1e-6;
        int only_z = fabs(d[AX_X]) < 1e-9 && fabs(d[AX_Y]) < 1e-9 && fabs(d[AX_A]) < 1e-9;
        b->cat = rapid ? (only_z ? CAT_LIFT : CAT_TRAVEL)
                       : (only_z ? CAT_PLUNGE : (torch ? CAT_CUT : CAT_INDEX));
        b->sync = sync_pending;
        b->torch = torch; b->rapid = rapid;
        memcpy(b->a, pos, sizeof pos); memcpy(b->b, tgt, sizeof tgt);
        sync_pending = 0;
        memcpy(pos, tgt, sizeof pos);
    }

    /* tốc độ tối đa tại điểm vào mỗi khối - junction deviation */
    double jd = m->junction_deviation > 1e-6 ? m->junction_deviation : 1e-6;
    Blk *prev = NULL;
    for (int i = 0; i < nb; i++) {
        Blk *b = &bl[i];
        if (b->dwell) { prev = NULL; continue; }
        if (!prev || b->sync) { b->v_junc = 0; }
        else {
            double cs = 0;
            for (int k = 0; k < NAX; k++) cs -= prev->unit[k] * b->unit[k];
            double v2;
            if (cs > 0.999999) v2 = 0;
            else if (cs < -0.999999) v2 = 1e300;
            else {
                double ju[NAX], n = 0;
                for (int k = 0; k < NAX; k++) { ju[k] = b->unit[k] - prev->unit[k]; n += ju[k] * ju[k]; }
                n = sqrt(n);
                if (n > 1e-12) for (int k = 0; k < NAX; k++) ju[k] /= n;
                double aj = limit_by_axes(acc, ju);
                if (aj <= 0) aj = b->accel;
                double sh = sqrt(0.5 * (1 - cs));
                v2 = aj * jd * sh / (1 - sh);
            }
            double lim = b->v_nom * b->v_nom < prev->v_nom * prev->v_nom ? b->v_nom * b->v_nom : prev->v_nom * prev->v_nom;
            b->v_junc = sqrt(v2 < lim ? v2 : lim);
        }
        prev = b;
    }

    /* các đoạn liền mạch giữa hai lần đồng bộ */
    out->cap = nb + 1;
    out->mv = (Move *)calloc((size_t)out->cap, sizeof(Move));
    int depth = (m->planner_blocks > 2 ? m->planner_blocks : 2) - 1;
    double tnow = 0;
    int i = 0;
    while (i < nb) {
        if (bl[i].dwell) {
            Move *mv = &out->mv[out->n++];
            mv->t0 = tnow; mv->dt = bl[i].dwell_t; mv->dwell = 1; mv->line = bl[i].line;
            mv->torch = bl[i].torch;
            memcpy(mv->a, bl[i].a, sizeof mv->a); memcpy(mv->b, bl[i].b, sizeof mv->b);
            out->by_cat[CAT_DWELL] += mv->dt;
            tnow += mv->dt;
            i++;
            continue;
        }
        int j = i + 1;
        while (j < nb && !bl[j].dwell && !bl[j].sync) j++;
        int n = j - i;
        out->syncs++;
        double *pref = (double *)calloc((size_t)n + 1, sizeof(double));
        double *ex = (double *)calloc((size_t)n, sizeof(double));
        for (int k = 0; k < n; k++) pref[k + 1] = pref[k] + 2 * bl[i + k].accel * bl[i + k].len;
        double v_next = 0;
        for (int k = n - 1; k >= 0; k--) {
            int e = k + depth < n ? k + depth : n;
            double room = pref[e] - pref[k + 1];
            double r = sqrt(room > 0 ? room : 0);
            ex[k] = v_next < r ? v_next : r;
            Blk *b = &bl[i + k];
            double reach = sqrt(ex[k] * ex[k] + 2 * b->accel * b->len);
            v_next = b->v_junc < reach ? b->v_junc : reach;
        }
        double v_in = 0;
        for (int k = 0; k < n; k++) {
            Blk *b = &bl[i + k];
            double ve = k ? (v_in < b->v_junc ? v_in : b->v_junc) : 0;
            double reach = sqrt(ve * ve + 2 * b->accel * b->len);
            double vx = ex[k];
            if (reach < vx) vx = reach;
            if (b->v_nom < vx) vx = b->v_nom;
            double dt = trap_time(b->len, ve, vx, b->v_nom, b->accel);
            Move *mv = &out->mv[out->n++];
            mv->t0 = tnow; mv->dt = dt; mv->line = b->line;
            mv->rapid = b->rapid; mv->torch = b->torch;
            mv->v_entry = ve; mv->v_exit = vx; mv->v_nom = b->v_nom; mv->accel = b->accel;
            memcpy(mv->a, b->a, sizeof mv->a); memcpy(mv->b, b->b, sizeof mv->b);
            out->by_cat[b->cat] += dt;
            tnow += dt;
            if (k && ve < 0.05 * (b->v_nom < bl[i + k - 1].v_nom ? b->v_nom : bl[i + k - 1].v_nom))
                out->full_stops++;
            v_in = vx;
        }
        free(pref);
        free(ex);
        i = j;
    }
    out->total = tnow;
    free(bl);
    return 0;
}

void plan_state(const Plan *p, double t, double pos[NAX], int *torch, int *line)
{
    if (!p->n) { memset(pos, 0, sizeof(double) * NAX); *torch = 0; *line = 0; return; }
    if (t <= 0) { memcpy(pos, p->mv[0].a, sizeof(double) * NAX); *torch = 0; *line = p->mv[0].line; return; }
    /* tìm nhị phân khối đang chạy */
    int lo = 0, hi = p->n - 1;
    while (lo < hi) {
        int mid = (lo + hi + 1) / 2;
        if (p->mv[mid].t0 <= t) lo = mid; else hi = mid - 1;
    }
    const Move *mv = &p->mv[lo];
    double f = 1.0;
    if (mv->dwell) f = 1.0;
    else if (mv->dt > 1e-12 && t < mv->t0 + mv->dt) {
        double L = 0;
        for (int i = 0; i < NAX; i++) L += (mv->b[i] - mv->a[i]) * (mv->b[i] - mv->a[i]);
        L = sqrt(L);
        f = L > 0 ? trap_dist(t - mv->t0, L, mv->v_entry, mv->v_exit, mv->v_nom, mv->accel) / L : 1.0;
        if (f > 1) f = 1;
        if (f < 0) f = 0;
    }
    for (int i = 0; i < NAX; i++) pos[i] = mv->a[i] + (mv->b[i] - mv->a[i]) * f;
    *torch = mv->torch;
    *line = mv->line;
}
