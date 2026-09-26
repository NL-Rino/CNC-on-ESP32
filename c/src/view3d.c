/* Khung nhìn 3D bằng GDI thuần - chuyển từ pipecut/machinescene.py + ui/machineview.py.
 *
 * Không OpenGL, không thư viện ngoài: mọi khối đều là đa giác tô đặc, sáng tối
 * tính theo pháp tuyến (Blinn-Phong đơn giản, đèn gắn theo góc nhìn), vẽ theo
 * thứ tự xa trước gần sau.  Vẽ vào bitmap trong bộ nhớ rồi mới chép ra màn hình
 * nên không nháy hình. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <windowsx.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "view3d.h"

/* ---- bảng màu: cùng bộ màu khung nhìn 3D của bản Python ---- */
#define C_VIEW_TOP   RGB(0x5b, 0x8f, 0xc4)
#define C_VIEW_BOT   RGB(0xca, 0xdc, 0xee)
#define C_METAL      RGB(0xea, 0xef, 0xf4)
#define C_METAL_EDGE RGB(0x37, 0x40, 0x48)
#define C_MACHINE    RGB(0x3b, 0x42, 0x4b)
#define C_MACH_EDGE  RGB(0x8a, 0x96, 0xa3)
#define C_NOZZLE     RGB(0xc4, 0x7a, 0x3a)
#define C_CUT        RGB(0xd9, 0x3f, 0x21)
#define C_TORCH_ON   RGB(0xff, 0x7a, 0x1a)
#define C_ARC_CORE   RGB(0xff, 0xf4, 0xd8)
#define C_HUD_BG     RGB(0x14, 0x22, 0x33)
#define C_HUD_FG     RGB(0xee, 0xf4, 0xfa)
#define C_ACCENT     RGB(0x1f, 0x6c, 0xba)
#define C_AX_X       RGB(0xe5, 0x53, 0x4b)
#define C_AX_Y       RGB(0x3f, 0xb9, 0x50)
#define C_AX_Z       RGB(0x4c, 0x9e, 0xf8)

typedef struct { double x, y, z; } V3;

typedef struct { double az, el; V3 dir, right, up; } Cam;

typedef struct { double t, u, v; int start; } TP;

typedef struct {
    const Section *sec;
    const Machine *mach;
    const Plan *plan;
    double len;
    TP *tr; int ntr, captr;          /* vết cắt của chương trình (theo thời gian) */
    TP *lv; int nlv, caplv;          /* vết cắt khi bám theo máy thật */
    double t, pos[NAX];
    int torch, live;
    double y_lo, y_hi;               /* khoảng trục dọc chương trình đi qua */
    Cam cam;
    double scale, ox, oy;
    int focus_work;
    int drag_mode, mx, my;
    HFONT f_mono, f_ui, f_small;
} View;

static double rad(double d) { return d * PC_PI / 180.0; }
static double dot(V3 a, V3 b) { return a.x * b.x + a.y * b.y + a.z * b.z; }
static V3 v3(double x, double y, double z) { V3 r = {x, y, z}; return r; }
static V3 unit(V3 a) { double n = sqrt(dot(a, a)); if (n < 1e-12) n = 1; return v3(a.x / n, a.y / n, a.z / n); }

static void cam_update(Cam *c)
{
    double az = rad(c->az), el = rad(c->el < -85 ? -85 : c->el > 85 ? 85 : c->el);
    c->dir = v3(cos(el) * cos(az), cos(el) * sin(az), sin(el));
    V3 r = v3(-c->dir.y, c->dir.x, 0);
    double n = hypot(r.x, r.y);
    if (n < 1e-12) n = 1;
    c->right = v3(r.x / n, r.y / n, 0);
    V3 d = c->dir, q = c->right;
    c->up = v3(d.y * q.z - d.z * q.y, d.z * q.x - d.x * q.z, d.x * q.y - d.y * q.x);
}

static void cam_default(Cam *c) { c->az = -38.0; c->el = 28.0; cam_update(c); }
static int faces(const Cam *c, V3 n) { return dot(n, c->dir) > 0.0; }
static double depth(const Cam *c, V3 p) { return dot(p, c->dir); }

static POINT P(const View *v, V3 p)
{
    POINT q;
    double sx = dot(p, v->cam.right), sy = -dot(p, v->cam.up);
    q.x = (LONG)lround(v->ox + sx * v->scale);
    q.y = (LONG)lround(v->oy + sy * v->scale);
    return q;
}

/* ---- ánh sáng ---- */
static COLORREF shade(const View *v, COLORREF base, V3 n, double amb, double dif, double spec, double shin)
{
    const Cam *c = &v->cam;
    V3 L = unit(v3(0.55 * c->dir.x + 0.75 * c->up.x - 0.35 * c->right.x,
                   0.55 * c->dir.y + 0.75 * c->up.y - 0.35 * c->right.y,
                   0.55 * c->dir.z + 0.75 * c->up.z - 0.35 * c->right.z));
    V3 H = unit(v3(L.x + c->dir.x, L.y + c->dir.y, L.z + c->dir.z));
    double ndl = dot(n, L), ndh = dot(n, H);
    if (ndl < 0) ndl = 0;
    if (ndh < 0) ndh = 0;
    double k = amb + dif * ndl, s = spec * pow(ndh, shin);
    double r = GetRValue(base) * k, g = GetGValue(base) * k, b = GetBValue(base) * k;
    r += (255 - r) * s; g += (255 - g) * s; b += (255 - b) * s;
    return RGB(r > 255 ? 255 : (int)r, g > 255 ? 255 : (int)g, b > 255 ? 255 : (int)b);
}

