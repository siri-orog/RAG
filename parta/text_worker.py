"""
text_worker.py
--------------
Pull-based Docling PDF extraction worker.

Polls extraction_server.py for chunks when free.
No hardcoded worker peer IPs anywhere.
No blacklist — dead workers stop polling naturally.

Run on any machine that can reach the extraction server:
    python text_worker.py

Override server URL via environment variable:
    EXTRACTION_SERVER_URL=http://10.61.82.20:8004 python text_worker.py

Multiple workers can run simultaneously on any number of machines.
"""

import os
import sys
import time
import socket
import tempfile
import requests
import warnings
import logging
from pathlib import Path

warnings.filterwarnings("ignore")
logging.getLogger("transformers").setLevel(logging.ERROR)
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# ── Config ────────────────────────────────────────────────────────────────────
EXTRACTION_SERVER_URL = os.environ.get(
    "EXTRACTION_SERVER_URL",
    "http://127.0.0.1:8004"     # Master Node — change if needed or use env var
)
POLL_INTERVAL_IDLE = 5    # seconds between polls when no work is available
POLL_INTERVAL_BUSY = 1    # seconds between polls after completing a chunk
REQUEST_TIMEOUT    = 600  # max seconds for one Docling conversion

# Unique ID for this worker instance (hostname + PID for clarity in logs)
WORKER_ID = f"{socket.gethostname()}_{os.getpid()}"

# ── Offline Docling model path ────────────────────────────────────────────────
CURRENT_DIR = Path(__file__).parent.absolute()
MODELS_DIR  = CURRENT_DIR / "portable" / "docling"
os.environ["DOCLING_ARTIFACTS_PATH"] = str(MODELS_DIR)

print(f"[WORKER] ID:            {WORKER_ID}")
print(f"[WORKER] Master server: {EXTRACTION_SERVER_URL}")
print(f"[WORKER] Docling path:  {MODELS_DIR}")

# ── Load Docling once at startup ──────────────────────────────────────────────
# Two converters are instantiated because turning OCR on/off requires different
# pipeline options and rebuilding a DocumentConverter mid-run is expensive.
# - converter_fast : do_ocr=False → used for digital (text-layer) PDFs
# - converter_ocr  : do_ocr=True  → used when the upload toggle requests OCR
# Both use TableFormerMode.ACCURATE — as per explicit user requirement,
# table structure accuracy is non-negotiable.
try:
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, TableFormerMode

    def _make_converter(do_ocr: bool) -> DocumentConverter:
        opts = PdfPipelineOptions()
        opts.do_table_structure = True
        opts.table_structure_options.mode = TableFormerMode.ACCURATE
        opts.do_ocr = do_ocr
        opts.artifacts_path = str(MODELS_DIR)
        return DocumentConverter(
            allowed_formats=[InputFormat.PDF],
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=opts)
            },
        )

    converter_fast = _make_converter(do_ocr=False)
    converter_ocr  = _make_converter(do_ocr=True)
    print("[WORKER] ✅ Docling loaded (fast + OCR converters). Ready to pull jobs.")
