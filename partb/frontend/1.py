"""
chat.html — EXACT CHANGES TO MAKE
===================================
This file documents the three precise changes to make in chat.html.
Do NOT rewrite the whole file. Find each FIND block and replace with
the corresponding REPLACE block. Everything else stays identical.

CHANGE 1 — Add PDF.js script tag (one line in <head>)
CHANGE 2 — Replace the book panel HTML
CHANGE 3 — Replace the BOOK VIEWER PANEL JS section

SETUP REQUIRED BEFORE THESE CHANGES:
  Download PDF.js prebuilt package from:
    https://github.com/mozilla/pdf.js/releases/latest
  Extract and copy two files to partb/static/pdfjs/:
    pdf.min.js          (the main library)
    pdf.worker.min.js   (the web worker, handles PDF parsing)

  Your static folder structure:
    partb/
      static/
        pdfjs/
          pdf.min.js
          pdf.worker.min.js
        isro-logo.svg    (already there)
"""


# ═══════════════════════════════════════════════════════════════════════════
# CHANGE 1 — Add PDF.js script tag
# ═══════════════════════════════════════════════════════════════════════════
# FIND this line (it is the last script tag before </head>):
CHANGE_1_FIND = """<script src="https://cdnjs.cloudflare.com/ajax/libs/marked/9.1.6/marked.min.js"></script>"""

# REPLACE with this (add the PDF.js script tag right after marked):
CHANGE_1_REPLACE = """<script src="https://cdnjs.cloudflare.com/ajax/libs/marked/9.1.6/marked.min.js"></script>
<script src="/static/pdfjs/pdf.min.js"></script>"""


# ═══════════════════════════════════════════════════════════════════════════
# CHANGE 2 — Replace book panel CSS (add page input style)
# ═══════════════════════════════════════════════════════════════════════════
# FIND this CSS block:
CHANGE_2_FIND = """#book-panel-content .page-text strong { color: #93c5fd; }
#book-panel-content .page-text table { width: 100%; border-collapse: collapse; margin-bottom: 12px; }
#book-panel-content .page-text th,
#book-panel-content .page-text td   { border: 1px solid #2d3748; padding: 6px 10px; font-size: 12px; }
#book-panel-content .page-text th   { background: #1e2736; }"""

# REPLACE with (add page-input style after):
CHANGE_2_REPLACE = """#book-panel-content .page-text strong { color: #93c5fd; }
#book-panel-content .page-text table { width: 100%; border-collapse: collapse; margin-bottom: 12px; }
#book-panel-content .page-text th,
#book-panel-content .page-text td   { border: 1px solid #2d3748; padding: 6px 10px; font-size: 12px; }
#book-panel-content .page-text th   { background: #1e2736; }
#pdf-page-input:focus { border-color: #2563eb !important; }
#pdf-page-input::-webkit-inner-spin-button,
#pdf-page-input::-webkit-outer-spin-button { opacity: 0.5; }"""


# ═══════════════════════════════════════════════════════════════════════════
# CHANGE 3 — Replace the book panel HTML
# ═══════════════════════════════════════════════════════════════════════════
# FIND this entire block:
CHANGE_3_FIND = """    <!-- Book Viewer Panel -->
    <div id="book-panel">
      <div id="book-panel-header">
        <div>
          <div id="book-panel-title">Book Viewer</div>
          <div id="book-panel-subtitle"></div>
        </div>
        <button id="book-panel-close" onclick="closeBookPanel()">✕</button>
      </div>
      <div id="book-panel-content">
        <div style="color:#475569;font-size:13px;padding:20px;text-align:center;">
          Click a source chip to view the page.
        </div>
      </div>
    </div>"""