static COLORREF mix(COLORREF a, COLORREF b, double t)
{
    return RGB((int)(GetRValue(a) + (GetRValue(b) - GetRValue(a)) * t),
               (int)(GetGValue(a) + (GetGValue(b) - GetGValue(a)) * t),
               (int)(GetBValue(a) + (GetBValue(b) - GetBValue(a)) * t));
}

/* ---- vẽ nguyên thuỷ ---- */
static void fillp(HDC dc, const POINT *pt, int n, COLORREF fill, COLORREF edge)
{
    SelectObject(dc, GetStockObject(DC_PEN));
    SelectObject(dc, GetStockObject(DC_BRUSH));
    SetDCPenColor(dc, edge);
    SetDCBrushColor(dc, fill);
    Polygon(dc, pt, n);
}

static void line(HDC dc, const POINT *pt, int n, COLORREF col, int width, int dashed)
{
    if (n < 2) return;
    LOGBRUSH lb = {BS_SOLID, col, 0};
    DWORD style[2] = {(DWORD)(5 * (width > 1 ? width : 1)), (DWORD)(4 * (width > 1 ? width : 1))};
    HPEN pen = ExtCreatePen(PS_GEOMETRIC | (dashed ? PS_USERSTYLE : PS_SOLID) | PS_ENDCAP_ROUND | PS_JOIN_ROUND,
                            width < 1 ? 1 : width, &lb, dashed ? 2 : 0, dashed ? style : NULL);
    HGDIOBJ old = SelectObject(dc, pen);
    Polyline(dc, pt, n);
    SelectObject(dc, old);
    DeleteObject(pen);
}

static void seg2(HDC dc, POINT a, POINT b, COLORREF col, int width, int dashed)
{
    POINT p[2] = {a, b};
    line(dc, p, 2, col, width, dashed);
}

/* ---- tư thế máy ---- */
typedef struct { double along, rotary, cross, lift, y_head, y_tail; } Pose;

static Pose pose_of(const View *v)
{
    Pose p;
    p.along = v->pos[AX_Y]; p.rotary = v->pos[AX_A]; p.cross = v->pos[AX_X]; p.lift = v->pos[AX_Z];
    p.y_head = -p.along;
    p.y_tail = v->len - p.along;
    return p;
}

static V3 surf(const View *v, const Pose *ps, double s, double y, double scale)
{
    double cx, cy;
    sec_point(v->sec, s, &cx, &cy);
    double a = rad(ps->rotary);
    return v3((cx * cos(a) - cy * sin(a)) * scale, y, (cx * sin(a) + cy * cos(a)) * scale);
}

static V3 normal_at(const View *v, const Pose *ps, double s)
{
    double psi = rad(sec_normal(v->sec, fmod(fmod(s, v->sec->perimeter) + v->sec->perimeter, v->sec->perimeter)) - ps->rotary);
    return v3(sin(psi), 0, cos(psi));
}

/* ---- các khối ---- */
static void box(HDC dc, const View *v, double x0, double x1, double y0, double y1,
                double z0, double z1, COLORREF col, COLORREF edge)
{
    V3 c[8];
    int k = 0;
    for (int i = 0; i < 2; i++) for (int j = 0; j < 2; j++) for (int l = 0; l < 2; l++)
        c[k++] = v3(i ? x1 : x0, j ? y1 : y0, l ? z1 : z0);
    static const int F[6][4] = {{0, 1, 3, 2}, {4, 6, 7, 5}, {0, 4, 5, 1}, {2, 3, 7, 6}, {0, 2, 6, 4}, {1, 5, 7, 3}};
    static const double N[6][3] = {{-1, 0, 0}, {1, 0, 0}, {0, -1, 0}, {0, 1, 0}, {0, 0, -1}, {0, 0, 1}};
    for (int f = 0; f < 6; f++) {
        V3 n = v3(N[f][0], N[f][1], N[f][2]);
        if (!faces(&v->cam, n)) continue;
        POINT pt[4];
        for (int i = 0; i < 4; i++) pt[i] = P(v, c[F[f][i]]);
        fillp(dc, pt, 4, shade(v, col, n, 0.5, 0.5, 0.25, 26), edge);
    }
}

static double nice_step(double raw)
{
    if (raw < 1e-6) raw = 1e-6;
    double e = pow(10, floor(log10(raw)));
    if (e >= raw) return e;
    if (2 * e >= raw) return 2 * e;
    if (5 * e >= raw) return 5 * e;
    return 10 * e;
}

static void draw_ground(HDC dc, const View *v, const Pose *ps)
{
    double r = v->sec->max_radius, base = -r * 1.9;
    double y0 = (ps->y_head < -r * 8 ? ps->y_head : -r * 8) - r * 2;
    double y1 = (ps->y_tail > r * 8 ? ps->y_tail : r * 8) + r * 2;
    double step = nice_step((y1 - y0) / 24.0), half = r * 3.2;
    COLORREF g = mix(mix(C_VIEW_TOP, C_VIEW_BOT, 0.5), C_HUD_FG, 0.22);
    for (int k = (int)floor(y0 / step); k <= (int)ceil(y1 / step); k++)
        seg2(dc, P(v, v3(-half, k * step, base)), P(v, v3(half, k * step, base)), g, 1, 0);
    int xs = (int)(half / step);
    for (int k = -xs; k <= xs; k++)
        seg2(dc, P(v, v3(k * step, y0, base)), P(v, v3(k * step, y1, base)), g, 1, 0);
    for (int sd = -1; sd <= 1; sd += 2)
        seg2(dc, P(v, v3(sd * r * 1.7, y0, base)), P(v, v3(sd * r * 1.7, y1, base)), C_MACH_EDGE, 2, 0);
}

