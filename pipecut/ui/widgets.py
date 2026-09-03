"""Các thành phần giao diện dùng lại được."""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog, ttk
from typing import Any, Callable, Dict, List, Optional, Sequence

PAD = 6


class ParamForm(ttk.Frame):
    """Biểu mẫu nhập liệu tự sinh từ mô tả tham số.

    Nhờ đọc thẳng ``OP_CATALOG`` mà thêm một nguyên công mới chỉ cần khai báo
    tham số ở một chỗ duy nhất - giao diện tự có ô nhập tương ứng.
    """

    def __init__(self, master, on_change: Optional[Callable[[], None]] = None, **kw):
        super().__init__(master, **kw)
        self.on_change = on_change
        self._vars: Dict[str, tk.Variable] = {}
        self._specs: List[Dict[str, Any]] = []
        self.columnconfigure(1, weight=1)

    def build(self, specs: Sequence[Dict[str, Any]], values: Optional[Dict[str, Any]] = None) -> None:
        for child in self.winfo_children():
            child.destroy()
        self._vars.clear()
        self._specs = list(specs)
        values = values or {}
        for row, spec in enumerate(self._specs):
            name = spec["name"]
            label = spec["label"] + (f" [{spec['unit']}]" if spec.get("unit") else "")
            ttk.Label(self, text=label).grid(row=row, column=0, sticky="w", padx=(0, PAD), pady=2)
            value = values.get(name, spec["default"])
            kind = spec.get("kind", "float")
            if kind == "bool":
                var: tk.Variable = tk.BooleanVar(value=bool(value))
                w = ttk.Checkbutton(self, variable=var, command=self._changed)
                w.grid(row=row, column=1, sticky="w", pady=2)
            elif kind == "choice":
                var = tk.StringVar(value=str(value))
                w = ttk.Combobox(self, textvariable=var, state="readonly",
                                 values=list(spec.get("choices") or []), width=14)
                w.grid(row=row, column=1, sticky="ew", pady=2)
                w.bind("<<ComboboxSelected>>", lambda _e: self._changed())
            elif kind == "file":
                var = tk.StringVar(value=str(value))
                box = ttk.Frame(self)
                box.grid(row=row, column=1, sticky="ew", pady=2)
                box.columnconfigure(0, weight=1)
                w = ttk.Entry(box, textvariable=var, width=14)
                w.grid(row=0, column=0, sticky="ew")
                w.bind("<FocusOut>", lambda _e: self._changed())
                w.bind("<Return>", lambda _e: self._changed())
                ttk.Button(box, text="Chọn...", width=8,
                           command=lambda v=var: self._pick_file(v)).grid(row=0, column=1,
                                                                          padx=(4, 0))
            else:
                var = tk.StringVar(value=_fmt_value(value))
                w = ttk.Entry(self, textvariable=var, width=14)
                w.grid(row=row, column=1, sticky="ew", pady=2)
                w.bind("<FocusOut>", lambda _e: self._changed())
                w.bind("<Return>", lambda _e: self._changed())
            self._vars[name] = var
            if spec.get("hint"):
                ttk.Label(self, text=spec["hint"], foreground="#5a646e",
                          font=("TkDefaultFont", 8)).grid(row=row, column=2, sticky="w",
                                                          padx=(PAD, 0))

    def _pick_file(self, var: tk.StringVar) -> None:
        """Hộp thoại chọn tệp biên dạng, lọc sẵn theo các định dạng đọc được."""
        try:
            from ..importers import FILE_TYPES
            types = list(FILE_TYPES)
        except Exception:                              # pragma: no cover
            types = [("Mọi tệp", "*.*")]
        types.append(("Mọi tệp", "*.*"))
        current = var.get()
        path = filedialog.askopenfilename(
            title="Chọn tệp biên dạng",
            filetypes=types,
            initialdir=os.path.dirname(current) if current else None,
        )
        if path:
            var.set(path)
            self._changed()

    def _changed(self) -> None:
        if self.on_change:
            self.on_change()

    def values(self) -> Dict[str, Any]:
        """Đọc giá trị đang nhập, tự ép kiểu theo mô tả tham số."""
        out: Dict[str, Any] = {}
        for spec in self._specs:
            name = spec["name"]
            var = self._vars.get(name)
            if var is None:
                continue
            kind = spec.get("kind", "float")
            raw = var.get()
            if kind == "bool":
                out[name] = bool(raw)
            elif kind in ("choice", "file", "str"):
                out[name] = str(raw)
            else:
                try:
                    out[name] = float(str(raw).replace(",", "."))
                except (TypeError, ValueError):
                    out[name] = spec["default"]
        return out


