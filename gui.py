"""
Logistics Agent Dashboard
==========================

A modern, dark-themed tkinter GUI for demonstrating the existing
Logistics Agent backend (`logistics_agent.py`). This file only ever
CALLS into the backend's public functions (`run_pipeline`) -- it never
reimplements, patches, or alters any backend logic. All resolution,
flagging, and distance rules live entirely in logistics_agent.py,
unchanged.

Uses only Python's standard library (tkinter). No external packages.

Run with:
    python3 gui.py
"""

from __future__ import annotations

import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

# Make sure we can import the backend module regardless of the caller's
# current working directory (it lives alongside this file).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from logistics_agent import ResolutionStatus, run_pipeline  # noqa: E402


# =============================================================================
# Design tokens -- dark navy dashboard theme, purple/electric-blue accents
# =============================================================================

BG_APP = "#0D1220"          # app background (near-black navy)
BG_PANEL = "#131A2C"        # section / toolbar panels
BG_CARD = "#1B2338"         # card + table background
BG_CARD_HOVER = "#212B45"
BORDER = "#242E48"

ACCENT = "#8B5CF6"          # electric purple
ACCENT_2 = "#3B82F6"        # electric blue (secondary accent)
ACCENT_HOVER = "#7C4DEF"

TEXT_PRIMARY = "#E9ECF5"
TEXT_SECONDARY = "#8A93A8"
TEXT_MUTED = "#5B6479"

GREEN = "#22C55E"
GREEN_BG = "#132A1D"
RED = "#F87171"
RED_BG = "#2B1618"
YELLOW = "#FBBF24"
YELLOW_BG = "#2B2410"

FONT_FAMILY = "Helvetica"
FONT_MONO = "Courier"


