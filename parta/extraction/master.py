"""
extraction/master.py
--------------------
Thin client called by pipeline_controller for text extraction.

Responsibilities:
  1. Tell extraction_server to start splitting and queuing the PDF
  2. Poll extraction_server until all chunks are processed
  3. Fetch the assembled markdown result
  4. Write it to data/processed/{book_id}.md
  5. Return that path to pipeline_controller

All worker management, fault tolerance, and retries are handled
inside extraction_server.py — this file has no worker logic.
"""

import requests
import time
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
# URL of extraction_server.py running on Master Node port 8004
EXTRACTION_SERVER_URL = "http://localhost:8004"
POLL_INTERVAL_SEC     = 5


def run_extraction(
    book_id:           str,
    pdf_path:          str,
    base_dir:          str,
    progress_callback = None,
    ocr_enabled:       bool = False,
) -> str:
    """
    Called by pipeline_controller.
    Returns path to the assembled .md file.
    Raises RuntimeError on failure.

    The ocr_enabled flag is forwarded to extraction_server.py and from there
    to every worker so workers pick the correct Docling pipeline (OCR or fast).
    """
    processed_dir = Path(base_dir) / "data" / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    output_file = processed_dir / f"{book_id}.md"

    print(f"\n[EXTRACT] Starting extraction for: {book_id}")

    # ── Step 1: Tell extraction server to split and queue the PDF ─────────────
    if progress_callback:
        progress_callback(
            percent=7,
            stage="Text Extraction",
            message="Sending PDF to extraction server for splitting...",
        )

    try:
        resp = requests.post(
            f"{EXTRACTION_SERVER_URL}/start_extraction",
            json={
                "book_id":     book_id,
                "pdf_path":    pdf_path,
                "base_dir":    base_dir,
                "ocr_enabled": ocr_enabled,
            },
            timeout=60,
        )
    except Exception as e:
        raise RuntimeError(
            f"Cannot reach extraction server at {EXTRACTION_SERVER_URL}. "
            f"Is extraction_server.py running on port 8004? Error: {e}"
        )

    if resp.status_code != 200:
        raise RuntimeError(
            f"Extraction server rejected start: {resp.status_code} — {resp.text}"
        )

    data         = resp.json()
    total_chunks = data.get("total_chunks", 1)
    total_pages  = data.get("total_pages",  0)

    mode_label = "OCR" if ocr_enabled else "fast"
    print(f"[EXTRACT] {total_chunks} chunks queued "
          f"({total_pages} pages total, mode={mode_label})")

    if progress_callback:
        progress_callback(
            percent=10,
            stage="Text Extraction",
            message=f"Queued {total_chunks} chunks "
                    f"({total_pages} pages, {mode_label}). Workers processing...",
        )

    # ── Step 2: Poll until all chunks are done ────────────────────────────────
    t_start = time.time()

    while True:
        time.sleep(POLL_INTERVAL_SEC)

        try:
            status_resp = requests.get(
                f"{EXTRACTION_SERVER_URL}/extraction_status/{book_id}",
                timeout=15,
            )
            status = status_resp.json()
        except Exception as e:
            print(f"[EXTRACT] ⚠ Could not poll status: {e}. Retrying...")
            continue

        completed   = status.get("completed",   0)
        is_finished = status.get("is_finished", False)
        overall     = status.get("status",      "running")
        elapsed     = int(time.time() - t_start)

        print(f"[EXTRACT] {completed}/{total_chunks} chunks done | {elapsed}s elapsed")

        if progress_callback:
            ui_pct = 10 + int(completed / max(total_chunks, 1) * 39)
            progress_callback(
                percent=ui_pct,
                stage="Text Extraction",
                message=f"Extracted {completed} of {total_chunks} chunks ({elapsed}s elapsed)",
                extra={"chunks_done": completed, "total_chunks": total_chunks},
            )

        if is_finished:
            if overall == "failed":
                failed_chunks = status.get("failed_chunks", [])
                raise RuntimeError(
                    f"Extraction failed: chunk(s) {failed_chunks} exhausted all retries. "
                    "Check Docling workers and PDF integrity."
                )
            break

    # ── Step 3: Fetch assembled markdown from server ──────────────────────────
    if progress_callback:
        progress_callback(
            percent=49,
            stage="Text Extraction",
            message="All chunks complete. Assembling full text...",
        )

    try:
        result_resp = requests.get(
            f"{EXTRACTION_SERVER_URL}/get_result/{book_id}",
            timeout=60,
        )
    except Exception as e:
        raise RuntimeError(f"Could not fetch result from extraction server: {e}")

    if result_resp.status_code != 200:
        raise RuntimeError(
            f"Result fetch failed: {result_resp.status_code} — {result_resp.text}"
        )

    full_text = result_resp.json().get("content", "")

    # ── Step 4: Write markdown file ───────────────────────────────────────────
    with open(str(output_file), "w", encoding="utf-8") as f:
        f.write(full_text)

    elapsed = int(time.time() - t_start)
    print(f"[EXTRACT] ✅ Done in {elapsed}s → {output_file}")

    if progress_callback:
        progress_callback(
            percent=50,
            stage="Text Extraction",
            message=f"Extraction complete. {total_pages} pages in {elapsed}s.",
        )

    return str(output_file)
