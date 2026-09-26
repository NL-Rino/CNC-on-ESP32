/* Biên dạng -> G-code FluidNC.  Chuyển từ pipecut/gcode.py + kinematics.py:
 *   - tư thế máy tại mỗi điểm: A = góc pháp tuyến, X = lệch ngang, Z = bù chênh cao
 *   - F từng đoạn = v_cắt * L_trục / L_bề_mặt  (FluidNC cộng độ của A như mm)
 *   - không trục nào bị ép quá max_rate của nó */
#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "core.h"

static const char LET[NAX] = {'X', 'Y', 'Z', 'A'};

void gbuf_free(GBuf *g) { free(g->text); memset(g, 0, sizeof *g); }

static void gput(GBuf *g, const char *fmtstr, ...)
{
    char line[256];
    va_list ap;
    va_start(ap, fmtstr);
    int n = vsnprintf(line, sizeof line, fmtstr, ap);
    va_end(ap);
    if (n < 0) return;
    if (n > (int)sizeof line - 2) n = (int)sizeof line - 2;
    if (g->len + (size_t)n + 2 > g->cap) {
        g->cap = (g->cap + (size_t)n + 2) * 2;
        g->text = (char *)realloc(g->text, g->cap);
    }
    memcpy(g->text + g->len, line, (size_t)n);
    g->len += (size_t)n;
    g->text[g->len++] = '\n';
    g->text[g->len] = 0;
    g->lines++;
}

/* Số gọn nhất có thể (bỏ 0 thừa) nhưng đủ 3 chữ số thập phân - như fmt() của Python */
static const char *num(double v, char *buf)
{
    if (fabs(v) < 0.0005) { strcpy(buf, "0"); return buf; }
    sprintf(buf, "%.3f", v);
    char *p = buf + strlen(buf) - 1;
    while (*p == '0') *p-- = 0;
    if (*p == '.') *p = 0;
    if (!strcmp(buf, "-0")) strcpy(buf, "0");
    return buf;
}

typedef struct {
    GBuf  *g;
    double pos[NAX];
    int    known[NAX];
    int    mode;           /* 0 = G0, 1 = G1, -1 = chưa có */
    double feed;
} Writer;

static void wmove(Writer *w, const double tgt[NAX], const int use[NAX], double feed)
{
    char line[200], nb[32];
    int n = 0, any = 0;
    int mode = feed > 0 ? 1 : 0;
    line[0] = 0;
    if (w->mode != mode) n += sprintf(line + n, "%s", mode ? "G1" : "G0");
    for (int i = 0; i < NAX; i++) {
        if (!use[i]) continue;
        if (!w->known[i] || fabs(tgt[i] - w->pos[i]) > 0.0005) {
            n += sprintf(line + n, "%s%c%s", n ? " " : "", LET[i], num(tgt[i], nb));
            any = 1;
        }
    }
    if (!any) return;
    w->mode = mode;
    if (mode && (w->feed <= 0 || fabs(feed - w->feed) / w->feed > 0.04)) {
        n += sprintf(line + n, " F%.0f", feed);
        w->feed = feed;
    }
    gput(w->g, "%s", line);
    for (int i = 0; i < NAX; i++) if (use[i]) { w->pos[i] = tgt[i]; w->known[i] = 1; }
}

static void pose(const Section *s, UV p, double zoff, double out[NAX])
{
    Contact c = sec_contact(s, p.v);
    out[AX_X] = c.cross;
    out[AX_Y] = p.u;
    out[AX_Z] = zoff + (c.height - s->ref_height);
    out[AX_A] = c.theta;
}

static double feed_for(const Machine *m, const double a[NAX], const double b[NAX],
                       double l_real)
{
    double lm = 0;
    for (int i = 0; i < NAX; i++) lm += (b[i] - a[i]) * (b[i] - a[i]);
    lm = sqrt(lm);
    if (lm < 1e-12) return m->cut_feed;
    double f = l_real > 1e-9 ? m->cut_feed * lm / l_real : m->max_feed;
    for (int i = 0; i < NAX; i++) {
        double d = fabs(b[i] - a[i]);
        if (d > 1e-12 && m->max_rate[i] > 0 && m->max_rate[i] * lm / d < f)
            f = m->max_rate[i] * lm / d;
    }
    if (f > m->max_feed) f = m->max_feed;
    if (f < m->min_feed) f = m->min_feed;
    return f;
}