static void draw_pipe(HDC dc, const View *v, const Pose *ps)
{
    const Section *s = v->sec;
    double per = s->perimeter, y0 = ps->y_head, y1 = ps->y_tail;
    /* các dải dọc thân ống hướng về người xem: khối lồi nên không đè nhau */
    double vs[160];
    int nv = 0;
    for (int i = 0; i < 96; i++) vs[nv++] = per * i / 96;
    double bp[16];
    int nb = sec_breakpoints(s, bp, 16);
    for (int i = 0; i < nb; i++) if (bp[i] < per - 1e-9) vs[nv++] = bp[i];
    for (int i = 1; i < nv; i++) for (int j = i; j > 0 && vs[j] < vs[j - 1]; j--) { double t = vs[j]; vs[j] = vs[j - 1]; vs[j - 1] = t; }
    for (int i = 0; i < nv; i++) {
        double va = vs[i], vb = i + 1 < nv ? vs[i + 1] : vs[0] + per;
        if (vb - va < 1e-9) continue;
        V3 n = normal_at(v, ps, 0.5 * (va + vb));
        if (!faces(&v->cam, n)) continue;
        COLORREF c = shade(v, C_METAL, n, 0.34, 0.7, 0.5, 26);
        POINT q[4] = {P(v, surf(v, ps, va, y0, 1)), P(v, surf(v, ps, vb, y0, 1)),
                      P(v, surf(v, ps, vb, y1, 1)), P(v, surf(v, ps, va, y1, 1))};
        fillp(dc, q, 4, c, c);
    }
    /* miệng ống phía đầu tự do: vành khăn + lòng ống tối */
    if (faces(&v->cam, v3(0, -1, 0))) {
        POINT ring[96], hole[96];
        double a = 0, b = 0;
        for (int i = 0; i < 96; i++) {
            double cx, cy;
            sec_point(s, per * i / 96, &cx, &cy);
            if (fabs(cx) > a) a = fabs(cx);
            if (fabs(cy) > b) b = fabs(cy);
        }
        double t = s->kind == SEC_ROUND ? 0.06 * s->radius : s->wall;
        if (t <= 0) t = 2;
        double fx = (a - t) / a, fy = (b - t) / b, rr = rad(ps->rotary);
        for (int i = 0; i < 96; i++) {
            ring[i] = P(v, surf(v, ps, per * i / 96, y0, 1));
            double cx, cy;
            sec_point(s, per * i / 96, &cx, &cy);
            cx *= fx; cy *= fy;
            hole[i] = P(v, v3(cx * cos(rr) - cy * sin(rr), y0, cx * sin(rr) + cy * cos(rr)));
        }
        fillp(dc, ring, 96, shade(v, C_METAL, v3(0, -1, 0), 0.5, 0.6, 0.5, 26), C_METAL_EDGE);
        fillp(dc, hole, 96, mix(C_METAL_EDGE, C_HUD_BG, 0.35), C_METAL_EDGE);
    }
    /* đường sinh mảnh cho thấy ống đang xoay; vạch mốc 0 độ màu nhấn */
    for (int m = 0; m < 8; m++) {
        double vv = per * m / 8;
        if (!faces(&v->cam, normal_at(v, ps, vv))) continue;
        seg2(dc, P(v, surf(v, ps, vv, y0, 1)), P(v, surf(v, ps, vv, y1, 1)),
             m == 0 ? C_ACCENT : mix(C_METAL_EDGE, C_METAL, 0.62), m == 0 ? 2 : 1, 0);
    }
}

static void draw_trace(HDC dc, const View *v, const Pose *ps, const TP *tr, int n, double tmax, int ghost)
{
    POINT *run = (POINT *)malloc(sizeof(POINT) * (size_t)(n + 1));
    int k = 0;
    COLORREF ghostc = mix(C_CUT, C_METAL_EDGE, 0.2), halo = mix(C_CUT, C_HUD_BG, 0.6);
    for (int pass = 0; pass < (ghost ? 1 : 2); pass++) {
        k = 0;
        int prev_ok = 0;
        for (int i = 0; i < n; i++) {
            if (!ghost && tr[i].t > tmax) break;
            int ok = faces(&v->cam, normal_at(v, ps, tr[i].v));
            if (tr[i].start || !ok || !prev_ok) {
                if (k >= 2) line(dc, run, k, ghost ? ghostc : (pass ? C_CUT : halo), ghost ? 1 : (pass ? 2 : 5), ghost);
                k = 0;
            }
            if (ok) run[k++] = P(v, surf(v, ps, tr[i].v, tr[i].u + ps->y_head, 1.004));
            prev_ok = ok;
        }
        if (k >= 2) line(dc, run, k, ghost ? ghostc : (pass ? C_CUT : halo), ghost ? 1 : (pass ? 2 : 5), ghost);
    }
    free(run);
}

