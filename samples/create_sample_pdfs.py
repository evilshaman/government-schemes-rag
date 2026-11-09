"""
Generates clean, valid sample PDF guideline circulars for offline parsing and verification.
"""

import os
from typing import List


def generate_pdf_bytes(lines: List[str]) -> bytes:
    """
    Constructs a well-formed single-page PDF with standard Helvetica typography and correct xref offsets.
    """
    stream_lines = ["BT", "/F1 11 Tf", "50 740 Td", "15 TL"]
    for l in lines:
        escaped = (
            l.replace("\\", "\\\\")
            .replace("(", "\\(")
            .replace(")", "\\)")
        )
        stream_lines.append(f"({escaped}) Tj")
        stream_lines.append("T*")
    stream_lines.append("ET")
    stream_bytes = "\n".join(stream_lines).encode("latin-1")

    body = [b"%PDF-1.4"]
    offsets = []

    def add_obj(content: bytes):
        offsets.append(sum(len(b) + 1 for b in body))
        body.append(content)

    add_obj(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj")
    add_obj(b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj")
    add_obj(
        f"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj".encode(
            "latin-1"
        )
    )
    add_obj(
        f"4 0 obj\n<< /Length {len(stream_bytes)} >>\nstream\n".encode("latin-1")
        + stream_bytes
        + b"\nendstream\nendobj"
    )
    add_obj(b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj")

    startxref = sum(len(b) + 1 for b in body)
    xref = [b"xref", f"0 {len(offsets) + 1}".encode("latin-1"), b"0000000000 65535 f "]
    for off in offsets:
        xref.append(f"{off:010d} 00000 n ".encode("latin-1"))
    trailer = (
        b"trailer\n<< /Size "
        + str(len(offsets) + 1).encode("latin-1")
        + b" /Root 1 0 R >>\nstartxref\n"
        + str(startxref).encode("latin-1")
        + b"\n%%EOF"
    )

    return b"\n".join(body) + b"\n" + b"\n".join(xref) + b"\n" + trailer


def main():
    guidelines_dir = os.path.join(os.path.dirname(__file__), "guidelines")
    os.makedirs(guidelines_dir, exist_ok=True)

    # 1. PMEGP Sample Circular
    pmegp_lines = [
        "GOVERNMENT OF INDIA - MINISTRY OF MSME",
        "OPERATIONAL GUIDELINES: PRIME MINISTER EMPLOYMENT GENERATION PROGRAMME (PMEGP)",
        "",
        "1. Overview & Objective:",
        "To generate continuous self-employment opportunities for micro enterprises in rural and urban areas.",
        "",
        "2. Eligibility Criteria:",
        "1. Any individual above 18 years of age is eligible to apply.",
        "2. Minimum VIII standard pass required for manufacturing projects above Rs 10 Lakh.",
        "3. Only new greenfield enterprises are eligible for initial funding.",
        "4. Self Help Groups (SHGs) and Charitable Trusts are also eligible.",
        "",
        "3. Financial Assistance and Subsidy:",
        "1. Margin money subsidy of 35 % margin money subsidy for rural special categories.",
        "2. General category gets 15 percent urban and 25 percent rural subsidy.",
        "3. Maximum project cost cap is Rs 50 Lakh for manufacturing and Rs 20 Lakh for services.",
        "",
        "4. Documents Required:",
        "1. Aadhaar Card and PAN Card",
        "2. Detailed Project Report (DPR)",
        "3. Educational Marksheet (Class 8th Certificate)",
        "4. Special Category / Caste Certificate if applicable",
        "5. Gram Panchayat Rural Certificate",
    ]
    pmegp_path = os.path.join(guidelines_dir, "pmegp_guidelines.pdf")
    with open(pmegp_path, "wb") as f:
        f.write(generate_pdf_bytes(pmegp_lines))
    print(f"Generated: {pmegp_path}")

    # 2. ZED Sample Circular
    zed_lines = [
        "MINISTRY OF MICRO, SMALL AND MEDIUM ENTERPRISES",
        "MSME SUSTAINABLE (ZED) CERTIFICATION SCHEME OPERATIONAL CIRCULAR",
        "",
        "1. Policy Objective:",
        "To facilitate MSMEs to adopt Zero Defect Zero Effect manufacturing practices and attain world-class standards.",
        "",
        "2. Qualifying Criteria:",
        "1. Open to all Micro, Small, and Medium Enterprises with valid Udyam Registration.",
        "2. Applicable exclusively to active manufacturing units across all industrial sectors.",
        "3. 10 percent additional subsidy for women and SC/ST owned manufacturing units.",
        "",
        "3. Quantum of Assistance:",
        "1. Subsidy of 80 % subsidy on assessment and certification fees for Micro enterprises.",
        "2. 60 percent subsidy for Small enterprises and 50 percent for Medium enterprises.",
        "3. Maximum financial assistance cap of Rs 5 Lakh per enterprise.",
        "",
        "4. Mandatory Documents Checklist:",
        "1. Udyam Registration Certificate",
        "2. Factory License or Consent to Operate",
        "3. Self-declaration on energy and quality compliance",
        "4. Bank Account Details and Cancelled Cheque",
    ]
    zed_path = os.path.join(guidelines_dir, "zed_guidelines.pdf")
    with open(zed_path, "wb") as f:
        f.write(generate_pdf_bytes(zed_lines))
    print(f"Generated: {zed_path}")


if __name__ == "__main__":
    main()
