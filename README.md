# Account Opening Document Checker

FastAPI-based document processing pipeline for **Sequis Asset Management** Individual Account Opening Forms.

OCR → Compliance Check (L1) → LLM Sanity Check (L2) — all automated.

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start the server
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Open [http://localhost:8000](http://localhost:8000) for the frontend, or [http://localhost:8000/docs](http://localhost:8000/docs) for the Swagger API.

---

## Architecture

```
PDF Upload / Scan
      ↓
OCR Engine (pypdfium2 + llama-server)
      ↓
JSON Cache (per-document)
      ↓
L1 Compliance Check (rule-based field validation)
      ↓
L2 Sanity Check (LLM-assisted cross-field analysis)
      ↓
SQLite DB (docmatch.db) — status tracking + audit trail
```

---

## Folder Structure

```
AccountOpening/
├── main.py                 # FastAPI app — endpoints, OCR pipeline, file serving
├── field_extractor.py      # Regex-based field extraction from OCR text
├── compliance_rules.py     # Required fields, patterns, page locations
├── compliance_checker.py   # L1 rule-based compliance engine
├── level2_sanity.py        # L2 LLM-assisted sanity check pipeline
├── llm_config.py           # LLM endpoint configuration (env vars)
├── database.py             # SQLite document tracking DB
├── index.html              # Frontend UI
├── docmatch.db             # SQLite database (auto-created)
├── requirements.txt
└── README.md
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Frontend UI |
| `GET` | `/docs` | Swagger API docs |
| `POST` | `/api/upload` | Upload PDF → OCR → cache JSON |
| `POST` | `/api/process` | Full pipeline: upload + OCR + L1 + optional L2 |
| `POST` | `/api/check-compliance` | Run L1 compliance on submitted payload |
| `GET` | `/api/compliance/{filename}` | Run L1 on cached OCR data |
| `GET` | `/api/sanity-check/{filename}` | Run L2 sanity check on cached data |
| `POST` | `/api/sanity-check` | Run L2 on submitted payload |
| `GET` | `/api/sanity-results/{filename}` | Retrieve stored L2 results |
| `POST` | `/api/scan-directory` | Batch scan directory for unprocessed PDFs |
| `GET` | `/api/documents` | List all tracked documents + status |
| `GET` | `/api/health` | Server + DB + LLM health check |
| `GET` | `/{filename}.pdf` | Serve PDF file |
| `GET` | `/{filename}.json` | Serve JSON file |

---

## Two-Level Checking

### L1: Compliance Check (Rule-Based)
- **Page 1**: Cover page — SID, customer code, name
- **Page 2**: Personal data — 13+ required fields + checkbox selections
- **Page 4**: Signature, date, KTP attachment
- **Page 5**: Investor profile — minimum 3 answers
- **Page 7**: Beneficial owner — 5 required fields

Returns: `completeness_score` (0–100%), `missing_fields[]`, `overall_status`

### L2: Sanity Check (LLM-Assisted)
- Extracts structured data from OCR text
- Sends to LLM for cross-field validation
- Checks: format validity, cross-field consistency, OCR artifacts, logical consistency, regulatory flags

Returns: `overall_assessment` (pass/review_needed/fail), `issues[]`, `confidence`, `summary`

---

## LLM Configuration

Default: local `llama-server` at `localhost:8080`

Override via environment variables:

```bash
export LLM_BASE_URL="http://your-server:8080/v1"
export LLM_API_KEY="your-key"
export LLM_MODEL="your-model"
export LLM_MAX_TOKENS=4096
export LLM_TEMPERATURE=0.1
```

---

## Requirements

- Python 3.11+
- FastAPI + uvicorn
- pypdfium2 (PDF rendering)
- requests (LLM API calls)
- SQLite (built-in)
- A running LLM server (llama-server, vLLM, etc.)

---

## Data Flow

1. **Upload**: PDF saved to disk, OCR'd page-by-page via llama-server
2. **Cache**: OCR results stored as `{filename}.json` alongside the PDF
3. **L1 Check**: Rule-based field validation against `compliance_rules.py`
4. **L2 Check**: Structured data → LLM prompt → sanity analysis
5. **Track**: All results persisted to `docmatch.db` for audit trail

---

## Roadmap

| Feature | Status |
|---------|--------|
| PDF upload + OCR | ✅ |
| JSON caching | ✅ |
| L1 compliance check | ✅ |
| L2 LLM sanity check | ✅ |
| Document tracking DB | ✅ |
| Batch directory scan | ✅ |
| Frontend UI | ✅ |
| Multi-form support | 🔜 |
| Export reports (PDF/Excel) | 🔜 |
| Authentication | 🔜 |
