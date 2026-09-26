/* Kết nối FluidNC: cổng COM (Win32 CreateFile) hoặc WiFi (Winsock, telnet 23).
 * Chỉ dùng API có sẵn trong Windows. */
#ifndef _WIN32_WINNT
#define _WIN32_WINNT 0x0601
#endif
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "comm.h"

#define MAXPEND 256
#define NLOG    128
#define LOGLEN  240

struct Comm {
    HANDLE port;
    SOCKET sock;
    int    is_tcp;
    HANDLE thread;
    volatile LONG quit;
    CRITICAL_SECTION cs;
    HWND   notify;
    UINT   msg;
    volatile LONG posted;
    int    rx_buffer;
    /* lệnh người dùng: hàng đợi vòng */
    char  *cmd[64];
    int    cmd_head, ncmd;
    /* chương trình đang chạy */
    char  *job;
    char **jl;
    int    njl, jidx;
    /* các dòng đã gửi mà bo chưa trả lời */
    int    pend_len[MAXPEND], pend_job[MAXPEND], pend_head, npend, pend_bytes;
    unsigned char rt[32];
    int    nrt;
    char   rx[512];
    int    nrx;
    char   log[NLOG][LOGLEN];
    int    log_head, nlog;
    double wco[NAX];
    CommStatus st;
};

static const char *ERR_VI[] = {
    NULL,
    "Từ lệnh G-code không hợp lệ hoặc thiếu chữ cái",
    "Giá trị số sai định dạng",
    "Lệnh '$' không được hỗ trợ",
    "Giá trị âm không hợp lệ",
    "Công tắc hành trình đang tắt, không thể về gốc",
    "Bước thời gian quá nhỏ",
    "Đọc EEPROM lỗi, đã dùng giá trị mặc định",
    "Lệnh '$' chỉ dùng được khi máy rảnh",
    "Đang khoá bởi báo động hoặc đang về gốc, G-code bị chặn",
    "Chưa bật soft limit",
    "Dòng lệnh quá dài",
    "Tốc độ bước vượt quá khả năng của bo mạch",
    "Cửa an toàn đang mở",
    "Chuỗi thông điệp quá dài",
    "Quãng đường jog vượt hành trình",
    "Lệnh jog sai cú pháp",
    "Laser cần bật chế độ laser",
    NULL, NULL,
    "Có lệnh G không được hỗ trợ",
    "Nhiều lệnh cùng nhóm modal trong một dòng",
    "Thiếu hoặc sai giá trị F",
    "Giá trị lệnh G cần số nguyên",
    "Hai lệnh cùng dùng chữ cái trục",
    "Từ lệnh bị lặp lại",
    "Lệnh cần chữ cái trục nhưng không có",
    "Số dòng N vượt giá trị cho phép",
    "Lệnh thiếu giá trị P hoặc L",
    "Hệ toạ độ chi tiết không được hỗ trợ",
    "G53 chỉ dùng được với G0 hoặc G1",
    "Có chữ cái trục thừa",
    "G2/G3 cần ít nhất một trục trong mặt phẳng",
    "Toạ độ đích không hợp lệ",
    "Bán kính cung tròn không hợp lệ",
    "G2/G3 thiếu I, J hoặc K",
    "Có giá trị thừa không được dùng",
    "G43.1 phải tác động lên trục bù chiều dài dao",
    "Số hiệu dao vượt giới hạn",
};

static const char *ALARM_VI[] = {
    NULL,
    "Chạm công tắc hành trình cứng - cần về gốc lại",
    "Lệnh vượt hành trình mềm - toạ độ đích ngoài vùng làm việc",
    "Đã reset khi máy đang chạy - vị trí có thể sai",
    "Dò tìm thất bại - đầu dò đã kích hoạt sẵn",
    "Dò tìm thất bại - không chạm được trong hành trình",
    "Về gốc thất bại - bị reset giữa chừng",
    "Về gốc thất bại - cửa an toàn mở",
    "Về gốc thất bại - không rời khỏi công tắc",
    "Về gốc thất bại - không tìm thấy công tắc",
    "Về gốc thất bại - lỗi trục kép",
};

/* ------------------------------------------------------------------ */
static void poke(Comm *c)
{
    if (c->notify && !InterlockedExchange(&c->posted, 1))
        PostMessageW(c->notify, c->msg, 0, 0);
}