except Exception as e:
    print(f"[WORKER] ❌ Failed to load Docling: {e}")
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────────────────────────────────────
def main():
    wait_count = 0

    while True:
        try:
            # ── Poll for a job ────────────────────────────────────────────────
            try:
                resp    = requests.get(
                    f"{EXTRACTION_SERVER_URL}/get_job",
                    params={"worker_id": WORKER_ID},
                    timeout=15,
                )
                payload = resp.json()
            except Exception as e:
                print(f"[WORKER] ⚠ Cannot reach server: {e}. Waiting...")
                time.sleep(POLL_INTERVAL_IDLE)
                continue

            action = payload.get("action")

            if action == "SHUTDOWN":
                print("[WORKER] Server says all work done. Exiting cleanly.")
                sys.exit(0)

            if action == "WAIT":
                wait_count += 1
                if wait_count % 12 == 1:
                    print(f"[WORKER] Waiting for work... (polling every {POLL_INTERVAL_IDLE}s)")
                time.sleep(POLL_INTERVAL_IDLE)
                continue

            if action != "PROCESS":
                time.sleep(POLL_INTERVAL_IDLE)
                continue

            # ── Got a real chunk to process ───────────────────────────────────
            wait_count  = 0
            job_id      = payload["job_id"]
            book_id     = payload["book_id"]
            chunk_idx   = payload["chunk_idx"]
            start_offset = payload["start_offset"]
            ocr_enabled  = bool(payload.get("ocr_enabled", False))

            mode_label = "OCR" if ocr_enabled else "fast"
            print(f"\n[WORKER] 📄 Got chunk {chunk_idx} for '{book_id}' "
                  f"(starts at page {start_offset + 1}, mode={mode_label})")

            # ── Download PDF bytes (binary, no base64) ────────────────────────
            success, result = _download_and_process(
                job_id, chunk_idx, start_offset, ocr_enabled
            )

            # ── Submit result to server ───────────────────────────────────────
            try:
                submit_resp = requests.post(
                    f"{EXTRACTION_SERVER_URL}/submit_result",
                    json={
                        "job_id":    job_id,
                        "worker_id": WORKER_ID,
                        "success":   success,
                        "content":   result if success else "",
                    },
                    timeout=30,
                )
                if submit_resp.status_code == 200:
                    if success:
                        print(f"[WORKER] ✅ Chunk {chunk_idx} submitted successfully")
                    else:
                        print(f"[WORKER] ⚠ Chunk {chunk_idx} failed — server will re-queue it")
                else:
                    print(f"[WORKER] ⚠ Submit returned {submit_resp.status_code}")
            except Exception as e:
                print(f"[WORKER] ⚠ Could not submit result: {e}. Chunk will timeout on server.")

            time.sleep(POLL_INTERVAL_BUSY)

        except KeyboardInterrupt:
            print("\n[WORKER] Interrupted. Exiting.")
            sys.exit(0)

        except Exception as e:
            print(f"[WORKER] ❌ Unexpected error: {e}")
            time.sleep(POLL_INTERVAL_IDLE)


# ─────────────────────────────────────────────────────────────────────────────
# DOWNLOAD + PROCESS
# ─────────────────────────────────────────────────────────────────────────────
def _download_and_process(
    job_id:       str,
    chunk_idx:    int,
    start_offset: int,
    ocr_enabled:  bool = False,
) -> tuple:
    """
    Downloads raw PDF bytes from server, runs Docling, returns markdown.
    Returns (success: bool, markdown_text: str).

    Selects converter_fast or converter_ocr based on the ocr_enabled flag
    set by the user at upload time.
    """
    # Use system temp dir with unique filename — no CWD dependency, no conflicts
    temp_path = Path(tempfile.gettempdir()) / f"rag_chunk_{job_id}.pdf"

    try:
        # Download binary PDF chunk from server
        dl_resp = requests.get(
            f"{EXTRACTION_SERVER_URL}/chunk/{job_id}",
            timeout=60,
            stream=True,
        )
        if dl_resp.status_code != 200:
            print(f"[WORKER] ❌ Could not download chunk {chunk_idx}: "
                  f"HTTP {dl_resp.status_code}")
            return False, ""

        with open(str(temp_path), "wb") as f:
            for block in dl_resp.iter_content(chunk_size=65536):
                f.write(block)

        # Run Docling with the converter requested by the job
        converter = converter_ocr if ocr_enabled else converter_fast
        t_start   = time.time()
        result    = converter.convert(str(temp_path))
        elapsed   = time.time() - t_start
        num_pages = len(result.document.pages)

        # Build markdown with correct real page numbers
        pages = []
        for local_pg in range(1, num_pages + 1):
            real_pg = start_offset + local_pg
            page_md = result.document.export_to_markdown(page_no=local_pg)
            header  = f"\n\n\n## --- PAGE {real_pg} ---\n\n"
            pages.append(header + page_md)

        markdown = "".join(pages)
        print(f"[WORKER] ✅ Chunk {chunk_idx}: {num_pages} pages in {elapsed:.1f}s")
        return True, markdown

    except Exception as e:
        print(f"[WORKER] ❌ Processing failed for chunk {chunk_idx}: {e}")
        return False, ""

    finally:
        # Always clean up temp file regardless of success or failure
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
