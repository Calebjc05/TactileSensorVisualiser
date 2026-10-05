
import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
import time
import csv
import serial
import serial.tools.list_ports
import numpy as np
import cv2
from tkinter import filedialog

APP_TITLE = "Tactile Visualiser"
MAX_ROWS = 32
MAX_COLS = 32
SIM_MAX_FORCE_N = 40.0
SATURATION_FORCE_N = 40.0

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")


class TactileVisualiserApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title(APP_TITLE)
        self.geometry("1420x880")
        self.minsize(1120, 730)

        # =====================================================
        # Sensor / simulation state
        # =====================================================
        self.rows = 16
        self.cols = 16

        # Keep simulated and live sensor data completely separate.
        # Simulation values are stored directly in newtons.
        self.sim_force_matrix = np.zeros((self.rows, self.cols), dtype=float)
        self.live_force_matrix = np.zeros((self.rows, self.cols), dtype=float)

        self.data_source = tk.StringVar(value="Simulation")
        self.live_sensor_connected = False

        self.raw_matrix = np.zeros((self.rows, self.cols), dtype=float)
        self.normalised_matrix = np.zeros((self.rows, self.cols), dtype=float)
        self.baseline = np.zeros((self.rows, self.cols), dtype=float)
        self.baseline_captured = False

        self.selected_row = 7
        self.selected_col = 7
        self.hover_row = None
        self.hover_col = None

        self.display_mode = tk.StringVar(value="normalised")
        self.mode_text = tk.StringVar(value="Simulation")
        self.connection_text = tk.StringVar(value="No hardware")
        self.fps_text = tk.StringVar(value="0.0 FPS")
        self.grid_text = tk.StringVar(value=f"{self.rows} × {self.cols}")
        self.appearance_mode = tk.StringVar(value="Light")
        self._apply_root_colours()
        self.hardware_detect_text = tk.StringVar(value="No hardware detected")
        self.detected_port = None

        self.last_frame_time = time.time()
        self.fps_smoothed = 0.0

        # =====================================================
        # Recording / playback state
        # =====================================================
        self.is_recording = False
        self.is_playing = False
        self.is_paused = False
        self.recording = []   # list of dict frames
        self.recording_source = "Simulation"
        self.record_start_time = None
        self.playback_index = 0
        self.playback_last_step = time.time()
        self.playback_speed = 1.0

        self.record_status_text = tk.StringVar(value="Idle")
        self.record_time_text = tk.StringVar(value="00:00.0")
        self.playback_position_text = tk.StringVar(value="No recording")

        # Rolling graph history. Each item stores the full matrix for the active source.
        self.live_history = []
        self.history_window_seconds = 10.0

        # Viridis lookup table
        values = np.arange(256, dtype=np.uint8).reshape(-1, 1)
        self.viridis_lut = cv2.applyColorMap(values, cv2.COLORMAP_VIRIDIS)[:, 0, :]

        self.current_page = "live"

        self._build_shell()
        self._show_live_page()
        self._update_loop()

    def _palette(self):
        """Return colours for the current appearance mode."""
        dark = self.appearance_mode.get() == "Dark"

        if dark:
            return {
                "window": "#0f1115",
                "shell": "#151922",
                "sidebar": "#121722",
                "page": "#0f1115",
                "card": "#181d27",
                "card_alt": "#202633",
                "text": "#f3f4f6",
                "muted": "#9ca3af",
                "border": "#2b3340",
                "canvas": "#0b1020",
                "button_soft": "#252c38",
                "button_soft_hover": "#303947",
                "danger_soft": "#3a1f24",
                "danger_soft_hover": "#4a272d",
            }

        return {
            "window": "#f3f6fa",
            "shell": "#f8fafc",
            "sidebar": "#f8fafc",
            "page": "#eef2f7",
            "card": "#ffffff",
            "card_alt": "#f8fafc",
            "text": "#0f172a",
            "muted": "#64748b",
            "border": "#cbd5e1",
            "canvas": "#0f172a",
            "button_soft": "#f1f5f9",
            "button_soft_hover": "#e2e8f0",
            "danger_soft": "#fee2e2",
            "danger_soft_hover": "#fecaca",
        }

    def _apply_root_colours(self):
        p = self._palette()
        self.configure(fg_color=p["window"])

    # =========================================================
    # SHELL
    # =========================================================
    def _build_shell(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(self, corner_radius=0, fg_color=self._palette()["shell"])
        top.grid(row=0, column=0, columnspan=2, sticky="ew")
        top.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            top,
            text="◌  Tactile Visualiser",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=self._palette()["text"],
        ).grid(row=0, column=0, padx=(18, 8), pady=14, sticky="w")

        ctk.CTkLabel(
            top,
            text="Multi-Axis Tactile Array Test Rig",
            font=ctk.CTkFont(size=14),
            text_color=self._palette()["muted"],
        ).grid(row=0, column=1, padx=8, sticky="w")

        status = ctk.CTkFrame(top, fg_color="transparent")
        status.grid(row=0, column=2, padx=18, sticky="e")

        ctk.CTkLabel(
            status, text="●", text_color="#22c55e",
            font=ctk.CTkFont(size=13)
        ).pack(side="left", padx=(0, 5))

        ctk.CTkLabel(status, textvariable=self.connection_text).pack(side="left", padx=(0, 16))
        ctk.CTkLabel(status, textvariable=self.mode_text, text_color="#2563eb").pack(side="left", padx=(0, 16))
        ctk.CTkLabel(status, textvariable=self.fps_text).pack(side="left")

        # Sidebar
        sidebar = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color=self._palette()["sidebar"])
        sidebar.grid(row=1, column=0, sticky="nsew")
        sidebar.grid_propagate(False)

        ctk.CTkLabel(
            sidebar, text="WORKSPACE",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=self._palette()["muted"]
        ).pack(anchor="w", padx=18, pady=(18, 8))

        self.live_btn = ctk.CTkButton(
            sidebar, text="Live View", anchor="w",
            command=self._show_live_page, height=42
        )
        self.live_btn.pack(fill="x", padx=12, pady=4)

        self.cal_btn = ctk.CTkButton(
            sidebar, text="Calibration", anchor="w",
            command=self._show_calibration_page, height=42,
            fg_color="transparent", text_color=self._palette()["text"],
            hover_color=self._palette()["button_soft_hover"],
        )
        self.cal_btn.pack(fill="x", padx=12, pady=4)

        self.health_btn = ctk.CTkButton(
            sidebar, text="Sensor Health", anchor="w",
            command=self._show_sensor_health_page, height=42,
            fg_color="transparent", text_color=self._palette()["text"],
            hover_color=self._palette()["button_soft_hover"],
        )
        self.health_btn.pack(fill="x", padx=12, pady=4)

        self.settings_btn = ctk.CTkButton(
            sidebar, text="Settings", anchor="w",
            command=self._show_settings_page, height=42,
            fg_color="transparent", text_color=self._palette()["text"],
            hover_color=self._palette()["button_soft_hover"],
        )
        self.settings_btn.pack(fill="x", padx=12, pady=4)

        ctk.CTkLabel(
            sidebar, text="SYSTEM",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=self._palette()["muted"]
        ).pack(anchor="w", padx=18, pady=(26, 8))

        system_card = ctk.CTkFrame(sidebar, fg_color=self._palette()["card"], corner_radius=12)
        system_card.pack(fill="x", padx=12)

        ctk.CTkLabel(
            system_card, text="●  System Status",
            text_color="#16a34a",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(anchor="w", padx=14, pady=(12, 2))

        ctk.CTkLabel(
            system_card, text="Simulation ready",
            text_color=self._palette()["muted"], font=ctk.CTkFont(size=12)
        ).pack(anchor="w", padx=14, pady=(0, 10))

        ctk.CTkLabel(
            system_card, text="Grid",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(anchor="w", padx=14)

        ctk.CTkLabel(
            system_card, textvariable=self.grid_text,
            text_color=self._palette()["muted"], font=ctk.CTkFont(size=11)
        ).pack(anchor="w", padx=14, pady=(1, 12))

        self.page_container = ctk.CTkFrame(self, fg_color=self._palette()["page"], corner_radius=0)
        self.page_container.grid(row=1, column=1, sticky="nsew")
        self.page_container.grid_columnconfigure(0, weight=1)
        self.page_container.grid_rowconfigure(0, weight=1)

    def _clear_page(self):
        for child in self.page_container.winfo_children():
            child.destroy()

    def _set_nav_state(self, page):
        self.current_page = page

        def style(btn, active):
            if active:
                btn.configure(fg_color="#2563eb", text_color="#ffffff", hover_color="#1d4ed8")
            else:
                btn.configure(fg_color="transparent", text_color=self._palette()["text"], hover_color=self._palette()["button_soft_hover"])

        style(self.live_btn, page == "live")
        style(self.cal_btn, page == "calibration")
        style(self.health_btn, page == "health")
        style(self.settings_btn, page == "settings")

    # =========================================================
    # LIVE PAGE
    # =========================================================
    def _show_live_page(self):
        self._clear_page()
        self._set_nav_state("live")

        page = ctk.CTkFrame(self.page_container, fg_color="transparent")
        page.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)
        page.grid_columnconfigure(0, weight=1)
        page.grid_columnconfigure(1, weight=0)
        page.grid_rowconfigure(0, weight=1)

        # -------------------------
        # Heatmap card
        # -------------------------
        heat_card = ctk.CTkFrame(page, fg_color=self._palette()["card"], corner_radius=14)
        heat_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        heat_card.grid_columnconfigure(0, weight=1)
        heat_card.grid_rowconfigure(1, weight=1)

        title_row = ctk.CTkFrame(heat_card, fg_color="transparent")
        title_row.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 10))
        title_row.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            title_row, text="Live Tactile Map",
            font=ctk.CTkFont(size=18, weight="bold")
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            title_row, text="SIMULATION",
            fg_color="#dbeafe", text_color="#1d4ed8",
            corner_radius=8, padx=10, pady=4,
            font=ctk.CTkFont(size=11, weight="bold")
        ).grid(row=0, column=1, padx=6)

        source_menu = ctk.CTkSegmentedButton(
            title_row,
            values=["Simulation", "Live Sensor"],
            command=self._change_data_source
        )
        source_menu.set(self.data_source.get())
        source_menu.grid(row=0, column=2, padx=(8, 8))

        display_menu = ctk.CTkSegmentedButton(
            title_row,
            values=["Normalised", "Raw"],
            command=self._change_display_mode
        )
        display_menu.set("Normalised" if self.display_mode.get() == "normalised" else "Raw")
        display_menu.grid(row=0, column=3, padx=(0, 0))

        self.heatmap_canvas = tk.Canvas(
            heat_card,
            bg=self._palette()["canvas"],
            highlightthickness=0,
            cursor="crosshair"
        )
        self.heatmap_canvas.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 10))

        self.heatmap_canvas.bind("<Motion>", self._on_heatmap_motion)
        self.heatmap_canvas.bind("<Leave>", self._on_heatmap_leave)
        self.heatmap_canvas.bind("<Button-1>", self._on_heatmap_click)
        self.heatmap_canvas.bind("<Button-2>", self._on_heatmap_middle_click)
        self.heatmap_canvas.bind("<Button-3>", self._on_heatmap_right_click)
        self.heatmap_canvas.bind("<MouseWheel>", self._on_mouse_wheel)
        self.heatmap_canvas.bind("<Button-4>", lambda e: self._adjust_hovered_force(+self.force_step.get()))
        self.heatmap_canvas.bind("<Button-5>", lambda e: self._adjust_hovered_force(-self.force_step.get()))
        self.heatmap_canvas.bind("<Configure>", lambda e: self._draw_heatmap())

        # Interaction hint
        footer = ctk.CTkFrame(heat_card, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 8))
        footer.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            footer,
            text="Simulation: hover + scroll = force (N)   •   Click = select   •   Right-click = clear",
            text_color=self._palette()["muted"],
            font=ctk.CTkFont(size=12)
        ).grid(row=0, column=0, sticky="w")

        self.hover_value_text = tk.StringVar(value="Hover: —")
        ctk.CTkLabel(
            footer,
            textvariable=self.hover_value_text,
            text_color="#2563eb",
            font=ctk.CTkFont(size=12, weight="bold")
        ).grid(row=0, column=2, sticky="e")

        # Recording / playback strip
        record_bar = ctk.CTkFrame(heat_card, fg_color=self._palette()["shell"], corner_radius=10)
        record_bar.grid(row=3, column=0, sticky="ew", padx=16, pady=(0, 14))
        record_bar.grid_columnconfigure(5, weight=1)

        self.record_button = ctk.CTkButton(
            record_bar,
            text="● Record",
            width=105,
            fg_color="#dc2626",
            hover_color="#b91c1c",
            command=self._toggle_recording
        )
        self.record_button.grid(row=0, column=0, padx=(10, 6), pady=10)

        self.play_button = ctk.CTkButton(
            record_bar,
            text="▶ Play",
            width=90,
            command=self._toggle_playback,
            fg_color="#16a34a",
            hover_color="#15803d"
        )
        self.play_button.grid(row=0, column=1, padx=6, pady=10)

        self.stop_button = ctk.CTkButton(
            record_bar,
            text="■ Stop",
            width=85,
            command=self._stop_recording_playback,
            fg_color="#64748b",
            hover_color="#475569"
        )
        self.stop_button.grid(row=0, column=2, padx=6, pady=10)

        self.export_button = ctk.CTkButton(
            record_bar,
            text="Export CSV",
            width=100,
            command=self._export_full_recording_csv,
            fg_color="#334155",
            hover_color="#1e293b"
        )
        self.export_button.grid(row=0, column=3, padx=6, pady=10)

        ctk.CTkLabel(
            record_bar,
            textvariable=self.record_time_text,
            font=ctk.CTkFont(size=13, weight="bold")
        ).grid(row=0, column=4, padx=(10, 6))

        self.timeline = ctk.CTkSlider(
            record_bar,
            from_=0,
            to=1,
            number_of_steps=1,
            command=self._on_timeline_changed
        )
        self.timeline.set(0)
        self.timeline.grid(row=0, column=5, sticky="ew", padx=10, pady=10)

        ctk.CTkLabel(
            record_bar,
            textvariable=self.playback_position_text,
            text_color=self._palette()["muted"],
            font=ctk.CTkFont(size=11)
        ).grid(row=0, column=6, padx=(4, 10))

        # -------------------------
        # Right column
        # -------------------------
        right = ctk.CTkFrame(page, fg_color="transparent", width=330)
        right.grid(row=0, column=1, sticky="ns")
        right.grid_propagate(False)

        self._build_selected_taxel_card(right)
        self._build_history_graph_card(right)
        self._build_simulation_controls_card(right)

    def _build_selected_taxel_card(self, parent):
        card = ctk.CTkFrame(parent, fg_color=self._palette()["card"], corner_radius=14)
        card.pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            card, text="Selected Taxel",
            font=ctk.CTkFont(size=17, weight="bold")
        ).pack(anchor="w", padx=16, pady=(14, 8))

        self.sel_position = tk.StringVar(value="Row 8, Column 8")
        self.sel_force = tk.StringVar(value="0.0 N")
        self.sel_raw = tk.StringVar(value="0.0")
        self.sel_norm = tk.StringVar(value="0.000")

        self._card_row(card, "Position", self.sel_position)
        self._card_row(card, "Force", self.sel_force, highlight=True)
        self._card_row(card, "Raw value", self.sel_raw)
        self._card_row(card, "Normalised", self.sel_norm)

        ctk.CTkLabel(
            card,
            text="Click a taxel to select it. Its history appears below.",
            justify="left",
            text_color=self._palette()["muted"],
            font=ctk.CTkFont(size=11)
        ).pack(anchor="w", padx=16, pady=(10, 14))

    def _build_history_graph_card(self, parent):
        card = ctk.CTkFrame(parent, fg_color=self._palette()["card"], corner_radius=14)
        card.pack(fill="x", pady=(0, 12))

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(14, 6))

        ctk.CTkLabel(
            top, text="Force History",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(side="left")

        self.graph_mode = tk.StringVar(value="Selected Taxel")
        graph_menu = ctk.CTkOptionMenu(
            top,
            width=145,
            values=["Selected Taxel", "Grid Average"],
            variable=self.graph_mode,
            command=self._on_graph_mode_changed
        )
        graph_menu.set("Selected Taxel")
        graph_menu.pack(side="right")

        self.graph_canvas = tk.Canvas(
            card,
            width=295,
            height=165,
            bg=self._palette()["card"],
            highlightthickness=0
        )
        self.graph_canvas.pack(fill="x", padx=12, pady=(0, 4))

        self.graph_caption = tk.StringVar(value="Live 10 s window")
        ctk.CTkLabel(
            card,
            textvariable=self.graph_caption,
            text_color=self._palette()["muted"],
            font=ctk.CTkFont(size=10)
        ).pack(anchor="w", padx=16, pady=(0, 12))

    def _build_simulation_controls_card(self, parent):
        card = ctk.CTkFrame(parent, fg_color=self._palette()["card"], corner_radius=14)
        card.pack(fill="x")

        ctk.CTkLabel(
            card, text="Simulation",
            font=ctk.CTkFont(size=17, weight="bold")
        ).pack(anchor="w", padx=16, pady=(14, 8))

        ctk.CTkLabel(
            card, text="Force step per scroll (N)",
            text_color=self._palette()["muted"],
            font=ctk.CTkFont(size=11)
        ).pack(anchor="w", padx=16)

        self.force_step = tk.DoubleVar(value=1.0)
        step_menu = ctk.CTkOptionMenu(
            card,
            values=["0.5", "1", "2", "5"],
            command=lambda v: self.force_step.set(float(v))
        )
        step_menu.set("1")
        step_menu.pack(fill="x", padx=16, pady=(4, 10))

        ctk.CTkButton(
            card,
            text="Clear Selected Taxel",
            command=self._clear_selected_taxel,
            fg_color=self._palette()["button_soft"],
            text_color=self._palette()["text"],
            hover_color=self._palette()["button_soft_hover"]
        ).pack(fill="x", padx=16, pady=4)

        ctk.CTkButton(
            card,
            text="Clear All Force",
            command=self._clear_all_force,
            fg_color=self._palette()["danger_soft"],
            text_color="#b91c1c",
            hover_color=self._palette()["danger_soft_hover"]
        ).pack(fill="x", padx=16, pady=(4, 14))

    def _card_row(self, card, label, variable, highlight=False):
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=16, pady=3)

        ctk.CTkLabel(
            row, text=label, text_color=self._palette()["muted"],
            font=ctk.CTkFont(size=12)
        ).pack(side="left")

        ctk.CTkLabel(
            row,
            textvariable=variable,
            text_color="#3b82f6" if highlight else self._palette()["text"],
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(side="right")

    # =========================================================
    # CALIBRATION PAGE
    # =========================================================
    def _show_calibration_page(self):
        self._clear_page()
        self._set_nav_state("calibration")

        page = ctk.CTkFrame(self.page_container, fg_color="transparent")
        page.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

        ctk.CTkLabel(
            page, text="Calibration",
            font=ctk.CTkFont(size=26, weight="bold")
        ).pack(anchor="w")

        ctk.CTkLabel(
            page,
            text="Capture a baseline and switch between raw and normalised values.",
            text_color=self._palette()["muted"]
        ).pack(anchor="w", pady=(4, 16))

        card = ctk.CTkFrame(page, fg_color=self._palette()["card"], corner_radius=14)
        card.pack(fill="x")

        self.calibration_status = tk.StringVar(value="No baseline captured")

        ctk.CTkLabel(
            card, textvariable=self.calibration_status,
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(anchor="w", padx=18, pady=(18, 12))

        buttons = ctk.CTkFrame(card, fg_color="transparent")
        buttons.pack(anchor="w", padx=18, pady=(0, 14))

        ctk.CTkButton(
            buttons, text="Capture Baseline",
            command=self._capture_baseline
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            buttons, text="Clear Baseline",
            command=self._clear_baseline,
            fg_color=self._palette()["button_soft"],
            text_color=self._palette()["text"],
            hover_color=self._palette()["button_soft_hover"]
        ).pack(side="left")

        ctk.CTkLabel(
            card,
            text="Tip: clear simulated forces before baseline capture.",
            text_color=self._palette()["muted"]
        ).pack(anchor="w", padx=18, pady=(0, 18))

    # =========================================================
    # SENSOR HEALTH PAGE
    # =========================================================
    def _show_sensor_health_page(self):
        self._clear_page()
        self._set_nav_state("health")

        page = ctk.CTkFrame(self.page_container, fg_color="transparent")
        page.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            page, text="Sensor Health",
            font=ctk.CTkFont(size=26, weight="bold")
        ).grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            page,
            text=(
                "Health monitoring is ready for live hardware. In simulation, "
                "taxels are treated as healthy unless they are saturated."
            ),
            text_color=self._palette()["muted"]
        ).grid(row=1, column=0, sticky="w", pady=(4, 16))

        content = ctk.CTkFrame(page, fg_color=self._palette()["card"], corner_radius=14)
        content.grid(row=2, column=0, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(1, weight=1)

        active_force = self._active_force_matrix()
        saturated_count = int(np.sum(active_force >= SATURATION_FORCE_N))
        total = self.rows * self.cols

        summary = ctk.CTkFrame(content, fg_color="transparent")
        summary.grid(row=0, column=0, sticky="ew", padx=18, pady=16)

        ctk.CTkLabel(
            summary,
            text=f"Taxels: {total}",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(side="left", padx=(0, 18))

        ctk.CTkLabel(
            summary,
            text=f"Saturated: {saturated_count}",
            text_color="#dc2626" if saturated_count else "#16a34a",
            font=ctk.CTkFont(size=14, weight="bold")
        ).pack(side="left")

        self.health_canvas = tk.Canvas(
            content,
            bg=self._palette()["card_alt"],
            highlightthickness=0
        )
        self.health_canvas.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 18))
        self.health_canvas.bind("<Configure>", lambda _e: self._draw_health_map())

        self._draw_health_map()

    def _draw_health_map(self):
        if not hasattr(self, "health_canvas") or not self.health_canvas.winfo_exists():
            return

        canvas = self.health_canvas
        canvas.delete("all")

        w = max(canvas.winfo_width(), 200)
        h = max(canvas.winfo_height(), 200)
        cell_w = w / self.cols
        cell_h = h / self.rows

        force = self._active_force_matrix()

        for r in range(self.rows):
            for c in range(self.cols):
                if force[r, c] >= SATURATION_FORCE_N:
                    fill = "#ef4444"       # saturated
                elif self.data_source.get() == "Live Sensor" and not self.live_sensor_connected:
                    fill = "#cbd5e1"       # no data
                else:
                    fill = "#22c55e"       # healthy / simulated healthy

                x0 = c * cell_w
                y0 = r * cell_h
                x1 = (c + 1) * cell_w
                y1 = (r + 1) * cell_h

                canvas.create_rectangle(
                    x0, y0, x1, y1,
                    fill=fill,
                    outline="#ffffff",
                    width=1
                )

    # =========================================================
    # SETTINGS PAGE
    # =========================================================
    def _show_settings_page(self):
        self._clear_page()
        self._set_nav_state("settings")

        page = ctk.CTkFrame(self.page_container, fg_color="transparent")
        page.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)

        ctk.CTkLabel(
            page, text="Settings",
            font=ctk.CTkFont(size=26, weight="bold")
        ).pack(anchor="w")

        ctk.CTkLabel(
            page,
            text="Configure the simulated tactile array.",
            text_color=self._palette()["muted"]
        ).pack(anchor="w", pady=(4, 16))

        card = ctk.CTkFrame(page, fg_color=self._palette()["card"], corner_radius=14)
        card.pack(fill="x")

        ctk.CTkLabel(
            card, text="Grid Size",
            font=ctk.CTkFont(size=17, weight="bold")
        ).pack(anchor="w", padx=18, pady=(16, 8))

        form = ctk.CTkFrame(card, fg_color="transparent")
        form.pack(anchor="w", padx=18, pady=(0, 14))

        ctk.CTkLabel(form, text="Rows").grid(row=0, column=0, padx=(0, 8))
        self.rows_entry = ctk.CTkEntry(form, width=90)
        self.rows_entry.insert(0, str(self.rows))
        self.rows_entry.grid(row=0, column=1, padx=(0, 18))

        ctk.CTkLabel(form, text="Columns").grid(row=0, column=2, padx=(0, 8))
        self.cols_entry = ctk.CTkEntry(form, width=90)
        self.cols_entry.insert(0, str(self.cols))
        self.cols_entry.grid(row=0, column=3, padx=(0, 18))

        ctk.CTkButton(
            form, text="Apply",
            command=self._apply_grid_size
        ).grid(row=0, column=4)

        ctk.CTkLabel(
            card,
            text="Each dimension can be 1–32, for example 5×20, 16×16, or 32×32.",
            text_color=self._palette()["muted"]
        ).pack(anchor="w", padx=18, pady=(0, 18))


        appearance_card = ctk.CTkFrame(page, fg_color=self._palette()["card"], corner_radius=14)
        appearance_card.pack(fill="x", pady=(14, 0))

        ctk.CTkLabel(
            appearance_card,
            text="Appearance",
            font=ctk.CTkFont(size=17, weight="bold")
        ).pack(anchor="w", padx=18, pady=(16, 6))

        ctk.CTkLabel(
            appearance_card,
            text="Switch between light and dark mode for the GUI.",
            text_color=self._palette()["muted"]
        ).pack(anchor="w", padx=18, pady=(0, 10))

        appearance_menu = ctk.CTkSegmentedButton(
            appearance_card,
            values=["Light", "Dark"],
            variable=self.appearance_mode,
            command=self._change_appearance_mode
        )
        appearance_menu.set(self.appearance_mode.get())
        appearance_menu.pack(anchor="w", padx=18, pady=(0, 18))


        detect_card = ctk.CTkFrame(page, fg_color=self._palette()["card"], corner_radius=14)
        detect_card.pack(fill="x", pady=(14, 0))

        ctk.CTkLabel(
            detect_card,
            text="Automatic Sensor Detection",
            font=ctk.CTkFont(size=17, weight="bold")
        ).pack(anchor="w", padx=18, pady=(16, 6))

        ctk.CTkLabel(
            detect_card,
            text=(
                "Scan connected USB/serial devices for a compatible tactile "
                "sensor controller and automatically configure the grid size."
            ),
            text_color=self._palette()["muted"],
            wraplength=720,
            justify="left"
        ).pack(anchor="w", padx=18, pady=(0, 10))

        ctk.CTkButton(
            detect_card,
            text="Detect Connected Grid",
            command=self._detect_connected_grid
        ).pack(anchor="w", padx=18, pady=(0, 10))

        ctk.CTkLabel(
            detect_card,
            textvariable=self.hardware_detect_text,
            text_color=self._palette()["muted"]
        ).pack(anchor="w", padx=18, pady=(0, 18))

    # =========================================================
    # HARDWARE DETECTION
    # =========================================================
    def _detect_connected_grid(self):
        """
        Scan likely USB serial devices for a future tactile-controller handshake.

        Expected future firmware reply:
            TACTILE,ROWS=16,COLS=16,MODEL=ViTac

        On systems with no tactile hardware connected, this safely returns
        "No sensor detected" without changing the current manual grid size.
        """
        self.hardware_detect_text.set("Scanning for tactile hardware...")
        self.update_idletasks()

        try:
            ports = list(serial.tools.list_ports.comports())
        except Exception:
            self.live_sensor_connected = False
            self.detected_port = None
            self.hardware_detect_text.set("No sensor detected")
            return

        # Avoid probing macOS Bluetooth/debug/pseudo serial ports.
        candidates = []
        for p in ports:
            device = (p.device or "").lower()
            description = (p.description or "").lower()
            manufacturer = (p.manufacturer or "").lower()

            looks_usb = (
                p.vid is not None
                or "usb" in device
                or "usb" in description
                or "arduino" in description
                or "wch" in manufacturer
                or "ftdi" in manufacturer
            )

            if looks_usb:
                candidates.append(p)

        if not candidates:
            self.live_sensor_connected = False
            self.detected_port = None
            self.hardware_detect_text.set("No sensor detected")
            if self.data_source.get() == "Live Sensor":
                self.connection_text.set("No sensor detected")
            return

        for port_info in candidates:
            port_name = port_info.device

            try:
                with serial.Serial(
                    port_name,
                    baudrate=115200,
                    timeout=0.25,
                    write_timeout=0.25
                ) as ser:
                    try:
                        ser.reset_input_buffer()
                    except Exception:
                        pass

                    ser.write(b"IDENTIFY\n")
                    ser.flush()
                    reply = ser.readline().decode(
                        "utf-8", errors="ignore"
                    ).strip()

                parsed = self._parse_hardware_identity(reply)

                if parsed is None:
                    continue

                rows, cols, model = parsed

                if not (1 <= rows <= MAX_ROWS and 1 <= cols <= MAX_COLS):
                    continue

                self.detected_port = port_name
                self.live_sensor_connected = True
                self.hardware_detect_text.set(
                    f"Detected {model}: {rows} × {cols} on {port_name}"
                )

                if self.data_source.get() == "Live Sensor":
                    self.connection_text.set(f"Connected: {port_name}")
                    self.mode_text.set("Live Sensor")

                self._set_grid_size(rows, cols)

                messagebox.showinfo(
                    "Sensor Detected",
                    f"{model}\nGrid: {rows} × {cols}\nPort: {port_name}"
                )
                return

            except Exception:
                # Unknown/busy/non-compatible serial devices are simply ignored.
                continue

        self.detected_port = None
        self.live_sensor_connected = False
        self.hardware_detect_text.set("No compatible tactile sensor detected")

        if self.data_source.get() == "Live Sensor":
            self.connection_text.set("No sensor detected")
            self.mode_text.set("Live Sensor")

    def _parse_hardware_identity(self, reply):
        """
        Parse a future firmware response such as:
            TACTILE,ROWS=16,COLS=16,MODEL=ViTac

        Returns:
            (rows, cols, model) or None
        """
        if not reply:
            return None

        upper = reply.upper()
        if "TACTILE" not in upper:
            return None

        rows = None
        cols = None
        model = "Tactile Sensor"

        parts = [part.strip() for part in reply.split(",")]

        for part in parts:
            if "=" not in part:
                continue

            key, value = part.split("=", 1)
            key = key.strip().upper()
            value = value.strip()

            if key == "ROWS":
                try:
                    rows = int(value)
                except ValueError:
                    return None

            elif key == "COLS":
                try:
                    cols = int(value)
                except ValueError:
                    return None

            elif key == "MODEL":
                model = value or model

        if rows is None or cols is None:
            return None

        return rows, cols, model

    def _set_grid_size(self, rows, cols):
        """
        Shared grid-resize helper used by both manual settings and
        future automatic hardware detection.
        """
        self._stop_recording_playback()

        self.rows = rows
        self.cols = cols

        self.sim_force_matrix = np.zeros((rows, cols), dtype=float)
        self.live_force_matrix = np.zeros((rows, cols), dtype=float)
        self.raw_matrix = np.zeros((rows, cols), dtype=float)
        self.normalised_matrix = np.zeros((rows, cols), dtype=float)
        self.baseline = np.zeros((rows, cols), dtype=float)

        self.selected_row = min(self.selected_row, rows - 1)
        self.selected_col = min(self.selected_col, cols - 1)

        self.hover_row = None
        self.hover_col = None

        self.recording = []
        self.live_history = []

        self.grid_text.set(f"{rows} × {cols}")
        self.baseline_captured = False

    def _change_appearance_mode(self, value):
        self.appearance_mode.set(value)
        ctk.set_appearance_mode(value.lower())

        # Apply colours to the root, then rebuild the shell so all hard-coded
        # cards, sidebars and canvases switch with the selected theme.
        self._apply_root_colours()

        current = self.current_page

        # Rebuild the complete shell rather than only the current page.
        for child in self.winfo_children():
            child.destroy()

        self._build_shell()

        if current == "live":
            self._show_live_page()
        elif current == "calibration":
            self._show_calibration_page()
        elif current == "health":
            self._show_sensor_health_page()
        else:
            self._show_settings_page()

    # =========================================================
    # INTERACTION
    # =========================================================
    def _change_data_source(self, value):
        # Stop recording/playback before switching so datasets never mix sources.
        self._stop_recording_playback()

        self.data_source.set(value)
        self.live_history = []

        if value == "Simulation":
            self.mode_text.set("Simulation")
            self.connection_text.set("Simulation")
        else:
            self.mode_text.set("Live Sensor")
            if self.live_sensor_connected:
                self.connection_text.set(
                    f"Connected: {self.detected_port}"
                    if self.detected_port else "Sensor connected"
                )
            else:
                self.connection_text.set("No sensor detected")

        self._update_selected_taxel_info()
        self._draw_heatmap()

    def _change_display_mode(self, value):
        self.display_mode.set("normalised" if value == "Normalised" else "raw")
        self._draw_heatmap()

    def _event_to_cell(self, event):
        if not hasattr(self, "heatmap_canvas"):
            return None, None

        w = max(self.heatmap_canvas.winfo_width(), 1)
        h = max(self.heatmap_canvas.winfo_height(), 1)

        margin_left = 38
        margin_bottom = 28
        margin_top = 10
        margin_right = 10

        draw_w = w - margin_left - margin_right
        draw_h = h - margin_top - margin_bottom

        lx = event.x - margin_left
        ly = event.y - margin_top

        if draw_w <= 0 or draw_h <= 0:
            return None, None

        if not (0 <= lx < draw_w and 0 <= ly < draw_h):
            return None, None

        col = int(lx / (draw_w / self.cols))
        row = int(ly / (draw_h / self.rows))

        return int(np.clip(row, 0, self.rows - 1)), int(np.clip(col, 0, self.cols - 1))

    def _on_heatmap_motion(self, event):
        row, col = self._event_to_cell(event)
        self.hover_row, self.hover_col = row, col

        if row is None:
            self.hover_value_text.set("Hover: —")
        else:
            active_force = self._active_force_matrix()
            self.hover_value_text.set(
                f"Hover: R{row+1}, C{col+1}  |  Force {active_force[row, col]:.1f} N"
            )
        self._draw_heatmap()

    def _on_heatmap_leave(self, _event):
        self.hover_row = None
        self.hover_col = None
        self.hover_value_text.set("Hover: —")
        self._draw_heatmap()

    def _on_heatmap_click(self, event):
        row, col = self._event_to_cell(event)
        if row is None:
            return
        self.selected_row = row
        self.selected_col = col
        self._update_selected_taxel_info()
        self._draw_heatmap()
        self._draw_history_graph()

    def _on_heatmap_right_click(self, event):
        row, col = self._event_to_cell(event)
        if row is None or self.is_playing or self.data_source.get() != "Simulation":
            return
        self.sim_force_matrix[row, col] = 0.0

    def _on_heatmap_middle_click(self, event):
        self._on_heatmap_right_click(event)

    def _on_mouse_wheel(self, event):
        if self.is_playing or self.data_source.get() != "Simulation":
            return "break"
        if self.hover_row is None or self.hover_col is None:
            return "break"

        if event.delta > 0:
            direction = 1
        elif event.delta < 0:
            direction = -1
        else:
            return "break"

        self._adjust_hovered_force(direction * self.force_step.get())
        return "break"

    def _adjust_hovered_force(self, delta):
        if self.is_playing:
            return
        if self.hover_row is None or self.hover_col is None:
            return

        r, c = self.hover_row, self.hover_col
        self.sim_force_matrix[r, c] = np.clip(
            self.sim_force_matrix[r, c] + delta,
            0.0,
            SIM_MAX_FORCE_N
        )

        if r == self.selected_row and c == self.selected_col:
            self._update_selected_taxel_info()

        self.hover_value_text.set(
            f"Hover: R{r+1}, C{c+1}  |  Force {self.sim_force_matrix[r, c]:.1f} N"
        )

    def _clear_selected_taxel(self):
        if not self.is_playing and self.data_source.get() == "Simulation":
            self.sim_force_matrix[self.selected_row, self.selected_col] = 0.0

    def _clear_all_force(self):
        if not self.is_playing and self.data_source.get() == "Simulation":
            self.sim_force_matrix.fill(0.0)

    def _active_force_matrix(self):
        if self.data_source.get() == "Live Sensor":
            return self.live_force_matrix
        return self.sim_force_matrix

    def _widget_exists(self, widget):
        """Return True only if a Tk/CustomTkinter widget still exists."""
        if widget is None:
            return False
        try:
            return bool(widget.winfo_exists())
        except (tk.TclError, AttributeError):
            return False

    # =========================================================
    # RECORDING / PLAYBACK
    # =========================================================
    def _toggle_recording(self):
        if self.is_playing:
            self._stop_playback()

        if not self.is_recording:
            self.recording = []
            self.recording_source = self.data_source.get()
            self.record_start_time = time.time()
            self.is_recording = True
            self.record_status_text.set("Recording")
            self.record_button.configure(text="■ Stop Rec", fg_color="#991b1b")

            # Prevent exporting an incomplete recording.
            if self._widget_exists(getattr(self, "export_button", None)):
                self.export_button.configure(
                    state="disabled",
                    fg_color="#cbd5e1",
                    text_color=self._palette()["muted"]
                )

            self.playback_position_text.set("Recording…")
        else:
            self._stop_recording()

    def _stop_recording(self):
        if not self.is_recording:
            return
        self.is_recording = False
        if self._widget_exists(getattr(self, "record_button", None)):
            self.record_button.configure(text="● Record", fg_color="#dc2626")

        # Recording is complete, so exporting is safe again.
        if self._widget_exists(getattr(self, "export_button", None)):
            self.export_button.configure(
                state="normal",
                fg_color="#334155",
                text_color="#ffffff"
            )

        if self.recording:
            duration = self.recording[-1]["t"]
            self.playback_position_text.set(
                f"{len(self.recording)} frames • {duration:.1f} s"
            )
            if self._widget_exists(getattr(self, "timeline", None)):
                self.timeline.configure(
                    from_=0,
                    to=max(len(self.recording) - 1, 1),
                    number_of_steps=max(len(self.recording) - 1, 1)
                )
                self.timeline.set(0)
            self.playback_index = 0
        else:
            self.playback_position_text.set("No recording")

    def _toggle_playback(self):
        if not self.recording:
            messagebox.showinfo("Playback", "Record some simulated data first.")
            return

        if self.is_recording:
            self._stop_recording()

        if not self.is_playing:
            self.is_playing = True
            self.is_paused = False
            self.play_button.configure(text="❚❚ Pause", fg_color="#d97706", hover_color="#b45309")
            self.mode_text.set("Playback")
            self.playback_last_step = time.time()

            if self.playback_index >= len(self.recording) - 1:
                self.playback_index = 0
        else:
            # Toggle pause/resume
            self.is_paused = not self.is_paused
            if self.is_paused:
                self.play_button.configure(text="▶ Resume", fg_color="#16a34a", hover_color="#15803d")
            else:
                self.play_button.configure(text="❚❚ Pause", fg_color="#d97706", hover_color="#b45309")
                self.playback_last_step = time.time()

    def _stop_playback(self):
        self.is_playing = False
        self.is_paused = False
        self.mode_text.set("Simulation")
        if self._widget_exists(getattr(self, "play_button", None)):
            self.play_button.configure(
                text="▶ Play",
                fg_color="#16a34a",
                hover_color="#15803d"
            )

    def _stop_recording_playback(self):
        self._stop_recording()
        self._stop_playback()

    def _record_current_frame(self):
        if not self.is_recording:
            return

        t = time.time() - self.record_start_time
        self.recording.append({
            "t": t,
            "force": self._active_force_matrix().copy(),
            "raw": self.raw_matrix.copy(),
            "norm": self.normalised_matrix.copy(),
        })
        self.record_time_text.set(self._format_time(t))

    def _advance_playback(self):
        if not self.is_playing or self.is_paused or not self.recording:
            return

        now = time.time()
        frame_interval = 1.0 / 30.0 / self.playback_speed

        if now - self.playback_last_step < frame_interval:
            return

        self.playback_last_step = now

        self.playback_index += 1
        if self.playback_index >= len(self.recording):
            self.playback_index = len(self.recording) - 1
            self._stop_playback()
            return

        self._apply_recorded_frame(self.playback_index)

    def _apply_recorded_frame(self, index):
        if not self.recording:
            return

        index = int(np.clip(index, 0, len(self.recording) - 1))
        self.playback_index = index
        frame = self.recording[index]

        if self.recording_source == "Live Sensor":
            self.live_force_matrix = frame["force"].copy()
        else:
            self.sim_force_matrix = frame["force"].copy()

        self.raw_matrix = frame["raw"].copy()
        self.normalised_matrix = frame["norm"].copy()

        if self._widget_exists(getattr(self, "timeline", None)):
            self.timeline.set(index)

        self.record_time_text.set(self._format_time(frame["t"]))
        self.playback_position_text.set(
            f"Frame {index + 1}/{len(self.recording)}"
        )

    def _on_timeline_changed(self, value):
        if not self.recording:
            return
        index = int(round(float(value)))
        self._apply_recorded_frame(index)

    @staticmethod
    def _format_time(seconds):
        mins = int(seconds // 60)
        secs = seconds % 60
        return f"{mins:02d}:{secs:04.1f}"

    def _export_full_recording_csv(self):
        if self.is_recording:
            messagebox.showinfo(
                "Export CSV",
                "Stop the current recording before exporting."
            )
            return

        if not self.recording:
            messagebox.showinfo(
                "Export CSV",
                "There is no recording to export yet."
            )
            return

        path = filedialog.asksaveasfilename(
            title="Export CSV",
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile="tactile_recording.csv"
        )
        if not path:
            return

        with open(path, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow([
                "time_s",
                "source",
                "row",
                "column",
                "force_N",
                "raw_value",
                "normalised_value"
            ])

            for frame in self.recording:
                t = float(frame["t"])
                force = frame["force"]
                raw = frame["raw"]
                norm = frame["norm"]

                for r in range(self.rows):
                    for c in range(self.cols):
                        writer.writerow([
                            f"{t:.3f}",
                            self.recording_source,
                            r + 1,
                            c + 1,
                            f"{float(force[r, c]):.3f}",
                            f"{float(raw[r, c]):.3f}",
                            f"{float(norm[r, c]):.6f}"
                        ])

        messagebox.showinfo(
            "Export Complete",
            f"Full recording exported successfully:\n{path}"
        )

    # =========================================================
    # SIMULATION
    # =========================================================
    def _generate_raw_matrix(self):
        # Live Sensor mode intentionally does not accept simulated edits.
        # Until the real streaming protocol exists, it displays zeros when
        # no sensor is connected, preserving a clean separation from simulation.
        if self.data_source.get() == "Live Sensor":
            if not self.live_sensor_connected:
                self.live_force_matrix.fill(0.0)
                return np.zeros((self.rows, self.cols), dtype=float)

            # Placeholder for future hardware streaming:
            # self.live_force_matrix should be populated directly from the
            # interface/DAQ in newtons.
            return np.clip(
                (self.live_force_matrix / SATURATION_FORCE_N) * 1000.0,
                0.0,
                1000.0
            )

        yy, xx = np.mgrid[0:self.rows, 0:self.cols]
        result = np.zeros((self.rows, self.cols), dtype=float)

        active = np.argwhere(self.sim_force_matrix > 0)

        for r, c in active:
            force_n = float(self.sim_force_matrix[r, c])
            force_ratio = np.clip(force_n / SIM_MAX_FORCE_N, 0.0, 1.0)

            # Higher force gives a slightly wider contact footprint.
            spread = 1.0 + 4.0 * force_ratio

            gaussian = np.exp(
                -(
                    (xx - c) ** 2
                    + (yy - r) ** 2
                ) / spread
            )

            peak_raw = 1000.0 * force_ratio
            result += gaussian * peak_raw

        return np.clip(result, 0.0, 1000.0)

    def _calculate_normalised_matrix(self):
        corrected = np.clip(self.raw_matrix - self.baseline, 0.0, None)

        max_val = np.max(corrected)
        if max_val <= 0:
            return np.zeros_like(corrected)

        return corrected / max_val

    # =========================================================
    # GRAPH
    # =========================================================
    def _update_live_history(self):
        now = time.time()

        # Store complete matrix snapshots, not only the currently selected taxel.
        # This means changing selection later still shows the correct historical
        # values for the newly selected taxel.
        self.live_history.append({
            "t": now,
            "force": self._active_force_matrix().copy(),
            "norm": self.normalised_matrix.copy(),
        })

        cutoff = now - self.history_window_seconds
        self.live_history = [
            frame for frame in self.live_history
            if frame["t"] >= cutoff
        ]

    def _on_graph_mode_changed(self, value):
        self.graph_mode.set(value)
        self._draw_history_graph()

    def _get_graph_series(self):
        """
        Return force history in newtons.

        Selected Taxel:
            Shows the force history of the currently selected taxel.

        Grid Average:
            Shows the arithmetic mean force across every taxel in the grid
            for each live or recorded frame.
        """
        mode = (
            self.graph_mode.get()
            if hasattr(self, "graph_mode")
            else "Selected Taxel"
        )

        # Playback: use the full recorded session.
        if self.is_playing and self.recording:
            xs = [frame["t"] for frame in self.recording]

            if mode == "Grid Average":
                ys = [
                    float(np.mean(frame["force"]))
                    for frame in self.recording
                ]
                label = "Average force (N)"
                self.graph_caption.set(
                    "Recorded session • whole-grid average"
                )
            else:
                ys = [
                    float(
                        frame["force"][
                            self.selected_row,
                            self.selected_col
                        ]
                    )
                    for frame in self.recording
                ]
                label = "Force (N)"
                self.graph_caption.set(
                    f"Recorded session • R{self.selected_row + 1}, "
                    f"C{self.selected_col + 1}"
                )

            return xs, ys, SATURATION_FORCE_N, label

        # Live mode: each history frame contains the complete force matrix.
        if not self.live_history:
            return [], [], SATURATION_FORCE_N, "Force (N)"

        t0 = self.live_history[0]["t"]
        xs = [
            frame["t"] - t0
            for frame in self.live_history
        ]

        if mode == "Grid Average":
            ys = [
                float(np.mean(frame["force"]))
                for frame in self.live_history
            ]
            label = "Average force (N)"
            self.graph_caption.set(
                "Live 10 s window • whole-grid average"
            )
        else:
            ys = [
                float(
                    frame["force"][
                        self.selected_row,
                        self.selected_col
                    ]
                )
                for frame in self.live_history
            ]
            label = "Force (N)"
            self.graph_caption.set(
                f"Live 10 s window • R{self.selected_row + 1}, "
                f"C{self.selected_col + 1}"
            )

        return xs, ys, SATURATION_FORCE_N, label

    def _draw_history_graph(self):
        if not hasattr(self, "graph_canvas") or not self.graph_canvas.winfo_exists():
            return

        canvas = self.graph_canvas
        canvas.delete("all")

        w = max(canvas.winfo_width(), 280)
        h = max(canvas.winfo_height(), 160)

        left = 42
        right = 10
        top = 12
        bottom = 28

        plot_w = max(w - left - right, 1)
        plot_h = max(h - top - bottom, 1)

        # Grid/background
        p = self._palette()
        canvas.configure(bg=p["card"])

        canvas.create_rectangle(
            left, top, left + plot_w, top + plot_h,
            outline=p["border"], fill=p["card"]
        )

        for i in range(1, 4):
            y = top + plot_h * i / 4
            canvas.create_line(
                left, y, left + plot_w, y,
                fill=self._palette()["border"]
            )

        xs, ys, y_max, y_label = self._get_graph_series()

        canvas.create_text(
            8, top + plot_h / 2,
            text=y_label,
            angle=90,
            anchor="w",
            fill=self._palette()["muted"],
            font=("Arial", 9)
        )

        canvas.create_text(
            left + plot_w / 2, h - 4,
            text="Time (s)",
            anchor="s",
            fill=self._palette()["muted"],
            font=("Arial", 9)
        )

        canvas.create_text(
            left - 5, top,
            text=f"{y_max:g}",
            anchor="e",
            fill=self._palette()["muted"],
            font=("Arial", 8)
        )
        canvas.create_text(
            left - 5, top + plot_h,
            text="0",
            anchor="e",
            fill=self._palette()["muted"],
            font=("Arial", 8)
        )

        if len(xs) < 2:
            canvas.create_text(
                left + plot_w / 2,
                top + plot_h / 2,
                text="No history yet",
                fill=self._palette()["muted"],
                font=("Arial", 10)
            )
            return

        x_min = min(xs)
        x_max = max(xs)
        if x_max <= x_min:
            x_max = x_min + 1.0

        points = []
        for x, y in zip(xs, ys):
            px = left + (x - x_min) / (x_max - x_min) * plot_w
            py = top + plot_h - np.clip(y / y_max, 0, 1) * plot_h
            points.extend([px, py])

        canvas.create_line(
            *points,
            fill="#2563eb",
            width=2,
            smooth=False
        )

        # Playback marker
        if self.is_playing and self.recording:
            current_t = self.recording[self.playback_index]["t"]
            marker_x = left + (current_t - x_min) / (x_max - x_min) * plot_w
            canvas.create_line(
                marker_x, top,
                marker_x, top + plot_h,
                fill="#dc2626",
                width=2
            )

    # =========================================================
    # HEATMAP
    # =========================================================
    def _draw_heatmap(self):
        if not hasattr(self, "heatmap_canvas") or not self.heatmap_canvas.winfo_exists():
            return

        canvas = self.heatmap_canvas
        canvas.delete("all")

        w = max(canvas.winfo_width(), 100)
        h = max(canvas.winfo_height(), 100)

        margin_left = 38
        margin_bottom = 28
        margin_top = 10
        margin_right = 10

        draw_w = max(w - margin_left - margin_right, 1)
        draw_h = max(h - margin_top - margin_bottom, 1)

        cell_w = draw_w / self.cols
        cell_h = draw_h / self.rows

        if self.display_mode.get() == "raw":
            scaled = np.clip(self.raw_matrix / 1000.0, 0.0, 1.0)
        else:
            scaled = np.clip(self.normalised_matrix, 0.0, 1.0)

        for r in range(self.rows):
            for c in range(self.cols):
                val = float(scaled[r, c])
                idx = int(np.clip(val * 255, 0, 255))
                b, g, rr = self.viridis_lut[idx]
                colour = f"#{rr:02x}{g:02x}{b:02x}"

                x0 = margin_left + c * cell_w
                y0 = margin_top + r * cell_h
                x1 = margin_left + (c + 1) * cell_w
                y1 = margin_top + (r + 1) * cell_h

                selected = (r == self.selected_row and c == self.selected_col)
                hovered = (r == self.hover_row and c == self.hover_col)

                if selected:
                    outline = "#ffffff"
                    width = 3
                elif hovered:
                    outline = "#38bdf8"
                    width = 2
                else:
                    outline = "#334155"
                    width = 1

                canvas.create_rectangle(
                    x0, y0, x1, y1,
                    fill=colour,
                    outline=outline,
                    width=width
                )

        row_step = 1 if self.rows <= 16 else 2 if self.rows <= 24 else 4
        col_step = 1 if self.cols <= 16 else 2 if self.cols <= 24 else 4

        for r in range(0, self.rows, row_step):
            y = margin_top + (r + 0.5) * cell_h
            canvas.create_text(
                margin_left - 8, y,
                text=str(r + 1),
                fill=self._palette()["border"],
                anchor="e",
                font=("Arial", 9)
            )

        for c in range(0, self.cols, col_step):
            x = margin_left + (c + 0.5) * cell_w
            canvas.create_text(
                x, margin_top + draw_h + 7,
                text=str(c + 1),
                fill=self._palette()["border"],
                anchor="n",
                font=("Arial", 9)
            )

    # =========================================================
    # CALIBRATION / SETTINGS
    # =========================================================
    def _capture_baseline(self):
        self.baseline = self.raw_matrix.copy()
        self.baseline_captured = True
        self.calibration_status.set(
            f"Baseline captured for {self.rows} × {self.cols}"
        )

    def _clear_baseline(self):
        self.baseline = np.zeros((self.rows, self.cols), dtype=float)
        self.baseline_captured = False
        self.calibration_status.set("No baseline captured")

    def _apply_grid_size(self):
        try:
            rows = int(self.rows_entry.get())
            cols = int(self.cols_entry.get())
        except (ValueError, tk.TclError):
            messagebox.showerror(
                "Invalid Grid",
                "Rows and columns must be whole numbers."
            )
            return

        if not (1 <= rows <= MAX_ROWS and 1 <= cols <= MAX_COLS):
            messagebox.showerror(
                "Invalid Grid",
                "Each grid dimension must be between 1 and 32."
            )
            return

        self._set_grid_size(rows, cols)

        # Stay on Settings so the change is obvious.
        self.hardware_detect_text.set(
            f"Manual grid configured: {rows} × {cols}"
        )

        # Refresh entry fields from the applied values.
        if self._widget_exists(getattr(self, "rows_entry", None)):
            self.rows_entry.delete(0, "end")
            self.rows_entry.insert(0, str(rows))

        if self._widget_exists(getattr(self, "cols_entry", None)):
            self.cols_entry.delete(0, "end")
            self.cols_entry.insert(0, str(cols))

    # =========================================================
    # INFO / UPDATE
    # =========================================================
    def _update_selected_taxel_info(self):
        if not hasattr(self, "sel_position"):
            return

        r = self.selected_row
        c = self.selected_col

        self.sel_position.set(f"Row {r+1}, Column {c+1}")
        active_force = self._active_force_matrix()
        force_n = float(active_force[r, c])
        self.sel_force.set(f"{force_n:.1f} N")
        self.sel_raw.set(f"{self.raw_matrix[r, c]:.1f}")
        self.sel_norm.set(f"{self.normalised_matrix[r, c]:.3f}")

    def _update_loop(self):
        now = time.time()
        dt = now - self.last_frame_time
        self.last_frame_time = now

        if dt > 0:
            fps = 1.0 / dt
            self.fps_smoothed = (
                fps if self.fps_smoothed == 0
                else 0.9 * self.fps_smoothed + 0.1 * fps
            )
            self.fps_text.set(f"{self.fps_smoothed:.1f} FPS")

        if self.is_playing:
            self._advance_playback()
        else:
            self.raw_matrix = self._generate_raw_matrix()
            self.normalised_matrix = self._calculate_normalised_matrix()

            self._update_live_history()
            self._record_current_frame()

        if self.current_page == "live":
            self._update_selected_taxel_info()
            self._draw_heatmap()
            self._draw_history_graph()

        self.after(33, self._update_loop)


if __name__ == "__main__":
    app = TactileVisualiserApp()
    app.mainloop()
