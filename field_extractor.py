"""
Extracts structured field data from OCR text output.
Works on the markdown-formatted text produced by the llama-server OCR pipeline.
"""
import re
from typing import Optional


def extract_field_value(text: str, pattern: str) -> Optional[str]:
    """Extract a field value using regex. Returns None if blank/missing."""
    match = re.search(pattern, text, re.MULTILINE)
    if not match:
        return None
    value = match.group(1).strip() if match.lastindex else match.group(0).strip()
    # Treat empty/whitespace-only as missing
    if not value:
        return None
    blank_markers = ["*(blank)*", "*blank*", "[MISSING", "*(Blank)*"]
    if any(bm.lower() in value.lower() for bm in blank_markers):
        return None
    return value


def extract_checkbox_selections(text: str, group_key: str) -> list[str]:
    """Find which checkboxes are checked (☑) in a section around group_key."""
    section_pattern = rf"###\s*\d+\.\s*{re.escape(group_key)}.*?(?=###|\Z)"
    section_match = re.search(section_pattern, text, re.DOTALL | re.MULTILINE)
    if not section_match:
        return []
    section_text = section_match.group(0)

    checked = []
    for m in re.finditer(r"☑\s*(.+?)(?:\s{2,}|\n|$)", section_text):
        checked.append(m.group(1).strip())
    return checked


def count_investor_profile_answers(text: str) -> int:
    """Count how many investor profile questions have ☑ selections on page 5."""
    return len(re.findall(r"☑", text))


def check_page4_signature(text: str) -> dict:
    """Check page 4 for date and signature completeness."""
    result = {}

    date_match = re.search(r"\*\*Tanggal/bulan/tahun[^\n]*:[^\n]*?\*\*[^\n]*?([^\n]+)", text)
    if date_match:
        date_val = date_match.group(1).strip()
        result["date"] = date_val if date_val and "blank" not in date_val.lower() else None
    else:
        result["date"] = None

    stamp_match = re.search(r"materai.*?:?\s*\n\n(.+)", text, re.IGNORECASE)
    result["stamp_duty"] = bool(stamp_match and stamp_match.group(1).strip())

    # KTP checkbox and KTP label are in separate <td> cells — check for ☑ near KTP
    # in table rows: <td>☑</td>\n      <td>...KTP...</td>
    result["ktp_attached"] = bool(
        re.search(r"☑.*?</td>[\s\S]{0,200}?KTP", text, re.DOTALL)
        or re.search(r"☑.*?</td>[\s\S]{0,200}?Paspor", text, re.DOTALL)
    )

    return result


def extract_page_header_info(text: str) -> dict:
    """Extract SID, customer code, name from page 1."""
    info = {}
    sid_match = re.search(r"Nomor SID\s*:\s*(.+)", text)
    info["sid"] = sid_match.group(1).strip() if sid_match else None

    code_match = re.search(r"Kode Nasabah\s*:\s*(.+)", text)
    info["customer_code"] = code_match.group(1).strip() if code_match else None

    name_match = re.search(r"Nama Nasabah\s*:\s*(.+)", text)
    info["customer_name"] = name_match.group(1).strip() if name_match else None

    sales_match = re.search(r"Nama Sales\s*:\s*(.+)", text)
    info["sales_name"] = sales_match.group(1).strip() if sales_match else None

    return info


def extract_beneficial_owner(text: str) -> dict:
    """Extract Beneficial Owner fields from page 7."""
    bo_fields = {
        "name": r"\*\*Nama Beneficial Owner[^\n]*\*\*[^\n]*:([^\n]+)",
        "relationship": r"\*\*Hubungan BO[^\n]*\*\*[^\n]*:([^\n]+)",
        "birth": r"\*\*Tempat[^\n]*Tanggal Lahir BO[^\n]*\*\*[^\n]*:([^\n]+)",
        "gender": r"\*\*Jenis Kelamin BO[^\n]*\*\*[^\n]*:([^\n]+)",
        "id_number": r"\*\*No\.\s*Identitas BO[^\n]*\*\*[^\n]*:([^\n]+)",
        "address": r"\*\*Alamat Lengkap BO[^\n]*\*\*[^\n]*:([^\n]+)",
        "nationality": r"\*\*Kewarganegaraan BO[^\n]*\*\*[^\n]*:([^\n]+)",
    }

    result = {}
    for field, pattern in bo_fields.items():
        value = extract_field_value(text, pattern)
        result[field] = value
    return result
