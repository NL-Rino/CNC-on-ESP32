/* Nguyên công -> biên dạng trên mặt trải phẳng (u dọc ống, v theo chu vi).
 * Chuyển từ pipecut/shapes.py + phần bù kerf / vào dao của pipecut/pathops.py. */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#include "core.h"

static double rad(double d) { return d * PC_PI / 180.0; }

const wchar_t *op_name(OpKind k)
{
    switch (k) {
    case OP_CUTOFF: return L"Cắt đứt / cắt vát";
    case OP_HOLE:   return L"Lỗ khoan xuyên ống tròn";
    case OP_CIRCLE: return L"Lỗ tròn trên mặt";
    case OP_SLOT:   return L"Rãnh chữ nhật bo góc";
    default:        return L"?";
    }
}

void contour_free(Contour *c)
{
    free(c->pt);
    c->pt = NULL; c->n = c->cap = 0;
}

static void push(Contour *c, double u, double v)
{
    if (c->n == c->cap) {
        c->cap = c->cap ? c->cap * 2 : 256;
        c->pt = (UV *)realloc(c->pt, (size_t)c->cap * sizeof(UV));
    }
    c->pt[c->n].u = u; c->pt[c->n].v = v; c->n++;
}

static int in_arc(const Section *s, double v)
{
    if (s->kind != SEC_BOX) return 0;
    double p = fmod(v, s->perimeter);
    if (p < 0) p += s->perimeter;
    for (int i = 0; i < s->nseg; i++)
        if (s->seg[i].kind == 1 && p >= s->seg[i].start && p <= s->seg[i].start + s->seg[i].length)
            return 1;
    return 0;
}

/* Chia nhỏ + chèn điểm gãy của ống hộp.  Tại chỗ mặt phẳng chuyển sang góc lượn
   độ cong nhảy bậc, đường chạy dao BẮT BUỘC có đỉnh ở đó, nếu không đoạn nội suy
   cắt ngang qua chỗ chuyển tiếp. Trên cung góc chia mịn hơn vì trục A quay nhanh. */
static void refine(Contour *c, const Section *s, double max_seg)
{
    double bp[16];
    int nb = sec_breakpoints(s, bp, 16);
    double per = s->perimeter;
    Contour out = {0};
    out.closed = c->closed; out.wrap = c->wrap; out.lead = 0;
    memcpy(out.name, c->name, sizeof out.name);
    if (c->n == 0) return;
    push(&out, c->pt[0].u, c->pt[0].v);
    for (int i = 1; i < c->n; i++) {
        UV a = c->pt[i - 1], b = c->pt[i];
        /* các điểm gãy nằm giữa a.v và b.v (xét cả các vòng chu vi) */
        double ts[64]; int nt = 0;
        if (nb > 0 && fabs(b.v - a.v) > 1e-9) {
            double lo = a.v < b.v ? a.v : b.v, hi = a.v < b.v ? b.v : a.v;
            int k0 = (int)floor(lo / per) - 1, k1 = (int)floor(hi / per) + 1;
            for (int k = k0; k <= k1 && nt < 60; k++)
                for (int j = 0; j < nb && nt < 60; j++) {
                    double v = bp[j] + k * per;
                    if (v > lo + 1e-9 && v < hi - 1e-9) ts[nt++] = (v - a.v) / (b.v - a.v);
                }
            for (int x = 1; x < nt; x++)                /* sắp tăng dần */
                for (int y = x; y > 0 && ts[y] < ts[y - 1]; y--) {
                    double t = ts[y]; ts[y] = ts[y - 1]; ts[y - 1] = t;
                }
        }
        ts[nt++] = 1.0;
        double t0 = 0.0;
        for (int j = 0; j < nt; j++) {
            double t1 = ts[j];
            double ua = a.u + (b.u - a.u) * t0, va = a.v + (b.v - a.v) * t0;
            double ub = a.u + (b.u - a.u) * t1, vb = a.v + (b.v - a.v) * t1;
            double len = hypot(ub - ua, vb - va);
            double step = in_arc(s, 0.5 * (va + vb)) ? 0.3 : max_seg;
            int m = (int)ceil(len / step);
            if (m < 1) m = 1;
            for (int q = 1; q <= m; q++)
                push(&out, ua + (ub - ua) * q / m, va + (vb - va) * q / m);
            t0 = t1;
        }
    }
    contour_free(c);
    *c = out;
}