static void draw_chuck(HDC dc, const View *v, const Pose *ps)
{
    double r = v->sec->max_radius * 1.55, y0 = ps->y_tail, y1 = ps->y_tail + v->sec->max_radius * 0.9;
    for (int k = 0; k < 48; k++) {
        double a0 = 2 * PC_PI * k / 48, a1 = 2 * PC_PI * (k + 1) / 48, am = 0.5 * (a0 + a1);
        V3 n = v3(sin(am), 0, cos(am));
        if (!faces(&v->cam, n)) continue;
        COLORREF c = shade(v, C_MACHINE, n, 0.5, 0.55, 0.35, 26);
        POINT q[4] = {P(v, v3(r * sin(a0), y0, r * cos(a0))), P(v, v3(r * sin(a1), y0, r * cos(a1))),
                      P(v, v3(r * sin(a1), y1, r * cos(a1))), P(v, v3(r * sin(a0), y1, r * cos(a0)))};
        fillp(dc, q, 4, c, c);
    }
    for (int e = 0; e < 2; e++) {
        double yy = e ? y1 : y0;
        V3 n = v3(0, e ? 1 : -1, 0);
        if (!faces(&v->cam, n)) continue;
        POINT q[48];
        for (int k = 0; k < 48; k++) q[k] = P(v, v3(r * sin(2 * PC_PI * k / 48), yy, r * cos(2 * PC_PI * k / 48)));
        fillp(dc, q, 48, shade(v, C_MACHINE, n, 0.55, 0.5, 0.25, 26), C_MACH_EDGE);
    }
    double rr = v->sec->max_radius;
    for (int k = 0; k < 360; k += 120) {       /* ba vấu kẹp cho thấy mâm đang quay */
        double a = rad(k - ps->rotary);
        seg2(dc, P(v, v3(rr * 1.5 * sin(a), y0 - 0.5, rr * 1.5 * cos(a))),
             P(v, v3(rr * 1.0 * sin(a), y0 - 0.5, rr * 1.0 * cos(a))), C_MACH_EDGE, 4, 0);
    }
}

static void draw_torch(HDC dc, View *v, const Pose *ps)
{
    double r = v->sec->max_radius, x = ps->cross;
    double tip = v->sec->ref_height + ps->lift;
    double rt = r * 0.26 < 4 ? 4 : (r * 0.26 > 16 ? 16 : r * 0.26);
    double nozzle = tip + rt * 1.6, top = v->sec->ref_height + r * 2.4;
    V3 d = v->cam.dir, h = unit(v3(d.x, d.y, 0)), sd = v->cam.right;
    for (int part = 0; part < 2; part++) {
        double z0 = part ? tip : nozzle, z1 = part ? nozzle : top;
        double r0 = part ? rt * 0.32 : rt, r1 = part ? rt * 0.8 : rt;
        COLORREF base = part ? C_NOZZLE : C_METAL;
        for (int i = 0; i < 10; i++) {
            double f0 = -PC_PI / 2 + PC_PI * i / 10, f1 = -PC_PI / 2 + PC_PI * (i + 1) / 10, fm = 0.5 * (f0 + f1);
            V3 n = v3(cos(fm) * h.x + sin(fm) * sd.x, cos(fm) * h.y + sin(fm) * sd.y, 0);
            COLORREF c = shade(v, base, n, 0.45, 0.6, 0.6, 30);
            POINT q[4] = {
                P(v, v3(x + r0 * (cos(f0) * h.x + sin(f0) * sd.x), r0 * (cos(f0) * h.y + sin(f0) * sd.y), z0)),
                P(v, v3(x + r0 * (cos(f1) * h.x + sin(f1) * sd.x), r0 * (cos(f1) * h.y + sin(f1) * sd.y), z0)),
                P(v, v3(x + r1 * (cos(f1) * h.x + sin(f1) * sd.x), r1 * (cos(f1) * h.y + sin(f1) * sd.y), z1)),
                P(v, v3(x + r1 * (cos(f0) * h.x + sin(f0) * sd.x), r1 * (cos(f0) * h.y + sin(f0) * sd.y), z1))};
            fillp(dc, q, 4, c, c);
        }
    }
    double hit = sec_surface_height(v->sec, ps->rotary, x);
    POINT a = P(v, v3(x, 0, tip)), b = P(v, v3(x, 0, hit));
    if (v->torch) {
        seg2(dc, a, b, mix(C_TORCH_ON, C_VIEW_TOP, 0.45), 11, 0);
        seg2(dc, a, b, C_TORCH_ON, 5, 0);
        seg2(dc, a, b, C_ARC_CORE, 2, 0);
        SelectObject(dc, GetStockObject(DC_PEN));
        SelectObject(dc, GetStockObject(DC_BRUSH));
        SetDCPenColor(dc, C_TORCH_ON); SetDCBrushColor(dc, C_TORCH_ON);
        Ellipse(dc, b.x - 7, b.y - 7, b.x + 8, b.y + 8);
        SetDCPenColor(dc, C_ARC_CORE); SetDCBrushColor(dc, C_ARC_CORE);
        Ellipse(dc, b.x - 3, b.y - 3, b.x + 4, b.y + 4);
    } else {
        double gap = tip - hit;
        COLORREF gc = mix(C_HUD_FG, C_VIEW_TOP, 0.25);
        if (gap > 0.05 && gap < r * 4) seg2(dc, a, b, gc, 1, 1);
        if (gap > 0.5 && gap < r * 4) {
            wchar_t txt[48];
            swprintf(txt, 48, L"hở %.1f mm", gap);
            POINT p = P(v, v3(x + rt * 1.3 * sd.x, rt * 1.3 * sd.y, 0.5 * (tip + nozzle)));
            SelectObject(dc, v->f_ui);
            SIZE sz;
            GetTextExtentPoint32W(dc, txt, (int)wcslen(txt), &sz);
            RECT rc = {p.x - 4, p.y - sz.cy / 2 - 2, p.x + sz.cx + 4, p.y + sz.cy / 2 + 2};
            HBRUSH br = CreateSolidBrush(C_HUD_BG);
            FillRect(dc, &rc, br);
            DeleteObject(br);
            SetBkMode(dc, TRANSPARENT);
            SetTextColor(dc, gc);
            TextOutW(dc, p.x, p.y - sz.cy / 2, txt, (int)wcslen(txt));
        }
    }
}