def rounded_rect(canvas: tk.Canvas, x1, y1, x2, y2, radius=14, **kwargs):
    """Draws a rounded rectangle on a Canvas using a smoothed polygon --
    tkinter has no native rounded-rect primitive, so this is the standard
    workaround for "rounded card" styling."""
    points = [
        x1 + radius, y1,
        x2 - radius, y1,
        x2, y1,
        x2, y1 + radius,
        x2, y2 - radius,
        x2, y2,
        x2 - radius, y2,
        x1 + radius, y2,
        x1, y2,
        x1, y2 - radius,
        x1, y1 + radius,
        x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


class RoundedCard(tk.Frame):
    """A panel with a rounded-rectangle background. Put content in
    `self.inner` (a plain tk.Frame). Redraws itself on resize so it stays
    crisp at any window size."""

    def __init__(self, parent, bg_color=BG_CARD, radius=16, outline=BORDER, **kwargs):
        outer_bg = parent["bg"] if "bg" in parent.keys() else BG_APP
        super().__init__(parent, bg=outer_bg, **kwargs)
        self.bg_color = bg_color
        self.outline = outline
        self.radius = radius

        self.canvas = tk.Canvas(self, bg=outer_bg, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)

        self.inner = tk.Frame(self.canvas, bg=bg_color)
        self._win_id = None
        self.canvas.bind("<Configure>", self._redraw)

    def _redraw(self, event) -> None:
        w, h = event.width, event.height
        if w < 4 or h < 4:
            return
        self.canvas.delete("bg")
        rounded_rect(
            self.canvas, 1, 1, w - 1, h - 1, radius=self.radius,
            fill=self.bg_color, outline=self.outline, width=1, tags="bg",
        )
        if self._win_id is not None:
            self.canvas.delete(self._win_id)
        self._win_id = self.canvas.create_window(
            w / 2, h / 2, window=self.inner, width=max(w - 20, 1), height=max(h - 18, 1),
        )


class StatusBadge(tk.Frame):
    """Small pill-shaped status indicator (colored dot + text)."""

    def __init__(self, parent, text: str, color: str, bg: str, **kwargs):
        super().__init__(parent, bg=bg, **kwargs)
        canvas = tk.Canvas(self, width=10, height=10, bg=bg, highlightthickness=0)
        canvas.create_oval(1, 1, 9, 9, fill=color, outline=color)
        canvas.pack(side="left", padx=(0, 6))
        tk.Label(self, text=text, bg=bg, fg=color, font=(FONT_FAMILY, 10, "bold")).pack(side="left")


class ModernButton(tk.Button):
    """A flat, borderless button with hover feedback -- tkinter's default
    Button looks dated, this trims it down to a modern flat style."""

    def __init__(self, parent, text, command, bg, fg="white", hover_bg=None, **kwargs):
        self._bg = bg
        self._hover_bg = hover_bg or bg
        super().__init__(
            parent, text=text, command=command, bg=bg, fg=fg,
            activebackground=self._hover_bg, activeforeground=fg,
            font=(FONT_FAMILY, 10, "bold"), bd=0, relief="flat",
            padx=18, pady=10, cursor="hand2", highlightthickness=0,
            **kwargs,
        )
        self.bind("<Enter>", lambda e: self.configure(bg=self._hover_bg))
        self.bind("<Leave>", lambda e: self.configure(bg=self._bg))


# =============================================================================
# Main application
# =============================================================================

class LogisticsAgentDashboard(tk.Tk):

    def __init__(self) -> None:
        super().__init__()

        self.title("Logistics Agent Dashboard")
        self.geometry("1180x760")
        self.minsize(980, 640)
        self.configure(bg=BG_APP)

        self.selected_file_path: str | None = None
        self.jobs_by_id: dict[str, object] = {}
        self.has_run = False

        self._build_header()
        self._build_file_controls()
        self._build_summary_cards()
        self._build_main_area()

    # ------------------------------------------------------------------
    # Layout construction
    # ------------------------------------------------------------------
    def _build_header(self) -> None:
        header = tk.Frame(self, bg=BG_APP, padx=24)
        header.pack(fill="x", pady=(20, 10))

        left = tk.Frame(header, bg=BG_APP)
        left.pack(side="left")
        tk.Label(
            left, text="LOGISTICS AGENT", bg=BG_APP, fg=TEXT_PRIMARY,
            font=(FONT_FAMILY, 22, "bold"),
        ).pack(anchor="w")
        tk.Label(
            left, text="Delivery Assignment Intelligence", bg=BG_APP, fg=ACCENT,
            font=(FONT_FAMILY, 11),
        ).pack(anchor="w", pady=(2, 0))

        right = tk.Frame(header, bg=BG_APP)
        right.pack(side="right", anchor="e")
        self.header_status_badge_holder = right
        self.header_status = StatusBadge(right, "No file loaded", TEXT_MUTED, BG_APP)
        self.header_status.pack(anchor="e")

    def _build_file_controls(self) -> None:
        outer = tk.Frame(self, bg=BG_APP, padx=24, pady=8)
        outer.pack(fill="x")

        card = RoundedCard(outer, bg_color=BG_PANEL, radius=14, height=76)
        card.pack(fill="x")
        card.pack_propagate(False)

        row = card.inner
        row.configure(bg=BG_PANEL)

        ModernButton(
            row, "\U0001F4C1  Choose Delivery File", self._on_browse,
            bg=BG_CARD, hover_bg=BG_CARD_HOVER, fg=TEXT_PRIMARY,
        ).pack(side="left", padx=(4, 14), pady=14)

        self.file_path_var = tk.StringVar(value="No file selected")
        tk.Label(
            row, textvariable=self.file_path_var, bg=BG_PANEL, fg=TEXT_SECONDARY,
            font=(FONT_FAMILY, 10), anchor="w",
        ).pack(side="left", fill="x", expand=True, padx=4)

        ModernButton(
            row, "\u25B6  RUN AGENT", self._on_run_agent,
            bg=ACCENT, hover_bg=ACCENT_HOVER, fg="white",
        ).pack(side="right", padx=(14, 4), pady=14)

    def _build_summary_cards(self) -> None:
        outer = tk.Frame(self, bg=BG_APP, padx=24, pady=8)
        outer.pack(fill="x")

        for i in range(4):
            outer.columnconfigure(i, weight=1, uniform="cards")

        self.summary_vars = {
            "total_records": tk.StringVar(value="\u2014"),
            "total_jobs": tk.StringVar(value="\u2014"),
            "assignable_jobs": tk.StringVar(value="\u2014"),
            "flagged_jobs": tk.StringVar(value="\u2014"),
        }

        specs = [
            ("TOTAL RECORDS", "total_records", ACCENT_2),
            ("TOTAL JOBS", "total_jobs", ACCENT),
            ("ASSIGNABLE JOBS", "assignable_jobs", GREEN),
            ("FLAGGED JOBS", "flagged_jobs", RED),
        ]

        for i, (label_text, key, color) in enumerate(specs):
            card = RoundedCard(outer, bg_color=BG_CARD, radius=16, height=100)
            card.grid(row=0, column=i, sticky="nsew", padx=8)
            card.pack_propagate(False)

            content = card.inner
            content.configure(bg=BG_CARD)

            accent_strip = tk.Frame(content, bg=color, width=4)
            accent_strip.pack(side="left", fill="y", padx=(0, 14), pady=6)

            text_col = tk.Frame(content, bg=BG_CARD)
            text_col.pack(side="left", fill="both", expand=True, pady=14)

            tk.Label(
                text_col, text=label_text, bg=BG_CARD, fg=TEXT_SECONDARY,
                font=(FONT_FAMILY, 9, "bold"), anchor="w",
            ).pack(anchor="w")
            tk.Label(
                text_col, textvariable=self.summary_vars[key], bg=BG_CARD, fg=color,
                font=(FONT_FAMILY, 26, "bold"), anchor="w",
            ).pack(anchor="w")

    def _build_main_area(self) -> None:
        outer = tk.Frame(self, bg=BG_APP, padx=24)
        outer.pack(fill="both", expand=True, pady=(8, 20))
        outer.columnconfigure(0, weight=3)
        outer.columnconfigure(1, weight=2)
        outer.rowconfigure(0, weight=1)

        self._build_jobs_panel(outer)
        self._build_details_panel(outer)

    # -- Jobs table panel -------------------------------------------------
    def _build_jobs_panel(self, parent) -> None:
        card = RoundedCard(parent, bg_color=BG_CARD, radius=16)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        content = card.inner
        content.configure(bg=BG_CARD)

        title_row = tk.Frame(content, bg=BG_CARD)
        title_row.pack(fill="x", padx=18, pady=(16, 6))
        tk.Label(
            title_row, text="Jobs", bg=BG_CARD, fg=TEXT_PRIMARY,
            font=(FONT_FAMILY, 13, "bold"),
        ).pack(side="left")

        legend = tk.Frame(title_row, bg=BG_CARD)
        legend.pack(side="right")
        StatusBadge(legend, "Assignable", GREEN, BG_CARD).pack(side="left", padx=6)
        StatusBadge(legend, "Pending", YELLOW, BG_CARD).pack(side="left", padx=6)
        StatusBadge(legend, "Flagged", RED, BG_CARD).pack(side="left", padx=6)

        # Body: swaps between an empty-state message and the actual table.
        self.jobs_body = tk.Frame(content, bg=BG_CARD)
        self.jobs_body.pack(fill="both", expand=True, padx=18, pady=(4, 16))

        self.empty_state_frame = tk.Frame(self.jobs_body, bg=BG_CARD)
        tk.Label(
            self.empty_state_frame, text="\U0001F4E6", bg=BG_CARD, fg=TEXT_MUTED,
            font=(FONT_FAMILY, 34),
        ).pack(pady=(40, 6))
        self.empty_state_label = tk.Label(
            self.empty_state_frame, text="Select a delivery file to begin analysis",
            bg=BG_CARD, fg=TEXT_SECONDARY, font=(FONT_FAMILY, 11),
        )
        self.empty_state_label.pack()

        self.table_frame = tk.Frame(self.jobs_body, bg=BG_CARD)
        self._build_treeview(self.table_frame)

        self.empty_state_frame.pack(fill="both", expand=True)

    def _build_treeview(self, parent) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure(
            "Dark.Treeview",
            background=BG_CARD, fieldbackground=BG_CARD, foreground=TEXT_PRIMARY,
            rowheight=30, borderwidth=0, font=(FONT_FAMILY, 10),
        )
        style.configure(
            "Dark.Treeview.Heading",
            background=BG_PANEL, foreground=TEXT_SECONDARY,
            font=(FONT_FAMILY, 9, "bold"), borderwidth=0, relief="flat",
        )
        style.map("Dark.Treeview.Heading", background=[("active", BG_PANEL)])
        style.map(
            "Dark.Treeview",
            background=[("selected", ACCENT)],
            foreground=[("selected", "#FFFFFF")],
        )

        style.configure(
            "Dark.Vertical.TScrollbar",
            background=BG_PANEL, troughcolor=BG_CARD, bordercolor=BG_CARD,
            arrowcolor=TEXT_SECONDARY, relief="flat",
        )

        columns = ("job_id", "customer", "pickup_status", "drop_status", "distance_km", "assignable", "flag_reason")
        headings = {
            "job_id": "Job ID", "customer": "Customer", "pickup_status": "Pickup",
            "drop_status": "Drop", "distance_km": "Distance (km)",
            "assignable": "Status", "flag_reason": "Flag Reason",
        }
        widths = {
            "job_id": 90, "customer": 130, "pickup_status": 90, "drop_status": 90,
            "distance_km": 100, "assignable": 100, "flag_reason": 280,
        }

        table_wrap = tk.Frame(parent, bg=BG_CARD)
        table_wrap.pack(fill="both", expand=True)

        self.tree = ttk.Treeview(
            table_wrap, columns=columns, show="headings",
            selectmode="browse", style="Dark.Treeview",
        )
        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=widths[col], anchor="w")

        vsb = ttk.Scrollbar(table_wrap, orient="vertical", command=self.tree.yview, style="Dark.Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.tree.tag_configure("row_assignable", background=GREEN_BG, foreground=GREEN)
        self.tree.tag_configure("row_pending", background=YELLOW_BG, foreground=YELLOW)
        self.tree.tag_configure("row_flagged", background=RED_BG, foreground=RED)

        self.tree.bind("<<TreeviewSelect>>", self._on_row_selected)

    # -- Job details panel -------------------------------------------------
    def _build_details_panel(self, parent) -> None:
        card = RoundedCard(parent, bg_color=BG_CARD, radius=16)
        card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        content = card.inner
        content.configure(bg=BG_CARD)

        tk.Label(
            content, text="Job Details", bg=BG_CARD, fg=TEXT_PRIMARY,
            font=(FONT_FAMILY, 13, "bold"),
        ).pack(anchor="w", padx=18, pady=(16, 6))

        self.details_body = tk.Frame(content, bg=BG_CARD)
        self.details_body.pack(fill="both", expand=True, padx=18, pady=(4, 16))

        self.details_placeholder = tk.Label(
            self.details_body, text="Select a job row to view full details",
            bg=BG_CARD, fg=TEXT_MUTED, font=(FONT_FAMILY, 10), wraplength=300, justify="left",
        )
        self.details_placeholder.pack(anchor="w", pady=30)

        self.details_content = tk.Frame(self.details_body, bg=BG_CARD)
        # not packed yet -- shown once a job is selected

    def _section_heading(self, parent, text) -> None:
        tk.Label(
            parent, text=text.upper(), bg=BG_CARD, fg=TEXT_MUTED,
            font=(FONT_FAMILY, 9, "bold"),
        ).pack(anchor="w", pady=(14, 2))

    def _kv_row(self, parent, key, value, value_color=TEXT_PRIMARY) -> None:
        row = tk.Frame(parent, bg=BG_CARD)
        row.pack(fill="x", pady=1)
        tk.Label(row, text=key, bg=BG_CARD, fg=TEXT_SECONDARY, font=(FONT_FAMILY, 9), width=12, anchor="w").pack(side="left")
        tk.Label(
            row, text=str(value), bg=BG_CARD, fg=value_color,
            font=(FONT_MONO, 9), anchor="w", justify="left", wraplength=230,
        ).pack(side="left", fill="x", expand=True)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def _on_browse(self) -> None:
        path = filedialog.askopenfilename(
            title="Select a delivery file",
            filetypes=[
                ("Delivery data files", "*.json *.csv"),
                ("JSON files", "*.json"),
                ("CSV files", "*.csv"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return  # user cancelled -- not an error

        self.selected_file_path = path
        self.file_path_var.set(os.path.basename(path))
        self._set_header_status("File ready", ACCENT_2)

    def _on_run_agent(self) -> None:
        if not self.selected_file_path:
            messagebox.showwarning(
                "No file selected",
                "Choose a delivery file (.json or .csv) before running the agent.",
            )
            return

        if not os.path.exists(self.selected_file_path):
            messagebox.showerror(
                "File not found",
                "That file no longer exists. Please choose it again.",
            )
            return

        lower_path = self.selected_file_path.lower()
        if not (lower_path.endswith(".json") or lower_path.endswith(".csv")):
            messagebox.showerror(
                "Unsupported file type",
                "Please select a .json or .csv delivery file.",
            )
            return

        try:
            # Calls straight into the existing, unmodified backend pipeline.
            result = run_pipeline(self.selected_file_path)
        except Exception as exc:  # noqa: BLE001 -- GUI boundary: never crash on a bad file/backend error
            messagebox.showerror(
                "Agent run failed",
                f"The Logistics Agent could not process this file.\n\nDetails: {exc}",
            )
            return

        try:
            self._populate_summary(result)
            self._populate_jobs_table(result)
            self._clear_details()
            self.has_run = True
            self._set_header_status("Analysis complete", GREEN)
        except Exception as exc:  # noqa: BLE001 -- rendering should never crash the app either
            messagebox.showerror(
                "Display error",
                f"The agent ran, but results could not be displayed.\n\nDetails: {exc}",
            )

    def _on_row_selected(self, _event=None) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        job_id = self.tree.item(selection[0], "values")[0]
        job = self.jobs_by_id.get(job_id)
        if job is None:
            return
        self._show_job_details(job)

    # ------------------------------------------------------------------
    # Rendering helpers
    # ------------------------------------------------------------------
    def _set_header_status(self, text: str, color: str) -> None:
        self.header_status.destroy()
        self.header_status = StatusBadge(self.header_status_badge_holder, text, color, BG_APP)
        self.header_status.pack(anchor="e")

    def _populate_summary(self, result: dict) -> None:
        records = result.get("records", [])
        jobs = result.get("jobs", [])
        report = result.get("report", {})

        total_records = report.get("total_records", len(records))
        total_jobs = len(jobs)
        assignable_jobs = report.get("assignable_job_count", sum(1 for j in jobs if getattr(j, "assignable", False)))
        flagged_jobs = report.get("flagged_job_count", total_jobs - assignable_jobs)

        self.summary_vars["total_records"].set(str(total_records))
        self.summary_vars["total_jobs"].set(str(total_jobs))
        self.summary_vars["assignable_jobs"].set(str(assignable_jobs))
        self.summary_vars["flagged_jobs"].set(str(flagged_jobs))

    @staticmethod
    def _row_tag(job) -> str:
        if job.assignable:
            return "row_assignable"
        statuses = {job.pickup_status, job.drop_status}
        if (
            ResolutionStatus.EMPTY in statuses
            and ResolutionStatus.INVALID not in statuses
            and ResolutionStatus.MALFORMED_INPUT not in statuses
        ):
            return "row_pending"
        return "row_flagged"

    def _populate_jobs_table(self, result: dict) -> None:
        self.tree.delete(*self.tree.get_children())
        self.jobs_by_id.clear()

        jobs = result.get("jobs", [])

        if not jobs:
            self.empty_state_label.configure(
                text="The agent ran successfully but produced zero jobs\n(the source file may be empty)."
            )
            self.table_frame.pack_forget()
            self.empty_state_frame.pack(fill="both", expand=True)
            return

        for job in jobs:
            self.jobs_by_id[job.job_id] = job
            distance_display = "\u2014" if job.distance_km is None else f"{job.distance_km:.2f}"
            status_display = "\u2713 Assignable" if job.assignable else "\u2717 Flagged"
            flag_reason_display = job.flag_reason or "\u2014"

            self.tree.insert(
                "", "end",
                values=(
                    job.job_id, job.customer_name, job.pickup_status.value,
                    job.drop_status.value, distance_display, status_display, flag_reason_display,
                ),
                tags=(self._row_tag(job),),
            )

        self.empty_state_frame.pack_forget()
        self.table_frame.pack(fill="both", expand=True)

    def _clear_details(self) -> None:
        self.details_content.pack_forget()
        for child in self.details_content.winfo_children():
            child.destroy()
        self.details_placeholder.pack(anchor="w", pady=30)

    def _show_job_details(self, job) -> None:
        self.details_placeholder.pack_forget()
        for child in self.details_content.winfo_children():
            child.destroy()

        c = self.details_content

        # -- Header: job id / customer + overall status badge
        top = tk.Frame(c, bg=BG_CARD)
        top.pack(fill="x")
        tk.Label(top, text=job.job_id, bg=BG_CARD, fg=TEXT_PRIMARY, font=(FONT_FAMILY, 14, "bold")).pack(anchor="w")
        tk.Label(top, text=job.customer_name, bg=BG_CARD, fg=TEXT_SECONDARY, font=(FONT_FAMILY, 10)).pack(anchor="w")

        if job.assignable:
            badge_color, badge_bg, badge_text = GREEN, GREEN_BG, "ASSIGNABLE"
        else:
            tag = self._row_tag(job)
            if tag == "row_pending":
                badge_color, badge_bg, badge_text = YELLOW, YELLOW_BG, "PENDING"
            else:
                badge_color, badge_bg, badge_text = RED, RED_BG, "FLAGGED"

        badge_wrap = tk.Frame(c, bg=badge_bg)
        badge_wrap.pack(anchor="w", pady=(10, 0))
        tk.Label(
            badge_wrap, text=f"  {badge_text}  ", bg=badge_bg, fg=badge_color,
            font=(FONT_FAMILY, 9, "bold"),
        ).pack(padx=2, pady=4)

        # -- Pickup section
        self._section_heading(c, "Pickup")
        self._kv_row(c, "Address", job.pickup_raw_address or "(none)")
        self._kv_row(c, "Normalized", job.pickup_normalized_address or "(none)")
        self._kv_row(c, "Coords", f"{job.pickup_lat}, {job.pickup_lon}")
        self._kv_row(c, "Status", job.pickup_status.value,
                     GREEN if job.pickup_status == ResolutionStatus.RESOLVED else YELLOW)

        # -- Drop section
        self._section_heading(c, "Drop")
        self._kv_row(c, "Address", job.drop_raw_address or "(none)")
        self._kv_row(c, "Normalized", job.drop_normalized_address or "(none)")
        self._kv_row(c, "Coords", f"{job.drop_lat}, {job.drop_lon}")
        self._kv_row(c, "Status", job.drop_status.value,
                     GREEN if job.drop_status == ResolutionStatus.RESOLVED else YELLOW)

        # -- Route section
        self._section_heading(c, "Route")
        self._kv_row(c, "Distance", f"{job.distance_km} km" if job.distance_km is not None else "\u2014")
        self._kv_row(c, "Travel time", f"{job.travel_time_minutes} min" if job.travel_time_minutes is not None else "\u2014")
        tk.Label(
            c, text=job.travel_time_notes, bg=BG_CARD, fg=TEXT_MUTED,
            font=(FONT_FAMILY, 8), wraplength=300, justify="left",
        ).pack(anchor="w", pady=(2, 0))

        # -- Assignment status section
        self._section_heading(c, "Assignment Status")
        self._kv_row(c, "Assignable", "Yes" if job.assignable else "No", badge_color)
        self._kv_row(c, "Flag reason", job.flag_reason or "(none)", RED if job.flag_reason else TEXT_PRIMARY)
        self._kv_row(c, "Capacity", job.vehicle_capacity_required if job.vehicle_capacity_required is not None else "\u2014")
        tk.Label(
            c, text=job.vehicle_capacity_notes, bg=BG_CARD, fg=TEXT_MUTED,
            font=(FONT_FAMILY, 8), wraplength=300, justify="left",
        ).pack(anchor="w", pady=(2, 0))

        # -- Notes section
        self._section_heading(c, "Notes")
        tk.Label(
            c, text=job.package_notes or "(none)", bg=BG_CARD, fg=TEXT_PRIMARY,
            font=(FONT_MONO, 9), wraplength=300, justify="left",
        ).pack(anchor="w")

        self.details_content.pack(fill="both", expand=True)


def main() -> None:
    app = LogisticsAgentDashboard()
    app.mainloop()


if __name__ == "__main__":
    main()
