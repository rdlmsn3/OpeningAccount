import os
import io
import json
import base64
import requests
import pypdfium2 as pdfium
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from pathlib import Path
from datetime import datetime, timezone
from compliance_checker import run_compliance_check
from level2_sanity import run_sanity_check, extract_structured_data
import database as db

app = FastAPI(title="Account Opening Checker")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Static file serving for PDF/JSON (used by log viewer document loading) ---

@app.get("/{filename}.pdf")
async def serve_pdf(filename: str):
    """Serve a PDF file from the app directory."""
    pdf_path = Path(__file__).parent / f"{filename}.pdf"
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(pdf_path, media_type="application/pdf")

@app.get("/{filename}.json")
async def serve_json(filename: str):
    """Serve a JSON file from the app directory."""
    json_path = Path(__file__).parent / f"{filename}.json"
    if not json_path.exists():
        raise HTTPException(status_code=404, detail="JSON not found")
    return FileResponse(json_path, media_type="application/json")

# Configuration settings matching convertpdf.py
OCR_ENDPOINT = "http://localhost:8080/v1/chat/completions"
OCR_MODEL = "LOCAL"

def pdf_page_to_base64(page, scale=2.77):
    """Converts pypdfium2 page reference to a base64 encoded PNG data stream"""
    pil_image = page.render(scale=scale).to_pil()
    buffer = io.BytesIO()
    pil_image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")

def ocr_image(image_base64):
    """Dispatches binary image payload to local server model layout for text mining"""
    payload = {
        "model": OCR_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_base64}"
                        }
                    },
                    {
                        "type": "text",
                        "text": "Extract all text from this page. Keep structure."
                    }
                ]
            }
        ],
        "max_tokens": 8096,
        "temperature": 0.2,
        "top_p": 0.9,
        "cache_prompt": False,
    }
    response = requests.post(OCR_ENDPOINT, json=payload)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]

@app.get("/", response_class=HTMLResponse)
async def get_index():
    html_path = Path(__file__).parent / "index.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Frontend HTML file missing in root context directory.")
    return html_path.read_text(encoding="utf-8")

