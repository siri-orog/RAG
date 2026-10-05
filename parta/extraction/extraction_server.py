"""
extraction/extraction_server.py
--------------------------------
Pull-based PDF chunk extraction job server. Port 8004 on Master Node.

Architecture:
  - Workers pull jobs — no hardcoded worker IPs on master
  - Each job has a lease_deadline; expired lease returns chunk to PENDING
  - No worker blacklist — dead workers stop polling, chunks time out naturally
  - Binary chunk download via GET /chunk/{job_id} (no base64 overhead)
  - Idempotent submit — late duplicate submits safely ignored
  - Per-chunk attempt_count caps retries for genuinely corrupt PDF slices

Run with:
    uvicorn extraction.extraction_server:app --host 0.0.0.0 --port 8004
"""

import uuid
import time
import threading
import shutil
from pathlib import Path
from typing import Dict

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pypdf import PdfReader, PdfWriter

app = FastAPI(title="Extraction Job Server")

# ── Config ────────────────────────────────────────────────────────────────────
CHUNK_SIZE        = 10    # pages per chunk sent to each worker
LEASE_SECONDS     = 600   # lease per chunk; expired → back to PENDING
MAX_ATTEMPTS      = 3     # per-chunk global cap (Bug C5: was 10, far too many)
CLEANUP_DELAY_SEC = 300   # delete chunk files 5 min after book finishes

# ── In-memory state ───────────────────────────────────────────────────────────
extractions: Dict[str, dict] = {}
extraction_lock = threading.Lock()