static void logf_locked(Comm *c, const char *fmt, ...)
{
    int slot = (c->log_head + c->nlog) % NLOG;
    if (c->nlog == NLOG) c->log_head = (c->log_head + 1) % NLOG;
    else c->nlog++;
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(c->log[slot], LOGLEN, fmt, ap);
    va_end(ap);
}

#define LOG(c, ...) do { EnterCriticalSection(&(c)->cs); logf_locked((c), __VA_ARGS__); \
                         LeaveCriticalSection(&(c)->cs); poke(c); } while (0)

static void job_clear_locked(Comm *c)
{
    free(c->job); free(c->jl);
    c->job = NULL; c->jl = NULL; c->njl = c->jidx = 0;
    c->st.job_running = c->st.job_paused = 0;
}

/* ------------------------------------------------------------------ */
static int io_write(Comm *c, const void *data, int n)
{
    if (c->is_tcp) {
        const char *p = (const char *)data;
        while (n > 0) {
            int k = send(c->sock, p, n, 0);
            if (k <= 0) return -1;
            p += k; n -= k;
        }
        return 0;
    }
    DWORD w = 0;
    if (!WriteFile(c->port, data, (DWORD)n, &w, NULL) || (int)w != n) return -1;
    return 0;
}

/* Bỏ chuỗi thương lượng telnet (IAC 0xFF ...) nếu máy chủ có gửi. */
static int strip_telnet(unsigned char *b, int n)
{
    int o = 0;
    for (int i = 0; i < n; i++) {
        if (b[i] == 0xFF && i + 1 < n) {
            unsigned char x = b[i + 1];
            if (x == 0xFF) { b[o++] = 0xFF; i++; continue; }
            i += (x >= 0xFB && x <= 0xFE) ? 2 : 1;
            continue;
        }
        b[o++] = b[i];
    }
    return o;
}

/* Đọc tối đa ~20 ms. Trả về số byte, 0 = chưa có gì, -1 = mất kết nối. */
static int io_read(Comm *c, unsigned char *buf, int cap)
{
    if (c->is_tcp) {
        fd_set rs;
        FD_ZERO(&rs);
        FD_SET(c->sock, &rs);
        struct timeval tv = {0, 20000};
        int r = select(0, &rs, NULL, NULL, &tv);
        if (r < 0) return -1;
        if (r == 0) return 0;
        int k = recv(c->sock, (char *)buf, cap, 0);
        if (k <= 0) return -1;
        return strip_telnet(buf, k);
    }
    DWORD got = 0;
    if (!ReadFile(c->port, buf, (DWORD)cap, &got, NULL)) return -1;
    return (int)got;
}

/* ------------------------------------------------------------------ */
static void parse_status(Comm *c, char *s)
{
    /* <Idle|MPos:1.000,2.000,3.000,4.000|FS:0,0|WCO:...> */
    size_t n = strlen(s);
    if (n < 2) return;
    s[n - 1] = 0;
    s++;
    double mpos[NAX] = {0}, wpos[NAX] = {0};
    int have_m = 0, have_w = 0;
    c->st.torch = 0;
    for (int first = 1; s; first = 0) {
        char *f = s, *bar = strchr(s, '|');
        if (bar) { *bar = 0; s = bar + 1; } else s = NULL;
        if (first) {
            snprintf(c->st.state, sizeof c->st.state, "%s", f);
            continue;
        }
        char *colon = strchr(f, ':');
        if (!colon) continue;
        *colon = 0;
        char *val = colon + 1;
        double *dst = !strcmp(f, "MPos") ? mpos : !strcmp(f, "WPos") ? wpos : !strcmp(f, "WCO") ? c->wco : NULL;
        if (dst) {
            char *p = val;
            for (int i = 0; i < NAX && *p; i++) {
                dst[i] = strtod(p, &p);
                if (*p == ',') p++;
                else break;
            }
            if (dst == mpos) have_m = 1;
            if (dst == wpos) have_w = 1;
        } else if (!strcmp(f, "FS") || !strcmp(f, "F")) {
            c->st.feed = strtod(val, NULL);
        } else if (!strcmp(f, "A")) {        /* phụ kiện: S/C = trục chính (nguồn cắt) đang bật */
            c->st.torch = strchr(val, 'S') || strchr(val, 'C');
        }
    }
    if (have_w) memcpy(c->st.wpos, wpos, sizeof wpos);
    else if (have_m) for (int i = 0; i < NAX; i++) c->st.wpos[i] = mpos[i] - c->wco[i];
    if (have_w || have_m) c->st.have_pos = 1;
    c->st.alarm = !strncmp(c->st.state, "Alarm", 5);
}

