/* Tiết diện ống - chuyển từ pipecut/section.py, giữ đúng từng quy ước. */
#include <math.h>
#include "core.h"

static double deg(double r) { return r * 180.0 / PC_PI; }
static double rad(double d) { return d * PC_PI / 180.0; }

int sec_init_round(Section *s, double diameter)
{
    if (diameter <= 0) return -1;
    s->kind = SEC_ROUND;
    s->radius = diameter / 2.0;
    s->width = s->height = diameter;
    s->hx = s->hy = s->radius;
    s->rc = 0; s->wall = 0;
    s->perimeter = 2.0 * PC_PI * s->radius;
    s->max_radius = s->radius;
    s->ref_height = s->radius;
    s->nseg = 0;
    return 0;
}

static void add_flat(Section *s, double len, double px, double py, double dx, double dy, double psi)
{
    SecSeg *g = &s->seg[s->nseg++];
    g->kind = 0; g->length = len; g->px = px; g->py = py; g->dx = dx; g->dy = dy; g->psi = psi;
}

static void add_arc(Section *s, double len, double cx, double cy, double psi0)
{
    SecSeg *g = &s->seg[s->nseg++];
    g->kind = 1; g->length = len; g->cx = cx; g->cy = cy; g->psi = psi0;
}

int sec_init_box(Section *s, double width, double height, double corner, double wall)
{
    if (width <= 0 || height <= 0) return -1;
    s->kind = SEC_BOX;
    s->width = width; s->height = height; s->wall = wall;
    s->hx = width / 2.0; s->hy = height / 2.0;
    /* Góc lượn 0 nghĩa là "để phần mềm tự lấy" (2 lần chiều dày thành), không
       phải góc nhọn tuyệt đối: góc nhọn thì máy phải xoay tại chỗ, không cắt được. */
    double rc = corner > 0 ? corner : (2.0 * wall > 0.5 ? 2.0 * wall : 0.5);
    double lim = (s->hx < s->hy ? s->hx : s->hy) * 0.98;
    if (rc > lim) rc = lim;
    s->rc = rc;
    double hx = s->hx, hy = s->hy;
    double top = hx - rc, side = hy - rc, arc = PC_PI * rc / 2.0;
    s->nseg = 0;
    add_flat(s, top, 0.0, hy, 1.0, 0.0, 0.0);                 /* nửa mặt trên */
    add_arc(s, arc, hx - rc, hy - rc, 0.0);                    /* góc trên-phải */
    add_flat(s, 2 * side, hx, hy - rc, 0.0, -1.0, 90.0);       /* mặt phải */
    add_arc(s, arc, hx - rc, -(hy - rc), 90.0);
    add_flat(s, 2 * top, hx - rc, -hy, -1.0, 0.0, 180.0);      /* mặt dưới */
    add_arc(s, arc, -(hx - rc), -(hy - rc), 180.0);
    add_flat(s, 2 * side, -hx, -(hy - rc), 0.0, 1.0, 270.0);   /* mặt trái */
    add_arc(s, arc, -(hx - rc), hy - rc, 270.0);
    /* Nửa mặt trên còn lại mang pháp tuyến 360 chứ không phải 0: góc pháp tuyến
       phải tăng đơn điệu suốt một vòng thì gỡ cuộn trục A mới đúng. */
    add_flat(s, top, -(hx - rc), hy, 1.0, 0.0, 360.0);
    double acc = 0;
    for (int i = 0; i < s->nseg; i++) { s->seg[i].start = acc; acc += s->seg[i].length; }
    s->perimeter = acc;
    s->max_radius = sqrt((hx - rc) * (hx - rc) + (hy - rc) * (hy - rc)) + rc;
    s->ref_height = hy;
    return 0;
}

static double wrapv(const Section *s, double v)
{
    double p = s->perimeter;
    double r = fmod(v, p);
    if (r < 0) r += p;
    return r;
}

static const SecSeg *locate(const Section *s, double v, double *t)
{
    v = wrapv(s, v);
    for (int i = s->nseg - 1; i >= 0; i--) {
        if (v >= s->seg[i].start - 1e-12) { *t = v - s->seg[i].start; return &s->seg[i]; }
    }
    *t = v;
    return &s->seg[0];
}

void sec_point(const Section *s, double v, double *x, double *y)
{
    if (s->kind == SEC_ROUND) {
        double a = v / s->radius;
        *x = s->radius * sin(a); *y = s->radius * cos(a);
        return;
    }
    double t;
    const SecSeg *g = locate(s, v, &t);
    if (g->kind == 0) { *x = g->px + g->dx * t; *y = g->py + g->dy * t; return; }
    double a = rad(g->psi) + t / s->rc;
    *x = g->cx + s->rc * sin(a); *y = g->cy + s->rc * cos(a);
}

double sec_normal(const Section *s, double v)
{
    if (s->kind == SEC_ROUND) return deg(v / s->radius);
    double t;
    const SecSeg *g = locate(s, v, &t);
    if (g->kind == 0) return g->psi;
    return g->psi + deg(t / s->rc);
}