# REPLACE with (adds nav bar + canvas):
CHANGE_3_REPLACE = """    <!-- Book Viewer Panel -->
    <div id="book-panel">
      <div id="book-panel-header">
        <div>
          <div id="book-panel-title">Book Viewer</div>
          <div id="book-panel-subtitle"></div>
        </div>
        <button id="book-panel-close" onclick="closeBookPanel()">✕</button>
      </div>
      <!-- Navigation: Prev | page input | of N | Next -->
      <div id="book-panel-nav">
        <button class="nav-btn" id="pdf-prev" onclick="pdfPrev()" disabled>&#8592; Prev</button>
        <div style="display:flex;align-items:center;gap:6px;flex:1;justify-content:center;">
          <input
            type="number"
            id="pdf-page-input"
            min="1"
            value="1"
            style="width:50px;background:#1e2736;border:1px solid #2d3748;border-radius:6px;padding:4px 6px;color:#e2e8f0;font-size:12px;text-align:center;outline:none;"
            onchange="pdfJumpTo(parseInt(this.value))"
            onkeydown="if(event.key==='Enter')pdfJumpTo(parseInt(this.value))"
          />
          <span id="pdf-total-label" style="font-size:12px;color:#475569;">of &mdash;</span>
        </div>
        <button class="nav-btn" id="pdf-next" onclick="pdfNext()" disabled>Next &#8594;</button>
      </div>
      <!-- PDF canvas area -->
      <div id="book-panel-content" style="overflow-y:auto;background:#0f1117;padding:12px;display:flex;flex-direction:column;align-items:center;gap:0;">
        <canvas id="pdf-canvas" style="max-width:100%;border-radius:4px;box-shadow:0 2px 12px rgba(0,0,0,0.4);display:none;"></canvas>
        <div id="pdf-placeholder" style="color:#475569;font-size:13px;padding:40px;text-align:center;">
          Click a source chip to view the page.
        </div>
        <div id="pdf-loading" style="display:none;color:#475569;font-size:13px;padding:20px;text-align:center;display:flex;align-items:center;gap:8px;">
          <div class="spinner"></div> Rendering page...
        </div>
      </div>
    </div>"""


# ═══════════════════════════════════════════════════════════════════════════
# CHANGE 4 — Replace the BOOK VIEWER PANEL JavaScript section
# ═══════════════════════════════════════════════════════════════════════════
# FIND this entire JS section (from the comment to closeBookPanel closing brace):
CHANGE_4_FIND = """// ═════════════════════════════════════════════════════════════════
// BOOK VIEWER PANEL
// ═════════════════════════════════════════════════════════════════
async function openBookPanel(bookId, pageNumber, msgId) {
  // Mark active chip
  document.querySelectorAll('.source-chip').forEach(c => c.classList.remove('active'));
  const chips = document.querySelectorAll(`#src-${msgId} .source-chip`);
  chips.forEach(c => { if (c.textContent.includes(`Pg ${pageNumber}`)) c.classList.add('active'); });

  document.getElementById('book-panel').classList.add('open');
  await loadBookPage(bookId, pageNumber);
}

async function loadBookPage(bookId, pageNumber) {
  const contentEl  = document.getElementById('book-panel-content');
  const titleEl    = document.getElementById('book-panel-title');
  const subtitleEl = document.getElementById('book-panel-subtitle');

  titleEl.textContent    = bookId;
  subtitleEl.textContent = `Page ${pageNumber}`;
  contentEl.innerHTML    = '<div style="display:flex;align-items:center;gap:8px;padding:20px;color:#475569;"><div class="spinner"></div> Loading page...</div>';

  try {
    const res  = await fetch(`${API}/books/${bookId}/page/${pageNumber}`, { headers: authHeaders() });
    const data = await res.json();

    if (!res.ok) {
      contentEl.innerHTML = `<div style="color:#f87171;padding:16px;">Page not found.</div>`;
      return;
    }

    bookViewer = { bookId, pageNumber: data.page_number };

    subtitleEl.textContent = `Page ${data.page_number}`;

    contentEl.innerHTML = `<div class="page-text">${renderMarkdown(data.text || '')}</div>`;

  } catch(e) {
    contentEl.innerHTML = `<div style="color:#f87171;padding:16px;">Failed to load page.</div>`;
  }
}

function closeBookPanel() {
  document.getElementById('book-panel').classList.remove('open');
  document.querySelectorAll('.source-chip').forEach(c => c.classList.remove('active'));
  bookViewer = { bookId: null, pageNumber: null };
}"""

