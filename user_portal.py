"""
Logistics Agent - User Portal
==============================

A modern, dark-themed tkinter GUI for customer-facing delivery submission.
Allows users to create and submit delivery requests directly into the shared
delivery queue (`delivery_queue.csv`).

Features:
- Validates required fields (Customer Name, Pickup Address, Drop-off Address).
- Automatically generates unique Job IDs (e.g. JOB-007).
- Appends submissions to `delivery_queue.csv` with exact schema headers:
    id, customer_name, pickup_address, address, notes, weight
- Automatically creates `delivery_queue.csv` with headers if missing.
- Never overwrites existing deliveries.
- Displays clear success/error feedback and clears the form upon submission.
- Shows a live session history of submitted deliveries.
- Visual design is 100% consistent with the Logistics Agent Dashboard.

Uses only Python standard library (tkinter, csv, os, sys, re). No external dependencies.

Run with:
    python user_portal.py
"""

from __future__ import annotations

import csv
import os
import re
import sys
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional


# =============================================================================
# Design tokens -- matching Logistics Agent Dashboard
# =============================================================================

BG_APP = "#0D1220"          # app background (near-black navy)
BG_PANEL = "#131A2C"        # section / toolbar panels
BG_CARD = "#1B2338"         # card + input background
BG_CARD_HOVER = "#212B45"
BG_INPUT = "#131A2C"        # input field background
BORDER = "#242E48"
BORDER_FOCUS = "#8B5CF6"

ACCENT = "#8B5CF6"          # electric purple
ACCENT_2 = "#3B82F6"        # electric blue
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

CSV_HEADERS = ["id", "customer_name", "pickup_address", "address", "notes", "weight"]


# =============================================================================
# UI Components
# =============================================================================

def rounded_rect(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float, radius: int = 14, **kwargs) -> int:
    """Draws a rounded rectangle on a Canvas using a smoothed polygon."""
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
    """A panel with a rounded-rectangle background."""

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
    """A flat, borderless button with hover feedback."""

    def __init__(self, parent, text, command, bg, fg="white", hover_bg=None, padx=18, pady=10, **kwargs):
        self._bg = bg
        self._hover_bg = hover_bg or bg
        super().__init__(
            parent, text=text, command=command, bg=bg, fg=fg,
            activebackground=self._hover_bg, activeforeground=fg,
            font=(FONT_FAMILY, 10, "bold"), bd=0, relief="flat",
            padx=padx, pady=pady, cursor="hand2", highlightthickness=0,
            **kwargs,
        )
        self.bind("<Enter>", lambda e: self.configure(bg=self._hover_bg))
        self.bind("<Leave>", lambda e: self.configure(bg=self._bg))


# =============================================================================
# CSV Operations Helper
# =============================================================================