static void draw_hud(HDC dc, View *v, int w, int h)
{
    static const wchar_t *names[NAX] = {L"ngang", L"ống ra vào", L"lên xuống", L"xoay"};
    static const wchar_t let[NAX] = {L'X', L'Y', L'Z', L'A'};
    static const int order[NAX] = {AX_X, AX_Y, AX_Z, AX_A};
    wchar_t rows[6][80];
    int nr = 0;
    for (int i = 0; i < NAX; i++) {
        int a = order[i];
        swprintf(rows[nr++], 80, L"%lc %10.2f%ls  %ls", let[a], v->pos[a], a == AX_A ? L"°  " : L" mm", names[a]);
    }
    if (v->sec->kind == SEC_ROUND)
        swprintf(rows[nr++], 80, L"ống tròn Ø%g × dài %g mm", 2 * v->sec->radius, v->len);
    else
        swprintf(rows[nr++], 80, L"ống hộp %g×%g × dài %g mm", v->sec->width, v->sec->height, v->len);
    SelectObject(dc, v->f_mono);
    int wmax = 0, lh = 18;
    for (int i = 0; i < nr; i++) {
        SIZE sz;
        GetTextExtentPoint32W(dc, rows[i], (int)wcslen(rows[i]), &sz);
        if (sz.cx > wmax) wmax = sz.cx;
        lh = sz.cy + 2;
    }
    RECT rc = {8, 8, 8 + wmax + 20, 8 + lh * nr + 14 + (v->torch ? lh : 0)};
    HBRUSH br = CreateSolidBrush(C_HUD_BG);
    FillRect(dc, &rc, br);
    SetBkMode(dc, TRANSPARENT);
    SetTextColor(dc, C_HUD_FG);
    for (int i = 0; i < nr; i++) TextOutW(dc, 18, 14 + i * lh, rows[i], (int)wcslen(rows[i]));
    if (v->torch) {
        SelectObject(dc, v->f_ui);
        SetTextColor(dc, C_TORCH_ON);
        TextOutW(dc, 18, 14 + nr * lh, L"NGUỒN CẮT ĐANG BẬT", (int)wcslen(L"NGUỒN CẮT ĐANG BẬT"));
    }
    /* ba trục ở góc dưới trái */
    int ox = 46, oy = h - 46;
    SelectObject(dc, GetStockObject(DC_PEN));
    SelectObject(dc, GetStockObject(DC_BRUSH));
    SetDCPenColor(dc, C_HUD_BG); SetDCBrushColor(dc, C_HUD_BG);
    Ellipse(dc, ox - 34, oy - 34, ox + 34, oy + 34);
    struct { V3 e; COLORREF c; const wchar_t *l; } ax[3] = {
        {{1, 0, 0}, C_AX_X, L"X"}, {{0, 1, 0}, C_AX_Y, L"Y"}, {{0, 0, 1}, C_AX_Z, L"Z"}};
    for (int i = 0; i < 3; i++)                 /* xa vẽ trước */
        for (int j = i + 1; j < 3; j++)
            if (depth(&v->cam, ax[j].e) < depth(&v->cam, ax[i].e)) { __typeof__(ax[0]) t = ax[i]; ax[i] = ax[j]; ax[j] = t; }
    SelectObject(dc, v->f_ui);
    for (int i = 0; i < 3; i++) {
        double sx = dot(ax[i].e, v->cam.right) * 24, sy = -dot(ax[i].e, v->cam.up) * 24;
        POINT a = {ox, oy}, b = {ox + (LONG)sx, oy + (LONG)sy};
        seg2(dc, a, b, ax[i].c, 3, 0);
        SetTextColor(dc, ax[i].c);
        TextOutW(dc, ox + (int)(sx * 1.3) - 4, oy + (int)(sy * 1.3) - 8, ax[i].l, 1);
    }
    /* gợi ý thao tác */
    const wchar_t *hint = v->focus_work
        ? L"kéo trái: xoay · kéo phải: dịch · lăn chuột: phóng to · nháy đúp: toàn cảnh"
        : L"kéo trái: xoay · kéo phải: dịch · lăn chuột: phóng to · nháy đúp: vùng cắt";
    SelectObject(dc, v->f_small);
    SIZE sz;
    GetTextExtentPoint32W(dc, hint, (int)wcslen(hint), &sz);
    RECT hr = {w - sz.cx - 20, 8, w - 8, 8 + sz.cy + 6};
    FillRect(dc, &hr, br);
    SetTextColor(dc, C_HUD_FG);
    TextOutW(dc, hr.left + 6, 11, hint, (int)wcslen(hint));
    DeleteObject(br);
}