static double area(const Contour *c)
{
    double a = 0;
    for (int i = 0; i + 1 < c->n; i++)
        a += c->pt[i].u * c->pt[i + 1].v - c->pt[i + 1].u * c->pt[i].v;
    return 0.5 * a;
}

static void reverse(Contour *c)
{
    for (int i = 0, j = c->n - 1; i < j; i++, j--) { UV t = c->pt[i]; c->pt[i] = c->pt[j]; c->pt[j] = t; }
}

/* Vào dao từ trong lòng biên dạng kín (phần phế liệu) + chạy vượt qua điểm khép. */
static void leads_closed(Contour *c, const Machine *m, double inradius)
{
    if (c->n < 3) return;
    if (area(c) < 0) reverse(c);                   /* ngược chiều kim đồng hồ: lòng ở bên trái */
    UV p0 = c->pt[0], p1 = c->pt[1];
    double du = p1.u - p0.u, dv = p1.v - p0.v, n = hypot(du, dv);
    if (n < 1e-12) n = 1;
    double L = m->lead_in;
    if (L > 0.7 * inradius) L = 0.7 * inradius;
    /* chạy vượt: đi tiếp dọc biên dạng từ điểm đầu */
    double need = m->overcut, acc = 0;
    int base = c->n;
    for (int i = 1; i < base && need > 0; i++) {
        UV a = c->pt[i - 1], b = c->pt[i];
        double seg = hypot(b.u - a.u, b.v - a.v);
        if (acc + seg >= need) {
            double f = (need - acc) / (seg > 0 ? seg : 1);
            push(c, a.u + (b.u - a.u) * f, a.v + (b.v - a.v) * f);
            break;
        }
        push(c, b.u, b.v);
        acc += seg;
    }
    if (L > 0.05) {
        Contour t = {0};
        t.closed = c->closed; t.wrap = c->wrap;
        memcpy(t.name, c->name, sizeof t.name);
        push(&t, p0.u + (-dv / n) * L, p0.v + (du / n) * L);
        for (int i = 0; i < c->n; i++) push(&t, c->pt[i].u, c->pt[i].v);
        t.lead = 1;
        contour_free(c);
        *c = t;
    }
}

