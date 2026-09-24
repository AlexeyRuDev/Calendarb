"""
Календарь с задачами — desktop-приложение на Python (Tkinter).

Возможности:
  * Месячный календарь с навигацией по месяцам/годам.
  * Клик по любой ячейке дня открывает отдельный экран со списком задач
    на выбранный день.
  * На экране дня можно добавлять, отмечать выполненными и удалять задачи.
  * Задачи сохраняются в JSON-файл (tasks.json рядом с приложением),
    поэтому не теряются между запусками.

Запуск:
    python calendar_app.py
"""

import calendar
import json
import os
import tkinter as tk
from datetime import date
from tkinter import font as tkfont, messagebox

MONTHS_RU = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]
WEEKDAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

# ---- Палитра ---------------------------------------------------------------
BG_MAIN = "#f5f6fa"
BG_CARD = "#ffffff"
ACCENT = "#4a69bd"
ACCENT_DARK = "#3b528f"
TODAY_BG = "#e8f0fe"
OTHER_MONTH_FG = "#b2bec3"
TEXT_DARK = "#2d3436"
DONE_FG = "#95a5a6"
HOVER_BG = "#dfe6f5"


def tasks_file_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "tasks.json")


class TaskStore:
    """Хранилище задач: {iso_дата: [ {"text": str, "done": bool}, ... ]}"""

    def __init__(self, path: str):
        self.path = path
        self.data: dict[str, list[dict]] = {}
        self.load()

    def load(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                self.data = {
                    k: [t for t in v if isinstance(t, dict)]
                    for k, v in raw.items()
                }
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            self.data = {}

    def save(self) -> None:
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except OSError:
            pass  # не критично: приложение продолжит работу в памяти

    def get(self, d: date) -> list[dict]:
        return self.data.get(d.isoformat(), [])

    def add(self, d: date, text: str) -> None:
        self.data.setdefault(d.isoformat(), []).append({"text": text, "done": False})
        self.save()

    def remove(self, d: date, index: int) -> None:
        items = self.data.get(d.isoformat())
        if items and 0 <= index < len(items):
            items.pop(index)
            if not items:
                del self.data[d.isoformat()]
            self.save()

    def toggle(self, d: date, index: int) -> None:
        items = self.data.get(d.isoformat())
        if items and 0 <= index < len(items):
            items[index]["done"] = not items[index].get("done", False)
            self.save()

    def count_pending(self, d: date) -> int:
        return sum(1 for t in self.get(d) if not t.get("done", False))


class DayScreen(tk.Frame):
    """Отдельный экран со списком задач на выбранный день."""

    def __init__(self, master, app: "CalendarApp"):
        super().__init__(master, bg=BG_MAIN)
        self.app = app
        self.current_date: date | None = None

        # --- Верхняя панель: кнопка "назад" + заголовок ---------------------
        header = tk.Frame(self, bg=ACCENT, height=64)
        header.pack(fill="x")
        header.pack_propagate(False)

        self.btn_back = tk.Button(
            header,
            text="← К календарю",
            command=self.app.show_calendar,
            bg=ACCENT, fg="white",
            activebackground=ACCENT_DARK, activeforeground="white",
            relief="flat", font=("Segoe UI", 11, "bold"), cursor="hand2",
            padx=12,
        )
        self.btn_back.pack(side="left", padx=8, pady=10)

        self.lbl_title = tk.Label(
            header, text="", bg=ACCENT, fg="white",
            font=("Segoe UI", 16, "bold"),
        )
        self.lbl_title.pack(side="left", padx=8)

        # --- Форма добавления задачи ----------------------------------------
        form = tk.Frame(self, bg=BG_MAIN)
        form.pack(fill="x", padx=20, pady=(16, 8))

        self.entry = tk.Entry(
            form, font=("Segoe UI", 12), relief="flat",
            bg=BG_CARD, fg=TEXT_DARK, insertbackground=TEXT_DARK,
        )
        self.entry.pack(side="left", fill="x", expand=True, ipady=8, padx=(0, 8))
        self.entry.bind("<Return>", lambda e: self.add_task())

        self.placeholder = "Введите новую задачу…"
        self._show_placeholder()
        self.entry.bind("<FocusIn>", self._on_focus_in)
        self.entry.bind("<FocusOut>", self._on_focus_out)

        tk.Button(
            form, text="Добавить", command=self.add_task,
            bg=ACCENT, fg="white", activebackground=ACCENT_DARK,
            activeforeground="white", relief="flat",
            font=("Segoe UI", 11, "bold"), padx=18, pady=6, cursor="hand2",
        ).pack(side="right")

        # --- Список задач (скроллируемый) ------------------------------------
        list_wrap = tk.Frame(self, bg=BG_CARD, highlightthickness=1,
                             highlightcolor="#dcdde1", relief="flat")
        list_wrap.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        self.canvas = tk.Canvas(list_wrap, bg=BG_CARD, highlightthickness=0)
        vsb = tk.Scrollbar(list_wrap, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=BG_CARD)
        self.inner_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=vsb.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.inner.bind("<Configure>",
                        lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfigure(self.inner_id, width=e.width))
        # Прокрутка колесом мыши
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind_all("<Button-4>", self._on_mousewheel)
        self.canvas.bind_all("<Button-5>", self._on_mousewheel)

        self.lbl_empty = tk.Label(
            self, text="На этот день задач пока нет. Добавьте первую! 🎯",
            bg=BG_MAIN, fg=DONE_FG, font=("Segoe UI", 12, "italic"),
        )

        # Шрифты создаём один раз (повторное создание named-font вызывает ошибку Tcl)
        self.font_normal = tkfont.Font(name="TaskFontNormal", font=("Segoe UI", 12))
        self.font_done = tkfont.Font(name="TaskFontDone", font=("Segoe UI", 12),
                                     overstrike=1)

    # ---------- жизненный цикл экрана ----------
    def open_for(self, d: date) -> None:
        """Показать экран для указанной даты."""
        self.current_date = d
        self.lbl_title.config(
            text=f"{d.day} {MONTHS_RU[d.month - 1].lower()} {d.year} г."
        )
        self._render_tasks()

    def _on_mousewheel(self, event) -> None:
        if event.num == 5 or getattr(event, "delta", 0) < 0:
            self.canvas.yview_scroll(1, "units")
        elif event.num == 4 or getattr(event, "delta", 0) > 0:
            self.canvas.yview_scroll(-1, "units")

    # ---------- плейсхолдер поля ввода ----------
    def _show_placeholder(self) -> None:
        self.entry.delete(0, "end")
        self.entry.insert(0, self.placeholder)
        self.entry.config(fg=DONE_FG)

    def _on_focus_in(self, _e) -> None:
        if self.entry.get() == self.placeholder:
            self._show_placeholder()
            self.entry.config(fg=TEXT_DARK)

    def _on_focus_out(self, _e) -> None:
        if not self.entry.get().strip():
            self._show_placeholder()

    # ---------- действия с задачами ----------
    def add_task(self) -> None:
        if self.current_date is None:
            return
        text = self.entry.get().strip()
        if not text or text == self.placeholder:
            messagebox.showinfo("Пустая задача", "Введите текст задачи.", parent=self)
            return
        store = self.app.store
        store.add(self.current_date, text)
        self._show_placeholder()
        self.entry.config(fg=TEXT_DARK)
        self._render_tasks()
        self.app.refresh_calendar()

    def on_toggle(self, index: int) -> None:
        if self.current_date is None:
            return
        self.app.store.toggle(self.current_date, index)
        self._render_tasks()
        self.app.refresh_calendar()

    def on_delete(self, index: int) -> None:
        if self.current_date is None:
            return
        self.app.store.remove(self.current_date, index)
        self._render_tasks()
        self.app.refresh_calendar()

    # ---------- отрисовка списка ----------
    def _render_tasks(self) -> None:
        for w in self.inner.winfo_children():
            w.destroy()

        tasks = self.app.store.get(self.current_date) if self.current_date else []
        if not tasks:
            self.lbl_empty.pack(pady=20)
        else:
            self.lbl_empty.forget()

            for i, task in enumerate(tasks):
                row = tk.Frame(self.inner, bg=BG_CARD)
                row.pack(fill="x", padx=12, pady=4)

                var = tk.BooleanVar(value=bool(task.get("done", False)))
                chk = tk.Checkbutton(
                    row, variable=var, bg=BG_CARD, activebackground=BG_CARD,
                    command=lambda idx=i: self.on_toggle(idx), cursor="hand2",
                )
                chk.pack(side="left")

                lbl = tk.Label(
                    row, text=task.get("text", ""),
                    bg=BG_CARD, anchor="w", justify="left",
                    fg=DONE_FG if var.get() else TEXT_DARK,
                    font=self.font_done if var.get() else self.font_normal,
                )
                lbl.pack(side="left", fill="x", expand=True, padx=(4, 8))
                lbl.bind("<Button-1>", lambda e, idx=i: self.on_toggle(idx))

                tk.Button(
                    row, text="✕", command=lambda idx=i: self.on_delete(idx),
                    bg=BG_CARD, fg="#e74c3c", activeforeground="#c0392b",
                    relief="flat", font=("Segoe UI", 11, "bold"), cursor="hand2",
                ).pack(side="right")


class CalendarScreen(tk.Frame):
    """Экран месячного календаря."""

    def __init__(self, master, app: "CalendarApp"):
        super().__init__(master, bg=BG_MAIN)
        self.app = app
        self.year, self.month = app.view_year, app.view_month
        self.cells: dict[date, tk.Label] = {}

        # --- Шапка с навигацией ---------------------------------------------
        header = tk.Frame(self, bg=ACCENT, height=64)
        header.pack(fill="x")
        header.pack_propagate(False)

        nav = {"bg": ACCENT, "fg": "white", "activebackground": ACCENT_DARK,
               "activeforeground": "white", "relief": "flat",
               "font": ("Segoe UI", 12, "bold"), "cursor": "hand2", "width": 3}

        tk.Button(header, text="‹", command=lambda: self.step_month(-1), **nav)\
            .pack(side="left", padx=4, pady=10)
        tk.Button(header, text="›", command=lambda: self.step_month(1), **nav)\
            .pack(side="left", padx=4, pady=10)

        self.lbl_title = tk.Label(header, text="", bg=ACCENT, fg="white",
                                  font=("Segoe UI", 16, "bold"))
        self.lbl_title.pack(side="left", padx=12)

        tk.Button(header, text="Сегодня", command=self.go_today,
                  bg=ACCENT, fg="white", activebackground=ACCENT_DARK,
                  activeforeground="white", relief="flat",
                  font=("Segoe UI", 10, "bold"), cursor="hand2", padx=10)\
            .pack(side="right", padx=12, pady=10)

        # --- Сетка календаря --------------------------------------------------
        grid_frame = tk.Frame(self, bg=BG_MAIN)
        grid_frame.pack(fill="both", expand=True, padx=20, pady=20)
        self.grid_frame = grid_frame

        day_font = tkfont.Font(name="Segoe UI", size=11, weight="bold")
        for col, wd in enumerate(WEEKDAYS_RU):
            tk.Label(grid_frame, text=wd, bg=BG_MAIN, fg=ACCENT,
                     font=day_font).grid(row=0, column=col, sticky="ew", pady=(0, 6))

        self._build_grid()

    def _build_grid(self) -> None:
        # 6 строк недель x 7 столбцов
        for r in range(1, 7):
            self.grid_frame.rowconfigure(r, weight=1, uniform="row")
            for c in range(7):
                self.grid_frame.columnconfigure(c, weight=1, uniform="col")

    def step_month(self, delta: int) -> None:
        m = self.month - 1 + delta
        self.year += m // 12
        self.month = m % 12 + 1
        self.app.view_year, self.app.view_month = self.year, self.month
        self.render()

    def go_today(self) -> None:
        today = date.today()
        self.year, self.month = today.year, today.month
        self.app.view_year, self.app.view_month = self.year, self.month
        self.render()

    def render(self) -> None:
        """Перерисовать все ячейки текущего месяца."""
        self.year, self.month = self.app.view_year, self.app.view_month
        self.lbl_title.config(text=f"{MONTHS_RU[self.month - 1]} {self.year}")
        self.cells.clear()

        # Очистка старых ячеек
        for child in self.grid_frame.winfo_children():
            if hasattr(child, "_is_cell"):
                child.destroy()

        today = date.today()
        cal = calendar.Calendar(firstweekday=0)  # неделя с понедельника
        week_row = 1
        for week in cal.monthdatescalendar(self.year, self.month):
            for col, d in enumerate(week):
                cell = self._make_cell(d, in_month=(d.month == self.month),
                                       is_today=(d == today))
                cell.grid(row=week_row, column=col, sticky="nsew", padx=2, pady=2)
                self.cells[d] = cell
            week_row += 1

    def _make_cell(self, d: date, in_month: bool, is_today: bool) -> tk.Label:
        pending = self.app.store.count_pending(d)
        total = len(self.app.store.get(d))

        base = f"{d.day}"
        if in_month and total:
            base += f"\n• {pending} из {total}"

        bg = BG_CARD
        if is_today:
            bg = TODAY_BG
        fg = TEXT_DARK if in_month else OTHER_MONTH_FG

        label = tk.Label(
            self.grid_frame, text=base, bg=bg, fg=fg,
            font=("Segoe UI", 12, "bold" if is_today else "normal"),
            justify="left", anchor="nw", padx=8, pady=6, cursor="hand2",
            relief="solid", bd=1 if is_today else 0,
        )
        label._is_cell = True  # типизация для перерисовки

        label.bind("<Button-1>", lambda e, day=d: self.app.open_day(day))
        label.bind("<Enter>", lambda e, l=label, b=bg:
                   l.config(bg=self._hover(b)) if in_month else None)
        label.bind("<Leave>", lambda e, l=label, b=bg: l.config(bg=b))
        return label

    @staticmethod
    def _hover(bg: str) -> str:
        return HOVER_BG if bg == BG_CARD else bg


class CalendarApp(tk.Tk):
    """Главное окно: переключает экраны «Календарь» и «День»."""

    def __init__(self):
        super().__init__()
        self.title("📅 Календарь задач")
        self.geometry("860x620")
        self.minsize(700, 520)
        self.configure(bg=BG_MAIN)

        today = date.today()
        self.view_year, self.view_month = today.year, today.month
        self.store = TaskStore(tasks_file_path())

        container = tk.Frame(self, bg=BG_MAIN)
        container.pack(fill="both", expand=True)

        self.calendar_screen = CalendarScreen(container, self)
        self.day_screen = DayScreen(container, self)

        for screen in (self.calendar_screen, self.day_screen):
            screen.place(relx=0, rely=0, relwidth=1, relheight=1)

        self.show_calendar()

    # ---------- навигация между экранами ----------
    def show_calendar(self) -> None:
        self.refresh_calendar()
        self.calendar_screen.tkraise()

    def open_day(self, d: date) -> None:
        self.day_screen.open_for(d)
        self.day_screen.tkraise()
        self.day_screen.entry.focus_set()

    def refresh_calendar(self) -> None:
        self.calendar_screen.render()


if __name__ == "__main__":
    app = CalendarApp()
    app.mainloop()