def _fmt_value(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


class FieldGrid(ttk.Frame):
    """Lưới ô nhập đơn giản cho các thông số cố định (ống, tiến trình, máy)."""

    def __init__(self, master, fields: Sequence[Sequence[Any]], columns: int = 2, **kw):
        super().__init__(master, **kw)
        self.vars: Dict[str, tk.Variable] = {}
        self._kinds: Dict[str, str] = {}
        for i in range(columns):
            self.columnconfigure(i * 2 + 1, weight=1)
        for idx, field in enumerate(fields):
            key, label, value = field[0], field[1], field[2]
            kind = field[3] if len(field) > 3 else ("bool" if isinstance(value, bool) else "float")
            choices = field[4] if len(field) > 4 else None
            r, c = divmod(idx, columns)
            ttk.Label(self, text=label).grid(row=r, column=c * 2, sticky="w", padx=(0, 4), pady=2)
            if kind == "bool":
                var: tk.Variable = tk.BooleanVar(value=bool(value))
                ttk.Checkbutton(self, variable=var).grid(row=r, column=c * 2 + 1, sticky="w", pady=2)
            elif kind == "choice":
                var = tk.StringVar(value=str(value))
                ttk.Combobox(self, textvariable=var, values=list(choices or []),
                             state="readonly", width=12).grid(row=r, column=c * 2 + 1,
                                                              sticky="ew", pady=2, padx=(0, 10))
            else:
                var = tk.StringVar(value=_fmt_value(value))
                ttk.Entry(self, textvariable=var, width=12).grid(row=r, column=c * 2 + 1,
                                                                 sticky="ew", pady=2, padx=(0, 10))
            self.vars[key] = var
            self._kinds[key] = kind

    def get(self, key: str, fallback: Any = 0.0) -> Any:
        var = self.vars.get(key)
        if var is None:
            return fallback
        kind = self._kinds.get(key, "float")
        raw = var.get()
        if kind == "bool":
            return bool(raw)
        if kind in ("choice", "str"):
            return str(raw)
        try:
            return float(str(raw).replace(",", "."))
        except (TypeError, ValueError):
            return fallback

    def set(self, key: str, value: Any) -> None:
        var = self.vars.get(key)
        if var is not None:
            var.set(value if isinstance(value, bool) else _fmt_value(value))


class Console(ttk.Frame):
    """Cửa sổ nhật ký kèm ô gõ lệnh trực tiếp xuống máy."""

    MAX_LINES = 800

    def __init__(self, master, on_send: Optional[Callable[[str], None]] = None, **kw):
        super().__init__(master, **kw)
        self.on_send = on_send
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.text = tk.Text(self, height=10, wrap="none", state="disabled",
                            background="#11161b", foreground="#d6dde4",
                            insertbackground="#d6dde4", font=("Consolas", 9))
        self.text.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=sb.set)
        for tag, color in (("tx", "#7fc8ff"), ("rx", "#b9c4ce"), ("err", "#ff8a7a"),
                           ("ok", "#8ddf9f"), ("info", "#f2c66d")):
            self.text.tag_configure(tag, foreground=color)

        bar = ttk.Frame(self)
        bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        bar.columnconfigure(0, weight=1)
        self.entry = ttk.Entry(bar)
        self.entry.grid(row=0, column=0, sticky="ew")
        self.entry.bind("<Return>", self._send)
        ttk.Button(bar, text="Gửi", width=6, command=self._send).grid(row=0, column=1, padx=(4, 0))
        ttk.Button(bar, text="Xoá", width=6, command=self.clear).grid(row=0, column=2, padx=(4, 0))
        self._history: List[str] = []
        self._hist_idx = 0
        self.entry.bind("<Up>", self._history_up)
        self.entry.bind("<Down>", self._history_down)

    def _send(self, _event=None) -> None:
        cmd = self.entry.get().strip()
        if not cmd:
            return
        self.entry.delete(0, "end")
        self._history.append(cmd)
        self._hist_idx = len(self._history)
        if self.on_send:
            self.on_send(cmd)

    def _history_up(self, _event=None) -> str:
        if self._history and self._hist_idx > 0:
            self._hist_idx -= 1
            self.entry.delete(0, "end")
            self.entry.insert(0, self._history[self._hist_idx])
        return "break"

    def _history_down(self, _event=None) -> str:
        if self._hist_idx < len(self._history) - 1:
            self._hist_idx += 1
            self.entry.delete(0, "end")
            self.entry.insert(0, self._history[self._hist_idx])
        else:
            self.entry.delete(0, "end")
        return "break"

    def log(self, message: str, tag: str = "rx") -> None:
        self.text.configure(state="normal")
        self.text.insert("end", message.rstrip() + "\n", tag)
        lines = int(self.text.index("end-1c").split(".")[0])
        if lines > self.MAX_LINES:
            self.text.delete("1.0", f"{lines - self.MAX_LINES}.0")
        self.text.see("end")
        self.text.configure(state="disabled")

    def clear(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")


class DRO(ttk.LabelFrame):
    """Bảng hiển thị toạ độ hiện tại."""

    def __init__(self, master, letters: Sequence[str], **kw):
        super().__init__(master, text="Toạ độ", **kw)
        self.letters = list(letters)
        self._work: Dict[str, tk.StringVar] = {}
        self._machine: Dict[str, tk.StringVar] = {}
        ttk.Label(self, text="Trục", width=6).grid(row=0, column=0, padx=4)
        ttk.Label(self, text="Chi tiết (WPos)", width=14, anchor="e").grid(row=0, column=1, padx=4)
        ttk.Label(self, text="Máy (MPos)", width=14, anchor="e").grid(row=0, column=2, padx=4)
        for i, c in enumerate(self.letters, start=1):
            role = ""
            ttk.Label(self, text=c, font=("TkDefaultFont", 11, "bold")).grid(row=i, column=0, padx=4)
            wv = tk.StringVar(value="0.000")
            mv = tk.StringVar(value="0.000")
            ttk.Label(self, textvariable=wv, anchor="e", width=14,
                      font=("Consolas", 13)).grid(row=i, column=1, padx=4, sticky="e")
            ttk.Label(self, textvariable=mv, anchor="e", width=14,
                      font=("Consolas", 10), foreground="#5a646e").grid(row=i, column=2, padx=4, sticky="e")
            self._work[c] = wv
            self._machine[c] = mv

    def update_values(self, work: Dict[str, float], machine: Dict[str, float]) -> None:
        for c in self.letters:
            if c in work:
                self._work[c].set(f"{work[c]:9.3f}")
            if c in machine:
                self._machine[c].set(f"{machine[c]:9.3f}")


class StatusBadge(ttk.Label):
    """Nhãn trạng thái đổi màu theo tình trạng máy."""

    COLORS = {
        "Idle": ("#1f7a3d", "#e8f7ec"),
        "Run": ("#1667b3", "#e6f1fb"),
        "Jog": ("#1667b3", "#e6f1fb"),
        "Hold": ("#9a6b00", "#fdf3e0"),
        "Home": ("#9a6b00", "#fdf3e0"),
        "Alarm": ("#b3261e", "#fdeceb"),
        "Door": ("#b3261e", "#fdeceb"),
    }

    def __init__(self, master, **kw):
        super().__init__(master, text="Chưa kết nối", anchor="center", width=16,
                         font=("TkDefaultFont", 10, "bold"), **kw)
        self.set_state(None)

    def set_state(self, state: Optional[str], text: Optional[str] = None) -> None:
        fg, bg = self.COLORS.get(state or "", ("#39424b", "#eceff1"))
        self.configure(text=text or state or "Chưa kết nối", foreground=fg, background=bg)