class DeliveryQueueManager:
    """Handles reading and writing to delivery_queue.csv safely."""

    def __init__(self, filepath: Optional[str] = None):
        if filepath:
            self.filepath = filepath
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            self.filepath = os.path.join(base_dir, "delivery_queue.csv")

    def ensure_file_exists(self) -> None:
        """Creates delivery_queue.csv with headers if it does not exist."""
        if not os.path.exists(self.filepath):
            with open(self.filepath, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
                writer.writeheader()

    def get_existing_job_ids(self) -> set[str]:
        """Reads all existing job IDs from the CSV."""
        if not os.path.exists(self.filepath):
            return set()

        ids = set()
        try:
            with open(self.filepath, mode="r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row and "id" in row and row["id"]:
                        ids.add(row["id"].strip())
        except Exception:
            # If reading fails, return whatever IDs were gathered so far
            pass
        return ids

    def generate_next_job_id(self) -> str:
        """Generates the next sequential unique Job ID (e.g. JOB-001, JOB-002)."""
        existing_ids = self.get_existing_job_ids()
        max_num = 0

        for j_id in existing_ids:
            match = re.match(r"^JOB-(\d+)$", j_id, re.IGNORECASE)
            if match:
                try:
                    num = int(match.group(1))
                    if num > max_num:
                        max_num = num
                except ValueError:
                    continue

        next_num = max_num + 1
        candidate = f"JOB-{next_num:03d}"
        while candidate in existing_ids:
            next_num += 1
            candidate = f"JOB-{next_num:03d}"

        return candidate

    def append_delivery(self, record: dict[str, str]) -> tuple[bool, Optional[str]]:
        """
        Appends a new delivery record to delivery_queue.csv.
        Returns (success: bool, error_message: str | None).
        """
        try:
            file_existed = os.path.exists(self.filepath)

            # Check if file exists but is empty or missing headers
            needs_header = True
            if file_existed and os.path.getsize(self.filepath) > 0:
                needs_header = False

            with open(self.filepath, mode="a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_HEADERS, extrasaction="ignore")
                if needs_header:
                    writer.writeheader()
                writer.writerow(record)
            return True, None
        except Exception as exc:
            return False, str(exc)

    def load_recent_deliveries(self, limit: int = 15) -> list[dict[str, str]]:
        """Loads the most recent deliveries from the queue."""
        if not os.path.exists(self.filepath):
            return []
        try:
            with open(self.filepath, mode="r", newline="", encoding="utf-8") as f:
                reader = list(csv.DictReader(f))
                return reader[-limit:]
        except Exception:
            return []


# =============================================================================
# Main User Portal Application
# =============================================================================

class UserPortalApp(tk.Tk):

    def __init__(self, queue_manager: Optional[DeliveryQueueManager] = None) -> None:
        super().__init__()

        self.queue_mgr = queue_manager or DeliveryQueueManager()
        self.queue_mgr.ensure_file_exists()

        self.title("Logistics Agent - Delivery Portal")
        self.geometry("1100x740")
        self.minsize(920, 640)
        self.configure(bg=BG_APP)

        self._build_header()
        self._build_main_area()
        self._refresh_history_table()

    # ------------------------------------------------------------------
    # Layout construction
    # ------------------------------------------------------------------
    def _build_header(self) -> None:
        header = tk.Frame(self, bg=BG_APP, padx=24)
        header.pack(fill="x", pady=(20, 10))

        left = tk.Frame(header, bg=BG_APP)
        left.pack(side="left")
        tk.Label(
            left, text="USER DELIVERY PORTAL", bg=BG_APP, fg=TEXT_PRIMARY,
            font=(FONT_FAMILY, 22, "bold"),
        ).pack(anchor="w")
        tk.Label(
            left, text="Create & Dispatch Logistics Orders", bg=BG_APP, fg=ACCENT,
            font=(FONT_FAMILY, 11),
        ).pack(anchor="w", pady=(2, 0))

        right = tk.Frame(header, bg=BG_APP)
        right.pack(side="right", anchor="e")
        self.header_status_holder = right
        self.header_status = StatusBadge(right, "Queue Active", GREEN, BG_APP)
        self.header_status.pack(anchor="e")

    def _build_main_area(self) -> None:
        outer = tk.Frame(self, bg=BG_APP, padx=24)
        outer.pack(fill="both", expand=True, pady=(8, 20))
        outer.columnconfigure(0, weight=3)  # Form panel
        outer.columnconfigure(1, weight=2)  # Recent Submissions / Queue panel
        outer.rowconfigure(0, weight=1)

        self._build_form_panel(outer)
        self._build_queue_panel(outer)

    def _build_form_panel(self, parent: tk.Frame) -> None:
        card = RoundedCard(parent, bg_color=BG_CARD, radius=16)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        content = card.inner
        content.configure(bg=BG_CARD)

        title_frame = tk.Frame(content, bg=BG_CARD)
        title_frame.pack(fill="x", padx=20, pady=(16, 12))

        tk.Label(
            title_frame, text="Submit New Delivery", bg=BG_CARD, fg=TEXT_PRIMARY,
            font=(FONT_FAMILY, 14, "bold"),
        ).pack(side="left")

        tk.Label(
            title_frame, text="* Required fields", bg=BG_CARD, fg=TEXT_MUTED,
            font=(FONT_FAMILY, 9),
        ).pack(side="right")

        # Scrollable form container or compact layout
        form_body = tk.Frame(content, bg=BG_CARD)
        form_body.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        # 1. Customer Name (Required)
        self.customer_name_var = tk.StringVar()
        self._create_input_field(
            form_body, label="Customer Name *", var=self.customer_name_var,
            placeholder="e.g. Acme Corp / Priya Singh",
        )

        # 2. Pickup Address (Required)
        self.pickup_addr_var = tk.StringVar()
        self._create_input_field(
            form_body, label="Pickup Address *", var=self.pickup_addr_var,
            placeholder="e.g. 12 MG Road, Chennai, TN 600001",
        )

        # 3. Drop-off Address (Required)
        self.drop_addr_var = tk.StringVar()
        self._create_input_field(
            form_body, label="Drop-off Address *", var=self.drop_addr_var,
            placeholder="e.g. 45 Brigade Street, Bengaluru, KA",
        )

        # 4. Package Weight / Capacity (Optional)
        self.weight_var = tk.StringVar()
        self._create_input_field(
            form_body, label="Package Weight / Capacity", var=self.weight_var,
            placeholder="e.g. 500 kg / 2 pallets / 15 boxes",
        )

        # 5. Special Instructions / Notes (Optional)
        self._create_notes_field(form_body)

        # Inline Feedback Message Area
        self.feedback_frame = tk.Frame(content, bg=BG_CARD, height=32)
        self.feedback_frame.pack(fill="x", padx=20, pady=(4, 8))
        self.feedback_frame.pack_propagate(False)

        self.feedback_label = tk.Label(
            self.feedback_frame, text="", bg=BG_CARD, fg=GREEN,
            font=(FONT_FAMILY, 10, "bold"), anchor="w",
        )
        self.feedback_label.pack(side="left", fill="x")

        # Button row
        btn_row = tk.Frame(content, bg=BG_CARD)
        btn_row.pack(fill="x", padx=20, pady=(0, 16))

        ModernButton(
            btn_row, text="\u2714  Submit Delivery", command=self._on_submit_delivery,
            bg=ACCENT, hover_bg=ACCENT_HOVER, fg="white",
        ).pack(side="left", padx=(0, 10))

        ModernButton(
            btn_row, text="Clear Form", command=self._on_clear_form,
            bg=BG_PANEL, hover_bg=BG_CARD_HOVER, fg=TEXT_SECONDARY,
        ).pack(side="left")

    def _create_input_field(self, parent: tk.Frame, label: str, var: tk.StringVar, placeholder: str = "") -> None:
        field_wrap = tk.Frame(parent, bg=BG_CARD)
        field_wrap.pack(fill="x", pady=(0, 10))

        tk.Label(
            field_wrap, text=label, bg=BG_CARD, fg=TEXT_SECONDARY,
            font=(FONT_FAMILY, 10, "bold"), anchor="w",
        ).pack(anchor="w", pady=(0, 4))

        entry_frame = tk.Frame(field_wrap, bg=BORDER, bd=1)
        entry_frame.pack(fill="x")

        entry = tk.Entry(
            entry_frame, textvariable=var, bg=BG_INPUT, fg=TEXT_PRIMARY,
            insertbackground=ACCENT, relief="flat", font=(FONT_FAMILY, 10),
            bd=0, highlightthickness=0,
        )
        entry.pack(fill="x", ipady=7, padx=8)

        # Focus styling
        entry.bind("<FocusIn>", lambda e: entry_frame.configure(bg=BORDER_FOCUS))
        entry.bind("<FocusOut>", lambda e: entry_frame.configure(bg=BORDER))

    def _create_notes_field(self, parent: tk.Frame) -> None:
        field_wrap = tk.Frame(parent, bg=BG_CARD)
        field_wrap.pack(fill="both", expand=True, pady=(0, 6))

        tk.Label(
            field_wrap, text="Special Instructions", bg=BG_CARD, fg=TEXT_SECONDARY,
            font=(FONT_FAMILY, 10, "bold"), anchor="w",
        ).pack(anchor="w", pady=(0, 4))

        text_frame = tk.Frame(field_wrap, bg=BORDER, bd=1)
        text_frame.pack(fill="both", expand=True)

        self.notes_text = tk.Text(
            text_frame, bg=BG_INPUT, fg=TEXT_PRIMARY,
            insertbackground=ACCENT, relief="flat", font=(FONT_FAMILY, 10),
            bd=0, highlightthickness=0, height=3,
        )
        self.notes_text.pack(fill="both", expand=True, padx=8, pady=6)

        self.notes_text.bind("<FocusIn>", lambda e: text_frame.configure(bg=BORDER_FOCUS))
        self.notes_text.bind("<FocusOut>", lambda e: text_frame.configure(bg=BORDER))

    def _build_queue_panel(self, parent: tk.Frame) -> None:
        card = RoundedCard(parent, bg_color=BG_CARD, radius=16)
        card.grid(row=0, column=1, sticky="nsew", padx=(10, 0))

        content = card.inner
        content.configure(bg=BG_CARD)

        title_row = tk.Frame(content, bg=BG_CARD)
        title_row.pack(fill="x", padx=18, pady=(16, 12))

        tk.Label(
            title_row, text="Recent Queue Entries", bg=BG_CARD, fg=TEXT_PRIMARY,
            font=(FONT_FAMILY, 13, "bold"),
        ).pack(side="left")

        ModernButton(
            title_row, text="\u21BB Refresh", command=self._refresh_history_table,
            bg=BG_PANEL, hover_bg=BG_CARD_HOVER, fg=TEXT_SECONDARY, padx=10, pady=4,
        ).pack(side="right")

        table_wrap = tk.Frame(content, bg=BG_CARD)
        table_wrap.pack(fill="both", expand=True, padx=18, pady=(0, 16))

        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure(
            "Queue.Treeview",
            background=BG_CARD, fieldbackground=BG_CARD, foreground=TEXT_PRIMARY,
            rowheight=28, borderwidth=0, font=(FONT_FAMILY, 9),
        )
        style.configure(
            "Queue.Treeview.Heading",
            background=BG_PANEL, foreground=TEXT_SECONDARY,
            font=(FONT_FAMILY, 9, "bold"), borderwidth=0, relief="flat",
        )
        style.map("Queue.Treeview.Heading", background=[("active", BG_PANEL)])
        style.map(
            "Queue.Treeview",
            background=[("selected", ACCENT)],
            foreground=[("selected", "#FFFFFF")],
        )

        columns = ("id", "customer", "pickup", "drop", "weight")
        headings = {
            "id": "ID", "customer": "Customer", "pickup": "Pickup",
            "drop": "Drop-off", "weight": "Weight",
        }
        widths = {
            "id": 75, "customer": 110, "pickup": 110,
            "drop": 110, "weight": 75,
        }

        self.tree = ttk.Treeview(
            table_wrap, columns=columns, show="headings",
            selectmode="browse", style="Queue.Treeview",
        )
        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=widths[col], anchor="w")

        vsb = ttk.Scrollbar(table_wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

    # ------------------------------------------------------------------
    # Actions & Handlers
    # ------------------------------------------------------------------
    def _on_clear_form(self) -> None:
        self.customer_name_var.set("")
        self.pickup_addr_var.set("")
        self.drop_addr_var.set("")
        self.weight_var.set("")
        self.notes_text.delete("1.0", "end")
        self._show_feedback("", TEXT_PRIMARY)

    def _show_feedback(self, message: str, color: str) -> None:
        self.feedback_label.configure(text=message, fg=color)

    def _on_submit_delivery(self) -> None:
        customer_name = self.customer_name_var.get().strip()
        pickup_address = self.pickup_addr_var.get().strip()
        drop_address = self.drop_addr_var.get().strip()
        weight = self.weight_var.get().strip()
        notes = self.notes_text.get("1.0", "end-1c").strip()

        # Validation: Required fields
        missing_fields = []
        if not customer_name:
            missing_fields.append("Customer Name")
        if not pickup_address:
            missing_fields.append("Pickup Address")
        if not drop_address:
            missing_fields.append("Drop-off Address")

        if missing_fields:
            err_msg = f"Missing required fields: {', '.join(missing_fields)}"
            self._show_feedback(f"\u26A0 {err_msg}", RED)
            messagebox.showwarning("Validation Error", f"Please fill out all required fields:\n\n• " + "\n• ".join(missing_fields))
            return

        try:
            # Generate unique Job ID
            job_id = self.queue_mgr.generate_next_job_id()

            record = {
                "id": job_id,
                "customer_name": customer_name,
                "pickup_address": pickup_address,
                "address": drop_address,
                "notes": notes,
                "weight": weight,
            }

            success, error_msg = self.queue_mgr.append_delivery(record)
            if not success:
                self._show_feedback(f"\u2717 Failed to save: {error_msg}", RED)
                messagebox.showerror("Error Saving Delivery", f"Could not append delivery to queue file:\n\n{error_msg}")
                return

            # Success
            success_msg = f"\u2714 Delivery {job_id} submitted successfully!"
            self._show_feedback(success_msg, GREEN)
            messagebox.showinfo("Delivery Submitted", f"Delivery order {job_id} has been queued successfully!\n\nCustomer: {customer_name}\nPickup: {pickup_address}\nDrop: {drop_address}")

            # Clear form & refresh recent list
            self._on_clear_form()
            self._show_feedback(success_msg, GREEN)
            self._refresh_history_table()

        except Exception as exc:
            self._show_feedback(f"\u2717 Unexpected error: {exc}", RED)
            messagebox.showerror("System Error", f"An unexpected error occurred:\n\n{exc}")

    def _refresh_history_table(self) -> None:
        self.tree.delete(*self.tree.get_children())
        records = self.queue_mgr.load_recent_deliveries(limit=25)
        for r in reversed(records):
            self.tree.insert(
                "", "end",
                values=(
                    r.get("id", ""),
                    r.get("customer_name", ""),
                    r.get("pickup_address", ""),
                    r.get("address", ""),
                    r.get("weight", ""),
                ),
            )


def main() -> None:
    app = UserPortalApp()
    app.mainloop()


if __name__ == "__main__":
    main()
