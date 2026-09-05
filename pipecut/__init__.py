"""PipeCut Studio - phần mềm điều khiển máy cắt ống 4 trục dùng ESP32 + FluidNC.

Gói này gồm 3 lớp tách bạch:

*   **Lớp hình học / quỹ đạo** (`geom2d`, `shapes`, `pathops`, `kinematics`,
    `gcode`, `jobs`) - thuần Python, không phụ thuộc thư viện ngoài, có thể
    chạy và kiểm thử ở bất kỳ đâu.
*   **Lớp giao tiếp** (`protocol`, `transport`, `simulator`, `controller`) -
    nói chuyện với FluidNC qua cổng COM bằng giao thức character-counting
    (giống Grbl). Cần ``pyserial`` khi dùng cổng COM thật.
*   **Lớp giao diện** (`ui`, `cli`, `svgview`) - GUI Tkinter và CLI.
"""

__version__ = "1.10.0"
__all__ = ["__version__"]
