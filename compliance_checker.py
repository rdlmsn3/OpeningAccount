"""
Core compliance checking logic.
Analyzes OCR-extracted text against defined rules and produces a structured report.
"""
import re
from typing import Optional
from field_extractor import (
    extract_field_value,
    extract_checkbox_selections,
    count_investor_profile_answers,
    check_page4_signature,
    extract_page_header_info,
    extract_beneficial_owner,
)
from compliance_rules import (
    PAGE_1_REQUIRED,
    PAGE_2_REQUIRED_FIELDS,
    REQUIRED_SELECTIONS,
    PAGE_4_REQUIRED,
    PAGE_5_MINIMUM_ANSWERS,
    PAGE_7_REQUIRED,
)


def check_field(text: str, field: dict) -> dict:
    """Check a single required field. Returns {field, label, status, value}."""
    value = extract_field_value(text, field["pattern"])
    return {
        "field": field["key"],
        "label": field["label"],
        "status": "present" if value else "missing",
        "value": value,
    }


def check_selection(text: str, selection: dict) -> dict:
    """Check a checkbox radio group has at least one selection."""
    selected = extract_checkbox_selections(text, selection["key"])
    return {
        "field": selection["key"],
        "label": selection["key"],
        "status": "present" if selected else "missing",
        "value": selected,
    }


def _check_page1(text: str) -> dict:
    """Check page 1 cover page fields."""
    header_info = extract_page_header_info(text)
    issues = []

    for field_name in PAGE_1_REQUIRED:
        key_lower = field_name.lower()
        if key_lower not in text.lower():
            issues.append(field_name)
            continue
        val = re.search(rf"{re.escape(field_name)}\s*:\s*([^\n]+)", text)
        if val and not any(b in val.group(1).lower() for b in ["*(blank)*", "*blank*"]):
            pass  # OK
        else:
            issues.append(field_name)

    return {
        "status": "complete" if not issues else "incomplete",
        "customer_info": header_info,
        "issues": issues,
    }


def _check_page2(text: str) -> dict:
    """Check page 2 personal data fields and checkbox selections."""
    results = []

    for field in PAGE_2_REQUIRED_FIELDS:
        results.append(check_field(text, field))

    for selection in REQUIRED_SELECTIONS:
        results.append(check_selection(text, selection))

    missing = [r for r in results if r["status"] == "missing"]
    return {
        "status": "complete" if not missing else "incomplete",
        "total_fields": len(results),
        "missing_count": len(missing),
        "details": results,
    }


def _check_page4(text: str) -> dict:
    """Check page 4 signature and attachments."""
    page4 = check_page4_signature(text)
    issues = []

    if not page4["date"]:
        issues.append("Tanggal (Date) missing")

    if not page4["ktp_attached"]:
        issues.append("KTP/Passport copy not marked as attached")

    return {
        "status": "complete" if not issues else "incomplete",
        "details": page4,
        "issues": issues,
    }


def _check_page5(text: str) -> dict:
    """Check page 5 investor profile — minimum answers required."""
    answer_count = count_investor_profile_answers(text)
    return {
        "status": "complete" if answer_count >= PAGE_5_MINIMUM_ANSWERS else "incomplete",
        "answers_found": answer_count,
        "minimum_required": PAGE_5_MINIMUM_ANSWERS,
    }


def _check_page7(text: str) -> dict:
    """Check page 7 beneficial owner fields."""
    bo_data = extract_beneficial_owner(text)
    issues = []

    for field in PAGE_7_REQUIRED:
        value = extract_field_value(text, field["pattern"])
        if not value:
            issues.append(field["label"])

    return {
        "status": "complete" if not issues else "incomplete",
        "details": bo_data,
        "issues": issues,
    }


def run_compliance_check(pages: list[dict]) -> dict:
    """
    Run full compliance check on OCR-extracted pages.

    Args:
        pages: List of {"page": int, "text": str} dicts from OCR output.

    Returns:
        Structured compliance report with score, missing fields, section details.
    """
    report = {
        "overall_status": "incomplete",
        "completeness_score": 0.0,
        "total_checks": 0,
        "passed_checks": 0,
        "sections": {},
        "missing_fields": [],
        "warnings": [],
    }

    total_checks = 0
    passed_checks = 0

    page_map = {p["page"]: p["text"] for p in pages}

    # --- Page 1: Cover Page ---
    if 1 in page_map:
        section = _check_page1(page_map[1])
        report["sections"]["page_1_cover"] = section
        p1_checks = len(PAGE_1_REQUIRED)
        total_checks += p1_checks
        passed_checks += p1_checks - len(section["issues"])
        for issue in section["issues"]:
            report["missing_fields"].append({"page": 1, "field": issue})

    # --- Page 2: Personal Data ---
    if 2 in page_map:
        section = _check_page2(page_map[2])
        report["sections"]["page_2_personal_data"] = section
        p2_total = section["total_fields"]
        p2_missing = section["missing_count"]
        total_checks += p2_total
        passed_checks += p2_total - p2_missing
        for detail in section["details"]:
            if detail["status"] == "missing":
                report["missing_fields"].append({
                    "page": 2,
                    "field": detail["field"],
                    "label": detail.get("label"),
                })

    # --- Page 4: Signature & Attachments ---
    if 4 in page_map:
        section = _check_page4(page_map[4])
        report["sections"]["page_4_signature"] = section
        p4_total = 2  # date + ktp_attached
        p4_missing = len(section["issues"])
        total_checks += p4_total
        passed_checks += p4_total - p4_missing
        for issue in section["issues"]:
            report["missing_fields"].append({"page": 4, "field": issue})
        if p4_missing > 0:
            report["warnings"].append("Page 4: Signature/attachment incomplete")

    # --- Page 5: Investor Profile ---
    if 5 in page_map:
        section = _check_page5(page_map[5])
        report["sections"]["page_5_investor_profile"] = section
        total_checks += 1
        if section["status"] == "complete":
            passed_checks += 1
        else:
            report["warnings"].append(
                f"Page 5: Only {section['answers_found']}/{PAGE_5_MINIMUM_ANSWERS} minimum profile answers found"
            )

    # --- Page 7: Beneficial Owner ---
    if 7 in page_map:
        section = _check_page7(page_map[7])
        report["sections"]["page_7_beneficial_owner"] = section
        p7_total = len(PAGE_7_REQUIRED)
        p7_missing = len(section["issues"])
        total_checks += p7_total
        passed_checks += p7_total - p7_missing
        for issue in section["issues"]:
            report["missing_fields"].append({"page": 7, "field": issue})

    # --- Overall Score ---
    report["total_checks"] = total_checks
    report["passed_checks"] = passed_checks
    report["completeness_score"] = round((passed_checks / total_checks * 100), 1) if total_checks > 0 else 0.0
    report["overall_status"] = "complete" if report["completeness_score"] >= 90 else "incomplete"

    return report