@app.post("/api/upload")
async def upload_and_process_document(file: UploadFile = File(...)):
    filename = file.filename
    base_name, file_extension = os.path.splitext(filename)
    
    current_dir = Path(__file__).parent
    target_json_path = current_dir / f"{base_name}.json"
    target_doc_path = current_dir / filename
    
    # Save the file to your root directory if it isn't already there
    if not target_doc_path.exists():
        with open(target_doc_path, "wb") as f:
            f.write(await file.read())
    
    # Upsert into tracking DB
    doc_id = db.upsert_document(base_name, str(target_doc_path), str(target_json_path))
            
    json_data = None
    processing_executed = False

    # Condition: If the JSON file already exists, load it directly
    if target_json_path.exists():
        try:
            with open(target_json_path, "r", encoding="utf-8") as f:
                json_data = json.load(f)
            print(f"--> [CACHE MATCH] Found existing data parameters for: {target_json_path.name}. Skipping OCR.")
            db.update_status(base_name, "ocr_complete", pages=len(json_data))
        except Exception as e:
            print(f"Error reading existing local JSON file: {e}")

    # Condition: If the JSON file is missing, trigger the OCR pipeline
    if json_data is None:
        if file_extension.lower() != ".pdf":
            raise HTTPException(
                status_code=400, 
                detail="Matching JSON file was not found on disk, and automated parsing is restricted to PDF format structures."
            )
        
        print(f"--> [OCR TRIGGER] {target_json_path.name} not found. Running processing engine...")
        processing_executed = True
        results = []
        
        db.update_status(base_name, "ocr_processing",
                         ocr_started_at=datetime.now(timezone.utc).isoformat())
        
        try:
            pdf = pdfium.PdfDocument(str(target_doc_path))
            total_pages = len(pdf)
            
            for i in range(total_pages):
                print(f"Server Processing: Page {i + 1}/{total_pages}")
                page = pdf[i]
                img_base64 = pdf_page_to_base64(page)
                extracted_text = ocr_image(img_base64)
                
                results.append({
                    "page": i + 1,
                    "text": extracted_text
                })
            
            # Cache the newly generated JSON data to your directory
            with open(target_json_path, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            
            print(f"--> Saved newly generated OCR file to disk path: {target_json_path}")
            json_data = results
            
            db.update_status(base_name, "ocr_complete",
                             pages=len(results),
                             ocr_completed_at=datetime.now(timezone.utc).isoformat())
            
        except Exception as err:
            print(f"OCR Pipeline Execution Failure: {err}")
            db.update_status(base_name, "failed", error_message=str(err))
            raise HTTPException(status_code=500, detail=f"Internal OCR system failure: {str(err)}")

    return JSONResponse(content={
        "status": "success",
        "registered_base_name": base_name,
        "processing_executed": processing_executed,
        "auto_loaded_json": json_data
    })


# --- Compliance Check ---

class ComplianceCheckRequest(BaseModel):
    filename: str
    payload: List[dict]  # [{"page": int, "text": str}, ...]


@app.post("/api/check-compliance")
async def check_data_compliance(request: ComplianceCheckRequest):
    """Run data completeness check on OCR-extracted form data."""
    if not request.payload:
        raise HTTPException(status_code=400, detail="Empty payload — no page data provided.")

    try:
        report = run_compliance_check(request.payload)
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Compliance check failed: {str(err)}")

    # Persist compliance result to DB
    db.update_status(request.filename, "compliance_checked",
                     compliance_score=report["completeness_score"],
                     compliance_status=report["overall_status"],
                     missing_fields=report["missing_fields"])

    return JSONResponse(content={
        "status": "success",
        "filename": request.filename,
        "report": report,
    })


@app.get("/api/compliance/{filename}")
async def check_cached_file_compliance(filename: str):
    """Run compliance check on an already-processed file by its base name."""
    current_dir = Path(__file__).parent
    base_name = filename.replace(".json", "").replace(".pdf", "")
    json_path = current_dir / f"{base_name}.json"

    if not json_path.exists():
        raise HTTPException(status_code=404, detail=f"No cached OCR data found for: {base_name}")

    with open(json_path, "r", encoding="utf-8") as f:
        pages = json.load(f)

    report = run_compliance_check(pages)

    # Persist compliance result to DB
    db.update_status(base_name, "compliance_checked",
                     compliance_score=report["completeness_score"],
                     compliance_status=report["overall_status"],
                     missing_fields=report["missing_fields"])

    return JSONResponse(content={
        "status": "success",
        "filename": base_name,
        "report": report,
    })


# --- Level 2 Sanity Check (LLM-assisted) ---

@app.get("/api/sanity-check/{filename}")
async def run_sanity_check_on_file(filename: str):
    """
    Level 2 check: extract structured data from OCR, send to LLM for
    cross-field validation, format checks, and consistency analysis.
    """
    current_dir = Path(__file__).parent
    base_name = filename.replace(".json", "").replace(".pdf", "")
    json_path = current_dir / f"{base_name}.json"

    if not json_path.exists():
        raise HTTPException(status_code=404, detail=f"No cached OCR data found for: {base_name}")

    with open(json_path, "r", encoding="utf-8") as f:
        pages = json.load(f)

    try:
        result = run_sanity_check(pages)
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Sanity check failed: {str(err)}")

    # Persist to DB
    analysis = result["analysis"]
    db.update_status(base_name, "sanity_checked",
                     sanity_score=analysis.get("confidence"),
                     sanity_status=analysis.get("overall_assessment"),
                     sanity_issues=json.dumps(analysis.get("issues", []), ensure_ascii=False),
                     sanity_full_results=json.dumps({
                         "extracted_data": result["extracted_data"],
                         "analysis": result["analysis"],
                     }, ensure_ascii=False))

    return JSONResponse(content={
        "status": "success",
        "filename": base_name,
        "extracted_data": result["extracted_data"],
        "analysis": result["analysis"],
    })


class SanityCheckPayload(BaseModel):
    filename: str
    payload: List[dict]  # [{"page": int, "text": str}, ...]


@app.get("/api/sanity-results/{filename}")
async def get_stored_sanity_results(filename: str):
    """Retrieve previously stored L2 sanity check results from DB."""
    base_name = filename.replace(".json", "").replace(".pdf", "")
    doc = db.get_document(base_name)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {base_name}")
    if not doc.get("sanity_full_results") or doc["sanity_full_results"] in ("{}", "null", ""):
        raise HTTPException(status_code=404, detail=f"No sanity results stored for: {base_name}")

    full = json.loads(doc["sanity_full_results"])
    return JSONResponse(content={
        "status": "success",
        "filename": base_name,
        "extracted_data": full.get("extracted_data"),
        "analysis": full.get("analysis"),
    })


@app.post("/api/sanity-check")
async def run_sanity_check_on_payload(request: SanityCheckPayload):
    """Level 2 check on submitted page data (from frontend editor)."""
    if not request.payload:
        raise HTTPException(status_code=400, detail="Empty payload.")

    try:
        result = run_sanity_check(request.payload)
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Sanity check failed: {str(err)}")

    analysis = result["analysis"]
    db.update_status(request.filename, "sanity_checked",
                     sanity_score=analysis.get("confidence"),
                     sanity_status=analysis.get("overall_assessment"),
                     sanity_issues=json.dumps(analysis.get("issues", []), ensure_ascii=False),
                     sanity_full_results=json.dumps({
                         "extracted_data": result["extracted_data"],
                         "analysis": result["analysis"],
                     }, ensure_ascii=False))

    return JSONResponse(content={
        "status": "success",
        "filename": request.filename,
        "extracted_data": result["extracted_data"],
        "analysis": result["analysis"],
    })


# --- Auto-Scan & Document Tracking ---

class ScanDirectoryRequest(BaseModel):
    directory: Optional[str] = None  # defaults to app's own directory
    run_compliance: bool = True


def _scan_and_process_pdf(pdf_path: Path) -> dict:
    """Run OCR on a single PDF and save JSON. Returns status dict."""
    base_name = pdf_path.stem
    json_path = pdf_path.parent / f"{base_name}.json"

    db.upsert_document(base_name, str(pdf_path), str(json_path))
    db.update_status(base_name, "ocr_processing",
                     ocr_started_at=datetime.now(timezone.utc).isoformat())

    try:
        pdf = pdfium.PdfDocument(str(pdf_path))
        results = []

        for i in range(len(pdf)):
            print(f"[SCAN] {base_name}: page {i + 1}/{len(pdf)}")
            page = pdf[i]
            img_base64 = pdf_page_to_base64(page)
            extracted_text = ocr_image(img_base64)
            results.append({"page": i + 1, "text": extracted_text})

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        db.update_status(base_name, "ocr_complete",
                         pages=len(results),
                         ocr_completed_at=datetime.now(timezone.utc).isoformat())

        print(f"[DONE] {base_name} — saved {len(results)} pages")
        return {"file": base_name, "status": "completed", "pages": len(results)}

    except Exception as err:
        print(f"[FAIL] {base_name} — {err}")
        db.update_status(base_name, "failed", error_message=str(err))
        return {"file": base_name, "status": "failed", "error": str(err)}


@app.post("/api/scan-directory")
async def scan_directory(request: ScanDirectoryRequest):
    """
    Scan a directory for unprocessed PDFs and run OCR on each.
    Uses DB to track what's already processed — skips completed files.
    """
    scan_dir = Path(request.directory) if request.directory else Path(__file__).parent

    if not scan_dir.exists():
        raise HTTPException(status_code=400, detail=f"Directory not found: {scan_dir}")

    pdf_files = sorted(scan_dir.glob("*.pdf"))
    if not pdf_files:
        return JSONResponse(content={
            "status": "success",
            "message": "No PDF files found in directory",
            "directory": str(scan_dir),
            "results": [],
        })

    scan_results = []
    compliance_reports = []

    for pdf_path in pdf_files:
        base_name = pdf_path.stem
        json_path = scan_dir / f"{base_name}.json"

        # Check DB for existing status
        existing = db.get_document(base_name)
        if existing and existing["status"] in ("ocr_complete", "compliance_checked"):
            scan_results.append({"file": base_name, "status": "skipped", "reason": "already_processed"})
            # Still run compliance if requested and not yet checked
            if request.run_compliance and existing["status"] == "ocr_complete" and json_path.exists():
                try:
                    with open(json_path, "r", encoding="utf-8") as f:
                        pages = json.load(f)
                    report = run_compliance_check(pages)
                    db.update_status(base_name, "compliance_checked",
                                     compliance_score=report["completeness_score"],
                                     compliance_status=report["overall_status"],
                                     missing_fields=report["missing_fields"])
                    compliance_reports.append({"filename": base_name, "report": report})
                except Exception as e:
                    compliance_reports.append({"filename": base_name, "error": str(e)})
            continue

        # New or failed — run OCR
        result = _scan_and_process_pdf(pdf_path)
        scan_results.append(result)

        # Run compliance if requested and OCR succeeded
        if request.run_compliance and result["status"] == "completed":
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    pages = json.load(f)
                report = run_compliance_check(pages)
                db.update_status(base_name, "compliance_checked",
                                 compliance_score=report["completeness_score"],
                                 compliance_status=report["overall_status"],
                                 missing_fields=report["missing_fields"])
                compliance_reports.append({"filename": base_name, "report": report})
            except Exception as e:
                compliance_reports.append({"filename": base_name, "error": str(e)})

    return JSONResponse(content={
        "status": "success",
        "directory": str(scan_dir),
        "total_pdfs": len(pdf_files),
        "processed": [r for r in scan_results if r["status"] == "completed"],
        "skipped": [r for r in scan_results if r["status"] == "skipped"],
        "failed": [r for r in scan_results if r["status"] == "failed"],
        "compliance_reports": compliance_reports,
    })


@app.get("/api/documents")
async def list_documents(status: Optional[str] = None):
    """
    Log viewer — list all tracked documents with their processing and compliance status.
    Optional ?status=pending|ocr_processing|ocr_complete|compliance_checked|failed
    """
    documents = db.get_documents(status=status)
    return JSONResponse(content={
        "status": "success",
        "total": len(documents),
        "documents": documents,
    })


# --- Health Check ---

@app.get("/api/health")
async def health_check():
    """Server health + LLM connectivity probe."""
    health = {"server": "ok", "database": "ok", "llm": "unknown"}

    # Check DB
    try:
        db.get_documents()
    except Exception as e:
        health["database"] = f"error: {e}"

    # Check LLM
    try:
        resp = requests.get(OCR_ENDPOINT.replace("/chat/completions", "/models"), timeout=3)
        health["llm"] = "ok" if resp.status_code == 200 else f"status {resp.status_code}"
    except Exception as e:
        health["llm"] = f"unreachable: {e}"

    return JSONResponse(content={"status": "success", "health": health})


# --- Full Pipeline: Upload + OCR + L1 + optional L2 ---

@app.post("/api/process")
async def process_document(
    file: UploadFile = File(...),
    run_l2: bool = False,
):
    """
    Full pipeline in one shot:
      1. Save uploaded PDF
      2. OCR each page
      3. Run L1 compliance check
      4. Optionally run L2 sanity check
    Returns everything in one response.
    """
    filename = file.filename
    base_name, ext = os.path.splitext(filename)
    current_dir = Path(__file__).parent
    pdf_path = current_dir / filename
    json_path = current_dir / f"{base_name}.json"

    # Save file
    if not pdf_path.exists():
        with open(pdf_path, "wb") as f:
            f.write(await file.read())

    doc_id = db.upsert_document(base_name, str(pdf_path), str(json_path))

    result = {"filename": base_name, "ocr": None, "l1_compliance": None, "l2_sanity": None}

    # --- Step 1: OCR ---
    json_data = None
    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                json_data = json.load(f)
            db.update_status(base_name, "ocr_complete", pages=len(json_data))
        except Exception:
            json_data = None

    if json_data is None:
        if ext.lower() != ".pdf":
            raise HTTPException(status_code=400, detail="Only PDF files are supported.")
        db.update_status(base_name, "ocr_processing",
                         ocr_started_at=datetime.now(timezone.utc).isoformat())
        try:
            pdf = pdfium.PdfDocument(str(pdf_path))
            results = []
            for i in range(len(pdf)):
                page = pdf[i]
                img_base64 = pdf_page_to_base64(page)
                text = ocr_image(img_base64)
                results.append({"page": i + 1, "text": text})
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            json_data = results
            db.update_status(base_name, "ocr_complete",
                             pages=len(results),
                             ocr_completed_at=datetime.now(timezone.utc).isoformat())
        except Exception as err:
            db.update_status(base_name, "failed", error_message=str(err))
            raise HTTPException(status_code=500, detail=f"OCR failed: {err}")

    result["ocr"] = {"pages": len(json_data), "cached": json_path.exists()}

    # --- Step 2: L1 Compliance ---
    try:
        l1_report = run_compliance_check(json_data)
        db.update_status(base_name, "compliance_checked",
                         compliance_score=l1_report["completeness_score"],
                         compliance_status=l1_report["overall_status"],
                         missing_fields=l1_report["missing_fields"])
        result["l1_compliance"] = l1_report
    except Exception as err:
        result["l1_compliance"] = {"error": str(err)}

    # --- Step 3: L2 Sanity (optional) ---
    if run_l2:
        try:
            l2_result = run_sanity_check(json_data)
            analysis = l2_result["analysis"]
            db.update_status(base_name, "sanity_checked",
                             sanity_score=analysis.get("confidence"),
                             sanity_status=analysis.get("overall_assessment"),
                             sanity_issues=json.dumps(analysis.get("issues", []), ensure_ascii=False),
                             sanity_full_results=json.dumps({
                                 "extracted_data": l2_result["extracted_data"],
                                 "analysis": l2_result["analysis"],
                             }, ensure_ascii=False))
            result["l2_sanity"] = l2_result
        except Exception as err:
            result["l2_sanity"] = {"error": str(err)}

    return JSONResponse(content={"status": "success", "result": result})


# --- Consolidated Results Lookup ---

@app.get("/api/results/{filename}")
async def get_all_results(filename: str):
    """
    Return all stored data for a document: DB metadata + L1 report + L2 report.
    AI agents can call this to get everything in one response.
    """
    base_name = filename.replace(".json", "").replace(".pdf", "")
    doc = db.get_document(base_name)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Document not found: {base_name}")

    current_dir = Path(__file__).parent
    json_path = current_dir / f"{base_name}.json"
    ocr_data = None
    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                ocr_data = json.load(f)
        except Exception:
            pass

    # Rebuild L1 report from stored data
    l1_report = None
    if ocr_data:
        try:
            l1_report = run_compliance_check(ocr_data)
        except Exception:
            pass

    # Parse stored L2 results
    l2_report = None
    if doc.get("sanity_full_results") and doc["sanity_full_results"] not in ("{}", "null", ""):
        l2_report = json.loads(doc["sanity_full_results"])

    return JSONResponse(content={
        "status": "success",
        "filename": base_name,
        "document": doc,
        "ocr_pages": len(ocr_data) if ocr_data else 0,
        "l1_compliance": l1_report,
        "l2_sanity": l2_report,
    })


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