Contact sec_contact(const Section *s, double v)
{
    Contact c;
    if (s->kind == SEC_ROUND) {
        c.theta = deg(v / s->radius); c.cross = 0.0; c.height = s->radius;
        return c;
    }
    /* Gỡ cuộn cẩn thận ngay tại mốc chu vi: s âm cực nhỏ do sai số dấu phẩy
       động làm phần dư tròn lên đúng bằng chu vi -> trục A nhảy trọn 360 độ. */
    double per = s->perimeter;
    double lap = floor(v / per);
    double base = v - lap * per;
    if (base >= per - 1e-9) { base = 0.0; lap += 1; }
    else if (base < 0.0) base = 0.0;
    double psi = sec_normal(s, base) + 360.0 * lap;
    double cx, cy;
    sec_point(s, v, &cx, &cy);
    double a = rad(psi);
    c.theta = psi;
    c.cross = cx * cos(a) - cy * sin(a);
    c.height = cx * sin(a) + cy * cos(a);
    return c;
}

double sec_v_of_theta(const Section *s, double theta)
{
    if (s->kind == SEC_ROUND) return rad(theta) * s->radius;
    double lap = floor(theta / 360.0);
    double target = theta - 360.0 * lap;
    double lo = 0.0, hi = s->perimeter;
    for (int i = 0; i < 60; i++) {
        double mid = (lo + hi) / 2, cx, cy;
        sec_point(s, mid, &cx, &cy);
        double ang = fmod(deg(atan2(cx, cy)) + 360.0, 360.0);
        if (ang < target || (target == 0.0 && mid < s->perimeter / 2 && ang > 180.0)) lo = mid;
        else hi = mid;
    }
    return (lo + hi) / 2 + lap * s->perimeter;
}

double sec_v_of_contact(const Section *s, double theta, double cross)
{
    if (s->kind == SEC_ROUND) {
        double t = cross / s->radius;
        if (t > 1) t = 1;
        if (t < -1) t = -1;
        return (rad(theta) + asin(t)) * s->radius;
    }
    /* Tia thẳng đứng x = cross cắt biên tiết diện đã quay: lấy giao điểm cao nhất. */
    double per = s->perimeter;
    double lap0 = floor(theta / 360.0);
    double a = rad(theta - 360.0 * lap0), ca = cos(a), sa = sin(a);
    int n = 240;
    double best_v = -1, best_z = -1e18;
    double prev_v = 0, px, cx, cy;
    sec_point(s, 0, &cx, &cy);
    px = cx * ca - cy * sa;
    for (int i = 1; i <= n; i++) {
        double v = per * i / n, wx, wy;
        sec_point(s, v, &cx, &cy);
        wx = cx * ca - cy * sa; wy = cx * sa + cy * ca;
        if ((px - cross) * (wx - cross) <= 0 && fabs(wx - px) > 1e-12) {
            double lo = prev_v, hi = v;
            for (int k = 0; k < 40; k++) {
                double mid = 0.5 * (lo + hi), lx, ly, mx, my;
                sec_point(s, lo, &lx, &ly);
                sec_point(s, mid, &mx, &my);
                if (((lx * ca - ly * sa) - cross) * ((mx * ca - my * sa) - cross) <= 0) hi = mid;
                else lo = mid;
            }
            double vv = 0.5 * (lo + hi), qx, qy;
            sec_point(s, vv, &qx, &qy);
            double zz = qx * sa + qy * ca;
            if (zz > best_z) { best_z = zz; best_v = vv; }
        }
        prev_v = v; px = wx; (void)wy;
    }
    if (best_v < 0) best_v = 0;
    double lap = floor((theta - sec_normal(s, best_v)) / 360.0 + 0.5);
    return best_v + lap * per;
}

double sec_surface_height(const Section *s, double theta, double cross)
{
    double v = sec_v_of_contact(s, theta, cross), cx, cy;
    sec_point(s, wrapv(s, v), &cx, &cy);
    double a = rad(theta);
    return cx * sin(a) + cy * cos(a);
}

int sec_breakpoints(const Section *s, double *out, int max)
{
    int n = 0;
    if (s->kind == SEC_ROUND) return 0;
    for (int i = 0; i < s->nseg && n < max; i++) out[n++] = s->seg[i].start;
    if (n < max) out[n++] = s->perimeter;
    return n;
}

void machine_defaults(Machine *m)
{
    /* Khớp config/machine_round.json và tệp cấu hình FluidNC mẫu */
    double rate[NAX] = {3000, 4000, 2000, 3600};
    double acc[NAX] = {200, 250, 200, 400};
    for (int i = 0; i < NAX; i++) { m->max_rate[i] = rate[i]; m->accel[i] = acc[i]; }
    m->junction_deviation = 0.01;
    m->planner_blocks = 32;
    m->kerf = 1.5; m->cut_feed = 1600; m->plunge_feed = 600;
    m->cut_height = 1.6; m->pierce_height = 3.8; m->pierce_delay = 0.6; m->off_delay = 0.2;
    m->safe_height = 20; m->travel_height = 6;
    m->lead_in = 4; m->overcut = 1;
    m->power = 1000;
    m->max_feed = 4000; m->min_feed = 30;
    m->max_segment = 1.0;
}