static void render(View *v, HDC dc, int w, int h)
{
    /* nền chuyển sắc dọc kiểu FreeCAD */
    for (int i = 0; i < 64; i++) {
        RECT r = {0, h * i / 64, w, h * (i + 1) / 64 + 1};
        HBRUSH b = CreateSolidBrush(mix(C_VIEW_TOP, C_VIEW_BOT, i / 63.0));
        FillRect(dc, &r, b);
        DeleteObject(b);
    }
    if (!v->sec) {
        SetBkMode(dc, TRANSPARENT);
        SetTextColor(dc, C_HUD_FG);
        TextOutW(dc, 16, 16, L"Chưa có chương trình", (int)wcslen(L"Chưa có chương trình"));
        return;
    }
    Pose ps = pose_of(v);
    double r = v->sec->max_radius;
    draw_ground(dc, v, &ps);
    /* cột máy một bên ống: vẽ trước nếu nằm sau ống */
    double cx = -r * 1.9, w2 = r * 0.28, top = v->sec->ref_height + r * 2.4;
    int col_front = depth(&v->cam, v3(cx, 0, 0)) > depth(&v->cam, v3(0, 0, 0)) + r * 0.2;
    if (!col_front) box(dc, v, cx - w2, cx + w2, -w2, w2, -r * 1.9, top, C_MACHINE, C_MACH_EDGE);
    if (v->cam.dir.y <= 0) draw_chuck(dc, v, &ps);
    draw_pipe(dc, v, &ps);
    if (v->ntr) draw_trace(dc, v, &ps, v->tr, v->ntr, 0, 1);
    if (v->live) { if (v->nlv) draw_trace(dc, v, &ps, v->lv, v->nlv, 1e300, 0); }
    else if (v->ntr) draw_trace(dc, v, &ps, v->tr, v->ntr, v->t, 0);
    if (v->cam.dir.y > 0) draw_chuck(dc, v, &ps);
    if (col_front) box(dc, v, cx - w2, cx + w2, -w2, w2, -r * 1.9, top, C_MACHINE, C_MACH_EDGE);
    double hh = r * 0.18;
    box(dc, v, -r * 2.2, r * 1.6, -hh * 1.4, hh * 1.4, top - hh, top + hh, C_MACHINE, C_MACH_EDGE);
    draw_torch(dc, v, &ps);
    draw_hud(dc, v, w, h);
}

/* ---- canh khung nhìn ---- */
static void refit(View *v, int w, int h)
{
    if (!v->sec || w < 10 || h < 10) return;
    double r = v->sec->max_radius, mnx = 1e300, mny = 1e300, mxx = -1e300, mxy = -1e300;
    V3 pts[64];
    int n = 0;
    if (v->focus_work) {
        double span = r * 4 > 60 ? r * 4 : 60;
        for (int i = 0; i < 2; i++) for (int j = 0; j < 2; j++) for (int k = 0; k < 2; k++)
            pts[n++] = v3(i ? r * 1.7 : -r * 2.1, j ? span : -span, k ? v->sec->ref_height + r * 2.6 : -r * 1.2);
    } else {
        double y0 = -v->y_hi, y1 = v->len - v->y_lo, pad = v->len * 0.06 > r * 2 ? v->len * 0.06 : r * 2;
        y0 -= pad; y1 += pad;
        for (int i = 0; i < 2; i++) for (int j = 0; j < 2; j++) for (int k = 0; k < 2; k++)
            pts[n++] = v3(i ? r * 1.75 : -r * 2.2, j ? y1 : y0, k ? v->sec->ref_height + r * 2.6 : -r * 1.95);
    }
    for (int i = 0; i < n; i++) {
        double sx = dot(pts[i], v->cam.right), sy = -dot(pts[i], v->cam.up);
        if (sx < mnx) mnx = sx;
        if (sx > mxx) mxx = sx;
        if (sy < mny) mny = sy;
        if (sy > mxy) mxy = sy;
    }
    double pad = 34;
    double sx = (w - 2 * pad) / (mxx - mnx > 1e-6 ? mxx - mnx : 1e-6);
    double sy = (h - 2 * pad) / (mxy - mny > 1e-6 ? mxy - mny : 1e-6);
    v->scale = sx < sy ? sx : sy;
    v->ox = w / 2.0 - (mnx + mxx) / 2 * v->scale;
    v->oy = h / 2.0 - (mny + mxy) / 2 * v->scale;
}

static View *getv(HWND h) { return (View *)GetWindowLongPtrW(h, GWLP_USERDATA); }

static void build_trace(View *v)
{
    v->ntr = 0;
    v->y_lo = 0; v->y_hi = 0;
    if (!v->plan || !v->sec) return;
    int started = 0, prev_cut = 0;
    for (int i = 0; i < v->plan->n; i++) {
        const Move *m = &v->plan->mv[i];
        if (!m->dwell) {
            if (!started) { v->y_lo = v->y_hi = m->b[AX_Y]; started = 1; }
            if (m->b[AX_Y] < v->y_lo) v->y_lo = m->b[AX_Y];
            if (m->b[AX_Y] > v->y_hi) v->y_hi = m->b[AX_Y];
        }
        int cut = m->torch && !m->rapid && !m->dwell &&
                  (fabs(m->b[AX_Y] - m->a[AX_Y]) + fabs(m->b[AX_A] - m->a[AX_A]) + fabs(m->b[AX_X] - m->a[AX_X])) > 1e-9;
        if (!cut) { if (m->dwell && m->torch) continue; prev_cut = 0; continue; }
        double L = 0;
        for (int k = 0; k < NAX; k++) L += (m->b[k] - m->a[k]) * (m->b[k] - m->a[k]);
        L = sqrt(L);
        int steps = (int)ceil(L / 0.6);
        if (steps < 1) steps = 1;
        for (int s = prev_cut ? 1 : 0; s <= steps; s++) {
            double f = (double)s / steps;
            if (v->ntr == v->captr) {
                v->captr = v->captr ? v->captr * 2 : 4096;
                v->tr = (TP *)realloc(v->tr, sizeof(TP) * (size_t)v->captr);
            }
            TP *t = &v->tr[v->ntr++];
            double A = m->a[AX_A] + (m->b[AX_A] - m->a[AX_A]) * f;
            double X = m->a[AX_X] + (m->b[AX_X] - m->a[AX_X]) * f;
            t->u = m->a[AX_Y] + (m->b[AX_Y] - m->a[AX_Y]) * f;
            t->v = sec_v_of_contact(v->sec, A, X);
            t->t = m->t0 + m->dt * f;
            t->start = !prev_cut && s == 0;
        }
        prev_cut = 1;
    }
}

