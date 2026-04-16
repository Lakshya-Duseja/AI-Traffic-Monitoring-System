"""
Challan (E-Ticket) Generator — creates a printable PDF for each violation.
Requires: pip install fpdf2
"""

import os
from datetime import datetime
from fpdf import FPDF


class ChallPDF(FPDF):
    def header(self):
        self.set_fill_color(20, 40, 80)
        self.rect(0, 0, 210, 28, "F")
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 16)
        self.cell(0, 14, "TRAFFIC VIOLATION CHALLAN", ln=True, align="C")
        self.set_font("Helvetica", "", 9)
        self.cell(0, 8, "Smart Traffic Enforcement System — Auto-Generated", ln=True, align="C")
        self.set_text_color(0, 0, 0)
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, "This is a computer-generated document. Pay within 30 days to avoid penalty.", align="C")


def generate_challan(violation: dict, output_dir: str = "challans") -> str:
    """
    Generate a PDF challan for a violation dict.
    Returns the path to the saved PDF.
    """
    os.makedirs(output_dir, exist_ok=True)

    ts_clean = violation.get("timestamp", datetime.now().isoformat()).replace(":", "-")
    filename  = f"challan_{violation.get('track_id', 'UNK')}_{ts_clean}.pdf"
    filepath  = os.path.join(output_dir, filename)

    pdf = ChallPDF()
    pdf.add_page()

    # ── Challan ID banner ────────────────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_fill_color(240, 240, 240)
    challan_id = f"CH-{abs(hash(ts_clean)) % 9999999:07d}"
    pdf.cell(0, 10, f"Challan No: {challan_id}", ln=True, fill=True, align="C")
    pdf.ln(4)

    # ── Helper: two-column row ───────────────────────────────────────────────
    def row(label, value, highlight=False):
        if highlight:
            pdf.set_fill_color(255, 230, 230)
            pdf.set_text_color(180, 0, 0)
        else:
            pdf.set_fill_color(250, 250, 250)
            pdf.set_text_color(0, 0, 0)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(65, 9, label, border=1, fill=True)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(0, 0, 0)
        pdf.cell(0, 9, str(value), border=1, ln=True)

    # ── Vehicle & Violation details ──────────────────────────────────────────
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_fill_color(20, 40, 80)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 9, "  VEHICLE DETAILS", ln=True, fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(1)

    row("License Plate",   violation.get("plate", "UNKNOWN"))
    row("Vehicle Type",    violation.get("vtype", "Unknown"))
    row("Track ID",        violation.get("track_id", "-"))
    row("Camera",          violation.get("camera_id", "CAM-01"))
    row("Timestamp",       violation.get("timestamp", "-"))

    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_fill_color(20, 40, 80)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 9, "  VIOLATION DETAILS", ln=True, fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(1)

    row("Violation Type",  violation.get("violation", "-").upper(), highlight=True)
    row("Speed Recorded",  f"{violation.get('speed_kmph', 0):.1f} km/h")
    row("Zone",            violation.get("zone", "-"))

    fine = violation.get("fine_inr", 0)
    row("Fine Amount",     f"INR {fine:,}", highlight=True)

    # ── Snapshot image (if exists) ────────────────────────────────────────────
    snap = violation.get("snapshot")
    if snap and os.path.exists(snap):
        pdf.ln(6)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 8, "Evidence Snapshot:", ln=True)
        try:
            pdf.image(snap, x=10, w=100)
        except Exception:
            pdf.cell(0, 8, "(image could not be embedded)", ln=True)

    # ── Payment instructions ──────────────────────────────────────────────────
    pdf.ln(6)
    pdf.set_fill_color(20, 40, 80)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 9, "  PAYMENT INSTRUCTIONS", ln=True, fill=True)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "", 10)
    pdf.ln(2)
    pdf.multi_cell(0, 7,
        f"1. Pay INR {fine:,} within 30 days to avoid late fees.\n"
        "2. Online: parivahan.gov.in > E-Challan\n"
        f"3. Quote Challan No: {challan_id}\n"
        "4. Failure to pay will result in court summons."
    )

    pdf.output(filepath)
    return filepath
