import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import tkinter.font as tkfont
import datetime
import re
import os
import matplotlib.dates as mdates

# --- Парсер лог-файла ---
def parse_log_file(filepath):
    encodings = ['utf-8', 'cp1251', 'latin1']
    content = None
    for enc in encodings:
        try:
            with open(filepath, encoding=enc) as f:
                content = f.readlines()
            break
        except Exception:
            continue
    if content is None:
        raise Exception("Не удалось прочитать файл в поддерживаемых кодировках.")

    date_start = None
    events = []
    date_re = re.compile(r'^Logging started (\d{4}-\d{2}-\d{2})')
    event_re = re.compile(
        r'^\[(\d{2}):(\d{2}):(\d{2})\] (.+?) increased by ([\d,]+) to ([\d,]+)'
    )

    for line in content:
        line = line.strip()
        m = date_re.match(line)
        if m:
            date_start = m.group(1)
            continue
        m = event_re.match(line)
        if m and date_start:
            h, mi, s = map(int, m.groups()[:3])
            skill = m.group(4)
            inc = float(m.group(5).replace(',', '.'))
            newval = float(m.group(6).replace(',', '.'))
            dt = datetime.datetime.strptime(
                f"{date_start} {h:02d}:{mi:02d}:{s:02d}", "%Y-%m-%d %H:%M:%S"
            )
            events.append({
                'datetime': dt,
                'skill': skill,
                'increase': inc,
                'new_value': newval
            })
    return events