void view3d_set_scene(HWND h, const Section *s, const Machine *m, double len, const Plan *plan)
{
    View *v = getv(h);
    if (!v) return;
    v->sec = s; v->mach = m; v->len = len; v->plan = plan;
    v->nlv = 0;
    build_trace(v);
    RECT rc;
    GetClientRect(h, &rc);
    refit(v, rc.right, rc.bottom);
    view3d_set_time(h, v->t);
}

void view3d_set_time(HWND h, double t)
{
    View *v = getv(h);
    if (!v) return;
    v->t = t;
    v->live = 0;
    int line_no;
    if (v->plan) plan_state(v->plan, t, v->pos, &v->torch, &line_no);
    InvalidateRect(h, NULL, FALSE);
}

void view3d_set_live(HWND h, const double pos[NAX], int torch)
{
    View *v = getv(h);
    if (!v || !v->sec) return;
    if (!v->live) v->nlv = 0;
    v->live = 1;
    memcpy(v->pos, pos, sizeof v->pos);
    v->torch = torch;
    if (torch) {
        if (v->nlv == v->caplv) {
            v->caplv = v->caplv ? v->caplv * 2 : 4096;
            v->lv = (TP *)realloc(v->lv, sizeof(TP) * (size_t)v->caplv);
        }
        TP *t = &v->lv[v->nlv++];
        t->u = pos[AX_Y]; t->v = sec_v_of_contact(v->sec, pos[AX_A], pos[AX_X]); t->t = 0;
        t->start = v->nlv == 1;
    }
    InvalidateRect(h, NULL, FALSE);
}

void view3d_toggle_focus(HWND h)
{
    View *v = getv(h);
    if (!v) return;
    v->focus_work = !v->focus_work;
    RECT rc;
    GetClientRect(h, &rc);
    refit(v, rc.right, rc.bottom);
    InvalidateRect(h, NULL, FALSE);
}

int view3d_focus_is_work(HWND h) { View *v = getv(h); return v ? v->focus_work : 1; }

void view3d_reset(HWND h)
{
    View *v = getv(h);
    if (!v) return;
    cam_default(&v->cam);
    RECT rc;
    GetClientRect(h, &rc);
    refit(v, rc.right, rc.bottom);
    InvalidateRect(h, NULL, FALSE);
}

int view3d_render_bmp(HWND h, const wchar_t *path, int w, int hgt)
{
    View *v = getv(h);
    if (!v) return -1;
    HDC scr = GetDC(h);
    HDC dc = CreateCompatibleDC(scr);
    BITMAPINFO bi;
    memset(&bi, 0, sizeof bi);
    bi.bmiHeader.biSize = sizeof bi.bmiHeader;
    bi.bmiHeader.biWidth = w; bi.bmiHeader.biHeight = hgt;
    bi.bmiHeader.biPlanes = 1; bi.bmiHeader.biBitCount = 24; bi.bmiHeader.biCompression = BI_RGB;
    void *bits = NULL;
    HBITMAP bmp = CreateDIBSection(scr, &bi, DIB_RGB_COLORS, &bits, NULL, 0);
    HGDIOBJ old = SelectObject(dc, bmp);
    double s = v->scale, ox = v->ox, oy = v->oy;
    refit(v, w, hgt);
    render(v, dc, w, hgt);
    GdiFlush();
    v->scale = s; v->ox = ox; v->oy = oy;
    int stride = ((w * 3 + 3) / 4) * 4;
    BITMAPFILEHEADER fh;
    memset(&fh, 0, sizeof fh);
    fh.bfType = 0x4D42;
    fh.bfOffBits = sizeof fh + sizeof bi.bmiHeader;
    fh.bfSize = fh.bfOffBits + (DWORD)(stride * hgt);
    FILE *f = _wfopen(path, L"wb");
    int rc = -1;
    if (f) {
        fwrite(&fh, sizeof fh, 1, f);
        fwrite(&bi.bmiHeader, sizeof bi.bmiHeader, 1, f);
        fwrite(bits, 1, (size_t)(stride * hgt), f);
        fclose(f);
        rc = 0;
    }
    SelectObject(dc, old);
    DeleteObject(bmp);
    DeleteDC(dc);
    ReleaseDC(h, scr);
    return rc;
}

