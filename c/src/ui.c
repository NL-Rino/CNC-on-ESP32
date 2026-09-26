/* PipeCutC.exe - giao diện Win32 thuần cho bản C.
 *
 * Không khung giao diện, không thư viện ngoài: chỉ các điều khiển chuẩn của
 * Windows (comctl32), vẽ 3D bằng GDI (view3d.c), nói chuyện với máy qua
 * comm.c.  Bố cục giống bản Python: bên trái là phôi + nguyên công + thông số,
 * bên phải ba thẻ "Mô phỏng 3D", "G-code", "Máy".
 *
 * Dòng lệnh (để kiểm thử tự động):
 *   PipeCutC.exe --selftest THƯ_MỤC     sinh 2 chương trình mẫu, ghi số liệu + ảnh BMP rồi thoát
 *   PipeCutC.exe --shot ẢNH.bmp [thẻ]    mở cửa sổ, chụp lại rồi thoát (thẻ 0/1/2)
 *   PipeCutC.exe --connect ĐỊA_CHỈ [--run] [--log TỆP] [--quit-after GIÂY]
 *        --run chỉ được phép với 127.0.0.1/localhost (máy ảo), không bao giờ với máy thật.
 */
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0601
#endif
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <windowsx.h>
#include <commctrl.h>
#include <commdlg.h>
#include <shellapi.h>
#include <shlobj.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#include "core.h"
#include "view3d.h"
#include "comm.h"

int demo_ops(const Section *s, Operation *ops);

#define APP_NAME  L"PipeCut C"
#define APP_VER   L"0.1"
#define WM_COMM   (WM_APP + 1)
#define MAXOPS    64
#define PANEL_W   340
#define PANEL_H   752

enum {
    ID_KIND = 100, ID_DIA, ID_LEN, ID_W, ID_H, ID_RC, ID_WALL,
    ID_LIST, ID_OPKIND, ID_OX, ID_OT, ID_OA, ID_OB, ID_OC, ID_LA, ID_LB, ID_LC, ID_LT,
    ID_ADD, ID_UPD, ID_DEL, ID_DEMO,
    ID_FEED, ID_KERF, ID_CUTH, ID_PIERCEH, ID_PDELAY, ID_LEAD,
    ID_GEN, ID_OPEN, ID_SAVE, ID_STATS,
    ID_TAB, ID_VIEW, ID_PLAY, ID_SEEK, ID_TIME, ID_SPEED, ID_FOCUS, ID_RESETV,
    ID_GCODE,
    ID_PORTL, ID_PORT, ID_REFRESH, ID_CONNECT, ID_FOLLOW, ID_MSTATE,
    ID_HOME, ID_UNLOCK, ID_ZERO_Y, ID_ZERO_A, ID_JOGL, ID_JSTEP,
    ID_JXM, ID_JXP, ID_JYM, ID_JYP, ID_JZM, ID_JZP, ID_JAM, ID_JAP,
    ID_RUN, ID_PAUSE, ID_RESUME, ID_STOP, ID_PROG, ID_MDI, ID_SEND, ID_LOG,
    ID_STATUS
};
enum { TM_PLAY = 1, TM_SHOT = 2, TM_QUIT = 3, TM_RUN = 4 };

static HINSTANCE g_inst;
static HWND g_main, g_panel, g_tab, g_view, g_list, g_status;
static int g_dpi = 96;
static HFONT g_font, g_bold, g_mono, g_big;
static HWND g_page[3][32];
static int g_npage[3], g_cur_page;

static Section g_sec;
static Machine g_mach;
static double g_len = 1000;
static Operation g_ops[MAXOPS];
static int g_nops;
static GBuf g_gc;
static Plan g_plan;
static wchar_t g_file[MAX_PATH];          /* chương trình đang mở từ tệp (rỗng = tự sinh) */
static double g_t, g_speed = 1;
static int g_playing, g_last_line;
static DWORD g_last_tick;
static int g_filling;

static Comm *g_comm;
static wchar_t g_target[128];

static int g_scroll;                      /* khung trái đã cuộn bao nhiêu điểm ảnh */
static wchar_t g_ini[MAX_PATH];
static int g_selftest;
static wchar_t g_shot[MAX_PATH], g_logfile[MAX_PATH];
static int g_shot_page, g_autorun, g_quit_after;

static int S(int v) { return MulDiv(v, g_dpi, 96); }

/* ------------------------------------------------------------------ */
/* tạo điều khiển                                                       */
/* ------------------------------------------------------------------ */
static HWND mk(HWND parent, const wchar_t *cls, const wchar_t *text, DWORD style, int x, int y, int w, int h, int id)
{
    DWORD ex = !wcscmp(cls, L"EDIT") ? WS_EX_CLIENTEDGE : 0;
    HWND c = CreateWindowExW(ex, cls, text, WS_CHILD | WS_VISIBLE | style, S(x), S(y), S(w), S(h), parent,
                             (HMENU)(INT_PTR)id, g_inst, NULL);
    SendMessageW(c, WM_SETFONT, (WPARAM)g_font, FALSE);
    return c;
}

static HWND on_page(int page, HWND h)
{
    g_page[page][g_npage[page]++] = h;
    return h;
}

static HWND pbtn(int page, const wchar_t *t, int id) { return on_page(page, mk(g_main, L"BUTTON", t, WS_TABSTOP, 0, 0, 10, 10, id)); }

static void header(int y, const wchar_t *t)
{
    HWND h = mk(g_panel, L"STATIC", t, SS_LEFT, 10, y, 320, 20, 0);
    SendMessageW(h, WM_SETFONT, (WPARAM)g_bold, FALSE);
}

static void field(int x, int y, const wchar_t *label, int id, int lid)
{
    mk(g_panel, L"STATIC", label, SS_LEFT | SS_CENTERIMAGE, x, y, 102, 24, lid);
    mk(g_panel, L"EDIT", L"", WS_TABSTOP | ES_AUTOHSCROLL, x + 102, y, 54, 24, id);
}

static double getnum(HWND parent, int id, double def)
{
    wchar_t b[64], *e;
    GetDlgItemTextW(parent, id, b, 64);
    for (wchar_t *p = b; *p; p++) if (*p == L',') *p = L'.';
    double v = wcstod(b, &e);
    return e == b ? def : v;
}

static void setnum(HWND parent, int id, double v)
{
    wchar_t b[64];
    swprintf(b, 64, L"%g", v);
    SetDlgItemTextW(parent, id, b);
}

static void u8w(const char *s, wchar_t *out, int n) { MultiByteToWideChar(CP_UTF8, 0, s, -1, out, n); }

static void status(int part, const wchar_t *t) { SendMessageW(g_status, SB_SETTEXTW, part, (LPARAM)t); }

static void fmt_time(double s, wchar_t *out, int n)
{
    int m = (int)(s / 60);
    swprintf(out, n, L"%d:%04.1f", m, s - 60 * m);
}

/* ------------------------------------------------------------------ */
/* thiết lập (lưu ở %APPDATA%\PipeCutC\settings.ini)                   */
/* ------------------------------------------------------------------ */
static double ini_num(const wchar_t *sec, const wchar_t *key, double def)
{
    wchar_t b[64];
    if (!g_ini[0]) return def;
    GetPrivateProfileStringW(sec, key, L"", b, 64, g_ini);
    return b[0] ? wcstod(b, NULL) : def;
}

static void ini_put(const wchar_t *sec, const wchar_t *key, double v)
{
    wchar_t b[64];
    swprintf(b, 64, L"%.10g", v);
    WritePrivateProfileStringW(sec, key, b, g_ini);
}

static void settings_load(void)
{
    Machine d;
    machine_defaults(&d);
    SendDlgItemMessageW(g_panel, ID_KIND, CB_SETCURSEL, (WPARAM)(int)ini_num(L"pipe", L"kind", 0), 0);
    setnum(g_panel, ID_DIA, ini_num(L"pipe", L"dia", 60));
    setnum(g_panel, ID_LEN, ini_num(L"pipe", L"len", 1000));
    setnum(g_panel, ID_W, ini_num(L"pipe", L"w", 50));
    setnum(g_panel, ID_H, ini_num(L"pipe", L"h", 50));
    setnum(g_panel, ID_RC, ini_num(L"pipe", L"rc", 0));
    setnum(g_panel, ID_WALL, ini_num(L"pipe", L"wall", 2));
    setnum(g_panel, ID_FEED, ini_num(L"cut", L"feed", d.cut_feed));
    setnum(g_panel, ID_KERF, ini_num(L"cut", L"kerf", d.kerf));
    setnum(g_panel, ID_CUTH, ini_num(L"cut", L"cut_height", d.cut_height));
    setnum(g_panel, ID_PIERCEH, ini_num(L"cut", L"pierce_height", d.pierce_height));
    setnum(g_panel, ID_PDELAY, ini_num(L"cut", L"pierce_delay", d.pierce_delay));
    setnum(g_panel, ID_LEAD, ini_num(L"cut", L"lead_in", d.lead_in));
    g_nops = (int)ini_num(L"ops", L"count", -1);
    if (g_nops < 0 || g_nops > MAXOPS) g_nops = -1;
    for (int i = 0; i < g_nops; i++) {
        wchar_t key[16], b[200];
        swprintf(key, 16, L"op%d", i);
        b[0] = 0;
        if (g_ini[0]) GetPrivateProfileStringW(L"ops", key, L"", b, 200, g_ini);
        Operation *o = &g_ops[i];
        int kind = 0, en = 1;
        memset(o, 0, sizeof *o);
        if (swscanf(b, L"%d %d %lf %lf %lf %lf %lf", &kind, &en, &o->x, &o->theta, &o->a, &o->b, &o->c) < 5 ||
            kind < 0 || kind >= OP_KINDS) { g_nops = i; break; }
        o->kind = (OpKind)kind;
        o->enabled = en;
    }
    if (g_ini[0]) GetPrivateProfileStringW(L"conn", L"target", L"", g_target, 128, g_ini);
}