static void handle_line(Comm *c, char *line)
{
    while (*line == ' ' || *line == '\t') line++;
    if (!*line) return;
    EnterCriticalSection(&c->cs);
    if (line[0] == '<') {
        parse_status(c, line);
        LeaveCriticalSection(&c->cs);
        poke(c);
        return;
    }
    int is_ok = !strcmp(line, "ok"), is_err = !strncmp(line, "error:", 6);
    if (is_ok || is_err) {
        int was_job = 0;
        if (c->npend) {
            was_job = c->pend_job[c->pend_head];
            c->pend_bytes -= c->pend_len[c->pend_head];
            c->pend_head = (c->pend_head + 1) % MAXPEND;
            c->npend--;
        }
        if (is_err) {
            int code = atoi(line + 6);
            const char *vi = code > 0 && code < (int)(sizeof ERR_VI / sizeof *ERR_VI) && ERR_VI[code] ? ERR_VI[code] : "";
            if (was_job) {
                int k = c->st.job_acked;     /* chỉ số (từ 0) của dòng vừa bị từ chối */
                logf_locked(c, "LỖI dòng %d: %s %s -> %s  (đã dừng chương trình)", k + 1, line, vi,
                            k < c->njl ? c->jl[k] : "");
                job_clear_locked(c);
            } else {
                logf_locked(c, "%s %s", line, vi);
            }
        } else if (!was_job) {
            logf_locked(c, "ok");
        }
        if (was_job && c->st.job_running) {
            c->st.job_acked++;
            if (c->st.job_acked >= c->st.job_total && c->jidx >= c->njl) {
                logf_locked(c, "Hoàn tất %d dòng lệnh.", c->st.job_total);
                job_clear_locked(c);
            }
        }
        LeaveCriticalSection(&c->cs);
        poke(c);
        return;
    }
    if (!strncmp(line, "ALARM:", 6)) {
        int code = atoi(line + 6);
        const char *vi = code > 0 && code < (int)(sizeof ALARM_VI / sizeof *ALARM_VI) ? ALARM_VI[code] : "";
        logf_locked(c, "BÁO ĐỘNG %s: %s", line + 6, vi);
        c->st.alarm = 1;
        job_clear_locked(c);
    } else {
        logf_locked(c, "%s", line);
        /* lời chào sau reset: bo đã xoá bộ đệm nhận, chương trình dở coi như mất */
        if (!strncmp(line, "Grbl ", 5)) {
            c->npend = c->pend_head = c->pend_bytes = 0;
            if (c->st.job_running) logf_locked(c, "Bo mạch vừa khởi động lại - chương trình dừng.");
            job_clear_locked(c);
        }
    }
    LeaveCriticalSection(&c->cs);
    poke(c);
}

/* Chọn dòng kế tiếp nếu còn chỗ trong bộ đệm nhận của bo. */
static char *next_line_locked(Comm *c, int *is_job)
{
    char *line = NULL;
    if (c->ncmd) { line = c->cmd[c->cmd_head]; *is_job = 0; }
    else if (c->st.job_running && !c->st.job_paused && c->jidx < c->njl) { line = c->jl[c->jidx]; *is_job = 1; }
    if (!line) return NULL;
    int len = (int)strlen(line) + 1;
    int limit = c->rx_buffer - 1 > 16 ? c->rx_buffer - 1 : 16;
    if (c->npend >= MAXPEND || (c->npend && c->pend_bytes + len > limit)) return NULL;
    int slot = (c->pend_head + c->npend) % MAXPEND;
    c->pend_len[slot] = len;
    c->pend_job[slot] = *is_job;
    c->npend++;
    c->pend_bytes += len;
    if (*is_job) { c->jidx++; c->st.job_sent = c->jidx; }
    else { c->cmd_head = (c->cmd_head + 1) % 64; c->ncmd--; }
    return line;
}