# --- GUI ---
class SkillViewerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Wurm Online Skill Log Viewer")
        self.events = []
        self.filtered_events = []
        self.dates = []
        self.create_widgets()
        self.update_idletasks()
        self.minsize(self.winfo_width(), self.winfo_height())
        self.active_plots = []  # список: [{"win": ..., "params": {...}}, ...]
        self.update_always_on_top()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def create_widgets(self):
        # --- Первая строка: Кнопка выбора файла и дата , Отображать график---
        file_date_frame = tk.Frame(self)
        file_date_frame.pack(fill=tk.X, padx=5, pady=2)
        self.btn_open = tk.Button(file_date_frame, text="Выбрать лог-файл", command=self.open_file)
        self.btn_open.pack(side=tk.LEFT, padx=5)
        tk.Label(file_date_frame, text="Дата:").pack(side=tk.LEFT)
        self.date_var = tk.StringVar()
        self.date_menu = ttk.Combobox(file_date_frame, textvariable=self.date_var, state="readonly")
        self.date_menu.pack(side=tk.LEFT, padx=5)
        self.date_menu.bind("<<ComboboxSelected>>", self.on_date_selected)
        self.btn_plot = tk.Button(file_date_frame, text="Отображать график", command=self.show_skill_plot)
        self.btn_plot.pack(side=tk.RIGHT, padx=5)

        # --- Вторая строка: Сессия и время , Отображать поверх---
        session_time_frame = tk.Frame(self)
        session_time_frame.pack(fill=tk.X, padx=5, pady=2)

        tk.Label(session_time_frame, text="Сессия:").pack(side=tk.LEFT)
        self.sessions_combo = ttk.Combobox(session_time_frame, state="readonly", width=15)
        self.sessions_combo.pack(side=tk.LEFT, padx=2)
        self.sessions_combo.bind("<<ComboboxSelected>>", lambda e: [self.on_session_selected(), self.apply_filters()])

        tk.Label(session_time_frame, text="Время от:").pack(side=tk.LEFT, padx=(10, 0))
        self.time_from_var = tk.StringVar(value="00:00")
        self.time_from_entry = tk.Entry(session_time_frame, textvariable=self.time_from_var, width=5)
        self.time_from_entry.pack(side=tk.LEFT, padx=2)
        self.time_from_entry.bind("<KeyRelease>", self.on_time_entry)

        tk.Label(session_time_frame, text="до:").pack(side=tk.LEFT)
        self.time_to_var = tk.StringVar(value="23:59")
        self.time_to_entry = tk.Entry(session_time_frame, textvariable=self.time_to_var, width=5)
        self.time_to_entry.pack(side=tk.LEFT, padx=2)
        self.time_to_entry.bind("<KeyRelease>", self.on_time_entry)

        self.use_time_filter_var = tk.BooleanVar(value=False)
        self.cb_use_time_filter = tk.Checkbutton(
            session_time_frame, text="Фильтровать по времени",
            variable=self.use_time_filter_var, command=self.apply_filters
        )
        self.cb_use_time_filter.pack(side=tk.LEFT, padx=10)

        # --- Таблица ---
        columns = ("skill", "increase", "new_value")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", height=10)
        self.tree.heading("skill", text="Скилл", command=lambda: self.sort_column("skill", False))
        self.tree.heading("increase", text="Прирост", command=lambda: self.sort_column("increase", False))
        self.tree.heading("new_value", text="Итоговое значение", command=lambda: self.sort_column("new_value", False))
        self.tree.column("skill", width=200)
        self.tree.column("increase", width=100)
        self.tree.column("new_value", width=120)
        self.tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # --- Нижняя панель: чекбокс и версия в одной строке ---
        bottom_frame = tk.Frame(self)
        bottom_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=5, pady=(0, 5))

        self.always_on_top_var = tk.BooleanVar(value=True)
        self.cb_always_on_top = tk.Checkbutton(
            bottom_frame, text="Отображать поверх",
            variable=self.always_on_top_var, command=self.update_always_on_top
        )
        self.cb_always_on_top.pack(side=tk.LEFT)

        author_label = tk.Label(bottom_frame, text="By Vamashi v1.1", anchor="e")
        author_label.pack(side=tk.RIGHT)

    def open_file(self):
        filepath = filedialog.askopenfilename(
            title="Выберите лог-файл",
            filetypes=[("Log files", "*.txt *.log"), ("All files", "*.*")]
        )
        if not filepath:
            return
        try:
            self.events = parse_log_file(filepath)
            if not self.events:
                messagebox.showwarning("Внимание", "В файле не найдено событий.")
                return
            self.dates = sorted(list({e['datetime'].date() for e in self.events}), reverse=True)
            self.date_menu['values'] = [str(d) for d in self.dates]
            self.date_var.set(str(self.dates[0]))
            self.time_from_var.set("00:00")
            self.time_to_var.set("23:59")
            self.log_filepath = filepath
            self.log_last_mtime = os.path.getmtime(filepath)
            self.start_log_monitor()
            self.apply_filters()
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def start_log_monitor(self):
        self.after(1000, self.check_log_update)

    def check_log_update(self):
        if hasattr(self, 'log_filepath') and self.log_filepath:
            try:
                mtime = os.path.getmtime(self.log_filepath)
                if mtime != getattr(self, 'log_last_mtime', None):
                    self.log_last_mtime = mtime
                    self.events = parse_log_file(self.log_filepath)
                    self.apply_filters()  # <-- обновляет таблицу!
                if self.active_plots:
                    self.refresh_active_plot()
            except Exception:
                pass
        self.after(1000, self.check_log_update)

    def apply_filters(self):
        if not self.events:
            return
        date_str = self.date_var.get()
        try:
            date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        except Exception:
            return

        # Получаем выбранную сессию
        sessions = self.get_sessions_for_date(date)
        idx = self.sessions_combo.current()
        if not (0 <= idx < len(sessions)):
            self.filtered_events = []
            self.update_table()
            return
        session_start, session_end = sessions[idx]

        # Фильтрация по времени, если чекбокс включён
        if self.use_time_filter_var.get():
            t_from = self.time_from_var.get()
            t_to = self.time_to_var.get()
            try:
                t_from_dt = datetime.datetime.strptime(t_from, "%H:%M").time()
                t_to_dt = datetime.datetime.strptime(t_to, "%H:%M").time()
            except Exception:
                return
            self.filtered_events = [
                e for e in self.events
                if e['datetime'].date() == date
                and session_start <= e['datetime'].time() <= session_end
                and t_from_dt <= e['datetime'].time() <= t_to_dt
            ]
        else:
            # Без фильтра по времени — вся сессия
            self.filtered_events = [
                e for e in self.events
                if e['datetime'].date() == date
                and session_start <= e['datetime'].time() <= session_end
            ]
        self.update_table()

    def update_table(self):
        # Суммировать приросты по скиллам, взять последнее значение
        data = {}
        for e in self.filtered_events:
            skill = e['skill']
            if skill not in data:
                data[skill] = {'increase': 0.0, 'new_value': e['new_value']}
            data[skill]['increase'] += e['increase']
            data[skill]['new_value'] = e['new_value']
        # Очистить таблицу
        for row in self.tree.get_children():
            self.tree.delete(row)
        # Сортировать по приросту от большего к меньшему
        sorted_items = sorted(data.items(), key=lambda x: x[1]['increase'], reverse=True)
        # Добавить строки
        for skill, vals in sorted_items:
            self.tree.insert("", "end", values=(
                skill,
                f"{vals['increase']:.4f}".replace('.', ','),
                f"{vals['new_value']:.4f}".replace('.', ',')
            ))
        self.autosize_columns()
        # Автоматически менять высоту таблицы (от 10 до 30 строк)
        row_count = len(self.tree.get_children())
        tree_height = max(10, min(row_count, 30))
        self.tree.config(height=tree_height)
        self.update_idletasks()
        # --- Удалено управление размером окна ---
        
    def autosize_columns(self):
        font = tkfont.nametofont("TkDefaultFont")
        for col in self.tree["columns"]:
            max_width = font.measure(self.tree.heading(col)["text"])
            for item in self.tree.get_children():
                cell_val = str(self.tree.set(item, col))
                cell_width = font.measure(cell_val)
                if cell_width > max_width:
                    max_width = cell_width
            self.tree.column(col, width=max_width + 20)

    def sort_column(self, col, reverse):
        l = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        if col in ("increase", "new_value"):
            l.sort(key=lambda t: float(t[0].replace(',', '.')), reverse=reverse)
        else:
            l.sort(reverse=reverse)
        for index, (val, k) in enumerate(l):
            self.tree.move(k, '', index)
        self.tree.heading(col, command=lambda: self.sort_column(col, not reverse))

    def get_sessions_for_date(self, date, gap_minutes=30):
        events = [e for e in self.events if e['datetime'].date() == date]
        if not events:
            return []
        sessions = []
        session_start = events[0]['datetime'].time()
        last_time = events[0]['datetime']
        for e in events[1:]:
            delta = (e['datetime'] - last_time).total_seconds() / 60
            if delta > gap_minutes:
                sessions.append((session_start, last_time.time()))
                session_start = e['datetime'].time()
            last_time = e['datetime']
        sessions.append((session_start, last_time.time()))
        return sessions

    def on_date_selected(self, event=None):
        date_str = self.date_var.get()
        try:
            date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        except Exception:
            self.sessions_combo['values'] = []
            return
        sessions = self.get_sessions_for_date(date)
        session_labels = [f"{s[0].strftime('%H:%M')} - {s[1].strftime('%H:%M')}" for s in (sessions)]
        self.sessions_combo['values'] = session_labels
        if session_labels:
            self.sessions_combo.current(0)
            self.time_from_var.set(sessions[0][0].strftime('%H:%M'))
            self.time_to_var.set(sessions[0][1].strftime('%H:%M'))

    def on_session_selected(self, event=None):
        date_str = self.date_var.get()
        try:
            date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        except Exception:
            return
        sessions = self.get_sessions_for_date(date)
        idx = self.sessions_combo.current()
        if 0 <= idx < len(sessions):
            self.time_from_var.set(sessions[idx][0].strftime('%H:%M'))
            self.time_to_var.set(sessions[idx][1].strftime('%H:%M'))

    def on_time_entry(self, event):
        entry = event.widget
        value = entry.get().replace(":", "")
        if len(value) > 4:
            value = value[:4]
        if len(value) >= 3:
            value = value[:2] + ":" + value[2:]
        entry.delete(0, tk.END)
        entry.insert(0, value)
        if len(value) == 5:
            self.apply_filters()

    def show_skill_plot(self):
        import matplotlib.dates as mdates

        date_str = self.date_var.get()
        try:
            date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        except Exception:
            messagebox.showerror("Ошибка", "Некорректная дата.")
            return

        sessions = self.get_sessions_for_date(date)
        idx = self.sessions_combo.current()
        if not (0 <= idx < len(sessions)):
            messagebox.showerror("Ошибка", "Сессия не выбрана.")
            return
        session_start, session_end = sessions[idx]
        session_events = [
            e for e in self.events
            if e['datetime'].date() == date and session_start <= e['datetime'].time() <= session_end
        ]

        plot_win = tk.Toplevel(self)
        plot_win.title("График прироста скилла")
        if self.always_on_top_var.get():
            plot_win.attributes('-topmost', True)

        self.update_idletasks()
        main_x = self.winfo_rootx()
        main_y = self.winfo_rooty()
        main_w = self.winfo_width()
        plot_win.update_idletasks()
        new_x = main_x + main_w
        new_y = main_y - 30
        plot_win.geometry(f"+{new_x}+{new_y}")

        control_frame1 = tk.Frame(plot_win)
        control_frame1.pack(fill=tk.X, padx=10, pady=(8, 2))
        control_frame2 = tk.Frame(plot_win)
        control_frame2.pack(fill=tk.X, padx=10, pady=(2, 8))

        session_skills = sorted({e['skill'] for e in session_events})
        skill_var = tk.StringVar(value=session_skills[0] if session_skills else "")
        tk.Label(control_frame1, text="Скилл:").pack(side=tk.LEFT)
        skill_combo = ttk.Combobox(control_frame1, textvariable=skill_var, values=session_skills, state="readonly", width=20)
        skill_combo.pack(side=tk.LEFT, padx=2)

        tk.Label(control_frame1, text="Период (мин):").pack(side=tk.LEFT, padx=(10, 0))
        period_var = tk.StringVar(value="15")
        period_combo = ttk.Combobox(control_frame1, textvariable=period_var, values=["5", "10", "15", "20"], width=5, state="readonly")
        period_combo.pack(side=tk.LEFT)
        period_entry = tk.Entry(control_frame1, textvariable=period_var, width=5)
        period_entry.pack(side=tk.LEFT, padx=2)

        tk.Label(control_frame2, text="Макс. разрыв (мин):").pack(side=tk.LEFT)
        gap_var = tk.StringVar(value="1")
        gap_entry = tk.Entry(control_frame2, textvariable=gap_var, width=5)
        gap_entry.pack(side=tk.LEFT, padx=2)

        btn_analyze = tk.Button(control_frame2, text="Построить график")
        btn_analyze.pack(side=tk.LEFT, padx=10)

        def plot_action():
            skill = skill_var.get()
            try:
                period_min = int(period_var.get())
                gap_min = int(gap_var.get())
            except Exception:
                messagebox.showerror("Ошибка", "Некорректные параметры периода или разрыва.")
                return

            events = [e for e in session_events if e['skill'] == skill]
            if not events:
                messagebox.showinfo("Нет данных", "Нет данных по выбранному скиллу.")
                return

            events_sorted = sorted(events, key=lambda e: e['datetime'])
            session = []
            last_dt = None
            for e in reversed(events_sorted):
                if not session:
                    session.append(e)
                    last_dt = e['datetime']
                else:
                    delta = (last_dt - e['datetime']).total_seconds() / 60
                    if delta <= gap_min:
                        session.append(e)
                        last_dt = e['datetime']
                    else:
                        break
            session = list(reversed(session))
            if not session:
                messagebox.showinfo("Нет данных", "Нет подходящей сессии.")
                return

            end_time = session[-1]['datetime']
            start_time = end_time - datetime.timedelta(minutes=period_min)
            period_events = [e for e in session if e['datetime'] >= start_time]
            if len(period_events) < 2:
                messagebox.showinfo("Нет данных", "Недостаточно данных для построения графика.")
                return

            # --- Формируем summary для спойлера ---
            start_val = period_events[0]['new_value']
            end_val = period_events[-1]['new_value']
            start_time_str = period_events[0]['datetime'].strftime('%H:%M:%S')
            end_time_str = period_events[-1]['datetime'].strftime('%H:%M:%S')
            summary_text = (
                f"{start_time_str} - Скилл в начале: {start_val:.4f}\n"
                f"{end_time_str} - Скилл в конце : {end_val:.4f}"
            )

            # --- Окно графика ---
            graph_win = tk.Toplevel(self)
            graph_win.title(f"График прироста {skill}")
            if self.always_on_top_var.get():
                graph_win.attributes('-topmost', True)

            # --- Спойлер (collapsible frame) ---
            spoiler_frame = ttk.Frame(graph_win)
            spoiler_frame.pack(fill=tk.X, padx=10, pady=(10, 0))
            summary_label = tk.Label(spoiler_frame, text=summary_text, justify="left", font=("Consolas", 11))
            def toggle_summary():
                if summary_label.winfo_ismapped():
                    summary_label.pack_forget()
                    btn_spoiler.config(text="Показать детали")
                else:
                    summary_label.pack(fill=tk.X, padx=10, pady=5)
                    btn_spoiler.config(text="Скрыть детали")
            btn_spoiler = ttk.Button(spoiler_frame, text="Показать детали", command=toggle_summary)
            btn_spoiler.pack(anchor="w")
            # По умолчанию свернуто, не pack'аем summary_label

            # --- График ---
            times = [e['datetime'] for e in period_events]
            values = [e['new_value'] for e in period_events]
            gain_per_hour = []
            time_labels = []
            for i in range(1, len(times)):
                delta_skill = values[i] - values[i-1]
                delta_time = (times[i] - times[i-1]).total_seconds() / 3600
                if delta_time > 0:
                    gain_per_hour.append(delta_skill / delta_time)
                    time_labels.append(times[i])

            fig, ax = plt.subplots(figsize=(7, 4))
            ax.plot(time_labels, gain_per_hour, marker='o')
            ax.set_title(f"{skill}: прирост за час")
            ax.set_xlabel("Время")
            ax.set_ylabel("Gain per hour")
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
            fig.autofmt_xdate()

            canvas = FigureCanvasTkAgg(fig, master=graph_win)
            canvas.draw()
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

            # --- Позиционирование graph_win ---
            plot_win.update_idletasks()
            graph_win.update_idletasks()
            plot_x = plot_win.winfo_rootx()
            plot_y = plot_win.winfo_rooty()
            plot_h = plot_win.winfo_height()
            new_x = plot_x - 5
            new_y = plot_y + plot_h + 5
            graph_win.geometry(f"+{new_x}+{new_y}")

            # --- Сохраняем параметры для автообновления ---
            self.active_plots.append({
                "win": graph_win,
                "params": {
                    "skill": skill,
                    "period_min": period_min,
                    "gap_min": gap_min,
                    "plot_win": plot_win,
                    "fig": fig,
                    "ax": ax,
                    "canvas": canvas,
                    "summary_label": summary_label
                }
            })
            def on_close():
                self.active_plots = [p for p in self.active_plots if p["win"] != graph_win]
                graph_win.destroy()
            graph_win.protocol("WM_DELETE_WINDOW", on_close)
            
        btn_analyze.config(command=plot_action)

    def refresh_active_plot(self):

        for plot in self.active_plots[:]:
            graph_win = plot["win"]
            if not graph_win.winfo_exists():
                self.active_plots.remove(plot)
                continue
            params = plot["params"]
            skill = params["skill"]
            period_min = params["period_min"]
            gap_min = params["gap_min"]
            ax = params["ax"]
            canvas = params["canvas"]
            summary_label = params["summary_label"]

            # Пересобираем session_events из self.events (на случай новых данных)
            date_str = self.date_var.get()
            try:
                date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            except Exception:
                continue
            sessions = self.get_sessions_for_date(date)
            idx = self.sessions_combo.current()
            if not (0 <= idx < len(sessions)):
                continue
            session_start, session_end = sessions[idx]
            session_events = [
                e for e in self.events
                if e['datetime'].date() == date and session_start <= e['datetime'].time() <= session_end
            ]
            events = [e for e in session_events if e['skill'] == skill]
            if not events:
                continue

            events_sorted = sorted(events, key=lambda e: e['datetime'])
            session = []
            last_dt = None
            for e in reversed(events_sorted):
                if not session:
                    session.append(e)
                    last_dt = e['datetime']
                else:
                    delta = (last_dt - e['datetime']).total_seconds() / 60
                    if delta <= gap_min:
                        session.append(e)
                        last_dt = e['datetime']
                    else:
                        break
            session = list(reversed(session))
            if not session:
                continue

            end_time = session[-1]['datetime']
            start_time = end_time - datetime.timedelta(minutes=period_min)
            period_events = [e for e in session if e['datetime'] >= start_time]
            if len(period_events) < 2:
                continue

            times = [e['datetime'] for e in period_events]
            values = [e['new_value'] for e in period_events]
            gain_per_hour = []
            time_labels = []
            for i in range(1, len(times)):
                delta_skill = values[i] - values[i-1]
                delta_time = (times[i] - times[i-1]).total_seconds() / 3600
                if delta_time > 0:
                    gain_per_hour.append(delta_skill / delta_time)
                    time_labels.append(times[i])

            # --- Обновляем только содержимое графика ---
            ax.clear()
            ax.plot(time_labels, gain_per_hour, marker='o')
            ax.set_title(f"{skill}: прирост за час")
            ax.set_xlabel("Время")
            ax.set_ylabel("Gain per hour")
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
            ax.figure.autofmt_xdate()
            canvas.draw()

            start_val = period_events[0]['new_value']
            end_val = period_events[-1]['new_value']
            start_time_str = period_events[0]['datetime'].strftime('%H:%M:%S')
            end_time_str = period_events[-1]['datetime'].strftime('%H:%M:%S')
            summary_text = (
                f"Период: {start_time_str} - Скилл в начале: {start_val:.4f}\n"
                f"        {end_time_str}  - Скилл в конце: {end_val:.4f}"
            )
            summary_label.config(text=summary_text)

    def update_always_on_top(self):
        self.attributes('-topmost', self.always_on_top_var.get())

    def on_close(self):
        self.destroy()
        self.quit()

if __name__ == "__main__":
    app = SkillViewerApp()
    app.mainloop()