"""Write the fictional Extract v1/v2 comparison corpus (spec 0004).

Every document is generated deterministically so that both index arms, and any
re-run, use byte-identical files. All names and values are fictional (CC0).

    python scripts/extract_ab/make_corpus.py /tmp/extract-ab/corpus
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pymupdf

PAGE = (612, 792)
ZIP_TIME = (2026, 1, 1, 0, 0, 0)

# C1: each pair is (subject paragraph, value paragraph) in one column. The value
# paragraph never repeats the subject, so it only makes sense next to it.
TWO_COLUMN_PAGES = [
    {
        "left": [
            "The Harbor Point depot sits at the end of the old ferry road and serves "
            "the coastal routes. Drivers who start there collect their route sheets "
            "from the dispatch window beside the loading bay, and new staff are shown "
            "the yard layout on their first morning.",
            "On weekdays the gates open at 05:40, and the last vehicle must be checked "
            "in by 21:15. Visitors sign in at the gatehouse and wear an orange pass "
            "while they are on site.",
            "Brackenfield office handles invoices for all sites. Its team answers "
            "supplier questions by email and keeps a printed copy of each signed "
            "purchase order in the archive room.",
        ],
        "right": [
            "Kestrel Yard is the smaller inland site that handles refrigerated "
            "freight for the valley farms. Its crew rotates every four weeks between "
            "the cold rooms and the outbound docks so that everyone keeps both skills "
            "current.",
            "The cold rooms there are held at 2 degrees Celsius, and each door alarm "
            "sounds after 90 seconds open. Pallets that wait longer than 40 minutes "
            "on the dock are returned to the cold room.",
            "Notice boards in every canteen list the current shift leads, the first "
            "aid contacts and the date of the next site meeting.",
        ],
    },
    {
        "left": [
            "Moorland Crossing is the refuelling stop that every long-haul vehicle "
            "passes on the northern loop. It also keeps a small parts store for "
            "wiper blades, bulbs and fuses, and a rest room with showers.",
            "Its fuel pumps are serviced every 11 days, and the parts store closes "
            "at 18:30 on Saturdays. Receipts are scanned at the counter before the "
            "driver leaves.",
            "Route planners meet on Tuesday mornings to review delays from the "
            "previous week and agree any changes to the published timetables.",
        ],
        "right": [
            "The Saltmarsh Annex is where new drivers complete their classroom "
            "induction before their first supervised shift. It has two classrooms, "
            "a small library of route maps and a driving simulator.",
            "Induction there lasts 3 days, and the simulator can be booked in blocks "
            "of 45 minutes. Trainees bring their licence and a signed medical form "
            "on the first day.",
            "Lost property found in vehicles is logged by the shift lead and kept "
            "for one month before it is donated.",
        ],
    },
    {
        "left": [
            "Ashby Lantern Works is the main vehicle workshop for the whole fleet. "
            "Mechanics there rebuild gearboxes, replace brake lines and carry out "
            "the yearly safety inspection for every truck and van.",
            "Tyre pressure there is checked against a limit of 8.2 bar, and any "
            "vehicle that fails twice is sent for a full inspection. Results are "
            "written in the vehicle logbook.",
            "Each site keeps a spill kit near the fuel store and checks its contents "
            "at the start of every month.",
        ],
        "right": [
            "Fenwick Quay is the ferry terminal used for freight to the islands. "
            "Trailers are staged in marked lanes while the crossing is loaded, and "
            "drivers wait in the terminal lounge.",
            "The last ferry departs at 19:50, and freight must be booked 36 hours "
            "ahead. Hazardous loads need a separate declaration form.",
            "Uniform orders are placed through the people team twice a year, in "
            "March and in September.",
        ],
    },
]

SERVICES = [
    "Drain survey",
    "Roof inspection",
    "Cold storage audit",
    "Boiler service",
    "Fire door check",
    "Lift maintenance",
    "Window repair",
    "Pest control visit",
    "Electrical testing",
    "Gutter clearing",
    "Lighting upgrade",
    "Floor resurfacing",
    "Security patrol",
    "Water hygiene test",
    "Ventilation clean",
]
REGIONS = ["North", "South", "East", "West"]
RATE_HEADER = ["Code", "Service", "Region", "Hourly rate (EUR)", "Response time (h)"]


def rate_rows() -> list[list[str]]:
    rows = []
    for index in range(60):
        service = SERVICES[index // 4]
        region = REGIONS[index % 4]
        rate = 28 + ((index * 173) % 480) * 0.05
        hours = 2 + (index * 7) % 46
        rows.append([f"SR-{101 + index}", service, region, f"{rate:.2f}", str(hours)])
    return rows


# C3: the body text never names the part, so only headings tell them apart.
HANDBOOK = {
    "title": "Staff Handbook",
    "parts": [
        (
            "Part A: Employees",
            "A",
            {"notice": "37", "equipment": "5", "expense": "450"},
        ),
        (
            "Part B: Contractors",
            "B",
            {"notice": "14", "equipment": "2", "expense": "120"},
        ),
        ("Part C: Interns", "C", {"notice": "7", "equipment": "10", "expense": "60"}),
    ],
}
OVERVIEW = (
    "This part sets out the rules that apply to the people it covers. Read it with "
    "the general conduct rules at the start of the handbook. Where a local "
    "agreement gives a better entitlement, the local agreement applies. Questions "
    "about any rule in this part go to the people team, who keep a record of each "
    "question and the answer given. Rules are reviewed every January and changes "
    "are announced at least one month before they take effect."
)


def handbook_sections(values: dict[str, str]) -> list[tuple[str, str]]:
    return [
        ("Overview", OVERVIEW),
        (
            "Notice period",
            f"The notice period is {values['notice']} calendar days. It starts on "
            "the day after written notice is received by the people team. Notice "
            "can be shortened only by written agreement, and unused leave is "
            "settled in the final payment.",
        ),
        (
            "Equipment return",
            f"Laptops, badges and keys must be returned within {values['equipment']} "
            "working days of the last working day. Items are returned to the site "
            "reception, which issues a signed receipt for each item.",
        ),
        (
            "Expense limit",
            f"Travel and meal expenses are reimbursed up to EUR {values['expense']} "
            "per month. Claims need receipts and must be submitted within two "
            "months of the expense.",
        ),
    ]


SCANNED_PAGES = [
    [
        "Memo from the facilities team about the Quarry Lane warehouse canteen. "
        "From the first Monday of next month the canteen will open earlier, and "
        "breakfast will be served from 06:15 until 09:00 every weekday.",
        "The night bus between Quarry Lane and the town centre is changing. The new "
        "timetable adds a final departure at 23:40, and staff passes must be shown "
        "to the driver when boarding.",
    ],
    [
        "Fire drill planning for the Linden Street office. The next unannounced "
        "drill will be held during the second week of March, and the assembly "
        "point moves to the north car park.",
        "Locker renewals at the Linden Street office. Locker keys must be returned "
        "by 30 April, and a replacement key costs EUR 12 at the front desk.",
    ],
]

VENDOR_HEADER = ["Vendor", "Service", "Contract end", "Account manager"]
VENDORS = [
    ["Larkspur Freight", "Overflow haulage", "2027-03-31", "Dara Whitlock"],
    ["Copperline Print", "Printed forms", "2026-11-30", "Mira Okafor"],
    ["Tidewell Cleaning", "Window cleaning", "2027-06-30", "Joel Brandt"],
    ["Northgate Uniforms", "Workwear supply", "2026-12-31", "Aisha Romero"],
    ["Bellmoor Catering", "Canteen food", "2027-01-31", "Pavel Lindqvist"],
    ["Greystone Security", "Night guarding", "2027-09-30", "Hana Mercer"],
    ["Orchard Waste", "Waste collection", "2026-10-31", "Tomas Ferro"],
    ["Silverbank Couriers", "Document courier", "2027-04-30", "Leah Duvall"],
    ["Pinecrest Fleet Hire", "Spare van hire", "2027-02-28", "Omar Castell"],
    ["Ridgeway Tyres", "Tyre fitting", "2027-08-31", "Ines Calder"],
    ["Hollybrook IT", "Laptop support", "2027-05-31", "Ravi Thorne"],
    ["Marlow Signs", "Site signage", "2026-12-15", "Greta Hollis"],
]

EQUIPMENT_HEADER = ["Asset tag", "Equipment", "Location", "Last calibrated"]
EQUIPMENT_KINDS = [
    "Torque wrench",
    "Pallet scale",
    "Tyre gauge",
    "Gas detector",
    "Thermometer",
]
EQUIPMENT_LOCATIONS = [
    "Harbor Point depot",
    "Kestrel Yard",
    "Ashby Lantern Works",
    "Fenwick Quay",
]


def equipment_rows() -> list[list[str]]:
    rows = []
    for index in range(30):
        month = 1 + (index * 5) % 12
        day = 1 + (index * 11) % 28
        rows.append(
            [
                f"EQ-{1001 + index}",
                EQUIPMENT_KINDS[index % 5],
                EQUIPMENT_LOCATIONS[(index * 3) % 4],
                f"2026-{month:02d}-{day:02d}",
            ]
        )
    return rows


BUDGET_HEADER = ["Department", "Quarter", "Approved budget (EUR)"]
DEPARTMENTS = ["Logistics", "Maintenance", "Training", "Customer service"]


def budget_rows() -> list[list[str]]:
    rows = []
    for d_index, department in enumerate(DEPARTMENTS):
        for quarter in range(1, 5):
            amount = 90000 + ((d_index * 4 + quarter) * 23500) % 140000
            rows.append([department, f"Q{quarter}", str(amount)])
    return rows


TRAVEL_POLICY = [
    "Travel policy",
    "Staff who travel for work book rail tickets through the travel desk at least "
    "five working days before the journey. Standard class is used for journeys "
    "under three hours.",
    "Hotel stays are booked for a maximum of EUR 140 per night outside the capital "
    "and EUR 190 per night in the capital. Breakfast is included where the hotel "
    "offers it.",
    "Mileage for private cars used on company business is paid at EUR 0.32 per "
    "kilometre. The journey must be recorded in the mileage log within one week.",
    "Taxis are allowed only when no public transport runs, or when carrying "
    "equipment heavier than 15 kilograms.",
]

FAQ = """Frequently asked questions

