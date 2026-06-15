"""
Level 2 Sanity Checker — LLM-assisted data quality analysis.

Flow:
  1. Extract structured data from OCR text into a clean JSON block
  2. Build a parameterized prompt with the structured data
  3. Send to configured LLM endpoint
  4. Parse and return structured analysis
"""
import re
import json
import requests
from typing import Optional
from llm_config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, LLM_MAX_TOKENS, LLM_TEMPERATURE


# ===== Stage 1: Structured Data Extraction =====

def extract_structured_data(pages: list[dict]) -> dict:
    """
    Parse OCR text from all pages into a structured JSON object.
    Separates only relevant account-opening fields for the LLM prompt.
    """
    page_map = {p["page"]: p["text"] for p in pages}
    data = {}

    # --- Page 1: Cover Page ---
    if 1 in page_map:
        text = page_map[1]
        data["cover"] = {
            "sid": _extract(text, r"Nomor SID\s*:\s*([^\n]+)"),
            "customer_code": _extract(text, r"Kode Nasabah\s*:\s*([^\n]+)"),
            "customer_name": _extract(text, r"Nama Nasabah\s*:\s*([^\n]+)"),
            "sales_name": _extract(text, r"Nama Sales\s*:\s*([^\n]+)"),
        }

    # --- Page 2: Personal Data ---
    if 2 in page_map:
        text = page_map[2]
        data["personal"] = {
            "full_name": _heading_value(text, 1),
            "alias": _heading_value(text, 2),
            "place_date_of_birth": _heading_value(text, 3),
            "mothers_maiden_name": _heading_value(text, 4),
            "sex": _checkbox_value(text, "Jenis Kelamin"),
            "id_number_ktp": _heading_value(text, 6),
            "nationality": _checkbox_value(text, "Kewarganegaraan"),
            "npwp_tax_id": _heading_value(text, 8),
            "id_card_address": _heading_value(text, 9),
            "city": _subfield_value(text, "Kota"),
            "province": _subfield_value(text, "Provinsi"),
            "country": _subfield_value(text, "Negara"),
            "postal_code": _subfield_value(text, "Kode Pos"),
            "correspondence_address": _heading_value(text, 10),
            "phone": _heading_value(text, 11),
            "mobile_phone": _subfield_value(text, "Telepon Genggam"),
            "email": _heading_value(text, 12),
            "education": _checkbox_value(text, "Latar Belakang Pendidikan"),
            "religion": _checkbox_value(text, "Agama"),
            "marital_status": _checkbox_value(text, "Status Perkawinan"),
            "occupation": _checkbox_value(text, "Pekerjaan"),
            "occupation_other": _subfield_value(text, "Lainnya (Others)"),
        }

    # --- Page 2 continued: Family & Employment (items 17-25) ---
    if 2 in page_map:
        text = page_map[2]
        data["family_employment"] = {
            "spouse_or_parent_name": _heading_value(text, 17),
            "company_name": _heading_value(text, 18),
            "office_address": _heading_value(text, 19),
            "office_phone": _heading_value(text, 20),
            "business_type": _heading_value(text, 21),
            "annual_income": _checkbox_value(text, "Pendapatan per Tahun"),
            "source_of_funds": _checkbox_value(text, "Sumber Dana"),
            "investment_objective": _checkbox_value(text, "Tujuan Investasi"),
            "is_beneficial_owner": _checkbox_value(text, "Pemilik Manfaat"),
        }

    # --- Page 2: Bank Account ---
    if 2 in page_map:
        text = page_map[2]
        data["bank_account"] = {
            "account_number": _subfield_value(text, "Rekening Bank* (Bank Account) No"),
            "currency": _first_subfield_value(text, "Mata Uang"),
            "account_holder_name": _subfield_value(text, "Nama Pemilik Rekening*"),
            "bank_name_branch": _subfield_value(text, "Nama Bank dan Cabang*"),
        }

    # --- Page 4: Signature & Attachments ---
    if 4 in page_map:
        text = page_map[4]
        data["signature"] = {
            "date": _extract(text, r"\*\*Tanggal/bulan/tahun[^\n]*:[^\n]*?\*\*[^\n]*?([^\n]+)"),
            "stamp_duty_name": _extract(text, r"materai.*?:?\s*\n\n(.+)", re.IGNORECASE),
            "ktp_attached": bool(re.search(r"☑.*?</td>[\s\S]{0,200}?KTP", text, re.DOTALL)),
        }

    # --- Page 7: Beneficial Owner ---
    if 7 in page_map:
        text = page_map[7]
        data["beneficial_owner"] = {
            "name": _bo_field(text, "Nama Beneficial Owner"),
            "relationship": _bo_field(text, "Hubungan BO"),
            "birth": _bo_field(text, "Tempat.*Tanggal Lahir BO"),
            "gender": _bo_field(text, "Jenis Kelamin BO"),
            "id_number": _bo_field(text, "No\\.\\s*Identitas BO"),
            "address": _bo_field(text, "Alamat Lengkap BO"),
            "nationality": _bo_field(text, "Kewarganegaraan BO"),
        }

    return data


def _extract(text: str, pattern: str, flags: int = 0) -> Optional[str]:
    """Generic regex extractor — returns stripped value or None."""
    m = re.search(pattern, text, flags)
    if not m:
        return None
    val = m.group(1).strip()
    if not val or "blank" in val.lower() or val.startswith("**"):
        return None
    return val


def _heading_value(text: str, item_number: int) -> Optional[str]:
    """Extract value following a ### N. heading."""
    pattern = rf"###\s*{item_number}\.\s*[^\n]*\n\n([^\n]+)"
    return _extract(text, pattern)


