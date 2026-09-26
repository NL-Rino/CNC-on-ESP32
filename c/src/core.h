/*
 * PipeCut C - lõi tính toán: tiết diện ống, nguyên công, G-code, lập kế hoạch.
 *
 * Chỉ dùng thư viện chuẩn C (math.h, stdio.h, stdlib.h, string.h) nên lõi này
 * biên dịch được ở mọi nơi; phần giao diện Win32 nằm riêng ở ui.c / view3d.c.
 *
 * Quy ước giống hệt bản Python (pipecut/section.py, kinematics.py):
 *   u = mm dọc ống, tăng về phía đầu tự do
 *   v = mm theo chu vi tiết diện (độ dài cung), v = 0 ở đỉnh ống khi A = 0
 *   A = độ, X = trục ngang (mm), Y = dọc ống, Z = nâng hạ (0 = chạm mặt ở vị trí mốc)
 */
#ifndef PIPECUT_CORE_H
#define PIPECUT_CORE_H

#include <stddef.h>

#define PC_PI 3.14159265358979323846

/* ------------------------------------------------------------------ */
/* Tiết diện                                                           */
/* ------------------------------------------------------------------ */
typedef enum { SEC_ROUND = 0, SEC_BOX = 1 } SectionKind;

typedef struct {
    int kind;          /* 0 = đoạn thẳng, 1 = cung góc lượn */
    double length;
    double start;      /* vị trí v bắt đầu */
    double px, py;     /* đoạn thẳng: điểm đầu */
    double dx, dy;     /* đoạn thẳng: hướng */
    double cx, cy;     /* cung: tâm */
    double psi;        /* đoạn thẳng: góc pháp tuyến; cung: góc bắt đầu (độ) */
} SecSeg;

typedef struct {
    SectionKind kind;
    double radius;             /* ống tròn */
    double width, height;      /* ống hộp */
    double hx, hy, rc;         /* nửa cạnh, bán kính góc thực dùng */
    double wall;
    double perimeter;
    double max_radius;
    double ref_height;         /* chiều cao mặt tại v = 0 - gốc Z */
    SecSeg seg[9];
    int nseg;
} Section;

typedef struct { double theta, cross, height; } Contact;

int     sec_init_round(Section *s, double diameter);
int     sec_init_box(Section *s, double width, double height, double corner, double wall);
void    sec_point(const Section *s, double v, double *x, double *y);
double  sec_normal(const Section *s, double v);          /* độ, 0 = hướng lên */
Contact sec_contact(const Section *s, double v);          /* tư thế máy để cắt vuông góc tại v */
double  sec_v_of_theta(const Section *s, double theta);   /* điểm theo hướng nhìn theta (độ) */
double  sec_surface_height(const Section *s, double theta, double cross);
double  sec_v_of_contact(const Section *s, double theta, double cross);
int     sec_breakpoints(const Section *s, double *out, int max);

/* ------------------------------------------------------------------ */
/* Máy                                                                  */
/* ------------------------------------------------------------------ */
enum { AX_X = 0, AX_Y = 1, AX_Z = 2, AX_A = 3, NAX = 4 };

typedef struct {
    double max_rate[NAX];      /* mm/phút (độ/phút với A) */
    double accel[NAX];         /* mm/s^2 */
    double junction_deviation; /* mm */
    int    planner_blocks;
    /* tiến trình */
    double kerf, cut_feed, plunge_feed;
    double cut_height, pierce_height, pierce_delay, off_delay;
    double safe_height, travel_height;
    double lead_in, overcut;
    double power;
    double max_feed, min_feed;
    double max_segment;        /* chia nhỏ đường cắt trải phẳng (mm) */
} Machine;

void machine_defaults(Machine *m);

/* ------------------------------------------------------------------ */
/* Nguyên công                                                          */
/* ------------------------------------------------------------------ */
typedef enum { OP_CUTOFF = 0, OP_HOLE = 1, OP_CIRCLE = 2, OP_SLOT = 3, OP_KINDS } OpKind;

typedef struct {
    OpKind kind;
    int    enabled;
    double x;          /* vị trí dọc ống (tâm hoặc mặt cắt) */
    double theta;      /* góc tâm (độ) */
    double a;          /* cutoff: góc vát; hole/circle: đường kính; slot: dài dọc ống */
    double b;          /* slot: rộng theo góc (độ) */
    double c;          /* slot: bán kính bo góc */
} Operation;

const wchar_t *op_name(OpKind k);

typedef struct { double u, v; } UV;

typedef struct {
    UV    *pt;
    int    n, cap;
    int    closed;     /* khép kín trên mặt trải (lỗ, rãnh) */
    int    wrap;       /* quấn trọn chu vi (cắt đứt) */
    int    lead;       /* số điểm đầu thuộc đoạn vào dao */
    char   name[64];
} Contour;

void contour_free(Contour *c);
/* Dựng biên dạng đã bù kerf, đã gắn vào dao và chạy vượt. 0 = được, khác 0 = lỗi (msg). */
int  op_build(const Operation *op, const Section *s, const Machine *m, Contour *out,
              char *msg, size_t msglen);

/* ------------------------------------------------------------------ */
/* G-code                                                               */
/* ------------------------------------------------------------------ */
typedef struct {
    char  *text;
    size_t len, cap;
    int    lines;
    int    pierces;
    double cut_length;         /* mm trên bề mặt */
} GBuf;

void gbuf_free(GBuf *g);
/* Sinh cả chương trình từ danh sách nguyên công (theo thứ tự đã sắp). */
int  gcode_build(const Operation *ops, int nops, const Section *s, const Machine *m,
                 double pipe_length, GBuf *out, char *msg, size_t msglen);
/* Sắp thứ tự như máy laser: lỗ/rãnh trước, cắt đứt sau, từ đầu tự do vào. */
void ops_order(Operation *ops, int nops, const Section *s);

/* ------------------------------------------------------------------ */
/* Lập kế hoạch chuyển động (giống FluidNC) và mô phỏng                */
/* ------------------------------------------------------------------ */
enum { CAT_CUT = 0, CAT_TRAVEL, CAT_LIFT, CAT_PLUNGE, CAT_INDEX, CAT_DWELL, NCAT };

typedef struct {
    double t0, dt;             /* thời điểm bắt đầu, thời lượng (s) */
    double a[NAX], b[NAX];     /* vị trí đầu, cuối */
    int    rapid, torch, dwell;
    int    line;
    double v_entry, v_exit, v_nom, accel;   /* để nội suy đúng hình thang vận tốc */
} Move;

typedef struct {
    Move  *mv;
    int    n, cap;
    double total;
    double by_cat[NCAT];
    int    full_stops, syncs;
} Plan;

void plan_free(Plan *p);
int  plan_program(const char *gcode, const Machine *m, Plan *out);
/* Trạng thái máy tại thời điểm t (nội suy trong khối theo đúng hình thang vận tốc). */
void plan_state(const Plan *p, double t, double pos[NAX], int *torch, int *line);

extern const char *CAT_NAMES_VI[NCAT];

#endif
