"""Generate a small, fictional services agreement used for demos, tests, and evaluation.

Run from the backend folder:  uv run python ../samples/make_sample_pdf.py
"""

from pathlib import Path

from fpdf import FPDF

PAGES = [
    (
        "Master Services Agreement - Northwind Logistics and Contoso Cloud",
        [
            "1. Parties. This Master Services Agreement is entered into between Northwind Logistics "
            "(the Customer) and Contoso Cloud (the Provider), effective January 1, 2026.",
            "2. Term. The initial term is three (3) years. The agreement renews automatically for "
            "successive one-year terms unless either party gives ninety (90) days written notice.",
            "3. Services. The Provider shall host and operate the Customer's shipment tracking "
            "platform, including the web portal, public API, and nightly data exports.",
        ],
    ),
    (
        "Service Levels and Support",
        [
            "4. Availability. The Provider shall maintain 99.9% monthly availability for the "
            "production environment, excluding scheduled maintenance announced 72 hours in advance.",
            "5. Incident Response. Severity 1 incidents must be acknowledged within 15 minutes and "
            "resolved or mitigated within 4 hours. Severity 2 incidents must be acknowledged within 1 hour.",
            "6. Service Credits. If availability falls below 99.9%, the Customer is entitled to a "
            "credit of 10% of the monthly fee for each full 0.5% below the target, capped at 50%.",
            "7. Reporting. The Provider shall deliver a monthly service report by the fifth business "
            "day of each month covering availability, incidents, and open change requests.",
        ],
    ),
    (
        "Security, Data, and Fees",
        [
            "8. Encryption. All Customer data must be encrypted at rest using AES-256 and in transit "
            "using TLS 1.2 or higher.",
            "9. Breach Notification. The Provider shall notify the Customer of any confirmed security "
            "breach affecting Customer data within 24 hours of discovery.",
            "10. Data Residency. Customer data shall be stored only in data centers located in the "
            "European Union.",
            "11. Fees and Invoicing. The monthly fee is EUR 42,000. Invoices are payable within "
            "thirty (30) days of receipt. Late payments may accrue interest of 1% per month.",
            "12. Termination. Either party may terminate for material breach if the breach is not "
            "cured within thirty (30) days of written notice.",
        ],
    ),
]


def main() -> None:
    pdf = FPDF()
    pdf.set_margins(20, 20, 20)
    for title, paragraphs in PAGES:
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 14)
        pdf.multi_cell(0, 8, title)
        pdf.ln(4)
        pdf.set_font("Helvetica", size=11)
        for para in paragraphs:
            pdf.multi_cell(0, 6, para)
            pdf.ln(3)
    out = Path(__file__).parent / "sample_services_agreement.pdf"
    pdf.output(str(out))
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
