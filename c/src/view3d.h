/* Khung nhìn 3D vẽ bằng GDI - chuyển từ pipecut/machinescene.py */
#ifndef PIPECUT_VIEW3D_H
#define PIPECUT_VIEW3D_H
#include <windows.h>
#include "core.h"

#define VIEW3D_CLASS L"PipeCutView3D"

void view3d_register(HINSTANCE inst);
/* Nạp cảnh mới (phôi, máy, chương trình đã lập kế hoạch). Các con trỏ phải sống
   tới lần gọi sau; khung nhìn tự tính vết cắt từ kế hoạch. */
void view3d_set_scene(HWND h, const Section *s, const Machine *m, double pipe_len,
                      const Plan *plan);
void view3d_set_time(HWND h, double t);
/* Bám theo máy thật: đặt thẳng vị trí 4 trục (toạ độ chi tiết) và trạng thái mỏ. */
void view3d_set_live(HWND h, const double pos[NAX], int torch);
void view3d_toggle_focus(HWND h);
int  view3d_focus_is_work(HWND h);
void view3d_reset(HWND h);
/* Vẽ cảnh ra một ảnh BMP (tự kiểm không cần màn hình). */
int  view3d_render_bmp(HWND h, const wchar_t *path, int w, int hgt);
/* Đo tốc độ vẽ: vẽ `frames` khung w x hgt vào bộ nhớ, trả về ms trung bình mỗi khung. */
double view3d_bench(HWND h, int w, int hgt, int frames);

#endif