int op_build(const Operation *op, const Section *s, const Machine *m, Contour *out,
             char *msg, size_t msglen)
{
    memset(out, 0, sizeof *out);
    double half = m->kerf / 2.0;
    double per = s->perimeter;
    double vc = sec_v_of_theta(s, op->theta);

    if (op->kind == OP_CUTOFF) {
        if (fabs(op->a) >= 89.0) { snprintf(msg, msglen, "Góc vát phải nhỏ hơn 89 độ."); return -1; }
        double ta = tan(rad(op->a));
        out->wrap = 1;
        snprintf(out->name, sizeof out->name, "cat-dut x%.1f", op->x);
        /* Mặt phẳng cắt: u = x + tan(a) * (hình chiếu của điểm lên phương nghiêng).
           Bù kerf vuông góc với đường cắt, về phía đầu tự do (u lớn) là phế liệu. */
        double vend = per + m->overcut;
        int nstep = (int)ceil(vend / 0.5);
        for (int i = 0; i <= nstep; i++) {
            double v = vend * i / nstep, x, y, x1, y1, x2, y2;
            sec_point(s, v, &x, &y);
            sec_point(s, v - 0.05, &x1, &y1);
            sec_point(s, v + 0.05, &x2, &y2);
            double du = ta * (y2 - y1) / 0.1, n = sqrt(1 + du * du);
            push(out, op->x + ta * y + half / n, v - half * du / n);
        }
        refine(out, s, m->max_segment);
        /* vào dao: mồi lệch về phía đầu tự do rồi tiến ngang vào đường cắt */
        Contour t = {0};
        t.wrap = 1;
        memcpy(t.name, out->name, sizeof t.name);
        if (m->lead_in > 0) { push(&t, out->pt[0].u + m->lead_in, out->pt[0].v); t.lead = 1; }
        for (int i = 0; i < out->n; i++) push(&t, out->pt[i].u, out->pt[i].v);
        contour_free(out);
        *out = t;
        return 0;
    }

    if (op->kind == OP_HOLE) {
        if (s->kind != SEC_ROUND) { snprintf(msg, msglen, "Lỗ khoan xuyên ống chỉ dùng cho ống tròn."); return -1; }
        double R = s->radius, r = op->a / 2.0 - half;
        if (r <= 0 || r >= R) { snprintf(msg, msglen, "Lỗ D%.1f không nằm gọn trên ống.", op->a); return -1; }
        out->closed = 1;
        snprintf(out->name, sizeof out->name, "lo D%.1f", op->a);
        int n = (int)ceil(2 * PC_PI * r / 0.6);
        if (n < 36) n = 36;
        for (int i = 0; i <= n; i++) {
            double t = 2 * PC_PI * i / n;
            double py = r * sin(t), pz = sqrt(R * R - py * py);
            double px = -r * cos(t);                      /* khoan hướng tâm: b = 90 độ */
            push(out, op->x + px, vc + R * atan2(py, pz));
        }
        refine(out, s, m->max_segment);
        leads_closed(out, m, r);
        return 0;
    }

    if (op->kind == OP_CIRCLE) {
        double r = op->a / 2.0 - half;
        if (r <= 0 || op->a > per) { snprintf(msg, msglen, "Đường kính lỗ không hợp lệ."); return -1; }
        out->closed = 1;
        snprintf(out->name, sizeof out->name, "tron D%.1f", op->a);
        int n = (int)ceil(2 * PC_PI * r / 0.6);
        if (n < 36) n = 36;
        for (int i = 0; i <= n; i++) {
            double t = 2 * PC_PI * i / n;
            push(out, op->x + r * cos(t), vc + r * sin(t));
        }
        refine(out, s, m->max_segment);
        leads_closed(out, m, r);
        return 0;
    }

    if (op->kind == OP_SLOT) {
        double W = per * op->b / 360.0;
        double hu = op->a / 2.0 - half, hv = W / 2.0 - half;
        if (hu <= 0 || hv <= 0 || W > per) { snprintf(msg, msglen, "Kích thước rãnh không hợp lệ."); return -1; }
        double rr = op->c - half;
        if (rr < 0) rr = 0;
        double lim = (hu < hv ? hu : hv) * 0.999;
        if (rr > lim) rr = lim;
        out->closed = 1;
        snprintf(out->name, sizeof out->name, "ranh %.0fx%.0f", op->a, W);
        double cu = op->x;
        /* ngược chiều kim đồng hồ, bắt đầu giữa cạnh dưới: vào dao ở cạnh thẳng */
        double cx[4] = {cu + hu - rr, cu + hu - rr, cu - hu + rr, cu - hu + rr};
        double cy[4] = {vc - hv + rr, vc + hv - rr, vc + hv - rr, vc - hv + rr};
        double a0[4] = {-90, 0, 90, 180};
        push(out, cu, vc - hv);
        for (int k = 0; k < 4; k++) {
            int steps = rr > 0 ? (int)ceil(rr * PC_PI / 2 / 0.4) : 0;
            if (steps < 1) {
                /* góc nhọn */
                double sx = (k == 0 || k == 1) ? cu + hu : cu - hu;
                double sy = (k == 1 || k == 2) ? vc + hv : vc - hv;
                push(out, sx, sy);
            } else {
                for (int i = 0; i <= steps; i++) {
                    double a = rad(a0[k] + 90.0 * i / steps);
                    push(out, cx[k] + rr * cos(a), cy[k] + rr * sin(a));
                }
            }
        }
        push(out, cu, vc - hv);
        refine(out, s, m->max_segment);
        leads_closed(out, m, hu < hv ? hu : hv);
        return 0;
    }
    snprintf(msg, msglen, "Nguyên công không hỗ trợ.");
    return -1;
}
