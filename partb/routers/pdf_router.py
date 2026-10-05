"""
pdf_router.py  —  Part B
Serves PDF page images for the side-panel viewer in chat.html.

Endpoints:
  GET /pdf/{book_id}/info                      → {"total_pages": N}
  GET /pdf/{book_id}/page/{page_number}/image  → PNG of that page (JWT via ?token=)
  GET /pdf/{book_id}                           → raw PDF stream (legacy)
"""
from __future__ import annotations

from pathlib import Path

import pypdf
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response

from partb.auth_jwt import verify_token
from partb.config import PARTA_DATA_DIR

router = APIRouter(prefix="/pdf", tags=["pdf"])

PDF_DIR = PARTA_DATA_DIR / "raw"


def _pdf_path(book_id: str) -> Path:
    direct = PDF_DIR / f"{book_id}.pdf"
    if direct.is_file():
        return direct
    for path in PDF_DIR.glob("*.pdf"):
        if path.stem.lower() == book_id.lower():
            return path
    raise HTTPException(404, f"PDF not found for book '{book_id}'")


def _verify_query_token(token: str | None) -> None:
    if not token:
        raise HTTPException(401, "Missing token")
    try:
        from partb.auth_jwt import decode_token

        decode_token(token)
    except Exception as exc:
        raise HTTPException(401, "Invalid or expired token") from exc


def _render_page_png(path: Path, page_number: int, scale: float = 2.0) -> bytes:
    import fitz

    doc = fitz.open(str(path))
    try:
        if page_number < 1 or page_number > len(doc):
            raise HTTPException(404, f"Page {page_number} not found (PDF has {len(doc)} pages)")
        page = doc[page_number - 1]
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        return pix.tobytes("png")
    finally:
        doc.close()


@router.get("/{book_id}/info")
async def pdf_info(book_id: str, user=Depends(verify_token)):
    """Return total page count. Called once when opening the panel."""
    path = _pdf_path(book_id)
    try:
        reader = pypdf.PdfReader(str(path))
        return {"book_id": book_id, "total_pages": len(reader.pages)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Could not read PDF: {e}") from e


@router.get("/{book_id}/page/{page_number}/image")
async def page_image(book_id: str, page_number: int, token: str = Query(None)):
    """Render a single PDF page as PNG for the side-panel image viewer."""
    _verify_query_token(token)
    path = _pdf_path(book_id)
    try:
        png = _render_page_png(path, page_number)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Could not render page: {e}") from e
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.get("/{book_id}")
async def serve_pdf(book_id: str, token: str = Query(None)):
    """
    Stream the raw PDF binary (legacy).
    Token is accepted as a query param because iframe/img src
    cannot carry Authorization headers.
    """
    _verify_query_token(token)

    path = _pdf_path(book_id)
    return FileResponse(
        path=str(path),
        media_type="application/pdf",
        filename=f"{book_id}.pdf",
        headers={
            "Cache-Control": "private, max-age=3600",
            "Content-Disposition": f'inline; filename="{book_id}.pdf"',
        },
    )