static void settings_save(void)
{
    if (g_selftest || !g_ini[0]) return;
    ini_put(L"pipe", L"kind", (double)SendDlgItemMessageW(g_panel, ID_KIND, CB_GETCURSEL, 0, 0));
    static const struct { int id; const wchar_t *sec, *key; } F[] = {
        {ID_DIA, L"pipe", L"dia"}, {ID_LEN, L"pipe", L"len"}, {ID_W, L"pipe", L"w"}, {ID_H, L"pipe", L"h"},
        {ID_RC, L"pipe", L"rc"}, {ID_WALL, L"pipe", L"wall"}, {ID_FEED, L"cut", L"feed"},
        {ID_KERF, L"cut", L"kerf"}, {ID_CUTH, L"cut", L"cut_height"}, {ID_PIERCEH, L"cut", L"pierce_height"},
        {ID_PDELAY, L"cut", L"pierce_delay"}, {ID_LEAD, L"cut", L"lead_in"}};
    for (size_t i = 0; i < sizeof F / sizeof *F; i++) ini_put(F[i].sec, F[i].key, getnum(g_panel, F[i].id, 0));
    WritePrivateProfileSectionW(L"ops", L"\0", g_ini);
    ini_put(L"ops", L"count", g_nops);
    for (int i = 0; i < g_nops; i++) {
        wchar_t key[16], b[200];
        const Operation *o = &g_ops[i];
        swprintf(key, 16, L"op%d", i);
        swprintf(b, 200, L"%d %d %g %g %g %g %g", (int)o->kind, o->enabled, o->x, o->theta, o->a, o->b, o->c);
        WritePrivateProfileStringW(L"ops", key, b, g_ini);
    }
    WritePrivateProfileStringW(L"conn", L"target", g_target, g_ini);
}

/* ------------------------------------------------------------------ */
/* danh sách nguyên công                                               */
/* ------------------------------------------------------------------ */
static const wchar_t *short_name(OpKind k)
{
    static const wchar_t *N[OP_KINDS] = {L"Cắt đứt", L"Lỗ xuyên", L"Lỗ tròn", L"Rãnh"};
    return k < OP_KINDS ? N[k] : L"?";
}

static void op_size(const Operation *o, wchar_t *b, int n)
{
    switch (o->kind) {
    case OP_CUTOFF: swprintf(b, n, o->a ? L"vát %g°" : L"vuông", o->a); break;
    case OP_HOLE: case OP_CIRCLE: swprintf(b, n, L"Ø%g", o->a); break;
    case OP_SLOT: swprintf(b, n, L"%g × %g° r%g", o->a, o->b, o->c); break;
    default: b[0] = 0;
    }
}

static void list_fill(int sel)
{
    g_filling = 1;
    ListView_DeleteAllItems(g_list);
    for (int i = 0; i < g_nops; i++) {
        const Operation *o = &g_ops[i];
        wchar_t b[64];
        LVITEMW it;
        memset(&it, 0, sizeof it);
        it.mask = LVIF_TEXT;
        it.iItem = i;
        it.pszText = (wchar_t *)short_name(o->kind);
        ListView_InsertItem(g_list, &it);
        swprintf(b, 64, L"%g", o->x);
        ListView_SetItemText(g_list, i, 1, b);
        if (o->kind == OP_CUTOFF) wcscpy(b, L"-");
        else swprintf(b, 64, L"%g", o->theta);
        ListView_SetItemText(g_list, i, 2, b);
        op_size(o, b, 64);
        ListView_SetItemText(g_list, i, 3, b);
        ListView_SetCheckState(g_list, i, o->enabled);
    }
    if (sel >= 0 && sel < g_nops) {
        ListView_SetItemState(g_list, sel, LVIS_SELECTED | LVIS_FOCUSED, LVIS_SELECTED | LVIS_FOCUSED);
        ListView_EnsureVisible(g_list, sel, FALSE);
    }
    g_filling = 0;
}

static void editor_kind(OpKind k)
{
    static const wchar_t *LA[OP_KINDS] = {L"Góc vát (°)", L"Đường kính", L"Đường kính", L"Dài dọc ống"};
    if ((int)k < 0 || k >= OP_KINDS) k = OP_CUTOFF;
    SetDlgItemTextW(g_panel, ID_LA, LA[k]);
    SetDlgItemTextW(g_panel, ID_LB, k == OP_SLOT ? L"Rộng (° chu vi)" : L"-");
    SetDlgItemTextW(g_panel, ID_LC, k == OP_SLOT ? L"Bo góc (mm)" : L"-");
    EnableWindow(GetDlgItem(g_panel, ID_OT), k != OP_CUTOFF);
    EnableWindow(GetDlgItem(g_panel, ID_OB), k == OP_SLOT);
    EnableWindow(GetDlgItem(g_panel, ID_OC), k == OP_SLOT);
}

static void editor_load(int i)
{
    const Operation *o = &g_ops[i];
    SendDlgItemMessageW(g_panel, ID_OPKIND, CB_SETCURSEL, o->kind, 0);
    setnum(g_panel, ID_OX, o->x);
    setnum(g_panel, ID_OT, o->theta);
    setnum(g_panel, ID_OA, o->a);
    setnum(g_panel, ID_OB, o->b);
    setnum(g_panel, ID_OC, o->c);
    editor_kind(o->kind);
}

static Operation editor_read(void)
{
    Operation o;
    memset(&o, 0, sizeof o);
    int k = (int)SendDlgItemMessageW(g_panel, ID_OPKIND, CB_GETCURSEL, 0, 0);
    o.kind = (OpKind)(k < 0 ? 0 : k);
    o.enabled = 1;
    o.x = getnum(g_panel, ID_OX, 0);
    o.theta = o.kind == OP_CUTOFF ? 0 : getnum(g_panel, ID_OT, 0);
    o.a = getnum(g_panel, ID_OA, 0);
    o.b = o.kind == OP_SLOT ? getnum(g_panel, ID_OB, 0) : 0;
    o.c = o.kind == OP_SLOT ? getnum(g_panel, ID_OC, 0) : 0;
    return o;
}

static int list_sel(void) { return ListView_GetNextItem(g_list, -1, LVNI_SELECTED); }

/* ------------------------------------------------------------------ */
/* sinh chương trình                                                   */
/* ------------------------------------------------------------------ */
static int read_section(wchar_t *err, int n)
{
    int box = SendDlgItemMessageW(g_panel, ID_KIND, CB_GETCURSEL, 0, 0) == 1;
    g_len = getnum(g_panel, ID_LEN, 1000);
    if (g_len <= 0) { swprintf(err, n, L"Chiều dài ống phải lớn hơn 0."); return -1; }
    int rc = box ? sec_init_box(&g_sec, getnum(g_panel, ID_W, 0), getnum(g_panel, ID_H, 0),
                                getnum(g_panel, ID_RC, 0), getnum(g_panel, ID_WALL, 0))
                 : sec_init_round(&g_sec, getnum(g_panel, ID_DIA, 0));
    if (rc) swprintf(err, n, box ? L"Kích thước ống hộp không hợp lệ." : L"Đường kính ống không hợp lệ.");
    return rc;
}

static void read_machine(void)
{
    machine_defaults(&g_mach);
    g_mach.cut_feed = getnum(g_panel, ID_FEED, g_mach.cut_feed);
    g_mach.kerf = getnum(g_panel, ID_KERF, g_mach.kerf);
    g_mach.cut_height = getnum(g_panel, ID_CUTH, g_mach.cut_height);
    g_mach.pierce_height = getnum(g_panel, ID_PIERCEH, g_mach.pierce_height);
    g_mach.pierce_delay = getnum(g_panel, ID_PDELAY, g_mach.pierce_delay);
    g_mach.lead_in = getnum(g_panel, ID_LEAD, g_mach.lead_in);
    if (g_mach.cut_feed < g_mach.min_feed) g_mach.cut_feed = g_mach.min_feed;
    if (g_mach.kerf < 0) g_mach.kerf = 0;
}

static void show_gcode(void)
{
    HWND e = GetDlgItem(g_main, ID_GCODE);
    if (!g_gc.text) { SetWindowTextW(e, L""); return; }
    /* EDIT cần \r\n */
    size_t n = g_gc.len, extra = 0;
    for (size_t i = 0; i < n; i++) extra += g_gc.text[i] == '\n';
    char *crlf = (char *)malloc(n + extra + 1);
    size_t o = 0;
    for (size_t i = 0; i < n; i++) {
        if (g_gc.text[i] == '\n' && (i == 0 || g_gc.text[i - 1] != '\r')) crlf[o++] = '\r';
        crlf[o++] = g_gc.text[i];
    }
    crlf[o] = 0;
    int wn = MultiByteToWideChar(CP_UTF8, 0, crlf, -1, NULL, 0);
    wchar_t *w = (wchar_t *)malloc(sizeof(wchar_t) * (size_t)wn);
    MultiByteToWideChar(CP_UTF8, 0, crlf, -1, w, wn);
    SetWindowTextW(e, w);
    free(w);
    free(crlf);
    g_last_line = -1;
}