double view3d_bench(HWND h, int w, int hgt, int frames)
{
    View *v = getv(h);
    if (!v || frames < 1) return -1;
    HDC scr = GetDC(h), dc = CreateCompatibleDC(scr);
    HBITMAP bmp = CreateCompatibleBitmap(scr, w, hgt);
    HGDIOBJ old = SelectObject(dc, bmp);
    double s = v->scale, ox = v->ox, oy = v->oy, az = v->cam.az;
    refit(v, w, hgt);
    LARGE_INTEGER f, t0, t1;
    QueryPerformanceFrequency(&f);
    QueryPerformanceCounter(&t0);
    for (int i = 0; i < frames; i++) {
        v->cam.az = az + i * 2.0;               /* xoay dần như khi kéo chuột */
        cam_update(&v->cam);
        render(v, dc, w, hgt);
    }
    GdiFlush();
    QueryPerformanceCounter(&t1);
    v->cam.az = az;
    cam_update(&v->cam);
    v->scale = s; v->ox = ox; v->oy = oy;
    SelectObject(dc, old);
    DeleteObject(bmp);
    DeleteDC(dc);
    ReleaseDC(h, scr);
    return 1000.0 * (double)(t1.QuadPart - t0.QuadPart) / (double)f.QuadPart / frames;
}

static LRESULT CALLBACK proc(HWND h, UINT msg, WPARAM wp, LPARAM lp)
{
    View *v = getv(h);
    switch (msg) {
    case WM_CREATE: {
        v = (View *)calloc(1, sizeof(View));
        cam_default(&v->cam);
        v->focus_work = 1;
        v->scale = 1;
        v->f_mono = CreateFontW(-15, 0, 0, 0, FW_NORMAL, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY,
                                FIXED_PITCH, L"Consolas");
        v->f_ui = CreateFontW(-13, 0, 0, 0, FW_BOLD, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, L"Segoe UI");
        v->f_small = CreateFontW(-12, 0, 0, 0, FW_NORMAL, 0, 0, 0, DEFAULT_CHARSET, 0, 0, CLEARTYPE_QUALITY, 0, L"Segoe UI");
        SetWindowLongPtrW(h, GWLP_USERDATA, (LONG_PTR)v);
        return 0;
    }
    case WM_DESTROY:
        if (v) {
            DeleteObject(v->f_mono); DeleteObject(v->f_ui); DeleteObject(v->f_small);
            free(v->tr); free(v->lv); free(v);
            SetWindowLongPtrW(h, GWLP_USERDATA, 0);
        }
        return 0;
    case WM_SIZE:
        if (v) refit(v, LOWORD(lp), HIWORD(lp));
        InvalidateRect(h, NULL, FALSE);
        return 0;
    case WM_ERASEBKGND:
        return 1;
    case WM_PAINT: {
        PAINTSTRUCT ps;
        HDC dc = BeginPaint(h, &ps);
        RECT rc;
        GetClientRect(h, &rc);
        HDC mem = CreateCompatibleDC(dc);
        HBITMAP bmp = CreateCompatibleBitmap(dc, rc.right, rc.bottom);
        HGDIOBJ old = SelectObject(mem, bmp);
        if (v) render(v, mem, rc.right, rc.bottom);
        BitBlt(dc, 0, 0, rc.right, rc.bottom, mem, 0, 0, SRCCOPY);
        SelectObject(mem, old);
        DeleteObject(bmp);
        DeleteDC(mem);
        EndPaint(h, &ps);
        return 0;
    }
    case WM_LBUTTONDOWN: case WM_RBUTTONDOWN:
        SetFocus(h);
        SetCapture(h);
        v->drag_mode = msg == WM_LBUTTONDOWN && !(wp & MK_SHIFT) ? 1 : 2;
        v->mx = GET_X_LPARAM(lp); v->my = GET_Y_LPARAM(lp);
        return 0;
    case WM_LBUTTONUP: case WM_RBUTTONUP:
        v->drag_mode = 0;
        ReleaseCapture();
        return 0;
    case WM_MOUSEMOVE:
        if (v && v->drag_mode) {
            int x = GET_X_LPARAM(lp), y = GET_Y_LPARAM(lp);
            if (v->drag_mode == 1) {
                v->cam.az -= (x - v->mx) * 0.5;
                v->cam.el += (y - v->my) * 0.5;
                if (v->cam.el > 85) v->cam.el = 85;
                if (v->cam.el < -85) v->cam.el = -85;
                cam_update(&v->cam);
            } else {
                v->ox += x - v->mx; v->oy += y - v->my;
            }
            v->mx = x; v->my = y;
            InvalidateRect(h, NULL, FALSE);
        }
        return 0;
    case WM_MOUSEWHEEL: {
        /* phóng to quanh con trỏ: chỗ đang chỉ vào đứng yên */
        POINT p = {GET_X_LPARAM(lp), GET_Y_LPARAM(lp)};
        ScreenToClient(h, &p);
        double f = GET_WHEEL_DELTA_WPARAM(wp) > 0 ? 1.12 : 1 / 1.12;
        v->ox = p.x - (p.x - v->ox) * f;
        v->oy = p.y - (p.y - v->oy) * f;
        v->scale *= f;
        InvalidateRect(h, NULL, FALSE);
        return 0;
    }
    case WM_LBUTTONDBLCLK:
        view3d_toggle_focus(h);
        SendMessageW(GetParent(h), WM_COMMAND, MAKEWPARAM(GetDlgCtrlID(h), 1), (LPARAM)h);
        return 0;
    }
    return DefWindowProcW(h, msg, wp, lp);
}

void view3d_register(HINSTANCE inst)
{
    WNDCLASSW wc;
    memset(&wc, 0, sizeof wc);
    wc.style = CS_DBLCLKS | CS_HREDRAW | CS_VREDRAW;
    wc.lpfnWndProc = proc;
    wc.hInstance = inst;
    wc.hCursor = LoadCursor(NULL, IDC_ARROW);
    wc.lpszClassName = VIEW3D_CLASS;
    RegisterClassW(&wc);
}
