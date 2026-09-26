/* pipecutc-cli.exe - dòng lệnh: sinh G-code, tính thời gian, và các lệnh đối chiếu
 * con số với bản Python (dùng khi kiểm thử phần lõi).
 *
 *   pipecutc-cli gen round 60 ra.nc          sinh G-code chương trình mẫu (ống tròn D60)
 *   pipecutc-cli gen box 50 50 0 3 ra.nc     ống hộp 50x50, góc lượn tự tính, thành 3
 *   pipecutc-cli plan ra.nc                  thời gian chạy như FluidNC, chia theo loại
 *   pipecutc-cli contact round 60 N          bảng tư thế máy theo vị trí chu vi (kiểm thử)
 *   pipecutc-cli contact box W H rc t N
 *   pipecutc-cli surface box W H rc t        độ cao mặt phôi dưới mỏ theo góc xoay (kiểm thử)
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "core.h"

static int parse_section(int argc, char **argv, int i, Section *s, int *next)
{
    if (i < argc && !strcmp(argv[i], "round") && i + 1 < argc) {
        *next = i + 2;
        return sec_init_round(s, atof(argv[i + 1]));
    }
    if (i < argc && !strcmp(argv[i], "box") && i + 4 < argc) {
        *next = i + 5;
        return sec_init_box(s, atof(argv[i + 1]), atof(argv[i + 2]), atof(argv[i + 3]), atof(argv[i + 4]));
    }
    return -1;
}

static char *read_file(const char *path)
{
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    fseek(f, 0, SEEK_END);
    long n = ftell(f);
    fseek(f, 0, SEEK_SET);
    char *b = (char *)malloc((size_t)n + 1);
    size_t got = fread(b, 1, (size_t)n, f);
    b[got] = 0;
    fclose(f);
    return b;
}

/* Chương trình mẫu dùng chung với ô "Mẫu" trên giao diện */
int demo_ops(const Section *s, Operation *ops);

int main(int argc, char **argv)
{
    Machine m;
    machine_defaults(&m);
    if (argc < 2) {
        fprintf(stderr, "pipecutc-cli gen|plan|contact|surface ... (xem đầu tệp cli.c)\n");
        return 2;
    }
    if (!strcmp(argv[1], "plan") && argc >= 3) {
        char *g = read_file(argv[2]);
        if (!g) { fprintf(stderr, "không mở được %s\n", argv[2]); return 1; }
        Plan p;
        plan_program(g, &m, &p);
        printf("total %.6f\n", p.total);
        const char *keys[NCAT] = {"cut", "travel", "lift", "plunge", "index", "dwell"};
        for (int i = 0; i < NCAT; i++) printf("%s %.6f\n", keys[i], p.by_cat[i]);
        printf("full_stops %d\nsyncs %d\n", p.full_stops, p.syncs);
        plan_free(&p);
        free(g);
        return 0;
    }
    Section s;
    int next = 0;
    if (!strcmp(argv[1], "contact")) {
        if (parse_section(argc, argv, 2, &s, &next) || next >= argc) return 2;
        int n = atoi(argv[next]);
        for (int i = 0; i <= n; i++) {
            /* từ -1 vòng tới +2 vòng, cộng vài giá trị sát mốc chu vi */
            double v = -s.perimeter + 3.0 * s.perimeter * i / n;
            Contact c = sec_contact(&s, v);
            printf("%.9f %.9f %.9f %.9f\n", v, c.theta, c.cross, c.height);
        }
        double tricky[] = {-1e-15, 0.0, 1e-15, s.perimeter - 1e-12, s.perimeter, s.perimeter + 1e-12};
        for (int i = 0; i < 6; i++) {
            Contact c = sec_contact(&s, tricky[i]);
            printf("%.17g %.9f %.9f %.9f\n", tricky[i], c.theta, c.cross, c.height);
        }
        return 0;
    }
    if (!strcmp(argv[1], "surface")) {
        if (parse_section(argc, argv, 2, &s, &next)) return 2;
        for (int a = -30; a <= 390; a += 7)
            for (int x = -30; x <= 30; x += 6)
                printf("%d %d %.9f %.9f\n", a, x, sec_surface_height(&s, a, x),
                       sec_v_of_theta(&s, a));
        return 0;
    }
    if (!strcmp(argv[1], "gen")) {
        if (parse_section(argc, argv, 2, &s, &next) || next >= argc) return 2;
        Operation ops[16];
        int n = demo_ops(&s, ops);
        ops_order(ops, n, &s);
        GBuf g;
        char msg[200];
        gcode_build(ops, n, &s, &m, 1000.0, &g, msg, sizeof msg);
        if (msg[0]) fprintf(stderr, "%s\n", msg);
        FILE *f = fopen(argv[next], "wb");
        if (!f) return 1;
        fwrite(g.text, 1, g.len, f);
        fclose(f);
        Plan p;
        plan_program(g.text, &m, &p);
        printf("%d dong, %d lan moi, cat %.1f mm, uoc tinh %.1f s\n", g.lines, g.pierces,
               g.cut_length, p.total);
        plan_free(&p);
        gbuf_free(&g);
        return 0;
    }
    fprintf(stderr, "lệnh không rõ\n");
    return 2;
}