static void update_time(void)
{
    double total = g_plan.total;
    view3d_set_time(g_view, g_t);
    SendDlgItemMessageW(g_main, ID_SEEK, TBM_SETPOS, TRUE, total > 0 ? (LPARAM)lround(g_t / total * 1000) : 0);
    wchar_t a[32], b[32], s[80];
    fmt_time(g_t, a, 32);
    fmt_time(total, b, 32);
    swprintf(s, 80, L"%ls / %ls", a, b);
    SetDlgItemTextW(g_main, ID_TIME, s);
    if (g_cur_page == 1 && g_plan.n) {
        /* tô sáng dòng G-code đang chạy */
        double pos[NAX];
        int torch, line;
        plan_state(&g_plan, g_t, pos, &torch, &line);
        if (line != g_last_line && line > 0) {
            HWND e = GetDlgItem(g_main, ID_GCODE);
            LRESULT st = SendMessageW(e, EM_LINEINDEX, (WPARAM)(line - 1), 0);
            LRESULT ln = SendMessageW(e, EM_LINELENGTH, (WPARAM)st, 0);
            SendMessageW(e, EM_SETSEL, (WPARAM)st, (LPARAM)(st + ln));
            SendMessageW(e, EM_SCROLLCARET, 0, 0);
            g_last_line = line;
        }
    }
}

static void set_playing(int on)
{
    if (on && g_plan.total <= 0) on = 0;
    if (on && g_t >= g_plan.total - 1e-6) g_t = 0;
    g_playing = on;
    SetDlgItemTextW(g_main, ID_PLAY, on ? L"Dừng xem" : L"Chạy thử");
    if (on) { g_last_tick = GetTickCount(); SetTimer(g_main, TM_PLAY, 30, NULL); }
    else KillTimer(g_main, TM_PLAY);
}

static void show_stats(const char *warn)
{
    wchar_t s[1400], a[32], w[400];
    int n = 0;
    if (g_file[0]) {
        const wchar_t *base = wcsrchr(g_file, L'\\');
        n += swprintf(s + n, 1400 - n, L"Tệp: %ls\r\n", base ? base + 1 : g_file);
    }
    n += swprintf(s + n, 1400 - n, L"%d dòng lệnh", g_gc.lines);
    if (!g_file[0])
        n += swprintf(s + n, 1400 - n, L" · %d lần mồi · cắt %.0f mm", g_gc.pierces, g_gc.cut_length);
    fmt_time(g_plan.total, a, 32);
    n += swprintf(s + n, 1400 - n, L"\r\nThời gian chạy ước tính: %ls (tính như FluidNC)\r\n", a);
    for (int i = 0; i < NCAT; i++) {
        if (g_plan.by_cat[i] < 0.05) continue;
        wchar_t nm[40];
        u8w(CAT_NAMES_VI[i], nm, 40);
        n += swprintf(s + n, 1400 - n, L"  %ls %.1f s", nm, g_plan.by_cat[i]);
        if (i == 2) n += swprintf(s + n, 1400 - n, L"\r\n");
    }
    n += swprintf(s + n, 1400 - n, L"\r\n  máy dừng hẳn %d lần", g_plan.full_stops);
    if (warn && warn[0]) {
        u8w(warn, w, 400);
        n += swprintf(s + n, 1400 - n, L"\r\nLưu ý: %ls", w);
    }
    SetDlgItemTextW(g_panel, ID_STATS, s);
    swprintf(w, 400, L"%d dòng · ước tính %ls", g_gc.lines, a);
    status(1, w);
}

static void set_program(const char *warn)
{
    set_playing(0);
    plan_free(&g_plan);
    if (g_gc.text) plan_program(g_gc.text, &g_mach, &g_plan);
    g_t = 0;
    view3d_set_scene(g_view, &g_sec, &g_mach, g_len, &g_plan);
    show_gcode();
    show_stats(warn);
    update_time();
}

static void regen(void)
{
    wchar_t err[200];
    if (read_section(err, 200)) {
        SetDlgItemTextW(g_panel, ID_STATS, err);
        status(1, err);
        return;
    }
    read_machine();
    Operation ops[MAXOPS];
    memcpy(ops, g_ops, sizeof(Operation) * (size_t)g_nops);
    ops_order(ops, g_nops, &g_sec);
    gbuf_free(&g_gc);
    char msg[300];
    gcode_build(ops, g_nops, &g_sec, &g_mach, g_len, &g_gc, msg, sizeof msg);
    g_file[0] = 0;
    set_program(msg);
}

static void pipe_kind_changed(void)
{
    int box = SendDlgItemMessageW(g_panel, ID_KIND, CB_GETCURSEL, 0, 0) == 1;
    EnableWindow(GetDlgItem(g_panel, ID_DIA), !box);
    EnableWindow(GetDlgItem(g_panel, ID_W), box);
    EnableWindow(GetDlgItem(g_panel, ID_H), box);
    EnableWindow(GetDlgItem(g_panel, ID_RC), box);
    EnableWindow(GetDlgItem(g_panel, ID_WALL), box);
}