def _checkbox_value(text: str, group_key: str) -> Optional[str]:
    """Extract the checked (☑) option from a checkbox group."""
    section_pattern = rf"###\s*\d+\.\s*{re.escape(group_key)}.*?(?=###|\Z)"
    section_match = re.search(section_pattern, text, re.DOTALL | re.MULTILINE)
    if not section_match:
        return None
    m = re.search(r"☑\s*(.+?)(?:\s{2,}|\n|$)", section_match.group(0))
    return m.group(1).strip() if m else None


def _subfield_value(text: str, field_key: str) -> Optional[str]:
    """Extract value from a **Bold Field** followed by value on next line."""
    pattern = rf"(?:\*\*)?{re.escape(field_key)}[^\n]*(?:\*\*)?[^\n]*\n([^\n]+)"
    return _extract(text, pattern)


def _first_subfield_value(text: str, field_key: str) -> Optional[str]:
    """Extract first occurrence of a bold subfield."""
    pattern = rf"(?:\*\*)?{re.escape(field_key)}[^\n]*(?:\*\*)?[^\n]*\n([^\n]+)"
    return _extract(text, pattern)


def _bo_field(text: str, field_pattern: str) -> Optional[str]:
    """Extract a Beneficial Owner field."""
    pattern = rf"\*\*{field_pattern}[^\n]*\*\*[^\n]*:([^\n]+)"
    return _extract(text, pattern)


# ===== Stage 2: Parameterized Prompt =====

SYSTEM_PROMPT = """You are a compliance data analyst for an Indonesian asset management company (Sequis Asset Management). You are reviewing data extracted via OCR from an Individual Account Opening Form.

Your task is to perform SANITY CHECKS on the extracted data. You are NOT checking for missing fields — that is done separately. Focus on:

1. **Format Validity**: Does the KTP number look valid (16 digits)? Is the email format correct? Is the phone number reasonable?
2. **Cross-Field Consistency**: Does the city match the province? (e.g., "Jakarta Timur" should be in "DKI Jakarta"). Does the birth date make the person an adult (18+)?
3. **Data Quality**: Are there OCR artifacts or garbled text? (e.g., "satria 999 @gmail.com" looks wrong). Is the name consistent across fields, does the name in each page is correct?
4. **Logical Consistency**: If marital status is "Married", is there a spouse name? If occupation is "Wiraswasta", does the company field make sense?
5. **Regulatory Flags**: Is the NPWP present? Is the FATCA declaration consistent? Is the beneficial owner information complete?

Return your analysis as a JSON object with this exact structure:
{
  "overall_assessment": "pass" | "review_needed" | "fail",
  "confidence": 0.0 to 1.0,
  "issues": [
    {
      "severity": "critical" | "warning" | "info",
      "field": "field name",
      "description": "what's wrong",
      "suggestion": "what should be checked/fixed"
    }
  ],
  "summary": "summary of all the issues in professional email format to be sent back to the sales reps"
}

Be specific and reference actual values from the data. If data looks clean, say so — don't invent issues."""


def build_prompt(structured_data: dict) -> str:
    """Build the user prompt with structured data injected."""
    data_json = json.dumps(structured_data, indent=2, ensure_ascii=False)
    return f"""Please perform a sanity check on the following account opening form data extracted via OCR.

== EXTRACTED DATA ==
```json
{data_json}
```

== INSTRUCTIONS ==
Analyze the data for format validity, cross-field consistency, OCR artifacts, logical consistency, and regulatory compliance issues. Return your analysis as the specified JSON structure."""


# ===== Stage 3: LLM Call =====

def call_llm(prompt: str, system: str = SYSTEM_PROMPT) -> str:
    """Send a chat completion request to the configured LLM endpoint."""
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": LLM_MAX_TOKENS,
        "temperature": LLM_TEMPERATURE,
        "top_p": 0.9,
        "cache_prompt": False,
    }
    headers = {"Authorization": f"Bearer {LLM_API_KEY}"} if LLM_API_KEY != "not-needed" else {}

    response = requests.post(f"{LLM_BASE_URL}/chat/completions", json=payload, headers=headers, timeout=120)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def parse_llm_response(raw: str) -> dict:
    """Extract JSON from the LLM response, handling markdown code blocks."""
    # Try to find JSON in the response
    json_match = re.search(r"```(?:json)?\s*\n([\s\S]*?)\n```", raw)
    if json_match:
        raw = json_match.group(1)

    # Try parsing as-is
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Try to find a JSON object in the text
    brace_match = re.search(r"\{[\s\S]*\}", raw)
    if brace_match:
        try:
            return json.loads(brace_match.group(0))
        except json.JSONDecodeError:
            pass

    # Fallback: return raw text as summary
    return {
        "overall_assessment": "review_needed",
        "confidence": 0.0,
        "issues": [],
        "summary": raw,
        "_raw_response": True,
    }


# ===== Main Entry Point =====

def run_sanity_check(pages: list[dict]) -> dict:
    """
    Full Level 2 sanity check pipeline:
    1. Extract structured data from OCR pages
    2. Build parameterized prompt
    3. Call LLM
    4. Parse and return structured analysis
    """
    structured_data = extract_structured_data(pages)
    prompt = build_prompt(structured_data)

    raw_response = call_llm(prompt)
    analysis = parse_llm_response(raw_response)

    return {
        "extracted_data": structured_data,
        "analysis": analysis,
        "raw_response": raw_response,
    }