# ─────────────────────────────────────────────────────────────────────────────
# START EXTRACTION — called by pipeline_controller
# ─────────────────────────────────────────────────────────────────────────────
@app.post("/start_extraction")
def start_extraction(payload: dict):
    """
    Splits PDF into fixed-size chunk files on disk.
    Creates one PENDING job per chunk.
    Returns immediately — workers pull jobs asynchronously.
    """
    book_id      = payload.get("book_id")
    pdf_path     = payload.get("pdf_path")
    base_dir     = payload.get("base_dir", ".")
    ocr_enabled  = bool(payload.get("ocr_enabled", False))

    if not book_id or not pdf_path:
        raise HTTPException(400, "book_id and pdf_path are required")
    if not Path(pdf_path).exists():
        raise HTTPException(404, f"PDF not found: {pdf_path}")

    # FIX 2: Reject duplicate start if same book is already in-flight
    with extraction_lock:
        existing = extractions.get(book_id)
        if existing and not existing["is_finished"]:
            raise HTTPException(
                409,
                f"Book '{book_id}' is already being extracted "
                f"({existing['completed']}/{existing['total']} chunks done). "
                "Wait for it to finish or restart the server to clear state."
            )

    chunk_dir = Path(base_dir) / f"temp_extract_{book_id}"
    chunk_dir.mkdir(parents=True, exist_ok=True)

    reader      = PdfReader(pdf_path)
    total_pages = len(reader.pages)
    jobs        = {}
    queue_order = []

    print(f"[EXTRACT SERVER] Splitting {total_pages} pages for '{book_id}'...")

    for chunk_idx, start in enumerate(range(0, total_pages, CHUNK_SIZE)):
        end = min(start + CHUNK_SIZE, total_pages)

        writer = PdfWriter()
        for pg in range(start, end):
            writer.add_page(reader.pages[pg])

        chunk_path = chunk_dir / f"chunk_{chunk_idx}.pdf"
        with open(str(chunk_path), "wb") as f:
            writer.write(f)

        jid = str(uuid.uuid4())
        jobs[jid] = {
            "job_id":        jid,
            "book_id":       book_id,
            "chunk_idx":     chunk_idx,
            "chunk_path":    str(chunk_path),
            "start_offset":  start,
            "page_count":    end - start,
            "status":        "PENDING",
            "assigned_to":   None,
            "assigned_at":   0,
            "lease_deadline": 0,
            "attempt_count": 0,
            "result":        None,
        }
        queue_order.append(jid)

    total_chunks = len(queue_order)
    print(f"[EXTRACT SERVER] {total_chunks} chunks queued for '{book_id}'")

    with extraction_lock:
        extractions[book_id] = {
            "jobs":        jobs,
            "queue":       queue_order,
            "total":       total_chunks,
            "total_pages": total_pages,
            "completed":   0,
            "failed":      0,
            "is_finished": False,
            "chunk_dir":   str(chunk_dir),
            "started_at":  time.time(),
            "ocr_enabled": ocr_enabled,
        }

    return {
        "status":       "started",
        "book_id":      book_id,
        "total_chunks": total_chunks,
        "total_pages":  total_pages,
        "ocr_enabled":  ocr_enabled,
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET JOB — worker pulls when free
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/get_job")
def get_job(worker_id: str = "unknown"):
    """
    Workers call this when free. Returns job metadata.
    Worker then calls GET /chunk/{job_id} to download PDF bytes.

    Responses:
      {"action": "PROCESS", "job_id": ..., ...}  — here is your next chunk
      {"action": "WAIT"}                          — nothing now, poll again
      {"action": "SHUTDOWN"}                      — all books finished
    """
    now = time.time()

    with extraction_lock:
        any_active = False

        for book_id, state in extractions.items():
            if state["is_finished"]:
                continue
            any_active = True
            jobs  = state["jobs"]
            queue = state["queue"]

            # ── Lease expiry rescue: expired PROCESSING → back to PENDING ─────
            for jid, job in jobs.items():
                if job["status"] == "PROCESSING" and now > job["lease_deadline"]:
                    job["attempt_count"] += 1
                    print(f"[EXTRACT SERVER] ⏱ Chunk {job['chunk_idx']} lease expired "
                          f"(held by {job['assigned_to']}, attempt "
                          f"{job['attempt_count']}/{MAX_ATTEMPTS})")

                    if job["attempt_count"] >= MAX_ATTEMPTS:
                        job["status"] = "FAILED"
                        state["failed"] += 1
                        print(f"[EXTRACT SERVER] ❌ Chunk {job['chunk_idx']} "
                              f"permanently failed after {MAX_ATTEMPTS} attempts")
                        _check_finished(book_id, state)
                    else:
                        job["status"]         = "PENDING"
                        job["assigned_to"]    = None
                        job["assigned_at"]    = 0
                        job["lease_deadline"] = 0

            # ── Assign next PENDING chunk ─────────────────────────────────────
            for jid in queue:
                job = jobs[jid]
                if job["status"] != "PENDING":
                    continue

                job["status"]         = "PROCESSING"
                job["assigned_to"]    = worker_id
                job["assigned_at"]    = now
                job["lease_deadline"] = now + LEASE_SECONDS

                print(f"[EXTRACT SERVER] → Chunk {job['chunk_idx']} "
                      f"(pages {job['start_offset']+1}–"
                      f"{job['start_offset']+job['page_count']}) "
                      f"→ {worker_id}")

                return {
                    "action":       "PROCESS",
                    "job_id":       jid,
                    "book_id":      book_id,
                    "chunk_idx":    job["chunk_idx"],
                    "start_offset": job["start_offset"],
                    "ocr_enabled":  state.get("ocr_enabled", False),
                }

    # FIX 1: Return WAIT when no active books — workers keep polling for next upload
    # SHUTDOWN is intentionally removed: auto-shutdown breaks multi-book ingestion.
    # After book 1 finishes, workers must stay alive for book 2, 3, etc.
    return {"action": "WAIT"}


# ─────────────────────────────────────────────────────────────────────────────
# CHUNK BINARY — worker downloads raw PDF bytes
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/chunk/{job_id}")
def get_chunk_binary(job_id: str):
    """
    Returns raw PDF bytes for a chunk (application/octet-stream).
    No base64 encoding — direct binary transfer.
    Worker calls this after receiving a PROCESS response from /get_job.
    """
    with extraction_lock:
        chunk_path = None
        for state in extractions.values():
            if job_id in state["jobs"]:
                chunk_path = state["jobs"][job_id]["chunk_path"]
                break

    if not chunk_path:
        raise HTTPException(404, f"Job {job_id} not found")
    if not Path(chunk_path).exists():
        raise HTTPException(404, f"Chunk file missing for job {job_id}")

    return FileResponse(
        path=chunk_path,
        media_type="application/octet-stream",
        filename=f"chunk_{job_id}.pdf",
    )


# ─────────────────────────────────────────────────────────────────────────────
# SUBMIT RESULT — worker returns extracted markdown
# ─────────────────────────────────────────────────────────────────────────────
@app.post("/submit_result")
def submit_result(payload: dict):
    """
    Worker posts result after processing a chunk.
    Idempotent: duplicate submits for the same job_id are safely ignored.
    No blacklist: failed workers can retry; dead workers simply stop polling.
    """
    jid       = payload.get("job_id")
    worker_id = payload.get("worker_id", "unknown")
    success   = payload.get("success", False)
    content   = payload.get("content", "")

    with extraction_lock:
        for book_id, state in extractions.items():
            if jid not in state["jobs"]:
                continue

            job = state["jobs"][jid]

            # Idempotent: already completed (late duplicate submit) → ignore
            if job["status"] == "COMPLETED":
                return {"status": "ok", "note": "already completed, ignored"}

            if success and content:
                job["status"] = "COMPLETED"
                job["result"] = content
                state["completed"] += 1
                print(f"[EXTRACT SERVER] ✅ Chunk {job['chunk_idx']} done "
                      f"by {worker_id} [{state['completed']}/{state['total']}]")
            else:
                # Worker failed — return chunk to PENDING (no blacklist)
                job["attempt_count"] += 1
                print(f"[EXTRACT SERVER] ⚠ Chunk {job['chunk_idx']} failed "
                      f"by {worker_id} (attempt {job['attempt_count']}/{MAX_ATTEMPTS})")

                if job["attempt_count"] >= MAX_ATTEMPTS:
                    job["status"] = "FAILED"
                    state["failed"] += 1
                    print(f"[EXTRACT SERVER] ❌ Chunk {job['chunk_idx']} "
                          f"permanently failed after {MAX_ATTEMPTS} attempts")
                else:
                    job["status"]         = "PENDING"
                    job["assigned_to"]    = None
                    job["assigned_at"]    = 0
                    job["lease_deadline"] = 0

            _check_finished(book_id, state)
            return {"status": "ok"}

    raise HTTPException(404, f"Job {jid} not found")


# ─────────────────────────────────────────────────────────────────────────────
# STATUS — polled by pipeline_controller
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/extraction_status/{book_id}")
def extraction_status(book_id: str):
    with extraction_lock:
        state = extractions.get(book_id)

    if not state:
        return {"status": "not_found", "book_id": book_id}

    failed_chunks = [
        state["jobs"][jid]["chunk_idx"]
        for jid in state["queue"]
        if state["jobs"][jid]["status"] == "FAILED"
    ]
    overall = "running"
    if state["is_finished"]:
        overall = "failed" if state["failed"] > 0 else "completed"

    return {
        "book_id":       book_id,
        "status":        overall,
        "total_chunks":  state["total"],
        "completed":     state["completed"],
        "failed":        state["failed"],
        "is_finished":   state["is_finished"],
        "percent":       int(state["completed"] / max(state["total"], 1) * 100),
        "failed_chunks": failed_chunks,
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET RESULT — pipeline_controller fetches assembled markdown
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/get_result/{book_id}")
def get_result(book_id: str):
    with extraction_lock:
        state = extractions.get(book_id)

    if not state:
        raise HTTPException(404, f"No extraction for '{book_id}'")
    if not state["is_finished"]:
        raise HTTPException(400, "Extraction not finished yet")

    failed = [
        state["jobs"][jid]["chunk_idx"]
        for jid in state["queue"]
        if state["jobs"][jid]["status"] == "FAILED"
    ]
    if failed:
        raise HTTPException(
            500,
            f"Chunks {failed} permanently failed after {MAX_ATTEMPTS} attempts. "
            "Check PDF integrity and Docling workers."
        )

    full_text = f"# Text Extraction: {book_id}\n\n"
    for jid in state["queue"]:
        full_text += state["jobs"][jid]["result"]

    return {"book_id": book_id, "content": full_text}


# ─────────────────────────────────────────────────────────────────────────────
# HEALTH
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    with extraction_lock:
        active = {
            bid: {"completed": s["completed"], "total": s["total"]}
            for bid, s in extractions.items()
            if not s["is_finished"]
        }
    return {"status": "ok", "active_books": active}


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _check_finished(book_id: str, state: dict):
    done = state["completed"] + state["failed"]
    if done >= state["total"] and not state["is_finished"]:
        state["is_finished"] = True
        label = "❌ FAILED" if state["failed"] > 0 else "✅ COMPLETE"
        print(f"[EXTRACT SERVER] {label} — '{book_id}' "
              f"({state['completed']}/{state['total']} chunks)")
        threading.Thread(
            target=_cleanup_after_delay,
            args=(state["chunk_dir"],),
            daemon=True
        ).start()


def _cleanup_after_delay(chunk_dir: str):
    time.sleep(CLEANUP_DELAY_SEC)
    shutil.rmtree(chunk_dir, ignore_errors=True)
    print(f"[EXTRACT SERVER] 🧹 Cleaned {chunk_dir}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8004)