int gcode_build(const Operation *ops, int nops, const Section *s, const Machine *m,
                double pipe_length, GBuf *out, char *msg, size_t msglen)
{
    Writer w;
    memset(&w, 0, sizeof w);
    memset(out, 0, sizeof *out);
    w.g = out;
    w.mode = -1;
    static const int ALL[NAX] = {1, 1, 1, 1}, ONLYZ[NAX] = {0, 0, 1, 0}, XYA[NAX] = {1, 1, 0, 1};
    char nb[32];

    gput(out, "(PipeCut C - ong %s %.1f x dai %.0f mm)",
         s->kind == SEC_ROUND ? "tron D" : "hop", s->kind == SEC_ROUND ? 2 * s->radius : s->width,
         pipe_length);
    gput(out, "(kerf %.2f  F be mat %.0f mm/ph)", m->kerf, m->cut_feed);
    gput(out, "G21");
    gput(out, "G90");
    gput(out, "G94");
    gput(out, "G54");

    int first = 1;
    double prev_surf = 0;
    msg[0] = 0;
    for (int k = 0; k < nops; k++) {
        if (!ops[k].enabled) continue;
        Contour c;
        char err[160];
        if (op_build(&ops[k], s, m, &c, err, sizeof err) != 0) {
            snprintf(msg, msglen, "Nguyên công %d bỏ qua: %s", k + 1, err);
            continue;
        }
        if (c.n < 2) { contour_free(&c); continue; }
        gput(out, "");
        gput(out, "(--- %s ---)", c.name);

        double p0[NAX];
        pose(s, c.pt[0], m->pierce_height, p0);
        /* quay theo đường ngắn nhất khi chạy không (không bao giờ khi đang cắt) */
        double shift = 0;
        if (w.known[AX_A]) shift = 360.0 * floor((w.pos[AX_A] - p0[AX_A]) / 360.0 + 0.5);
        p0[AX_A] += shift;
        double surf0 = p0[AX_Z] - m->pierce_height;

        if (first) {
            double z[NAX] = {0, 0, m->safe_height, 0};
            wmove(&w, z, ONLYZ, 0);
            first = 0;
        } else {
            /* Chạy không: chỉ nhấc vừa đủ.  Ống tròn mặt chỗ nào cũng cao như nhau;
               ống hộp mà xoay qua góc thì phải qua được góc đang nhô lên. */
            double rise = prev_surf > surf0 ? prev_surf : surf0;
            if (s->kind == SEC_BOX && fabs(p0[AX_A] - w.pos[AX_A]) > 0.5)
                rise = s->max_radius - s->ref_height;
            double z[NAX] = {0, 0, rise + m->travel_height, 0};
            wmove(&w, z, ONLYZ, 0);
        }
        wmove(&w, p0, XYA, 0);
        wmove(&w, p0, ONLYZ, 0);                         /* xuống cao độ mồi */
        gput(out, "M3 S%.0f", m->power);
        out->pierces++;
        gput(out, "G4 P%s", num(m->pierce_delay, nb));
        double pc[NAX];
        pose(s, c.pt[0], m->cut_height, pc);
        pc[AX_A] += shift;
        wmove(&w, pc, ONLYZ, m->plunge_feed);

        double a[NAX];
        memcpy(a, pc, sizeof a);
        for (int i = 1; i < c.n; i++) {
            double b[NAX];
            pose(s, c.pt[i], m->cut_height, b);
            b[AX_A] += shift;
            double lr = hypot(c.pt[i].u - c.pt[i - 1].u, c.pt[i].v - c.pt[i - 1].v);
            double f = feed_for(m, a, b, lr);
            wmove(&w, b, ALL, f);
            if (i > c.lead) out->cut_length += lr;
            memcpy(a, b, sizeof a);
        }
        prev_surf = a[AX_Z] - m->cut_height;
        gput(out, "M5");
        gput(out, "G4 P%s", num(m->off_delay, nb));
        contour_free(&c);
    }
    gput(out, "");
    {
        double z[NAX] = {0, 0, m->safe_height, 0};
        wmove(&w, z, ONLYZ, 0);
    }
    gput(out, "M5");
    gput(out, "M30");
    return 0;
}

/* Sắp thứ tự như phần mềm máy laser cắt ống:
 *   - làm xong từng chi tiết một, từ đầu tự do (x lớn) vào;
 *   - lỗ/rãnh nằm ngoài một nhát cắt đứt phải cắt trước nhát đó;
 *   - trong nhóm: đi tới đường gần nhất theo thời gian máy (trục chậm nhất
 *     quyết định, góc tính qua mốc 360 độ). */
static double op_extent(const Operation *o, int hi)
{
    double r = o->kind == OP_SLOT ? o->a / 2 : (o->kind == OP_CUTOFF ? 0 : o->a / 2);
    return hi ? o->x + r : o->x - r;
}

void ops_order(Operation *ops, int nops, const Section *s)
{
    (void)s;
    Operation *tmp = (Operation *)malloc((size_t)(nops ? nops : 1) * sizeof *tmp);
    int *used = (int *)calloc((size_t)(nops ? nops : 1), sizeof *used);
    int n = 0;
    /* nhát cắt đứt theo x giảm dần */
    for (;;) {
        int best = -1;
        for (int i = 0; i < nops; i++)
            if (!used[i] && ops[i].kind == OP_CUTOFF && (best < 0 || ops[i].x > ops[best].x)) best = i;
        int last = 1;
        for (int i = 0; i < nops; i++)
            if (!used[i] && ops[i].kind == OP_CUTOFF && i != best) last = 0;
        /* nhóm: mọi lỗ/rãnh còn lại nằm ngoài nhát này (hoặc tất cả nếu là nhát cuối) */
        double here_x = n ? tmp[n - 1].x : 0.0, here_t = n ? tmp[n - 1].theta : 0.0;
        for (;;) {
            int pick = -1;
            double bc = 1e18;
            for (int i = 0; i < nops; i++) {
                if (used[i] || ops[i].kind == OP_CUTOFF) continue;
                if (best >= 0 && !last && op_extent(&ops[i], 1) <= ops[best].x) continue;
                double dt = fmod(fabs(ops[i].theta - here_t), 360.0);
                if (dt > 180) dt = 360 - dt;
                double cost = fabs(ops[i].x - here_x) / (4000.0 / 60) ;
                if (dt / (3600.0 / 60) > cost) cost = dt / (3600.0 / 60);
                if (cost < bc) { bc = cost; pick = i; }
            }
            if (pick < 0) break;
            used[pick] = 1;
            tmp[n++] = ops[pick];
            here_x = ops[pick].x; here_t = ops[pick].theta;
        }
        if (best < 0) break;
        used[best] = 1;
        tmp[n++] = ops[best];
    }
    memcpy(ops, tmp, (size_t)n * sizeof *tmp);
    free(tmp);
    free(used);
}
