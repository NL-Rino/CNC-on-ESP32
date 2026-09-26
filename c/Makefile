# Dựng bằng MinGW-w64 (trên Windows: w64devkit hoặc MSYS2; trên Linux: gói mingw-w64).
#   make            -> PipeCutC.exe (giao diện) và pipecutc-cli.exe (dòng lệnh)
# (Hai tên phải khác nhau không kể hoa thường: Windows coi PipeCutC.exe và
#  pipecutc.exe là cùng một tệp.)
# Chỉ liên kết với DLL có sẵn trong Windows: user32, gdi32, comctl32, comdlg32,
# ws2_32, advapi32, shell32.  Liên kết tĩnh libgcc nên không kèm DLL nào khác.
# Trên Windows (w64devkit/MSYS2) gọi:  make CC=gcc WINDRES=windres
ifeq ($(origin CC),default)
CC      = x86_64-w64-mingw32-gcc
endif
WINDRES ?= x86_64-w64-mingw32-windres
CFLAGS  ?= -O2 -std=c99 -Wall -Wextra -Wno-unused-parameter -DUNICODE -D_UNICODE
LDFLAGS ?= -s -static -static-libgcc
CORE    = src/section.c src/ops.c src/gcode.c src/planner.c src/demo.c
GUI     = src/ui.c src/view3d.c src/comm.c

all: PipeCutC.exe pipecutc-cli.exe

pipecutc-cli.exe: $(CORE) src/cli.c src/core.h
	$(CC) $(CFLAGS) -o $@ $(CORE) src/cli.c $(LDFLAGS) -lm

res.o: res/app.rc res/app.manifest res/pipecut.ico
	$(WINDRES) -I res -i res/app.rc -o $@

PipeCutC.exe: $(CORE) $(GUI) src/core.h src/view3d.h src/comm.h res.o
	$(CC) $(CFLAGS) -mwindows -municode -o $@ $(CORE) $(GUI) res.o $(LDFLAGS) \
	    -lm -lcomctl32 -lcomdlg32 -lgdi32 -luser32 -lws2_32 -ladvapi32 -lshell32

clean:
	rm -f *.exe res.o