static char *read_all(const wchar_t *path, size_t *len)
{
    FILE *f = _wfopen(path, L"rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    char *b = (char *)malloc((size_t)n + 1);
    size_t got = fread(b, 1, (size_t)n, f);
    b[got] = 0;
    fclose(f);
    if (len) *len = got;
    return b;
}

static void open_file(void)
{
    wchar_t path[MAX_PATH] = L"";
    OPENFILENAMEW of;
    memset(&of, 0, sizeof of);
    of.lStructSize = sizeof of;
    of.hwndOwner = g_main;
    of.lpstrFilter = L"G-code (*.nc;*.gcode;*.ngc;*.tap)\0*.nc;*.gcode;*.ngc;*.tap\0Mọi tệp\0*.*\0";
    of.lpstrFile = path;
    of.nMaxFile = MAX_PATH;
    of.Flags = OFN_FILEMUSTEXIST | OFN_HIDEREADONLY;
    if (!GetOpenFileNameW(&of)) return;
    wchar_t err[200];
    if (read_section(err, 200)) { MessageBoxW(g_main, err, APP_NAME, MB_ICONWARNING); return; }
    read_machine();
    size_t n = 0;
    char *text = read_all(path, &n);
    if (!text) { MessageBoxW(g_main, L"Không đọc được tệp.", APP_NAME, MB_ICONWARNING); return; }
    gbuf_free(&g_gc);
    g_gc.text = text;
    g_gc.len = g_gc.cap = n;
    for (size_t i = 0; i < n; i++) g_gc.lines += text[i] == '\n';
    wcscpy(g_file, path);
    set_program("Mô phỏng dùng kích thước ống đang nhập ở mục 1.");
}

static void save_file(void)
{
    if (!g_gc.text) return;
    wchar_t path[MAX_PATH] = L"pipecut.nc";
    OPENFILENAMEW of;
    memset(&of, 0, sizeof of);
    of.lStructSize = sizeof of;
    of.hwndOwner = g_main;
    of.lpstrFilter = L"G-code (*.nc)\0*.nc\0Mọi tệp\0*.*\0";
    of.lpstrFile = path;
    of.nMaxFile = MAX_PATH;
    of.lpstrDefExt = L"nc";
    of.Flags = OFN_OVERWRITEPROMPT | OFN_HIDEREADONLY;
    if (!GetSaveFileNameW(&of)) return;
    FILE *f = _wfopen(path, L"wb");
    if (!f || fwrite(g_gc.text, 1, g_gc.len, f) != g_gc.len) {
        if (f) fclose(f);
        MessageBoxW(g_main, L"Không ghi được tệp.", APP_NAME, MB_ICONWARNING);
        return;
    }
    fclose(f);
    wchar_t s[MAX_PATH + 40];
    swprintf(s, MAX_PATH + 40, L"Đã lưu %ls", path);
    status(1, s);
}

/* ------------------------------------------------------------------ */
/* máy                                                                  */
/* ------------------------------------------------------------------ */
static const wchar_t *state_vi(const char *st)
{
    static const struct { const char *k; const wchar_t *v; } M[] = {
        {"Idle", L"Sẵn sàng"}, {"Run", L"Đang chạy"}, {"Hold", L"Tạm dừng"}, {"Jog", L"Đang nhích"},
        {"Alarm", L"BÁO ĐỘNG"}, {"Door", L"Cửa an toàn"}, {"Check", L"Kiểm tra"},
        {"Home", L"Đang về gốc"}, {"Sleep", L"Ngủ"}};
    for (size_t i = 0; i < sizeof M / sizeof *M; i++)
        if (!strncmp(st, M[i].k, strlen(M[i].k))) return M[i].v;
    return L"Đang chờ bo trả lời…";
}

static void refresh_ports(void)
{
    HWND cb = GetDlgItem(g_main, ID_PORT);
    wchar_t cur[128];
    GetWindowTextW(cb, cur, 128);
    SendMessageW(cb, CB_RESETCONTENT, 0, 0);
    wchar_t names[32][32];
    int n = comm_list_ports(names, 32);
    for (int i = 0; i < n; i++) SendMessageW(cb, CB_ADDSTRING, 0, (LPARAM)names[i]);
    if (g_target[0] && SendMessageW(cb, CB_FINDSTRINGEXACT, (WPARAM)-1, (LPARAM)g_target) == CB_ERR)
        SendMessageW(cb, CB_ADDSTRING, 0, (LPARAM)g_target);
    if (cur[0]) SetWindowTextW(cb, cur);
    else if (g_target[0]) SetWindowTextW(cb, g_target);
    else if (n) SendMessageW(cb, CB_SETCURSEL, 0, 0);
    wchar_t s[80];
    swprintf(s, 80, L"Tìm thấy %d cổng COM", n);
    if (!g_comm) status(0, s);
}

static void machine_buttons(void)
{
    CommStatus st;
    comm_snapshot(g_comm, &st);
    int on = g_comm != NULL, busy = st.job_running;
    SetDlgItemTextW(g_main, ID_CONNECT, on ? L"Ngắt kết nối" : L"Kết nối");
    int ids[] = {ID_HOME, ID_UNLOCK, ID_ZERO_Y, ID_ZERO_A, ID_JXM, ID_JXP, ID_JYM, ID_JYP, ID_JZM, ID_JZP,
                 ID_JAM, ID_JAP, ID_MDI, ID_SEND};
    for (size_t i = 0; i < sizeof ids / sizeof *ids; i++) EnableWindow(GetDlgItem(g_main, ids[i]), on && !busy);
    EnableWindow(GetDlgItem(g_main, ID_RUN), on && !busy && g_gc.text != NULL);
    EnableWindow(GetDlgItem(g_main, ID_PAUSE), on && busy && !st.job_paused);
    EnableWindow(GetDlgItem(g_main, ID_RESUME), on);
    EnableWindow(GetDlgItem(g_main, ID_STOP), on);
    EnableWindow(GetDlgItem(g_main, ID_PORT), !on);
    EnableWindow(GetDlgItem(g_main, ID_REFRESH), !on);
}

static void log_add(const wchar_t *t)
{
    HWND lb = GetDlgItem(g_main, ID_LOG);
    int n = (int)SendMessageW(lb, LB_ADDSTRING, 0, (LPARAM)t);
    if (n > 3000) { SendMessageW(lb, LB_DELETESTRING, 0, 0); n--; }
    SendMessageW(lb, LB_SETTOPINDEX, (WPARAM)(n > 0 ? n : 0), 0);
}

static void disconnect(void)
{
    if (!g_comm) return;
    comm_close(g_comm);
    g_comm = NULL;
    log_add(L"Đã ngắt kết nối.");
    status(0, L"Chưa kết nối");
    SetDlgItemTextW(g_main, ID_MSTATE, L"Chưa kết nối máy");
    SendDlgItemMessageW(g_main, ID_PROG, PBM_SETPOS, 0, 0);
    view3d_set_time(g_view, g_t);           /* khung 3D quay về chạy thử */
    machine_buttons();
}

static void connect_toggle(void)
{
    if (g_comm) { disconnect(); return; }
    wchar_t t[128], err[300];
    GetDlgItemTextW(g_main, ID_PORT, t, 128);
    g_comm = comm_open(t, g_main, WM_COMM, err, 300);
    if (!g_comm) {
        log_add(err);
        if (!g_autorun) MessageBoxW(g_main, err, APP_NAME, MB_ICONWARNING);
        return;
    }
    wcscpy(g_target, t);
    wchar_t s[200];
    swprintf(s, 200, L"Đã kết nối %ls", t);
    log_add(s);
    status(0, s);
    machine_buttons();
}

static void on_comm(void)
{
    if (!g_comm) return;
    CommStatus st;
    comm_snapshot(g_comm, &st);
    char line[300];
    while (comm_pop_log(g_comm, line, sizeof line)) {
        wchar_t w[300];
        u8w(line, w, 300);
        log_add(w);
    }
    if (!st.connected) { disconnect(); return; }
    wchar_t s[300];
    swprintf(s, 300, L"%ls    X %.3f   Y %.3f   Z %.3f   A %.2f°    F %.0f%ls", state_vi(st.state),
             st.wpos[AX_X], st.wpos[AX_Y], st.wpos[AX_Z], st.wpos[AX_A], st.feed, st.torch ? L"    ĐANG CẮT" : L"");
    SetDlgItemTextW(g_main, ID_MSTATE, s);
    SendDlgItemMessageW(g_main, ID_PROG, PBM_SETPOS, st.job_total ? (WPARAM)(st.job_acked * 1000 / st.job_total) : 0, 0);
    swprintf(s, 300, L"%ls · %ls%ls", g_target, state_vi(st.state),
             st.job_running ? (st.job_paused ? L" · chương trình tạm dừng" : L" · đang chạy chương trình") : L"");
    status(0, s);
    if (st.have_pos && IsDlgButtonChecked(g_main, ID_FOLLOW) == BST_CHECKED)
        view3d_set_live(g_view, st.wpos, st.torch);
    machine_buttons();
}

static void run_job(void)
{
    if (!g_comm || !g_gc.text) return;
    if (!g_autorun) {
        wchar_t q[400];
        swprintf(q, 400, L"Chạy %d dòng lệnh trên máy thật?\n\nKiểm tra trước: đã về gốc, đã đặt gốc chi tiết, "
                 L"ống đã kẹp chắc, không có ai trong vùng cắt.", g_gc.lines);
        if (MessageBoxW(g_main, q, APP_NAME, MB_YESNO | MB_ICONQUESTION | MB_DEFBUTTON2) != IDYES) return;
    }
    set_playing(0);
    CheckDlgButton(g_main, ID_FOLLOW, BST_CHECKED);
    if (comm_start_job(g_comm, g_gc.text)) MessageBoxW(g_main, L"Đang có chương trình chạy dở.", APP_NAME, MB_ICONWARNING);
    machine_buttons();
}

static void jog(int axis, int sign)
{
    static const char L[NAX] = {'X', 'Y', 'Z', 'A'};
    wchar_t b[32];
    GetDlgItemTextW(g_main, ID_JSTEP, b, 32);
    double step = wcstod(b, NULL);
    if (step <= 0) step = 1;
    double feed = g_mach.max_rate[axis] * 0.5;
    char cmd[80];
    snprintf(cmd, sizeof cmd, "$J=G91 G21 %c%.3f F%.0f", L[axis], sign * step, feed);
    comm_command(g_comm, cmd);
}

static void send_mdi(void)
{
    wchar_t w[200];
    char s[400];
    GetDlgItemTextW(g_main, ID_MDI, w, 200);
    WideCharToMultiByte(CP_UTF8, 0, w, -1, s, sizeof s, NULL, NULL);
    if (!s[0]) return;
    comm_command(g_comm, s);
    SetDlgItemTextW(g_main, ID_MDI, L"");
}

/* ------------------------------------------------------------------ */
/* bố cục                                                               */
/* ------------------------------------------------------------------ */
static void show_page(int p)
{
    g_cur_page = p;
    for (int k = 0; k < 3; k++)
        for (int i = 0; i < g_npage[k]; i++) ShowWindow(g_page[k][i], k == p ? SW_SHOW : SW_HIDE);
    TabCtrl_SetCurSel(g_tab, p);
    g_last_line = -1;
    if (p == 1) update_time();
}

static void place(int id, int x, int y, int w, int h) { MoveWindow(GetDlgItem(g_main, id), x, y, w, h, TRUE); }

static void panel_scroll_to(int pos)
{
    SCROLLINFO si = {sizeof si, SIF_ALL, 0, 0, 0, 0, 0};
    GetScrollInfo(g_panel, SB_VERT, &si);
    int maxpos = si.nMax - (int)si.nPage + 1;
    if (pos > maxpos) pos = maxpos;
    if (pos < 0) pos = 0;
    if (pos != g_scroll)
        ScrollWindowEx(g_panel, 0, g_scroll - pos, NULL, NULL, NULL, NULL, SW_SCROLLCHILDREN | SW_INVALIDATE | SW_ERASE);
    g_scroll = pos;
    si.fMask = SIF_POS;
    si.nPos = pos;
    SetScrollInfo(g_panel, SB_VERT, &si, TRUE);
}

static void layout(void)
{
    RECT rc;
    GetClientRect(g_main, &rc);
    SendMessageW(g_status, WM_SIZE, 0, 0);
    RECT sr;
    GetWindowRect(g_status, &sr);
    int sh = sr.bottom - sr.top, W = rc.right, H = rc.bottom - sh;
    int parts[2] = {S(380), -1};
    SendMessageW(g_status, SB_SETPARTS, 2, (LPARAM)parts);

    int pw = S(PANEL_W) + GetSystemMetrics(SM_CXVSCROLL);
    MoveWindow(g_panel, 0, 0, pw, H, TRUE);
    SCROLLINFO si = {sizeof si, SIF_RANGE | SIF_PAGE, 0, S(PANEL_H), (UINT)H, 0, 0};
    SetScrollInfo(g_panel, SB_VERT, &si, TRUE);
    panel_scroll_to(g_scroll);

    int x0 = pw + S(4), y0 = S(6), tw = W - x0 - S(8), th = H - y0 - S(6);
    MoveWindow(g_tab, x0, y0, tw, th, TRUE);
    RECT a = {x0, y0, x0 + tw, y0 + th};
    TabCtrl_AdjustRect(g_tab, FALSE, &a);
    int ax = a.left + S(2), ay = a.top + S(2), aw = a.right - a.left - S(4), ah = a.bottom - a.top - S(4);
    int bh = S(28), g = S(6);

    /* thẻ 3D */
    int by = ay + ah - bh;
    MoveWindow(g_view, ax, ay, aw, ah - bh - g, TRUE);
    int x = ax;
    place(ID_PLAY, x, by, S(104), bh); x += S(104) + g;
    int right = S(110) + S(96) + S(64) + S(118) + 4 * g;
    place(ID_SEEK, x, by, aw - (x - ax) - right, bh); x = ax + aw - right + g;
    place(ID_TIME, x, by + S(5), S(110), bh - S(5)); x += S(110) + g;
    place(ID_SPEED, x, by + S(2), S(64), S(200)); x += S(64) + g;
    place(ID_FOCUS, x, by, S(96), bh); x += S(96) + g;
    place(ID_RESETV, x, by, S(118), bh);

    /* thẻ G-code */
    place(ID_GCODE, ax, ay, aw, ah);

    /* thẻ Máy */
    int y = ay + S(4);
    x = ax + S(4);
    place(ID_PORTL, x, y + S(4), S(110), S(20)); x += S(110);
    place(ID_PORT, x, y, S(210), S(300)); x += S(210) + g;
    place(ID_REFRESH, x, y, S(84), bh); x += S(84) + g;
    place(ID_CONNECT, x, y, S(116), bh); x += S(116) + g * 2;
    place(ID_FOLLOW, x, y + S(4), S(220), S(20));
    y += bh + g * 2;
    place(ID_MSTATE, ax + S(4), y, aw - S(8), S(30));
    y += S(30) + g;
    x = ax + S(4);
    place(ID_HOME, x, y, S(116), bh); x += S(116) + g;
    place(ID_UNLOCK, x, y, S(116), bh); x += S(116) + g;
    place(ID_ZERO_Y, x, y, S(136), bh); x += S(136) + g;
    place(ID_ZERO_A, x, y, S(136), bh);
    y += bh + g;
    x = ax + S(4);
    place(ID_JOGL, x, y + S(4), S(76), S(20)); x += S(76);
    place(ID_JSTEP, x, y + S(2), S(64), S(200)); x += S(64) + g;
    for (int id = ID_JXM; id <= ID_JAP; id++) { place(id, x, y, S(44), bh); x += S(44) + ((id - ID_JXM) % 2 ? g : S(2)); }
    y += bh + g;
    x = ax + S(4);
    place(ID_RUN, x, y, S(160), bh); x += S(160) + g;
    place(ID_PAUSE, x, y, S(96), bh); x += S(96) + g;
    place(ID_RESUME, x, y, S(96), bh); x += S(96) + g;
    place(ID_STOP, x, y, S(96), bh); x += S(96) + g;
    place(ID_PROG, x, y + S(4), ax + aw - S(4) - x, bh - S(8));
    y += bh + g;
    place(ID_MDI, ax + S(4), y, aw - S(8) - S(80) - g, S(24));
    place(ID_SEND, ax + aw - S(4) - S(80), y, S(80), S(24));
    y += S(24) + g;
    place(ID_LOG, ax + S(4), y, aw - S(8), ay + ah - y);
}

/* ------------------------------------------------------------------ */
static LRESULT CALLBACK panel_proc(HWND h, UINT msg, WPARAM wp, LPARAM lp)
{
    switch (msg) {
    case WM_COMMAND: case WM_NOTIFY:
        return SendMessageW(g_main, msg, wp, lp);
    case WM_VSCROLL: {
        SCROLLINFO si = {sizeof si, SIF_ALL, 0, 0, 0, 0, 0};
        GetScrollInfo(h, SB_VERT, &si);
        int pos = g_scroll;
        switch (LOWORD(wp)) {
        case SB_LINEUP: pos -= S(24); break;
        case SB_LINEDOWN: pos += S(24); break;
        case SB_PAGEUP: pos -= (int)si.nPage; break;
        case SB_PAGEDOWN: pos += (int)si.nPage; break;
        case SB_THUMBTRACK: case SB_THUMBPOSITION: pos = si.nTrackPos; break;
        case SB_TOP: pos = 0; break;
        case SB_BOTTOM: pos = si.nMax; break;
        }
        panel_scroll_to(pos);
        return 0;
    }
    case WM_MOUSEWHEEL: {
        panel_scroll_to(g_scroll - GET_WHEEL_DELTA_WPARAM(wp) * S(60) / WHEEL_DELTA);
        return 0;
    }
    }
    return DefWindowProcW(h, msg, wp, lp);
}

static void build_panel(void)
{
    header(8, L"1. Phôi ống");
    mk(g_panel, L"STATIC", L"Loại ống", SS_LEFT | SS_CENTERIMAGE, 10, 32, 102, 24, 0);
    HWND cb = mk(g_panel, L"COMBOBOX", L"", WS_TABSTOP | CBS_DROPDOWNLIST, 112, 32, 216, 200, ID_KIND);
    SendMessageW(cb, CB_ADDSTRING, 0, (LPARAM)L"Ống tròn");
    SendMessageW(cb, CB_ADDSTRING, 0, (LPARAM)L"Ống hộp vuông / chữ nhật");
    SendMessageW(cb, CB_SETCURSEL, 0, 0);
    field(10, 62, L"Đường kính", ID_DIA, 0);
    field(172, 62, L"Dài ống", ID_LEN, 0);
    field(10, 90, L"Rộng", ID_W, 0);
    field(172, 90, L"Cao", ID_H, 0);
    field(10, 118, L"Bo góc (0 = tự)", ID_RC, 0);
    field(172, 118, L"Thành ống", ID_WALL, 0);

    header(152, L"2. Nguyên công  (bỏ tích = không cắt)");
    g_list = mk(g_panel, WC_LISTVIEWW, L"", WS_TABSTOP | WS_BORDER | LVS_REPORT | LVS_SHOWSELALWAYS | LVS_SINGLESEL,
                10, 176, 318, 140, ID_LIST);
    ListView_SetExtendedListViewStyle(g_list, LVS_EX_FULLROWSELECT | LVS_EX_CHECKBOXES | LVS_EX_DOUBLEBUFFER);
    static const wchar_t *cols[4] = {L"Loại", L"x (mm)", L"θ (°)", L"Kích thước"};
    static const int cw[4] = {104, 56, 46, 100};
    for (int i = 0; i < 4; i++) {
        LVCOLUMNW c;
        memset(&c, 0, sizeof c);
        c.mask = LVCF_TEXT | LVCF_WIDTH;
        c.pszText = (wchar_t *)cols[i];
        c.cx = S(cw[i]);
        ListView_InsertColumn(g_list, i, &c);
    }
    mk(g_panel, L"STATIC", L"Loại", SS_LEFT | SS_CENTERIMAGE, 10, 322, 102, 24, 0);
    cb = mk(g_panel, L"COMBOBOX", L"", WS_TABSTOP | CBS_DROPDOWNLIST, 112, 322, 216, 200, ID_OPKIND);
    for (int k = 0; k < OP_KINDS; k++) SendMessageW(cb, CB_ADDSTRING, 0, (LPARAM)op_name((OpKind)k));
    SendMessageW(cb, CB_SETCURSEL, OP_CIRCLE, 0);
    field(10, 352, L"Vị trí x (mm)", ID_OX, 0);
    field(172, 352, L"Góc θ (°)", ID_OT, ID_LT);
    field(10, 380, L"", ID_OA, ID_LA);
    field(172, 380, L"", ID_OB, ID_LB);
    field(10, 408, L"", ID_OC, ID_LC);
    mk(g_panel, L"BUTTON", L"Thêm", WS_TABSTOP, 10, 442, 74, 28, ID_ADD);
    mk(g_panel, L"BUTTON", L"Cập nhật", WS_TABSTOP, 88, 442, 80, 28, ID_UPD);
    mk(g_panel, L"BUTTON", L"Xoá", WS_TABSTOP, 172, 442, 70, 28, ID_DEL);
    mk(g_panel, L"BUTTON", L"Mẫu", WS_TABSTOP, 246, 442, 82, 28, ID_DEMO);
    setnum(g_panel, ID_OX, 100);
    setnum(g_panel, ID_OT, 0);
    setnum(g_panel, ID_OA, 20);
    setnum(g_panel, ID_OB, 60);
    setnum(g_panel, ID_OC, 5);
    editor_kind(OP_CIRCLE);

    header(482, L"3. Thông số cắt");
    field(10, 506, L"Tốc độ (mm/ph)", ID_FEED, 0);
    field(172, 506, L"Kerf (mm)", ID_KERF, 0);
    field(10, 534, L"Cao độ cắt", ID_CUTH, 0);
    field(172, 534, L"Cao độ mồi", ID_PIERCEH, 0);
    field(10, 562, L"Trễ mồi (s)", ID_PDELAY, 0);
    field(172, 562, L"Vào dao (mm)", ID_LEAD, 0);
    mk(g_panel, L"BUTTON", L"Sinh G-code (Enter)", WS_TABSTOP | BS_DEFPUSHBUTTON, 10, 598, 150, 32, ID_GEN);
    mk(g_panel, L"BUTTON", L"Mở G-code…", WS_TABSTOP, 164, 598, 80, 32, ID_OPEN);
    mk(g_panel, L"BUTTON", L"Lưu…", WS_TABSTOP, 248, 598, 80, 32, ID_SAVE);
    mk(g_panel, L"STATIC", L"", SS_LEFT, 10, 640, 320, 108, ID_STATS);
}

static void build_pages(void)
{
    TCITEMW ti;
    memset(&ti, 0, sizeof ti);
    ti.mask = TCIF_TEXT;
    static const wchar_t *tabs[3] = {L"Mô phỏng 3D", L"G-code", L"Máy"};
    for (int i = 0; i < 3; i++) { ti.pszText = (wchar_t *)tabs[i]; TabCtrl_InsertItem(g_tab, i, &ti); }

    g_view = on_page(0, CreateWindowExW(0, VIEW3D_CLASS, L"", WS_CHILD | WS_VISIBLE, 0, 0, 10, 10, g_main,
                                        (HMENU)(INT_PTR)ID_VIEW, g_inst, NULL));
    pbtn(0, L"Chạy thử", ID_PLAY);
    HWND tb = on_page(0, mk(g_main, TRACKBAR_CLASSW, L"", WS_TABSTOP | TBS_NOTICKS | TBS_HORZ, 0, 0, 10, 10, ID_SEEK));
    SendMessageW(tb, TBM_SETRANGE, TRUE, MAKELPARAM(0, 1000));
    on_page(0, mk(g_main, L"STATIC", L"0:00.0 / 0:00.0", SS_CENTER, 0, 0, 10, 10, ID_TIME));
    HWND sp = on_page(0, mk(g_main, L"COMBOBOX", L"", WS_TABSTOP | CBS_DROPDOWNLIST, 0, 0, 64, 200, ID_SPEED));
    static const wchar_t *spd[] = {L"0.5×", L"1×", L"2×", L"5×", L"10×", L"20×"};
    for (int i = 0; i < 6; i++) SendMessageW(sp, CB_ADDSTRING, 0, (LPARAM)spd[i]);
    SendMessageW(sp, CB_SETCURSEL, 1, 0);
    pbtn(0, L"Toàn cảnh", ID_FOCUS);
    pbtn(0, L"Góc nhìn gốc", ID_RESETV);

    HWND ed = on_page(1, mk(g_main, L"EDIT", L"", WS_TABSTOP | WS_VSCROLL | WS_HSCROLL | ES_MULTILINE | ES_READONLY |
                                                     ES_NOHIDESEL | ES_AUTOVSCROLL | ES_AUTOHSCROLL,
                            0, 0, 10, 10, ID_GCODE));
    SendMessageW(ed, EM_SETLIMITTEXT, 0, 0);
    SendMessageW(ed, WM_SETFONT, (WPARAM)g_mono, FALSE);

    on_page(2, mk(g_main, L"STATIC", L"Cổng / địa chỉ:", SS_LEFT, 0, 0, 10, 10, ID_PORTL));
    HWND port = on_page(2, mk(g_main, L"COMBOBOX", L"", WS_TABSTOP | CBS_DROPDOWN | CBS_AUTOHSCROLL, 0, 0, 210, 300, ID_PORT));
    SendMessageW(port, CB_SETCUEBANNER, 0, (LPARAM)L"COM5 hoặc 192.168.1.50");
    pbtn(2, L"Làm mới", ID_REFRESH);
    pbtn(2, L"Kết nối", ID_CONNECT);
    HWND fol = on_page(2, mk(g_main, L"BUTTON", L"Khung 3D bám theo máy thật", WS_TABSTOP | BS_AUTOCHECKBOX, 0, 0, 10, 10, ID_FOLLOW));
    SendMessageW(fol, BM_SETCHECK, BST_CHECKED, 0);
    HWND ms = on_page(2, mk(g_main, L"STATIC", L"Chưa kết nối máy", SS_LEFT | SS_CENTERIMAGE, 0, 0, 10, 10, ID_MSTATE));
    SendMessageW(ms, WM_SETFONT, (WPARAM)g_big, FALSE);
    pbtn(2, L"Về gốc ($H)", ID_HOME);
    pbtn(2, L"Mở khoá ($X)", ID_UNLOCK);
    pbtn(2, L"Đặt gốc Y tại đây", ID_ZERO_Y);
    pbtn(2, L"Đặt gốc A tại đây", ID_ZERO_A);
    on_page(2, mk(g_main, L"STATIC", L"Nhích (mm/°):", SS_LEFT, 0, 0, 10, 10, ID_JOGL));
    HWND js = on_page(2, mk(g_main, L"COMBOBOX", L"", WS_TABSTOP | CBS_DROPDOWN, 0, 0, 64, 200, ID_JSTEP));
    static const wchar_t *steps[] = {L"0.1", L"1", L"5", L"10", L"50", L"90"};
    for (int i = 0; i < 6; i++) SendMessageW(js, CB_ADDSTRING, 0, (LPARAM)steps[i]);
    SendMessageW(js, CB_SETCURSEL, 1, 0);
    static const wchar_t *jl[8] = {L"X−", L"X+", L"Y−", L"Y+", L"Z−", L"Z+", L"A−", L"A+"};
    for (int i = 0; i < 8; i++) pbtn(2, jl[i], ID_JXM + i);
    pbtn(2, L"Chạy chương trình", ID_RUN);
    pbtn(2, L"Tạm dừng", ID_PAUSE);
    pbtn(2, L"Chạy tiếp", ID_RESUME);
    HWND stop = pbtn(2, L"DỪNG", ID_STOP);
    SendMessageW(stop, WM_SETFONT, (WPARAM)g_bold, FALSE);
    HWND pr = on_page(2, mk(g_main, PROGRESS_CLASSW, L"", 0, 0, 0, 10, 10, ID_PROG));
    SendMessageW(pr, PBM_SETRANGE32, 0, 1000);
    HWND mdi = on_page(2, mk(g_main, L"EDIT", L"", WS_TABSTOP | ES_AUTOHSCROLL, 0, 0, 10, 10, ID_MDI));
    SendMessageW(mdi, EM_SETCUEBANNER, TRUE, (LPARAM)L"Gõ lệnh G-code / $ rồi Enter, ví dụ  G0 Z20");
    pbtn(2, L"Gửi", ID_SEND);
    HWND lb = on_page(2, mk(g_main, L"LISTBOX", L"", WS_TABSTOP | WS_VSCROLL | WS_BORDER | LBS_NOINTEGRALHEIGHT |
                                                      LBS_NOSEL, 0, 0, 10, 10, ID_LOG));
    SendMessageW(lb, WM_SETFONT, (WPARAM)g_mono, FALSE);
}

/* ------------------------------------------------------------------ */
static int save_client_bmp(HWND h, const wchar_t *path)
{
    RECT rc;
    GetClientRect(h, &rc);
    int w = rc.right, hh = rc.bottom;
    HDC scr = GetDC(h), dc = CreateCompatibleDC(scr);
    BITMAPINFO bi;
    memset(&bi, 0, sizeof bi);
    bi.bmiHeader.biSize = sizeof bi.bmiHeader;
    bi.bmiHeader.biWidth = w; bi.bmiHeader.biHeight = hh;
    bi.bmiHeader.biPlanes = 1; bi.bmiHeader.biBitCount = 24; bi.bmiHeader.biCompression = BI_RGB;
    void *bits = NULL;
    HBITMAP bmp = CreateDIBSection(scr, &bi, DIB_RGB_COLORS, &bits, NULL, 0);
    HGDIOBJ old = SelectObject(dc, bmp);
    BitBlt(dc, 0, 0, w, hh, scr, 0, 0, SRCCOPY);
    GdiFlush();
    int stride = ((w * 3 + 3) / 4) * 4, rcode = -1;
    BITMAPFILEHEADER fh;
    memset(&fh, 0, sizeof fh);
    fh.bfType = 0x4D42;
    fh.bfOffBits = sizeof fh + sizeof bi.bmiHeader;
    fh.bfSize = fh.bfOffBits + (DWORD)(stride * hh);
    FILE *f = _wfopen(path, L"wb");
    if (f) {
        fwrite(&fh, sizeof fh, 1, f);
        fwrite(&bi.bmiHeader, sizeof bi.bmiHeader, 1, f);
        fwrite(bits, 1, (size_t)(stride * hh), f);
        fclose(f);
        rcode = 0;
    }
    SelectObject(dc, old);
    DeleteObject(bmp);
    DeleteDC(dc);
    ReleaseDC(h, scr);
    return rcode;
}

static void dump_log(void)
{
    if (!g_logfile[0]) return;
    FILE *f = _wfopen(g_logfile, L"wb");
    if (!f) return;
    HWND lb = GetDlgItem(g_main, ID_LOG);
    int n = (int)SendMessageW(lb, LB_GETCOUNT, 0, 0);
    for (int i = 0; i < n; i++) {
        wchar_t w[400];
        char s[1200];
        if (SendMessageW(lb, LB_GETTEXTLEN, (WPARAM)i, 0) >= 400) continue;
        SendMessageW(lb, LB_GETTEXT, (WPARAM)i, (LPARAM)w);
        WideCharToMultiByte(CP_UTF8, 0, w, -1, s, sizeof s, NULL, NULL);
        fprintf(f, "%s\n", s);
    }
    CommStatus st;
    comm_snapshot(g_comm, &st);
    fprintf(f, "#final state=%s pos=%.3f,%.3f,%.3f,%.3f acked=%d/%d running=%d\n", st.state, st.wpos[0],
            st.wpos[1], st.wpos[2], st.wpos[3], st.job_acked, st.job_total, st.job_running);
    fclose(f);
}

/* Đếm số màu khác nhau trong ảnh BMP 24 bit - ảnh trắng trơn hay chỉ có nền là hỏng. */
static int bmp_colors(const wchar_t *path)
{
    size_t n = 0;
    char *b = read_all(path, &n);
    if (!b || n < 54) { free(b); return -1; }
    unsigned char *seen = (unsigned char *)calloc(1 << 21, 1);
    int count = 0;
    for (size_t i = 54; i + 2 < n; i += 3) {
        unsigned c = (unsigned char)b[i] | ((unsigned char)b[i + 1] << 8) | ((unsigned)(unsigned char)b[i + 2] << 16);
        if (!(seen[c >> 3] & (1 << (c & 7)))) { seen[c >> 3] |= (unsigned char)(1 << (c & 7)); count++; }
    }
    free(seen);
    free(b);
    return count;
}

/* Tự kiểm: sinh 2 chương trình mẫu, ghi số liệu và ảnh 3D ra thư mục. */
static int selftest(FILE *f, const wchar_t *dir)
{
    wchar_t path[MAX_PATH];
    for (int box = 0; box < 2; box++) {
        SendDlgItemMessageW(g_panel, ID_KIND, CB_SETCURSEL, box, 0);
        pipe_kind_changed();
        read_section(path, MAX_PATH);
        g_nops = demo_ops(&g_sec, g_ops);
        list_fill(-1);
        regen();
        fprintf(f, "%s lines=%d pierces=%d cut=%.3f total=%.6f stops=%d moves=%d\n", box ? "box" : "round",
                g_gc.lines, g_gc.pierces, g_gc.cut_length, g_plan.total, g_plan.full_stops, g_plan.n);
        fflush(f);
        /* thời điểm giữa nhát cắt dài nhất để thấy hồ quang */
        double tbest = 0, lbest = -1;
        for (int i = 0; i < g_plan.n; i++)
            if (g_plan.mv[i].torch && !g_plan.mv[i].rapid && !g_plan.mv[i].dwell && g_plan.mv[i].dt > lbest) {
                lbest = g_plan.mv[i].dt;
                tbest = g_plan.mv[i].t0 + g_plan.mv[i].dt / 2;
            }
        const wchar_t *nm = box ? L"box" : L"round";
        for (int shot = 0; shot < 3; shot++) {
            g_t = shot == 0 ? tbest : shot == 1 ? g_plan.total * 0.999 : 0.0;
            view3d_set_time(g_view, g_t);
            if (shot == 1) view3d_toggle_focus(g_view);
            swprintf(path, MAX_PATH, L"%ls\\%ls_%d.bmp", dir, nm, shot);
            DWORD t0 = GetTickCount();
            int rc = view3d_render_bmp(g_view, path, 1000, 640);
            fprintf(f, "  shot %d t=%.3f render=%s %lums colors=%d\n", shot, g_t, rc ? "FAIL" : "ok",
                    (unsigned long)(GetTickCount() - t0), rc ? 0 : bmp_colors(path));
            if (shot == 1) view3d_toggle_focus(g_view);
        }
    }
    fprintf(f, "bench 1280x800 %.2f ms/frame\n", view3d_bench(g_view, 1280, 800, 60));
    fprintf(f, "ok\n");
    return 0;
}

static LRESULT CALLBACK main_proc(HWND h, UINT msg, WPARAM wp, LPARAM lp)
{
    switch (msg) {
    case WM_CREATE: {
        g_main = h;
        HDC dc = GetDC(h);
        g_dpi = GetDeviceCaps(dc, LOGPIXELSY);
        ReleaseDC(h, dc);
        NONCLIENTMETRICSW nm;
        memset(&nm, 0, sizeof nm);
        nm.cbSize = sizeof nm;
        SystemParametersInfoW(SPI_GETNONCLIENTMETRICS, sizeof nm, &nm, 0);
        /* Segoe UI có đủ dấu tiếng Việt; phông hệ thống cũ (Tahoma, MS Sans) thì không chắc */
        wcscpy(nm.lfMessageFont.lfFaceName, L"Segoe UI");
        nm.lfMessageFont.lfQuality = CLEARTYPE_QUALITY;
        g_font = CreateFontIndirectW(&nm.lfMessageFont);
        nm.lfMessageFont.lfWeight = FW_BOLD;
        g_bold = CreateFontIndirectW(&nm.lfMessageFont);
        nm.lfMessageFont.lfHeight = nm.lfMessageFont.lfHeight * 4 / 3;
        g_big = CreateFontIndirectW(&nm.lfMessageFont);
        g_mono = CreateFontW(-MulDiv(10, g_dpi, 72), 0, 0, 0, FW_NORMAL, 0, 0, 0, DEFAULT_CHARSET, 0, 0,
                             CLEARTYPE_QUALITY, FIXED_PITCH, L"Consolas");
        g_status = CreateWindowExW(0, STATUSCLASSNAMEW, L"", WS_CHILD | WS_VISIBLE | SBARS_SIZEGRIP, 0, 0, 0, 0, h,
                                   (HMENU)(INT_PTR)ID_STATUS, g_inst, NULL);
        g_panel = CreateWindowExW(WS_EX_CONTROLPARENT, L"PipeCutPanel", L"", WS_CHILD | WS_VISIBLE | WS_VSCROLL |
                                  WS_CLIPCHILDREN, 0, 0, 10, 10, h, NULL, g_inst, NULL);
        g_tab = CreateWindowExW(0, WC_TABCONTROLW, L"", WS_CHILD | WS_VISIBLE | WS_CLIPSIBLINGS | WS_TABSTOP,
                                0, 0, 10, 10, h, (HMENU)ID_TAB, g_inst, NULL);
        SendMessageW(g_tab, WM_SETFONT, (WPARAM)g_font, FALSE);
        SendMessageW(g_status, WM_SETFONT, (WPARAM)g_font, FALSE);
        build_panel();
        build_pages();
        /* thân thẻ nằm dưới cùng: các điều khiển của từng thẻ luôn vẽ đè lên nó */
        SetWindowPos(g_tab, HWND_BOTTOM, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);
        settings_load();
        if (g_nops < 0) {                        /* lần đầu chạy: chương trình mẫu */
            wchar_t e[100];
            read_section(e, 100);
            g_nops = demo_ops(&g_sec, g_ops);
        }
        pipe_kind_changed();
        list_fill(0);
        if (g_nops) editor_load(0);
        status(0, L"Chưa kết nối");
        layout();
        show_page(0);
        refresh_ports();
        regen();
        machine_buttons();
        return 0;
    }
    case WM_SIZE:
        layout();
        return 0;
    case WM_GETMINMAXINFO: {
        MINMAXINFO *mm = (MINMAXINFO *)lp;
        mm->ptMinTrackSize.x = S(1040);
        mm->ptMinTrackSize.y = S(480);
        return 0;
    }
    case WM_CTLCOLORSTATIC: {
        /* chữ trên thân thẻ: nền trắng như thẻ; chữ trên khung trái: nền mặc định */
        HWND c = (HWND)lp;
        if (GetParent(c) == h && c != g_status) {
            SetBkColor((HDC)wp, GetSysColor(COLOR_WINDOW));
            if (GetDlgCtrlID(c) == ID_MSTATE) {
                CommStatus st;
                comm_snapshot(g_comm, &st);
                SetTextColor((HDC)wp, st.alarm ? RGB(0xc6, 0x28, 0x28) : st.torch ? RGB(0xd8, 0x43, 0x15) : RGB(0x1b, 0x3a, 0x5c));
            }
            return (LRESULT)GetSysColorBrush(COLOR_WINDOW);
        }
        break;
    }
    case WM_NOTIFY: {
        NMHDR *nh = (NMHDR *)lp;
        if (nh->idFrom == ID_TAB && nh->code == TCN_SELCHANGE) show_page(TabCtrl_GetCurSel(g_tab));
        if (nh->idFrom == ID_LIST && nh->code == LVN_ITEMCHANGED && !g_filling) {
            NMLISTVIEW *lv = (NMLISTVIEW *)lp;
            if (lv->iItem >= 0 && lv->iItem < g_nops && (lv->uChanged & LVIF_STATE)) {
                if ((lv->uNewState ^ lv->uOldState) & LVIS_STATEIMAGEMASK) {
                    g_ops[lv->iItem].enabled = ListView_GetCheckState(g_list, lv->iItem) != 0;
                    regen();
                }
                if ((lv->uNewState & LVIS_SELECTED) && !(lv->uOldState & LVIS_SELECTED)) editor_load(lv->iItem);
            }
        }
        return 0;
    }
    case WM_HSCROLL:
        if ((HWND)lp == GetDlgItem(h, ID_SEEK)) {
            set_playing(0);
            g_t = g_plan.total * (double)SendMessageW((HWND)lp, TBM_GETPOS, 0, 0) / 1000.0;
            update_time();
        }
        return 0;
    case WM_TIMER:
        if (wp == TM_PLAY) {
            DWORD now = GetTickCount();
            g_t += (now - g_last_tick) / 1000.0 * g_speed;
            g_last_tick = now;
            if (g_t >= g_plan.total) { g_t = g_plan.total; set_playing(0); }
            update_time();
        } else if (wp == TM_SHOT) {
            KillTimer(h, TM_SHOT);
            save_client_bmp(h, g_shot);
            PostMessageW(h, WM_CLOSE, 0, 0);
        } else if (wp == TM_RUN) {
            KillTimer(h, TM_RUN);
            run_job();
        } else if (wp == TM_QUIT) {
            KillTimer(h, TM_QUIT);
            if (g_shot[0]) save_client_bmp(h, g_shot);
            dump_log();
            PostMessageW(h, WM_CLOSE, 0, 0);
        }
        return 0;
    case WM_COMM:
        on_comm();
        return 0;
    case WM_COMMAND: {
        int id = LOWORD(wp), code = HIWORD(wp);
        switch (id) {
        case IDOK: {
            HWND f = GetFocus();
            if (f == GetDlgItem(h, ID_MDI)) send_mdi();
            else if (GetParent(f) == GetDlgItem(h, ID_PORT) || f == GetDlgItem(h, ID_PORT)) connect_toggle();
            else if (IsChild(g_panel, f)) regen();
            break;
        }
        case ID_KIND: if (code == CBN_SELCHANGE) { pipe_kind_changed(); regen(); } break;
        case ID_OPKIND: if (code == CBN_SELCHANGE) editor_kind((OpKind)SendDlgItemMessageW(g_panel, ID_OPKIND, CB_GETCURSEL, 0, 0)); break;
        case ID_ADD:
            if (g_nops < MAXOPS) { g_ops[g_nops++] = editor_read(); list_fill(g_nops - 1); regen(); }
            break;
        case ID_UPD: {
            int i = list_sel();
            if (i >= 0) { int en = g_ops[i].enabled; g_ops[i] = editor_read(); g_ops[i].enabled = en; list_fill(i); regen(); }
            break;
        }
        case ID_DEL: {
            int i = list_sel();
            if (i >= 0) {
                memmove(&g_ops[i], &g_ops[i + 1], sizeof(Operation) * (size_t)(g_nops - i - 1));
                g_nops--;
                list_fill(i < g_nops ? i : g_nops - 1);
                regen();
            }
            break;
        }
        case ID_DEMO: {
            wchar_t e[200];
            if (read_section(e, 200)) { MessageBoxW(h, e, APP_NAME, MB_ICONWARNING); break; }
            if (g_nops && MessageBoxW(h, L"Thay danh sách nguyên công bằng chương trình mẫu?", APP_NAME,
                                      MB_YESNO | MB_ICONQUESTION) != IDYES) break;
            g_nops = demo_ops(&g_sec, g_ops);
            list_fill(0);
            editor_load(0);
            regen();
            break;
        }
        case ID_GEN: regen(); break;
        case ID_OPEN: open_file(); break;
        case ID_SAVE: save_file(); break;
        case ID_PLAY:
            set_playing(!g_playing);
            if (g_playing && g_comm) CheckDlgButton(h, ID_FOLLOW, BST_UNCHECKED);   /* xem chạy thử thay vì máy */
            break;
        case ID_SPEED:
            if (code == CBN_SELCHANGE) {
                static const double sp[] = {0.5, 1, 2, 5, 10, 20};
                int k = (int)SendDlgItemMessageW(h, ID_SPEED, CB_GETCURSEL, 0, 0);
                g_speed = k >= 0 && k < 6 ? sp[k] : 1;
            }
            break;
        case ID_FOCUS: view3d_toggle_focus(g_view); /* fall through: cập nhật nhãn */
        /* fallthrough */
        case ID_VIEW:
            SetDlgItemTextW(h, ID_FOCUS, view3d_focus_is_work(g_view) ? L"Toàn cảnh" : L"Vùng cắt");
            break;
        case ID_RESETV: view3d_reset(g_view); break;
        case ID_REFRESH: refresh_ports(); break;
        case ID_CONNECT: connect_toggle(); break;
        case ID_FOLLOW:
            if (IsDlgButtonChecked(h, ID_FOLLOW) != BST_CHECKED) view3d_set_time(g_view, g_t);
            else on_comm();
            break;
        case ID_HOME: comm_command(g_comm, "$H"); break;
        case ID_UNLOCK: comm_command(g_comm, "$X"); break;
        case ID_ZERO_Y: comm_command(g_comm, "G10 L20 P1 Y0"); break;
        case ID_ZERO_A: comm_command(g_comm, "G10 L20 P1 A0"); break;
        case ID_JXM: case ID_JXP: case ID_JYM: case ID_JYP: case ID_JZM: case ID_JZP: case ID_JAM: case ID_JAP:
            jog((id - ID_JXM) / 2, (id - ID_JXM) % 2 ? 1 : -1);
            break;
        case ID_RUN: run_job(); break;
        case ID_PAUSE: comm_pause(g_comm); machine_buttons(); break;
        case ID_RESUME: comm_resume(g_comm); machine_buttons(); break;
        case ID_STOP: comm_stop(g_comm); machine_buttons(); break;
        case ID_SEND: send_mdi(); break;
        }
        return 0;
    }
    case WM_CLOSE:
        settings_save();
        DestroyWindow(h);
        return 0;
    case WM_DESTROY:
        if (g_comm) { comm_close(g_comm); g_comm = NULL; }
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcW(h, msg, wp, lp);
}

/* Khi tự kiểm: có sự cố thì ghi mã lỗi vào báo cáo thay vì biến mất không dấu vết. */
static FILE *g_report;

static LONG WINAPI on_crash(EXCEPTION_POINTERS *e)
{
    if (g_report) {
        fprintf(g_report, "CRASH code=0x%08lx addr=%p\n", (unsigned long)e->ExceptionRecord->ExceptionCode,
                e->ExceptionRecord->ExceptionAddress);
        fclose(g_report);
        g_report = NULL;
    }
    return EXCEPTION_EXECUTE_HANDLER;
}

static int is_local(const wchar_t *t)
{
    return !wcsncmp(t, L"127.0.0.1", 9) || !wcsncmp(t, L"localhost", 9);
}

int WINAPI wWinMain(HINSTANCE inst, HINSTANCE prev, PWSTR cmd, int show)
{
    g_inst = inst;
    INITCOMMONCONTROLSEX ic = {sizeof ic, ICC_WIN95_CLASSES | ICC_BAR_CLASSES | ICC_TAB_CLASSES |
                                          ICC_LISTVIEW_CLASSES | ICC_PROGRESS_CLASS | ICC_STANDARD_CLASSES};
    InitCommonControlsEx(&ic);

    int argc = 0;
    wchar_t **argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    const wchar_t *selftest_dir = NULL, *connect_to = NULL;
    for (int i = 1; i < argc; i++) {
        if (!wcscmp(argv[i], L"--selftest") && i + 1 < argc) { selftest_dir = argv[++i]; g_selftest = 1; }
        else if (!wcscmp(argv[i], L"--shot") && i + 1 < argc) {
            wcsncpy(g_shot, argv[++i], MAX_PATH - 1);
            g_selftest = 1;
            if (i + 1 < argc && argv[i + 1][0] >= L'0' && argv[i + 1][0] <= L'2') g_shot_page = argv[++i][0] - L'0';
        }
        else if (!wcscmp(argv[i], L"--connect") && i + 1 < argc) connect_to = argv[++i];
        else if (!wcscmp(argv[i], L"--run")) g_autorun = 1;
        else if (!wcscmp(argv[i], L"--log") && i + 1 < argc) wcsncpy(g_logfile, argv[++i], MAX_PATH - 1);
        else if (!wcscmp(argv[i], L"--quit-after") && i + 1 < argc) g_quit_after = _wtoi(argv[++i]);
    }
    if (g_autorun && (!connect_to || !is_local(connect_to))) g_autorun = 0;   /* không bao giờ tự chạy máy thật */
    if (selftest_dir) {
        wchar_t rp[MAX_PATH];
        CreateDirectoryW(selftest_dir, NULL);
        swprintf(rp, MAX_PATH, L"%ls\\selftest.txt", selftest_dir);
        g_report = _wfopen(rp, L"wb");
        if (!g_report) return 2;
        SetUnhandledExceptionFilter(on_crash);
        fprintf(g_report, "start\n");
        fflush(g_report);
    }
    if (connect_to || g_logfile[0]) g_selftest = 1;

    if (!g_selftest) {
        wchar_t base[MAX_PATH];
        if (SUCCEEDED(SHGetFolderPathW(NULL, CSIDL_APPDATA, NULL, 0, base))) {
            swprintf(g_ini, MAX_PATH, L"%ls\\PipeCutC", base);
            CreateDirectoryW(g_ini, NULL);
            wcscat(g_ini, L"\\settings.ini");
        }
    }

    view3d_register(inst);
    WNDCLASSEXW wc;
    memset(&wc, 0, sizeof wc);
    wc.cbSize = sizeof wc;
    wc.lpfnWndProc = panel_proc;
    wc.hInstance = inst;
    wc.hCursor = LoadCursor(NULL, IDC_ARROW);
    wc.hbrBackground = (HBRUSH)(COLOR_BTNFACE + 1);
    wc.lpszClassName = L"PipeCutPanel";
    RegisterClassExW(&wc);
    wc.lpfnWndProc = main_proc;
    wc.lpszClassName = L"PipeCutMain";
    wc.hIcon = LoadIconW(inst, MAKEINTRESOURCEW(1));
    wc.hIconSm = (HICON)LoadImageW(inst, MAKEINTRESOURCEW(1), IMAGE_ICON, GetSystemMetrics(SM_CXSMICON),
                                   GetSystemMetrics(SM_CYSMICON), 0);
    RegisterClassExW(&wc);

    HDC sdc = GetDC(NULL);
    g_dpi = GetDeviceCaps(sdc, LOGPIXELSY);
    ReleaseDC(NULL, sdc);
    HWND h = CreateWindowExW(WS_EX_CONTROLPARENT, L"PipeCutMain", APP_NAME L" " APP_VER L" - bản thử C/Win32 thuần",
                             WS_OVERLAPPEDWINDOW | WS_CLIPCHILDREN, CW_USEDEFAULT, CW_USEDEFAULT, S(1360), S(860),
                             NULL, NULL, inst, NULL);
    if (!h) {
        if (g_report) { fprintf(g_report, "CreateWindowEx failed, error %lu\n", GetLastError()); fclose(g_report); }
        return 3;
    }
    if (selftest_dir) {
        fprintf(g_report, "window ok dpi=%d\n", g_dpi);
        int rc = selftest(g_report, selftest_dir);
        DestroyWindow(h);
        LocalFree(argv);
        fclose(g_report);
        g_report = NULL;
        return rc;
    }
    ShowWindow(h, g_selftest ? SW_SHOWNORMAL : show);
    UpdateWindow(h);
    if (g_shot[0] || connect_to) show_page(connect_to ? 2 : g_shot_page);
    if (connect_to) {
        SetDlgItemTextW(h, ID_PORT, connect_to);
        connect_toggle();
        if (g_autorun) SetTimer(h, TM_RUN, 800, NULL);
    }
    if (g_quit_after > 0) SetTimer(h, TM_QUIT, (UINT)g_quit_after * 1000, NULL);
    else if (g_shot[0]) SetTimer(h, TM_SHOT, 1500, NULL);
    LocalFree(argv);

    MSG m;
    while (GetMessageW(&m, NULL, 0, 0) > 0) {
        if (IsDialogMessageW(h, &m)) continue;
        TranslateMessage(&m);
        DispatchMessageW(&m);
    }
    return (int)m.wParam;
}
