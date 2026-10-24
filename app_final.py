"""
EcoQuill Invoice Generator (invoice-only edition)

Nothing is stored on the server. Every client detail (GSTIN, bank details,
logo, terms) is baked into this code / the assets folder, so a Streamlit
restart or wake-up from sleep always starts with the correct defaults.
"""

import html
import io
import re
import base64
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import streamlit as st
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
    Image,
)

st.set_page_config(
    page_title="EcoQuill Invoice Generator", page_icon="🌿", layout="wide"
)

BASE = Path(__file__).resolve().parent
ASSETS = BASE / "assets"

# ============================================================
# DEFAULTS - edit here if the client's details ever change
# ============================================================
COMPANY = {
    "name": "EcoQuill",
    "tagline": "Sustainability Starts With Every Bag",
    "address": "660, 9th Cross, Weavers Colony, Gottigere Post, Bannerghatta Road, Bengaluru - 560083",
    "phone": "+91 7899334559",
    "email": "ecoquill.biobags@gmail.com",
    "gstin": "29AALFE4303K1ZA",
    "website": "",
}
BANK = {
    "bank_name": "Canara Bank",
    "account_name": "EcoQuill",
    "account_no": "120041744725",
    "ifsc": "CNRB0000433",
    "upi": "",
}
TERMS = (
    "Goods once sold will not be taken back.\n"
    "Payment should be made as per agreed terms.\n"
    "Any dispute is subject to Bengaluru jurisdiction only.\n"
    "Please verify quantity and product details at delivery."
)
SETTINGS = {
    "invoice_prefix": "EQ/INV",
    "default_title": "TAX INVOICE",
    "default_place_of_supply": "Karnataka",
    "default_hsn": "39232990",
    "default_gst": 5.0,
    "system_note_1": "System Generated Invoice",
    "system_note_2": "No signature required",
    "thanks": "Experience the best with EcoQuill",
    "min_rows": 6,
    "dark": "#20242E",
    "accent": "#A8C832",
    "grid": "#E1E4E8",
}
PRODUCTS = [f"EcoQuill BioCarry {i} KG Compostable Bag" for i in range(1, 11)]
LOGO_NAMES = [
    "business_logo.png",
    "business_logo.jpg",
    "business_logo.jpeg",
    "logo.png",
    "logo.jpg",
    "logo.jpeg",
]
SIGN_NAMES = [
    "digital_signature.png",
    "digital_signature.jpg",
    "signature.png",
    "signature.jpg",
]


def find_asset(names):
    for folder in (ASSETS, BASE):
        for n in names:
            p = folder / n
            if p.exists() and p.is_file():
                return p.read_bytes()
    return None


def default_logo():
    data = find_asset(LOGO_NAMES)
    if data:
        return data
    try:
        from logo_data import LOGO_B64

        return base64.b64decode(LOGO_B64)
    except Exception:
        return None