static DWORD WINAPI worker(LPVOID arg)
{
    Comm *c = (Comm *)arg;
    DWORD last_poll = 0;
    unsigned char buf[512];
    while (!c->quit) {
        /* 1. lệnh thời gian thực đi trước mọi thứ */
        unsigned char rt[32];
        int nrt;
        EnterCriticalSection(&c->cs);
        nrt = c->nrt;
        memcpy(rt, c->rt, (size_t)nrt);
        c->nrt = 0;
        LeaveCriticalSection(&c->cs);
        if (nrt && io_write(c, rt, nrt)) break;
        DWORD now = GetTickCount();
        if (now - last_poll >= 200) {
            last_poll = now;
            if (io_write(c, "?", 1)) break;
        }
        /* 2. nạp dòng lệnh chừng nào bộ đệm của bo còn chỗ */
        int fail = 0;
        for (;;) {
            int is_job = 0;
            char out[256];
            EnterCriticalSection(&c->cs);
            char *line = next_line_locked(c, &is_job);
            if (line) snprintf(out, sizeof out, "%s\n", line);
            if (line && !is_job) logf_locked(c, "> %s", line);
            if (!is_job && line) free(line);
            LeaveCriticalSection(&c->cs);
            if (!line) break;
            if (io_write(c, out, (int)strlen(out))) { fail = 1; break; }
            poke(c);
        }
        if (fail) break;
        /* 3. đọc phản hồi */
        int n = io_read(c, buf, sizeof buf);
        if (n < 0) break;
        for (int i = 0; i < n; i++) {
            char ch = (char)buf[i];
            if (ch == '\r' || ch == '\n') {
                c->rx[c->nrx] = 0;
                if (c->nrx) handle_line(c, c->rx);
                c->nrx = 0;
            } else if (c->nrx < (int)sizeof c->rx - 1) {
                c->rx[c->nrx++] = ch;
            }
        }
    }
    if (!c->quit) {
        EnterCriticalSection(&c->cs);
        c->st.connected = 0;
        job_clear_locked(c);
        logf_locked(c, "Mất kết nối với bo mạch.");
        LeaveCriticalSection(&c->cs);
        poke(c);
    }
    return 0;
}

/* ------------------------------------------------------------------ */
int comm_list_ports(wchar_t names[][32], int max)
{
    HKEY key;
    int n = 0;
    if (RegOpenKeyExW(HKEY_LOCAL_MACHINE, L"HARDWARE\\DEVICEMAP\\SERIALCOMM", 0, KEY_READ, &key))
        return 0;
    for (DWORD i = 0; n < max; i++) {
        wchar_t vname[256], data[32];
        DWORD vl = 256, dl = sizeof data, type = 0;
        LONG r = RegEnumValueW(key, i, vname, &vl, NULL, &type, (BYTE *)data, &dl);
        if (r == ERROR_NO_MORE_ITEMS) break;
        if (r || type != REG_SZ) continue;
        data[31] = 0;
        wcsncpy(names[n], data, 31);
        names[n][31] = 0;
        n++;
    }
    RegCloseKey(key);
    /* COM2 trước COM10 */
    for (int i = 1; i < n; i++)
        for (int j = i; j > 0 && _wtoi(names[j] + 3) < _wtoi(names[j - 1] + 3); j--) {
            wchar_t t[32];
            wcscpy(t, names[j]); wcscpy(names[j], names[j - 1]); wcscpy(names[j - 1], t);
        }
    return n;
}

static int open_serial(Comm *c, const wchar_t *name, wchar_t *err, size_t errlen)
{
    wchar_t path[64];
    swprintf(path, 64, L"\\\\.\\%ls", name);
    c->port = CreateFileW(path, GENERIC_READ | GENERIC_WRITE, 0, NULL, OPEN_EXISTING, 0, NULL);
    if (c->port == INVALID_HANDLE_VALUE) {
        swprintf(err, errlen, L"Không mở được %ls (mã %lu). Cổng đang bị chương trình khác giữ, "
                 L"hoặc cắm nhầm cổng USB của ESP32-S3.", name, GetLastError());
        return -1;
    }
    SetupComm(c->port, 4096, 4096);
    DCB d;
    memset(&d, 0, sizeof d);
    d.DCBlength = sizeof d;
    GetCommState(c->port, &d);
    d.BaudRate = 115200;
    d.ByteSize = 8;
    d.Parity = NOPARITY;
    d.StopBits = ONESTOPBIT;
    d.fBinary = TRUE;
    d.fDtrControl = DTR_CONTROL_ENABLE;
    d.fRtsControl = RTS_CONTROL_ENABLE;
    d.fOutxCtsFlow = d.fOutxDsrFlow = d.fOutX = d.fInX = FALSE;
    SetCommState(c->port, &d);
    COMMTIMEOUTS to = {MAXDWORD, MAXDWORD, 20, 0, 2000};   /* đọc: chờ tối đa 20 ms */
    SetCommTimeouts(c->port, &to);
    PurgeComm(c->port, PURGE_RXCLEAR | PURGE_TXCLEAR);
    return 0;
}