# REPLACE with PDF.js-based viewer:
CHANGE_4_REPLACE = """// ═════════════════════════════════════════════════════════════════
// BOOK VIEWER PANEL — PDF.js renderer
// ═════════════════════════════════════════════════════════════════

// PDF.js state
let _pdfDoc        = null;   // loaded PDFDocumentProxy
let _pdfBookId     = null;   // book_id currently loaded
let _pdfCurPage    = 1;      // currently rendered page number
let _pdfTotalPages = 0;      // total pages in loaded PDF
let _pdfRendering  = false;  // guard: prevent concurrent renders

// Configure PDF.js worker (served from our static folder)
if (typeof pdfjsLib !== 'undefined') {
  pdfjsLib.GlobalWorkerOptions.workerSrc = '/static/pdfjs/pdf.worker.min.js';
}

function _pdfUpdateNav() {
  const prevBtn   = document.getElementById('pdf-prev');
  const nextBtn   = document.getElementById('pdf-next');
  const pageInput = document.getElementById('pdf-page-input');
  const totalLbl  = document.getElementById('pdf-total-label');

  if (prevBtn)   prevBtn.disabled   = (_pdfCurPage <= 1);
  if (nextBtn)   nextBtn.disabled   = (_pdfCurPage >= _pdfTotalPages);
  if (pageInput) pageInput.value    = _pdfCurPage;
  if (pageInput) pageInput.max      = _pdfTotalPages;
  if (totalLbl)  totalLbl.textContent = `of ${_pdfTotalPages}`;

  document.getElementById('book-panel-subtitle').textContent = `Page ${_pdfCurPage} of ${_pdfTotalPages}`;
}

async function _pdfRenderPage(pageNum) {
  if (!_pdfDoc || _pdfRendering) return;
  _pdfRendering = true;

  const canvas      = document.getElementById('pdf-canvas');
  const placeholder = document.getElementById('pdf-placeholder');
  const loading     = document.getElementById('pdf-loading');

  if (placeholder) placeholder.style.display = 'none';
  if (loading)     loading.style.display     = 'flex';
  if (canvas)      canvas.style.display      = 'none';

  try {
    const page     = await _pdfDoc.getPage(pageNum);
    const viewport = page.getViewport({ scale: 1.5 });
    const ctx      = canvas.getContext('2d');

    canvas.height = viewport.height;
    canvas.width  = viewport.width;

    await page.render({ canvasContext: ctx, viewport }).promise;

    canvas.style.display = 'block';
    _pdfCurPage = pageNum;
    _pdfUpdateNav();

  } catch(e) {
    console.error('PDF render error:', e);
    if (canvas) canvas.style.display = 'none';
    if (placeholder) {
      placeholder.textContent = 'Failed to render page.';
      placeholder.style.display = 'block';
    }
  } finally {
    _pdfRendering = false;
    if (loading) loading.style.display = 'none';
  }
}

async function _loadPdfForBook(bookId, jumpToPage) {
  const titleEl = document.getElementById('book-panel-title');
  titleEl.textContent = bookId;

  // If already loaded for this book, just jump to page
  if (_pdfDoc && _pdfBookId === bookId) {
    await _pdfRenderPage(Math.min(jumpToPage, _pdfTotalPages));
    return;
  }

  // Load the PDF from our endpoint
  const pdfUrl = `${API}/pdf/${bookId}`;

  try {
    const loadingTask = pdfjsLib.getDocument({
      url:     pdfUrl,
      httpHeaders: { 'Authorization': `Bearer ${token}` },
    });

    _pdfDoc        = await loadingTask.promise;
    _pdfBookId     = bookId;
    _pdfTotalPages = _pdfDoc.numPages;

    await _pdfRenderPage(Math.min(jumpToPage, _pdfTotalPages));

  } catch(e) {
    console.error('PDF load error:', e);
    const placeholder = document.getElementById('pdf-placeholder');
    if (placeholder) {
      placeholder.textContent = 'Failed to load PDF. Check the server is running.';
      placeholder.style.display = 'block';
    }
  }
}

// Called by source chips — same signature as before
async function openBookPanel(bookId, pageNumber, msgId) {
  // Mark active chip
  document.querySelectorAll('.source-chip').forEach(c => c.classList.remove('active'));
  const chips = document.querySelectorAll(`#src-${msgId} .source-chip`);
  chips.forEach(c => {
    if (c.textContent.includes(`Pg ${pageNumber}`)) c.classList.add('active');
  });

  // Open panel
  document.getElementById('book-panel').classList.add('open');
  bookViewer = { bookId, pageNumber };

  // Load PDF and jump to the source page
  await _loadPdfForBook(bookId, pageNumber);
}

// Called by Prev button
async function pdfPrev() {
  if (_pdfCurPage > 1) await _pdfRenderPage(_pdfCurPage - 1);
}

// Called by Next button
async function pdfNext() {
  if (_pdfCurPage < _pdfTotalPages) await _pdfRenderPage(_pdfCurPage + 1);
}

// Called by page number input (Enter or change)
async function pdfJumpTo(n) {
  if (!_pdfDoc) return;
  const page = Math.max(1, Math.min(_pdfTotalPages, n || 1));
  if (page !== _pdfCurPage) await _pdfRenderPage(page);
}

function closeBookPanel() {
  document.getElementById('book-panel').classList.remove('open');
  document.querySelectorAll('.source-chip').forEach(c => c.classList.remove('active'));
  bookViewer = { bookId: null, pageNumber: null };
  // Note: we intentionally keep _pdfDoc loaded in memory.
  // If user reopens the same book, pages render instantly.
  // _pdfDoc is only replaced when a different book_id is opened.
}"""