# ============================================================
# Helpers
# ============================================================
def money(v):
    try:
        return float(
            Decimal(str(v or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        )
    except Exception:
        return 0.0


def rupee(v):
    return f"Rs. {float(v):,.2f}"


def fin_year(d):
    y = d.year if d.month >= 4 else d.year - 1
    return f"{y}-{str(y + 1)[-2:]}"


def next_number(current):
    """Increase the trailing digits of an invoice number (EQ/INV/2026-27/000007 -> ...000008)."""
    m = re.search(r"(\d+)(\D*)$", current)
    if not m:
        return current
    digits = m.group(1)
    return current[: m.start(1)] + str(int(digits) + 1).zfill(len(digits)) + m.group(2)


# ============================================================
# PDF
# ============================================================
def draw_page(canvas, doc, inv, co, title, logo_bytes):
    canvas.saveState()
    w, h = A4
    dark = colors.HexColor(SETTINGS["dark"])
    accent = colors.HexColor(SETTINGS["accent"])
    muted = colors.HexColor("#68707B")
    canvas.setFillColor(colors.white)
    canvas.rect(0, 0, w, h, fill=1, stroke=0)
    canvas.setFillColor(accent)
    canvas.rect(0, h - 5 * mm, w, 5 * mm, fill=1, stroke=0)
    canvas.rect(0, 0, w, 4 * mm, fill=1, stroke=0)

    p = canvas.beginPath()
    p.moveTo(76 * mm, h - 5 * mm)
    p.lineTo(w, h - 5 * mm)
    p.lineTo(w, h - 38 * mm)
    p.lineTo(91 * mm, h - 38 * mm)
    p.close()
    canvas.setFillColor(dark)
    canvas.drawPath(p, fill=1, stroke=0)

    a = canvas.beginPath()
    a.moveTo(0, h - 5 * mm)
    a.lineTo(160 * mm, h - 5 * mm)
    a.lineTo(149 * mm, h - 13 * mm)
    a.lineTo(0, h - 13 * mm)
    a.close()
    canvas.setFillColor(accent)
    canvas.drawPath(a, fill=1, stroke=0)

    canvas.setFillColor(dark)
    canvas.setFont("Helvetica-Bold", 25)
    canvas.drawString(16 * mm, h - 27 * mm, (title or "INVOICE")[:40])
    canvas.setFont("Helvetica", 7.3)
    for i, (label, value) in enumerate(
        [
            ("Invoice No.", inv["no"]),
            ("Invoice Date", inv["date"]),
            ("Due Date", inv["due"]),
        ]
    ):
        y = h - (32 + i * 4.2) * mm
        canvas.setFillColor(muted)
        canvas.drawString(16 * mm, y, label + ":")
        canvas.setFillColor(dark)
        canvas.drawString(39 * mm, y, str(value))

    lx, ly, lw, lh = w - 87 * mm, h - 35 * mm, 38 * mm, 28 * mm
    canvas.setFillColor(colors.white)
    canvas.roundRect(lx, ly, lw, lh, 5 * mm, fill=1, stroke=0)
    drawn = False
    if logo_bytes:
        try:
            canvas.saveState()
            clip = canvas.beginPath()
            clip.roundRect(lx, ly, lw, lh, 5 * mm)
            canvas.clipPath(clip, stroke=0, fill=0)
            canvas.drawImage(
                ImageReader(io.BytesIO(logo_bytes)),
                lx,
                ly,
                width=lw,
                height=lh,
                preserveAspectRatio=True,
                mask="auto",
                anchor="c",
            )
            canvas.restoreState()
            drawn = True
        except Exception:
            canvas.restoreState()
    if not drawn:
        canvas.setFillColor(accent)
        canvas.setFont("Helvetica-Bold", 15)
        canvas.drawCentredString(lx + lw / 2, ly + lh / 2 - 3, "EQ")

    tx = lx + lw + 4 * mm
    maxw = w - 5 * mm - tx
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 12)
    canvas.drawString(tx, h - 20 * mm, co["name"])
    canvas.setFont("Helvetica", 7)
    lines, cur = [], ""
    for wd in co["tagline"].split():
        test = (cur + " " + wd).strip()
        if canvas.stringWidth(test, "Helvetica", 7) <= maxw:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = wd
    if cur:
        lines.append(cur)
    for i, t in enumerate(lines[:3]):
        canvas.drawString(tx, h - (24.5 + i * 3.2) * mm, t)

    f = canvas.beginPath()
    f.moveTo(0, 4 * mm)
    f.lineTo(137 * mm, 4 * mm)
    f.lineTo(149 * mm, 18 * mm)
    f.lineTo(0, 18 * mm)
    f.close()
    canvas.setFillColor(dark)
    canvas.drawPath(f, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica", 6.5)
    canvas.drawString(15 * mm, 10 * mm, co["phone"])
    canvas.drawString(65 * mm, 10 * mm, co["email"][:38])
    if co.get("website"):
        canvas.drawString(116 * mm, 10 * mm, co["website"][:26])
    canvas.restoreState()


def make_pdf(
    co,
    customer,
    inv,
    items,
    totals,
    bank,
    terms,
    title,
    logo_bytes,
    sign_bytes,
    signatory,
):
    dark = colors.HexColor(SETTINGS["dark"])
    accent = colors.HexColor(SETTINGS["accent"])
    grid = colors.HexColor(SETTINGS["grid"])
    fs = 7.2
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        topMargin=56 * mm,
        bottomMargin=25 * mm,
    )
    body = ParagraphStyle(
        "b",
        fontName="Helvetica",
        fontSize=fs,
        leading=fs * 1.3,
        textColor=colors.HexColor("#4B5563"),
    )
    right = ParagraphStyle("r", parent=body, alignment=TA_RIGHT)
    center = ParagraphStyle("ct", parent=body, alignment=TA_CENTER)
    bold = ParagraphStyle("bd", parent=body, fontName="Helvetica-Bold", textColor=dark)
    bold_right = ParagraphStyle("bdr", parent=bold, alignment=TA_RIGHT)
    head = ParagraphStyle(
        "hd",
        fontName="Helvetica-Bold",
        fontSize=7.2,
        leading=9,
        textColor=colors.white,
        alignment=TA_CENTER,
    )
    note = ParagraphStyle(
        "nt",
        fontName="Helvetica",
        fontSize=7,
        leading=9.5,
        textColor=colors.HexColor("#555B66"),
    )
    thank = ParagraphStyle(
        "th", fontName="Helvetica-BoldOblique", fontSize=10, leading=12, textColor=dark
    )
    e = lambda v: html.escape(str(v or ""))

    left = (
        f"<b>Invoice To:</b><br/><b>{e(customer['name'])}</b><br/>{e(customer['address'])}<br/>"
        f"{e(customer['phone'])}<br/>{e(customer['email'])}<br/>GSTIN: {e(customer['gstin'] or 'Not provided')}"
    )
    righttxt = (
        f"<b>{e(co['name'])}</b><br/>{e(co['address'])}<br/>Phone: {e(co['phone'])}<br/>"
        f"Email: {e(co['email'])}<br/>GSTIN: {e(co['gstin'])}"
    )
    t = Table(
        [[Paragraph(left, body), Paragraph(righttxt, right)]],
        colWidths=[112 * mm, 68 * mm],
    )
    t.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story = [t, Spacer(1, 7 * mm)]

    headers = [
        "SL#",
        "PRODUCT DESCRIPTION",
        "HSN/SAC",
        "UNIT PRICE",
        "QTY.",
        "GST",
        "TOTAL",
    ]
    widths = [12, 76, 22, 28, 24, 18, 28]
    f = 180 / sum(widths)
    widths = [x * f * mm for x in widths]
    rows = [[Paragraph(x, head) for x in headers]]
    n_rows = max(SETTINGS["min_rows"], len(items))
    for i in range(n_rows):
        it = items[i] if i < len(items) else None
        if it is None:
            # Empty filler row: no serial number
            rows.append([Paragraph("", center)] + [Paragraph("", body)] * 6)
        else:
            rows.append(
                [
                    Paragraph(f"{i + 1:02d}", center),
                    Paragraph(e(it["description"]), body),
                    Paragraph(e(it["hsn"]), right),
                    Paragraph(rupee(it["rate"]), right),
                    Paragraph(f"{it['quantity']:,.3f}", right),
                    Paragraph(f"{it['gst_percent']:,.2f}%", right),
                    Paragraph(rupee(it["line_amount"] + it["gst_amount"]), right),
                ]
            )
    total_qty = sum(x["quantity"] for x in items)
    total_amt = sum(x["line_amount"] + x["gst_amount"] for x in items)
    rows.append(
        [
            Paragraph("", body),
            Paragraph("TOTAL", bold),
            Paragraph("", body),
            Paragraph("", body),
            Paragraph(f"{total_qty:,.3f}", bold_right),
            Paragraph("", body),
            Paragraph(rupee(total_amt), bold_right),
        ]
    )
    last = len(rows) - 1
    table = Table(rows, colWidths=widths, repeatRows=1)
    # Row height: 13 mm for up to 6 rows; with more rows the rows get slightly
    # slimmer so up to ~10+ line items still fit on the same single page.
    row_h = min(13.0 * mm, (13.0 * mm * SETTINGS["min_rows"]) / max(n_rows, 1))
    pad = max(3, (row_h - 9) / 2)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (1, 0), dark),
                ("BACKGROUND", (2, 0), (-1, 0), accent),
                ("BACKGROUND", (0, last), (-1, last), colors.HexColor("#F1F4E6")),
                ("GRID", (0, 0), (-1, -1), 0.35, grid),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 1), (-1, last - 1), pad),
                ("BOTTOMPADDING", (0, 1), (-1, last - 1), pad),
                ("TOPPADDING", (0, last), (-1, last), 8),
                ("BOTTOMPADDING", (0, last), (-1, last), 8),
                ("TOPPADDING", (0, 0), (-1, 0), 8),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(table)

    pay = (
        f"<b>PAYMENT DETAILS:</b><br/>Bank: {e(bank['bank_name'])}<br/>Account Name: {e(bank['account_name'])}<br/>"
        f"Account No: {e(bank['account_no'])}<br/>IFSC: {e(bank['ifsc'])}"
        + (f"<br/>UPI: {e(bank['upi'])}" if bank.get("upi") else "")
        + "<br/><br/><b>TERMS AND CONDITIONS:</b><br/>"
        + "<br/>".join(e(x) for x in terms)
    )
    tr = [
        [Paragraph("Total Qty:", body), Paragraph(f"{total_qty:,.3f}", right)],
        [Paragraph("Subtotal:", body), Paragraph(rupee(totals["taxable"]), right)],
        [Paragraph("Taxation:", body), Paragraph(rupee(totals["gst"]), right)],
    ]
    if totals["packing"] > 0:
        tr.append(
            [
                Paragraph("Packing / Delivery:", body),
                Paragraph(rupee(totals["packing"]), right),
            ]
        )
    gi = len(tr)
    tr.append(
        [
            Paragraph("G. Total", bold),
            Paragraph(
                rupee(totals["grand"]),
                ParagraphStyle(
                    "g", parent=right, fontName="Helvetica-Bold", textColor=colors.white
                ),
            ),
        ]
    )
    tr += [
        [Paragraph("Paid:", body), Paragraph(rupee(totals["paid"]), right)],
        [Paragraph("Balance Due:", bold), Paragraph(rupee(totals["balance"]), right)],
    ]
    tt = Table(tr, colWidths=[37 * mm, 33 * mm])
    tt.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.35, grid),
                ("BACKGROUND", (0, gi), (-1, gi), accent),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    low = Table([[Paragraph(pay, note), tt]], colWidths=[110 * mm, 70 * mm])
    low.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story += [low, Spacer(1, 5 * mm)]

    # No signature: system generated invoice
    sig = [
        Paragraph(e(SETTINGS["system_note_1"]), bold_right),
        Paragraph(e(SETTINGS["system_note_2"]), ParagraphStyle("nr", parent=note, alignment=TA_RIGHT)),
    ]
    close = Table(
        [[Paragraph(e(SETTINGS["thanks"]), thank), sig]], colWidths=[116 * mm, 64 * mm]
    )
    close.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                ("ALIGN", (1, 0), (1, 0), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(close)

    doc.build(
        story,
        onFirstPage=lambda c, d: draw_page(c, d, inv, co, title, logo_bytes),
        onLaterPages=lambda c, d: draw_page(c, d, inv, co, title, logo_bytes),
    )
    return buf.getvalue()


# ============================================================
# UI
# ============================================================
def theme():
    st.markdown(
        """<style>
        .stApp{background:#f3f5f8}
        .block-container{max-width:1300px;padding-top:1.4rem}
        .hero{background:#fff;border:1px solid #e1e3e8;border-radius:20px;padding:22px 26px;margin-bottom:16px;box-shadow:0 10px 26px rgba(30,35,47,.07)}
        .hero h1{margin:0;font-size:28px;color:#111318}.hero p{margin:6px 0 0;color:#6f7480}
        .metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:14px 0}
        .metric{background:#fff;border:1px solid #e1e3e8;border-radius:14px;padding:14px}
        .metric label{font-size:12px;color:#747983;font-weight:700}.metric strong{display:block;font-size:20px;color:#101828;margin-top:4px}
        .stButton>button,.stDownloadButton>button{background:#17181c!important;color:#fff!important;border:0!important;border-radius:10px!important;font-weight:700!important}
        .stButton>button *,.stDownloadButton>button *{color:#fff!important}
        </style>""",
        unsafe_allow_html=True,
    )


def metrics(items):
    st.markdown(
        "<div class='metrics'>"
        + "".join(
            f"<div class='metric'><label>{html.escape(a)}</label><strong>{html.escape(b)}</strong></div>"
            for a, b in items
        )
        + "</div>",
        unsafe_allow_html=True,
    )


def pick_product(i):
    v = st.session_state.get(f"pick{i}", "Custom")
    if v != "Custom":
        st.session_state[f"desc{i}"] = v


def bump_invoice_number():
    st.session_state["inv_no"] = next_number(st.session_state["inv_no"])


def main():
    theme()
    st.markdown(
        "<div class='hero'><h1>🌿 EcoQuill Invoice Generator</h1>"
        "<p>GSTIN, logo, bank details and terms are pre-filled every time the app starts.</p></div>",
        unsafe_allow_html=True,
    )

    # ---- Sidebar: title and optional one-off overrides ----
    st.sidebar.markdown(f"### 🌿 {COMPANY['name']}")
    st.sidebar.caption(COMPANY["tagline"])
    presets = ["TAX INVOICE", "INVOICE", "Custom"]
    mode = st.sidebar.selectbox(
        "Invoice Title", presets, index=presets.index(SETTINGS["default_title"])
    )
    title = st.sidebar.text_input("Custom Title", "") if mode == "Custom" else mode
    title = title.strip() or SETTINGS["default_title"]
    signatory = ""  # no signature on the invoice (system generated)

    logo_bytes = default_logo()
    sign_bytes = None
    with st.sidebar.expander("Replace logo (this session only)"):
        up_logo = st.file_uploader("Logo", type=["png", "jpg", "jpeg"])
        if up_logo:
            logo_bytes = up_logo.getvalue()
    if logo_bytes:
        st.sidebar.image(logo_bytes, width=140)
    else:
        st.sidebar.warning(
            "No logo found. Upload logo_data.py and assets/business_logo.png to GitHub."
        )

    # ---- Business & bank details (pre-filled, editable per invoice) ----
    with st.expander("Business and payment details (pre-filled - open only to change)"):
        c1, c2 = st.columns(2)
        co = {
            "name": c1.text_input("Business Name", COMPANY["name"]),
            "tagline": c2.text_input("Tagline", COMPANY["tagline"]),
            "address": c1.text_area("Address", COMPANY["address"]),
            "phone": c2.text_input("Phone", COMPANY["phone"]),
            "email": c2.text_input("Email", COMPANY["email"]),
            "gstin": c1.text_input("EcoQuill GSTIN", COMPANY["gstin"]),
            "website": c2.text_input("Website", COMPANY["website"]),
        }
        c1, c2 = st.columns(2)
        bank = {
            "bank_name": c1.text_input("Bank Name", BANK["bank_name"]),
            "account_name": c2.text_input("Account Name", BANK["account_name"]),
            "account_no": c1.text_input("Account Number", BANK["account_no"]),
            "ifsc": c2.text_input("IFSC Code", BANK["ifsc"]),
            "upi": c1.text_input("UPI (optional)", BANK["upi"]),
        }
        terms_text = st.text_area("Terms and Conditions", TERMS, height=120)
    terms = [x.strip() for x in terms_text.splitlines() if x.strip()]

    # ---- Customer + invoice details ----
    left, right = st.columns([1.1, 0.9])
    with left:
        st.subheader("Customer")
        name = st.text_input("Customer Name")
        address = st.text_area("Customer Address")
        phone = st.text_input("Customer Phone")
        email = st.text_input("Customer Email (optional)")
        gstin = st.text_input("Customer GSTIN (optional)")
    with right:
        st.subheader("Invoice")
        dt = st.date_input("Invoice Date", value=date.today())
        due = st.date_input("Due Date", value=dt)
        if "inv_no" not in st.session_state:
            st.session_state["inv_no"] = (
                f"{SETTINGS['invoice_prefix']}/{fin_year(dt)}/000001"
            )
        inv_no = st.text_input(
            "Invoice Number (editable)",
            key="inv_no",
            help="Type any number you like. After you download an invoice the next number is suggested automatically.",
        )
        place = st.text_input("Place of Supply", SETTINGS["default_place_of_supply"])
        paid = st.number_input("Paid Amount", min_value=0.0, step=100.0)
        packing = st.number_input(
            "Packing / Delivery Charges", min_value=0.0, step=10.0
        )

    # ---- Product rows ----
    st.subheader("Product Details")
    count = st.number_input("Product Rows", 1, 20, 1)
    items = []
    for i in range(int(count)):
        if f"desc{i}" not in st.session_state:
            st.session_state[f"desc{i}"] = PRODUCTS[0] if i == 0 else ""
        a, b = st.columns([1.2, 2.4])
        b.text_input(f"Product Description {i + 1} (editable)", key=f"desc{i}")
        a.selectbox(
            f"Quick pick {i + 1}",
            ["Custom"] + PRODUCTS,
            key=f"pick{i}",
            on_change=pick_product,
            args=(i,),
        )
        c1, c2, c3, c4 = st.columns(4)
        kg = c1.number_input(
            f"Quantity KG {i + 1}",
            min_value=0.0,
            value=1.0,
            step=1.0,
            format="%.3f",
            key=f"q{i}",
        )
        rate = c2.number_input(
            f"Rate per KG {i + 1}",
            min_value=0.0,
            value=0.0,
            step=1.0,
            format="%.2f",
            key=f"r{i}",
        )
        gst = c3.number_input(
            f"GST % {i + 1}", 0.0, 100.0, SETTINGS["default_gst"], 0.5, key=f"g{i}"
        )
        hsn = c4.text_input(f"HSN/SAC {i + 1}", SETTINGS["default_hsn"], key=f"h{i}")
        desc = st.session_state[f"desc{i}"].strip()
        if desc and kg > 0 and rate > 0:
            line = money(kg * rate)
            items.append(
                {
                    "description": desc,
                    "hsn": hsn,
                    "quantity": kg,
                    "rate": rate,
                    "gst_percent": gst,
                    "line_amount": line,
                    "gst_amount": money(line * gst / 100),
                }
            )

    taxable = money(sum(x["line_amount"] for x in items))
    gstamt = money(sum(x["gst_amount"] for x in items))
    grand = money(taxable + gstamt + packing)
    balance = money(grand - paid)
    total_qty = sum(x["quantity"] for x in items)
    metrics(
        [
            ("Total Quantity", f"{total_qty:,.3f} KG"),
            ("Taxable Value", rupee(taxable)),
            ("GST", rupee(gstamt)),
            ("Grand Total", rupee(grand)),
            ("Balance Due", rupee(balance)),
        ]
    )

    def build():
        return make_pdf(
            co,
            {
                "name": name,
                "address": address,
                "phone": phone,
                "email": email,
                "gstin": gstin,
            },
            {
                "no": inv_no,
                "date": dt.strftime("%d/%m/%Y"),
                "due": due.strftime("%d/%m/%Y"),
                "place": place,
            },
            items,
            {
                "taxable": taxable,
                "gst": gstamt,
                "packing": packing,
                "grand": grand,
                "paid": paid,
                "balance": balance,
            },
            bank,
            terms,
            title,
            logo_bytes,
            sign_bytes,
            signatory,
        )

    def valid():
        if not name.strip() or not address.strip():
            st.error("Customer name and address are required.")
            return False
        if not inv_no.strip():
            st.error("Invoice number is required.")
            return False
        if not items:
            st.error("Add at least one product with description, quantity and rate.")
            return False
        return True

    b1, b2 = st.columns(2)
    if b1.button("Preview Invoice", use_container_width=True) and valid():
        st.session_state["pdf"] = build()
        st.session_state["pdf_name"] = re.sub(r"[^A-Za-z0-9_-]", "_", inv_no) + ".pdf"
    if b2.button("Generate Invoice", use_container_width=True) and valid():
        st.session_state["pdf"] = build()
        st.session_state["pdf_name"] = re.sub(r"[^A-Za-z0-9_-]", "_", inv_no) + ".pdf"
        st.success(f"Invoice {inv_no} is ready. Download it below.")

    pdf = st.session_state.get("pdf")
    if pdf:
        st.download_button(
            "Download Invoice PDF",
            pdf,
            "EcoQuill_Invoice_" + st.session_state["pdf_name"],
            "application/pdf",
            on_click=bump_invoice_number,
            use_container_width=True,
        )
        data = base64.b64encode(pdf).decode()
        st.components.v1.html(
            f'<iframe src="data:application/pdf;base64,{data}" width="100%" height="850"></iframe>',
            height=870,
        )


if __name__ == "__main__":
    main()