static int open_tcp(Comm *c, const wchar_t *target, wchar_t *err, size_t errlen)
{
    WSADATA wd;
    WSAStartup(MAKEWORD(2, 2), &wd);
    wchar_t host[256], port[16] = L"23";
    wcsncpy(host, target, 255);
    host[255] = 0;
    wchar_t *colon = wcschr(host, L':');
    if (colon) { *colon = 0; wcsncpy(port, colon + 1, 15); port[15] = 0; }
    ADDRINFOW hints, *res = NULL;
    memset(&hints, 0, sizeof hints);
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;
    if (GetAddrInfoW(host, port, &hints, &res) || !res) {
        swprintf(err, errlen, L"Không tìm thấy địa chỉ %ls.", host);
        return -1;
    }
    c->sock = socket(res->ai_family, res->ai_socktype, res->ai_protocol);
    /* kết nối không chặn, chờ tối đa 5 giây */
    u_long nb = 1;
    ioctlsocket(c->sock, FIONBIO, &nb);
    connect(c->sock, res->ai_addr, (int)res->ai_addrlen);
    FreeAddrInfoW(res);
    fd_set ws, es;
    FD_ZERO(&ws); FD_SET(c->sock, &ws);
    FD_ZERO(&es); FD_SET(c->sock, &es);
    struct timeval tv = {5, 0};
    int r = select(0, NULL, &ws, &es, &tv);
    if (r <= 0 || FD_ISSET(c->sock, &es)) {
        closesocket(c->sock);
        c->sock = INVALID_SOCKET;
        swprintf(err, errlen, L"Không kết nối được tới %ls:%ls. Kiểm tra bo đã lên WiFi chưa "
                 L"và máy tính có cùng mạng không.", host, port);
        return -1;
    }
    nb = 0;
    ioctlsocket(c->sock, FIONBIO, &nb);
    BOOL on = TRUE;
    setsockopt(c->sock, IPPROTO_TCP, TCP_NODELAY, (const char *)&on, sizeof on);
    c->is_tcp = 1;
    return 0;
}

Comm *comm_open(const wchar_t *target, HWND notify, UINT msg, wchar_t *err, size_t errlen)
{
    while (*target == L' ') target++;
    if (!*target) { swprintf(err, errlen, L"Chưa chọn cổng hoặc địa chỉ."); return NULL; }
    Comm *c = (Comm *)calloc(1, sizeof *c);
    c->port = INVALID_HANDLE_VALUE;
    c->sock = INVALID_SOCKET;
    c->notify = notify;
    c->msg = msg;
    c->rx_buffer = 127;              /* con số dè dặt, an toàn cho cả Grbl gốc */
    InitializeCriticalSection(&c->cs);
    int is_com = (target[0] == L'C' || target[0] == L'c') && (target[1] == L'O' || target[1] == L'o') &&
                 (target[2] == L'M' || target[2] == L'm');
    if (is_com ? open_serial(c, target, err, errlen) : open_tcp(c, target, err, errlen)) {
        DeleteCriticalSection(&c->cs);
        free(c);
        return NULL;
    }
    c->st.connected = 1;
    snprintf(c->st.state, sizeof c->st.state, "?");
    c->thread = CreateThread(NULL, 0, worker, c, 0, NULL);
    return c;
}

void comm_close(Comm *c)
{
    if (!c) return;
    InterlockedExchange(&c->quit, 1);
    if (c->is_tcp && c->sock != INVALID_SOCKET) shutdown(c->sock, SD_BOTH);
    WaitForSingleObject(c->thread, 3000);
    CloseHandle(c->thread);
    if (c->is_tcp) { closesocket(c->sock); WSACleanup(); }
    else CloseHandle(c->port);
    while (c->ncmd) { free(c->cmd[c->cmd_head]); c->cmd_head = (c->cmd_head + 1) % 64; c->ncmd--; }
    job_clear_locked(c);
    DeleteCriticalSection(&c->cs);
    free(c);
}

static void push_rt(Comm *c, unsigned char b)
{
    EnterCriticalSection(&c->cs);
    if (c->nrt < (int)sizeof c->rt) c->rt[c->nrt++] = b;
    LeaveCriticalSection(&c->cs);
}