How do I reset my staff portal password?
Use the "Forgot password" link on the portal sign-in page. The reset link is valid for 20 minutes.

Who do I call if a vehicle breaks down?
Call the fleet desk on extension 4417. The desk is staffed 24 hours a day.

When are payslips published?
Payslips are published in the staff portal on the 26th of each month.

Can I swap a shift with a colleague?
Yes. Both people must agree and the shift lead must approve the swap at least 48 hours before the shift starts.
"""


def _save_pdf(document: pymupdf.Document, path: Path) -> None:
    document.set_metadata({})
    document.save(path, garbage=3, deflate=True, no_new_id=True)


def save_two_column_pdf(path: Path) -> None:
    with pymupdf.open() as document:
        for spec in TWO_COLUMN_PAGES:
            page = document.new_page(width=PAGE[0], height=PAGE[1])
            for index in range(3):
                top = 72 + index * 140
                page.insert_textbox(
                    pymupdf.Rect(54, top, 290, top + 120),
                    spec["left"][index],
                    fontsize=10,
                )
                # The right column is offset so v1's top-to-bottom block sort
                # interleaves it with the left column.
                page.insert_textbox(
                    pymupdf.Rect(322, top + 15, 558, top + 135),
                    spec["right"][index],
                    fontsize=10,
                )
        _save_pdf(document, path)


def save_rates_pdf(path: Path) -> None:
    widths = [60, 150, 70, 120, 120]
    x_values = [46]
    for width in widths:
        x_values.append(x_values[-1] + width)
    rows = rate_rows()
    pages = [[RATE_HEADER, *rows[:40]], rows[40:]]
    with pymupdf.open() as document:
        for page_rows in pages:
            page = document.new_page(width=PAGE[0], height=PAGE[1])
            y_values = [50 + index * 16 for index in range(len(page_rows) + 1)]
            for x in x_values:
                page.draw_line((x, y_values[0]), (x, y_values[-1]))
            for y in y_values:
                page.draw_line((x_values[0], y), (x_values[-1], y))
            for row_index, row in enumerate(page_rows):
                for column, value in enumerate(row):
                    page.insert_text(
                        (x_values[column] + 5, y_values[row_index] + 11),
                        value,
                        fontsize=8,
                    )
        _save_pdf(document, path)


def save_handbook_pdf(path: Path) -> None:
    with pymupdf.open() as document:
        for part_index, (heading, letter, values) in enumerate(HANDBOOK["parts"]):
            page = document.new_page(width=PAGE[0], height=PAGE[1])
            top = 50
            if part_index == 0:
                page.insert_text(
                    (54, top + 24), HANDBOOK["title"], fontsize=24, fontname="hebo"
                )
                top += 50
            page.insert_text((54, top + 18), heading, fontsize=18, fontname="hebo")
            top += 36
            for number, (title, body) in enumerate(handbook_sections(values), start=1):
                page.insert_text(
                    (54, top + 13),
                    f"{letter}.{number} {title}",
                    fontsize=13,
                    fontname="hebo",
                )
                top += 22
                rect = pymupdf.Rect(54, top, 558, top + 140)
                spare = page.insert_textbox(rect, body, fontsize=11, fontname="helv")
                top += 140 - spare + 16
        _save_pdf(document, path)


def save_scanned_pdf(path: Path) -> None:
    with pymupdf.open() as scanned:
        for paragraphs in SCANNED_PAGES:
            with pymupdf.open() as native:
                page = native.new_page(width=PAGE[0], height=PAGE[1])
                top = 90
                for paragraph in paragraphs:
                    rect = pymupdf.Rect(72, top, 540, top + 260)
                    spare = page.insert_textbox(rect, paragraph, fontsize=17)
                    top += 260 - spare + 40
                image = page.get_pixmap(dpi=200, colorspace=pymupdf.csGRAY, alpha=False)
            target = scanned.new_page(width=PAGE[0], height=PAGE[1])
            target.insert_image(target.rect, stream=image.tobytes("png"))
        _save_pdf(scanned, path)


def save_travel_policy_pdf(path: Path) -> None:
    with pymupdf.open() as document:
        page = document.new_page(width=PAGE[0], height=PAGE[1])
        top = 72
        for index, paragraph in enumerate(TRAVEL_POLICY):
            size = 16 if index == 0 else 11
            rect = pymupdf.Rect(72, top, 540, top + 160)
            spare = page.insert_textbox(rect, paragraph, fontsize=size)
            top += 160 - spare + 14
        _save_pdf(document, path)


def _zip(files: dict[str, str]) -> bytes:
    output = io.BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, value in files.items():
            info = ZipInfo(name, date_time=ZIP_TIME)
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, value)
    return output.getvalue()


def vendor_docx_bytes() -> bytes:
    def paragraph(text: str, style: str | None = None) -> str:
        properties = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
        return f"<w:p>{properties}<w:r><w:t>{escape(text)}</w:t></w:r></w:p>"

    def row(values: list[str]) -> str:
        cells = "".join(f"<w:tc>{paragraph(value)}</w:tc>" for value in values)
        return f"<w:tr>{cells}</w:tr>"

    table = "".join(row(values) for values in [VENDOR_HEADER, *VENDORS])
    body = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        + paragraph("Vendor register", "Heading1")
        + paragraph("Current contracts held by the purchasing team.")
        + f"<w:tbl>{table}</w:tbl>"
        + "</w:body></w:document>"
    )
    return _zip(
        {
            "[Content_Types].xml": (
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Override PartName="/word/document.xml" ContentType="application/'
                'vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                "</Types>"
            ),
            "word/document.xml": body,
        }
    )


def budget_xlsx_bytes() -> bytes:
    def cell(value: str) -> str:
        if value.isdigit():
            return f"<c><v>{value}</v></c>"
        return f"<c t='inlineStr'><is><t>{escape(value)}</t></is></c>"

    rows = "".join(
        "<row>" + "".join(cell(value) for value in values) + "</row>"
        for values in [BUDGET_HEADER, *budget_rows()]
    )
    namespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    return _zip(
        {
            "[Content_Types].xml": (
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>'
            ),
            "xl/workbook.xml": f'<workbook xmlns="{namespace}"/>',
            "xl/worksheets/sheet1.xml": (
                f'<worksheet xmlns="{namespace}"><sheetData>{rows}</sheetData></worksheet>'
            ),
        }
    )


def equipment_csv_bytes() -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(EQUIPMENT_HEADER)
    writer.writerows(equipment_rows())
    return output.getvalue().encode()


DOCUMENTS = [
    ("field-guide-two-column.pdf", "C1", "F1 reading order"),
    ("service-rates.pdf", "C2", "F2 PDF tables"),
    ("staff-handbook.pdf", "C3", "F3/F4/F10 headings"),
    ("scanned-memo.pdf", "C4", "F5 OCR paragraphs"),
    ("vendor-register.docx", "C5", "F8 DOCX tables"),
    ("equipment.csv", "C6", "F8 CSV tables"),
    ("budget.xlsx", "C6", "F8 XLSX tables"),
    ("travel-policy.pdf", "K1", "control"),
    ("faq.txt", "K2", "control"),
]


def write_corpus(directory: Path) -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    save_two_column_pdf(directory / "field-guide-two-column.pdf")
    save_rates_pdf(directory / "service-rates.pdf")
    save_handbook_pdf(directory / "staff-handbook.pdf")
    save_scanned_pdf(directory / "scanned-memo.pdf")
    (directory / "vendor-register.docx").write_bytes(vendor_docx_bytes())
    (directory / "equipment.csv").write_bytes(equipment_csv_bytes())
    (directory / "budget.xlsx").write_bytes(budget_xlsx_bytes())
    save_travel_policy_pdf(directory / "travel-policy.pdf")
    (directory / "faq.txt").write_text(FAQ, encoding="utf-8", newline="\n")
    manifest = {
        "corpus": "extract-ab-v1",
        "documents": [
            {
                "filename": name,
                "category": category,
                "targets": target,
                "sha256": hashlib.sha256((directory / name).read_bytes()).hexdigest(),
            }
            for name, category, target in DOCUMENTS
        ],
    }
    (directory / "corpus-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )
    return manifest


def source_text() -> dict[str, str]:
    """The authored text of each document, for checking question expectations."""

    def table(header, rows):
        return "\n".join(" | ".join(row) for row in [header, *rows])

    handbook = [HANDBOOK["title"]]
    for heading, letter, values in HANDBOOK["parts"]:
        handbook.append(heading)
        for number, (title, body) in enumerate(handbook_sections(values), start=1):
            handbook.extend([f"{letter}.{number} {title}", body])
    return {
        "field-guide-two-column.pdf": "\n".join(
            text
            for page in TWO_COLUMN_PAGES
            for side in ("left", "right")
            for text in page[side]
        ),
        "service-rates.pdf": table(RATE_HEADER, rate_rows()),
        "staff-handbook.pdf": "\n".join(handbook),
        "scanned-memo.pdf": "\n".join(text for page in SCANNED_PAGES for text in page),
        "vendor-register.docx": table(VENDOR_HEADER, VENDORS),
        "equipment.csv": table(EQUIPMENT_HEADER, equipment_rows()),
        "budget.xlsx": table(BUDGET_HEADER, budget_rows()),
        "travel-policy.pdf": "\n".join(TRAVEL_POLICY),
        "faq.txt": FAQ,
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: make_corpus.py <output directory>")
    print(json.dumps(write_corpus(Path(sys.argv[1])), indent=2))
