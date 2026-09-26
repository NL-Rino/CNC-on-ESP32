/* Nói chuyện với FluidNC qua cổng COM hoặc WiFi (telnet cổng 23) - chuyển từ
 * pipecut/transport.py + protocol.py + controller.py.
 *
 * Một luồng nền lo hết việc đọc/ghi: gửi dòng lệnh theo kiểu đếm ký tự
 * (không để bộ đệm nhận 127 byte của bo tràn), hỏi trạng thái '?' 5 lần mỗi
 * giây, và báo cho cửa sổ bằng một thông điệp khi có gì mới. */
#ifndef PIPECUT_COMM_H
#define PIPECUT_COMM_H
#include <windows.h>
#include "core.h"

typedef struct Comm Comm;

typedef struct {
    int    connected;
    char   state[24];          /* Idle, Run, Hold:0, Alarm... */
    int    have_pos;
    double wpos[NAX];          /* toạ độ chi tiết, cùng thứ tự X Y Z A */
    double feed;
    int    torch;              /* nguồn cắt đang bật (trường A:S của báo cáo) */
    int    job_total, job_sent, job_acked, job_running, job_paused;
    int    alarm;
} CommStatus;

/* Liệt kê cổng COM đang có (đọc từ registry như Trình quản lý thiết bị). */
int   comm_list_ports(wchar_t names[][32], int max);
/* target: "COM5", "192.168.1.50", "fluidnc.local", "host:cổng".
   Mỗi khi có tin mới, cửa sổ `notify` nhận thông điệp `msg` (đã gộp bớt). */
Comm *comm_open(const wchar_t *target, HWND notify, UINT msg, wchar_t *err, size_t errlen);
void  comm_close(Comm *c);
void  comm_command(Comm *c, const char *line);       /* $H, $X, G10..., lệnh gõ tay */
int   comm_start_job(Comm *c, const char *program); /* 0 = đã bắt đầu, -1 = đang bận */
void  comm_pause(Comm *c);
void  comm_resume(Comm *c);
void  comm_stop(Comm *c);                            /* giữ dao + reset mềm, xoá hàng đợi */
void  comm_snapshot(Comm *c, CommStatus *out);
/* Lấy một dòng nhật ký (UTF-8). Trả về 0 khi hết. */
int   comm_pop_log(Comm *c, char *buf, size_t len);

#endif