void comm_command(Comm *c, const char *line)
{
    if (!c) return;
    while (*line == ' ') line++;
    if (!*line) return;
    if (line[0] == '?' || line[0] == '!' || line[0] == '~') { push_rt(c, (unsigned char)line[0]); return; }
    EnterCriticalSection(&c->cs);
    if (c->ncmd < 64) {
        size_t n = strlen(line);
        char *d = (char *)malloc(n + 1);
        memcpy(d, line, n + 1);
        c->cmd[(c->cmd_head + c->ncmd) % 64] = d;
        c->ncmd++;
    }
    LeaveCriticalSection(&c->cs);
}

/* Bỏ chú thích ( ) và ; , bỏ khoảng trắng hai đầu, bỏ dòng rỗng. */
int comm_start_job(Comm *c, const char *program)
{
    if (!c) return -1;
    EnterCriticalSection(&c->cs);
    if (c->st.job_running) { LeaveCriticalSection(&c->cs); return -1; }
    size_t n = strlen(program);
    c->job = (char *)malloc(n + 1);
    int lines = 1;
    for (size_t i = 0; i < n; i++) lines += program[i] == '\n';
    c->jl = (char **)malloc(sizeof(char *) * (size_t)lines);
    c->njl = c->jidx = 0;
    char *o = c->job;
    const char *p = program;
    while (*p) {
        const char *e = strchr(p, '\n');
        if (!e) e = p + strlen(p);
        char *start = o;
        int paren = 0;
        for (const char *q = p; q < e; q++) {
            if (*q == ';') break;
            if (*q == '(') { paren = 1; continue; }
            if (*q == ')') { paren = 0; continue; }
            if (!paren && *q != '\r') *o++ = *q;
        }
        while (o > start && (o[-1] == ' ' || o[-1] == '\t')) o--;
        *o = 0;
        char *s = start;
        while (*s == ' ' || *s == '\t') s++;
        if (*s) { c->jl[c->njl++] = s; o++; }
        else o = start;
        p = *e ? e + 1 : e;
    }
    c->st.job_total = c->njl;
    c->st.job_sent = c->st.job_acked = 0;
    c->st.job_running = c->njl > 0;
    c->st.job_paused = 0;
    logf_locked(c, "Bắt đầu chạy %d dòng lệnh.", c->njl);
    LeaveCriticalSection(&c->cs);
    poke(c);
    return 0;
}

void comm_pause(Comm *c)
{
    if (!c) return;
    EnterCriticalSection(&c->cs);
    c->st.job_paused = 1;
    logf_locked(c, "Tạm dừng (feed hold).");
    LeaveCriticalSection(&c->cs);
    push_rt(c, '!');
    poke(c);
}

void comm_resume(Comm *c)
{
    if (!c) return;
    EnterCriticalSection(&c->cs);
    c->st.job_paused = 0;
    logf_locked(c, "Chạy tiếp.");
    LeaveCriticalSection(&c->cs);
    push_rt(c, '~');
    poke(c);
}

void comm_stop(Comm *c)
{
    if (!c) return;
    EnterCriticalSection(&c->cs);
    job_clear_locked(c);
    while (c->ncmd) { free(c->cmd[c->cmd_head]); c->cmd_head = (c->cmd_head + 1) % 64; c->ncmd--; }
    c->npend = c->pend_head = c->pend_bytes = 0;
    if (c->nrt + 2 <= (int)sizeof c->rt) { c->rt[c->nrt++] = '!'; c->rt[c->nrt++] = 0x18; }
    logf_locked(c, "ĐÃ DỪNG chương trình (giữ dao + reset mềm).");
    LeaveCriticalSection(&c->cs);
    poke(c);
}

void comm_snapshot(Comm *c, CommStatus *out)
{
    if (!c) { memset(out, 0, sizeof *out); return; }
    InterlockedExchange(&c->posted, 0);
    EnterCriticalSection(&c->cs);
    *out = c->st;
    LeaveCriticalSection(&c->cs);
}

int comm_pop_log(Comm *c, char *buf, size_t len)
{
    if (!c) return 0;
    int got = 0;
    EnterCriticalSection(&c->cs);
    if (c->nlog) {
        snprintf(buf, len, "%s", c->log[c->log_head]);
        c->log_head = (c->log_head + 1) % NLOG;
        c->nlog--;
        got = 1;
    }
    LeaveCriticalSection(&c->cs);
    return got;
}
