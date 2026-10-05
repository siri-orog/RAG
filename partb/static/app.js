const API = '';

let token = localStorage.getItem('kr_token') || '';
let currentUser = null;
try {
  currentUser = JSON.parse(localStorage.getItem('kr_user') || 'null');
} catch {
  currentUser = null;
}

let currentChat = null;
let currentMode = 'balanced';
let modalMode = 'balanced';
let isStreaming = false;
let popupOpen = false;
let bookViewer = { bookId: null, pageNumber: 1, totalPages: 0 };

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function modeLabel(mode) {
  return { fast: '⚡ Fast', balanced: '⚖ Balanced', deep: '🧠 Deep' }[mode] || mode;
}

function renderMarkdown(text) {
  if (typeof marked !== 'undefined') {
    try { return marked.parse(text || ''); } catch { /* fall through */ }
  }
  return escHtml(text || '').replace(/\n/g, '<br>');
}

function authHeaders() {
  return { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` };
}

function showAuthForm(tab) {
  const isLogin = tab === 'login';
  document.querySelectorAll('.auth-tab').forEach((t, i) => {
    t.classList.toggle('active', i === (isLogin ? 0 : 1));
  });
  document.getElementById('form-login').classList.toggle('active', isLogin);
  document.getElementById('form-signup').classList.toggle('active', !isLogin);
}

function showLoginError(msg) {
  const el = document.getElementById('login-error');
  el.textContent = msg;
  el.style.display = 'block';
}

async function doLogin() {
  const email = document.getElementById('login-email').value.trim();
  const password = document.getElementById('login-password').value;
  const btn = document.getElementById('login-btn');
  document.getElementById('login-error').style.display = 'none';
  if (!email || !password) {
    showLoginError('Enter email and password.');
    return;
  }
  btn.textContent = 'Signing in...';
  btn.disabled = true;
  try {
    const res = await fetch(`${API}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    const data = await res.json();
    if (!res.ok) {
      showLoginError(data.detail || 'Login failed.');
      return;
    }
    token = data.token;
    currentUser = { user_id: data.user_id, name: data.name, email: data.email, role: data.role };
    localStorage.setItem('kr_token', token);
    localStorage.setItem('kr_user', JSON.stringify(currentUser));
    document.getElementById('login-screen').style.display = 'none';
    document.getElementById('app').style.display = 'flex';
    const ur = document.getElementById('user-role-display');
    if (ur) ur.textContent = `${currentUser.name} · ${currentUser.role}`;
    loadChats();
    checkHealth();
  } catch {
    showLoginError('Cannot connect to server. Is Part B running?');
  } finally {
    btn.textContent = 'Sign In';
    btn.disabled = false;
  }
}

async function doSignup() {
  const name = document.getElementById('signup-name').value.trim();
  const email = document.getElementById('signup-email').value.trim();
  const password = document.getElementById('signup-password').value;
  const errEl = document.getElementById('signup-error');
  const btn = document.getElementById('signup-btn');
  errEl.style.display = 'none';
  if (!name || !email || !password) {
    errEl.textContent = 'All fields are required.';
    errEl.style.display = 'block';
    return;
  }
  if (password.length < 6) {
    errEl.textContent = 'Password must be at least 6 characters.';
    errEl.style.display = 'block';
    return;
  }
  btn.textContent = 'Creating account...';
  btn.disabled = true;
  try {
    const res = await fetch(`${API}/auth/signup`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email, password }),
    });
    const data = await res.json();
    if (!res.ok) {
      errEl.textContent = data.detail || 'Sign up failed.';
      errEl.style.color = '#f87171';
      errEl.style.display = 'block';
      return;
    }
    errEl.textContent = data.message || 'Account created. Sign in below.';
    errEl.style.color = '#4ade80';
    errEl.style.display = 'block';
    document.getElementById('login-email').value = email;
    showAuthForm('login');
  } catch {
    errEl.textContent = 'Cannot connect to server.';
    errEl.style.color = '#f87171';
    errEl.style.display = 'block';
  } finally {
    btn.textContent = 'Create account';
    btn.disabled = false;
  }
}

function logout() {
  localStorage.removeItem('kr_token');
  localStorage.removeItem('kr_user');
  token = null;
  currentUser = null;
  location.reload();
}

async function checkHealth() {
  const el = document.getElementById('health-indicator');
  if (!el) return;
  try {
    const res = await fetch(`${API}/health`, { headers: authHeaders() });
    if (!res.ok) throw new Error('health failed');
    const data = await res.json();
    const core = ['neo4j', 'qdrant', 'mongodb', 'ollama'];
    const allOk = core.every(k => data[k]?.status === 'ok');
    el.textContent = allOk ? '● All systems OK' : '● Some services degraded';
    el.style.color = allOk ? '#4ade80' : '#fbbf24';
  } catch {
    el.textContent = '● Offline';
    el.style.color = '#f87171';
  }
}

async function loadChats() {
  try {
    const res = await fetch(`${API}/chats`, { headers: authHeaders() });
    if (res.status === 401) { logout(); return; }
    const data = await res.json();
    renderChatList(Array.isArray(data) ? data : (data.chats || []));
  } catch (e) {
    console.error('loadChats error:', e);
  }
}

function renderChatList(chats) {
  const el = document.getElementById('chat-list');
  if (!chats.length) {
    el.innerHTML = '<div style="color:#475569;font-size:12px;padding:12px;text-align:center;">No chats yet</div>';
    return;
  }
  el.innerHTML = chats.map(c => `
    <div class="chat-item ${currentChat?.chat_id === c.chat_id ? 'active' : ''}"
         onclick="openChat('${c.chat_id}')">
      <div class="chat-item-icon">💬</div>
      <div class="chat-item-body">
        <div class="chat-item-title">${escHtml(c.title || 'New Chat')}</div>
        <div class="chat-item-meta">${c.message_count || 0} messages</div>
      </div>
      <button class="chat-item-delete" onclick="deleteChat(event,'${c.chat_id}')">✕</button>
    </div>
  `).join('');
}

async function openChat(chatId) {
  try {
    const [chatRes, msgRes] = await Promise.all([
      fetch(`${API}/chats/${chatId}`, { headers: authHeaders() }),
      fetch(`${API}/chats/${chatId}/messages`, { headers: authHeaders() }),
    ]);
    if (chatRes.status === 401) { logout(); return; }
    const chat = await chatRes.json();
    const messages = msgRes.ok ? await msgRes.json() : [];
    currentChat = chat;
    currentMode = chat.default_mode || 'balanced';
    updateModeUI(currentMode);
    renderChatView(chat, messages);
    loadChats();
  } catch (e) {
    console.error('openChat error:', e);
  }
}

function renderChatView(chat, messages) {
  document.getElementById('chat-title').textContent = chat.title || 'New Chat';
  document.getElementById('chat-title').style.color = '#e2e8f0';
  const bookIds = chat.book_ids || [];
  document.getElementById('book-chips-area').innerHTML =
    bookIds.map(bid => `<span class="book-chip-header">📄 ${escHtml(bid)}</span>`).join('');
  const area = document.getElementById('messages-area');
  document.getElementById('empty-state')?.remove();
  area.innerHTML = '';
  if (!messages.length) {
    area.innerHTML = '<div style="padding:40px;color:#475569;text-align:center;font-size:13px;">No messages yet — ask your first question below.</div>';
  } else {
    messages.forEach(m => appendMessage(m.role, m.content, m.mode || 'balanced', m.sources || [], false));
  }
  scrollBottom();
}

async function deleteChat(e, chatId) {
  e.stopPropagation();
  if (!confirm('Delete this chat?')) return;
  await fetch(`${API}/chats/${chatId}`, { method: 'DELETE', headers: authHeaders() });
  if (currentChat?.chat_id === chatId) {
    currentChat = null;
    document.getElementById('chat-title').textContent = 'Select or create a chat';
    document.getElementById('chat-title').style.color = '#475569';
    document.getElementById('book-chips-area').innerHTML = '';
    document.getElementById('messages-area').innerHTML = `
      <div id="empty-state"><div class="icon">🛰</div><h3>ISRO Knowledge Assistant</h3>
      <p>Create a new chat and select the documents you want to query.</p></div>`;
    closeBookPanel();
  }
  loadChats();
}

function openNewChatModal() { showNewChatModal(); }
function closeNewChatModal() { closeModal(); }

async function showNewChatModal() {
  document.getElementById('modal-overlay').classList.add('show');
  document.getElementById('book-error').style.display = 'none';
  const nameEl = document.getElementById('new-chat-name');
  if (nameEl) nameEl.value = '';
  modalMode = 'balanced';
  selectModalMode('balanced');
  const listEl = document.getElementById('book-select-list');
  listEl.innerHTML = '<div style="color:#475569;font-size:12px;text-align:center;padding:12px;">Loading...</div>';
  try {
    const res = await fetch(`${API}/library`, { headers: authHeaders() });
    const data = await res.json();
    const books = data.books || [];
    if (!books.length) {
      listEl.innerHTML = '<div style="color:#475569;font-size:12px;text-align:center;padding:12px;">No ready documents found.</div>';
      return;
    }
    listEl.innerHTML = books.map(b => `
      <div class="book-select-item" id="bsi-${escHtml(b.book_id)}" onclick="toggleBookSelect('${escHtml(b.book_id)}')">
        <input type="checkbox" id="bsc-${escHtml(b.book_id)}" onclick="event.stopPropagation();toggleBookSelect('${escHtml(b.book_id)}')"/>
        <div>
          <div class="book-select-name">${escHtml(b.title || b.book_id)}</div>
          <div class="book-select-meta">${b.total_pages || '?'} pages · ${escHtml(b.book_id)}</div>
        </div>
      </div>`).join('');
  } catch {
    listEl.innerHTML = '<div style="color:#f87171;font-size:12px;text-align:center;padding:12px;">Failed to load books.</div>';
  }
}

function toggleBookSelect(bookId) {
  const item = document.getElementById(`bsi-${bookId}`);
  const cb = document.getElementById(`bsc-${bookId}`);
  if (!cb || !item) return;
  cb.checked = !cb.checked;
  item.classList.toggle('checked', cb.checked);
}

function selectModalMode(mode) {
  modalMode = mode;
  ['fast', 'balanced', 'deep'].forEach(m => {
    const el = document.getElementById(`mr-${m}`);
    if (el) el.classList.toggle('selected', m === mode);
  });
}

function closeModal() {
  document.getElementById('modal-overlay').classList.remove('show');
}

async function createChat() {
  const selectedBooks = Array.from(document.querySelectorAll('#book-select-list input[type=checkbox]:checked'))
    .map(cb => cb.id.replace('bsc-', ''));
  if (!selectedBooks.length) {
    document.getElementById('book-error').style.display = 'block';
    return;
  }
  const title = (document.getElementById('new-chat-name')?.value || '').trim() || undefined;
  try {
    const res = await fetch(`${API}/chats`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ book_ids: selectedBooks, default_mode: modalMode, title }),
    });
    const chat = await res.json();
    if (!res.ok) {
      alert(chat.detail || 'Failed to create chat.');
      return;
    }
    closeModal();
    currentChat = chat;
    currentMode = chat.default_mode || modalMode;
    updateModeUI(currentMode);
    renderChatView(chat, []);
    loadChats();
  } catch {
    alert('Network error creating chat.');
  }
}

function toggleModePopup(e) {
  e.stopPropagation();
  popupOpen = !popupOpen;
  document.getElementById('mode-popup').style.display = popupOpen ? 'block' : 'none';
}

function selectMode(mode) {
  currentMode = mode;
  updateModeUI(mode);
  popupOpen = false;
  document.getElementById('mode-popup').style.display = 'none';
  if (currentChat) {
    fetch(`${API}/chats/${currentChat.chat_id}`, {
      method: 'PATCH',
      headers: authHeaders(),
      body: JSON.stringify({ default_mode: mode }),
    }).catch(() => {});
  }
}

function updateModeUI(mode) {
  const icons = { fast: '⚡', balanced: '⚖', deep: '🧠' };
  const labels = { fast: 'Fast', balanced: 'Balanced', deep: 'Deep' };
  const iconEl = document.getElementById('mode-icon');
  const labelEl = document.getElementById('mode-label');
  if (iconEl) iconEl.textContent = icons[mode] || '⚖';
  if (labelEl) labelEl.textContent = labels[mode] || 'Balanced';
  ['fast', 'balanced', 'deep'].forEach(m => {
    const opt = document.getElementById(`mode-otp-${m}`);
    if (opt) opt.classList.toggle('selected', m === mode);
    const ck = document.getElementById(`mc-${m}`);
    if (ck) {
      ck.classList.toggle('on', m === mode);
      ck.textContent = m === mode ? '✓' : '';
    }
  });
}

document.addEventListener('click', e => {
  if (!e.target.closest('#mode-btn') && !e.target.closest('#mode-popup')) {
    popupOpen = false;
    const popup = document.getElementById('mode-popup');
    if (popup) popup.style.display = 'none';
  }
});

function appendMessage(role, content, mode, sources, streaming) {
  const area = document.getElementById('messages-area');
  document.getElementById('empty-state')?.remove();
  const row = document.createElement('div');
  row.className = 'msg-row';
  if (role === 'user') {
    row.innerHTML = `
      <div class="msg-user">
        <div class="msg-user-text">${escHtml(content)}</div>
        <div class="msg-user-meta"><span class="mode-badge ${mode}">${modeLabel(mode)}</span></div>
      </div>`;
  } else {
    const msgId = 'msg-' + Date.now() + Math.random().toString(36).slice(2, 6);
    const srcHtml = sources.length ? renderSourceChips(sources, msgId) : '';
    row.innerHTML = `
      <div class="msg-assistant">
        <div class="msg-assistant-text ${streaming ? 'streaming' : ''}" id="${msgId}">
          ${streaming ? '' : renderMarkdown(content)}
        </div>
        <div class="sources-row" id="src-${msgId}">${srcHtml}</div>
      </div>`;
    row.dataset.msgId = msgId;
  }
  area.appendChild(row);
  scrollBottom();
  return row;
}

function sourceStartPage(s) {
  if (s.page_range && Array.isArray(s.page_range) && s.page_range.length >= 1) return s.page_range[0];
  return s.page_number != null ? s.page_number : 1;
}

function renderSourceChips(sources, msgId) {
  if (!sources || !sources.length) return '';
  const seen = new Set();
  return sources.filter(s => {
    const k = `${s.book_id}:${sourceStartPage(s)}`;
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  }).map(s => {
    const p = sourceStartPage(s);
    const pr = s.page_range;
    const label = pr && pr.length >= 2 && pr[0] !== pr[1] ? `Pg ${pr[0]}–${pr[1]}` : `Pg ${p}`;
    return `<span class="source-chip" onclick="openBookPanel('${escHtml(s.book_id || '')}',${p},'${msgId}')">📄 ${escHtml(s.book_id || '')} · ${label}</span>`;
  }).join('');
}

async function sendQuestion(regenContent, regenMode, regenRowEl) {
  if (!currentChat) { openNewChatModal(); return; }
  if (isStreaming) return;
  const inputEl = document.getElementById('question-input');
  const question = regenContent !== undefined ? regenContent : inputEl.value.trim();
  const mode = regenMode !== undefined ? regenMode : currentMode;
  if (!question) return;
  isStreaming = true;
  document.getElementById('send-btn').disabled = true;
  if (regenRowEl) {
    regenRowEl.remove();
  } else {
    inputEl.value = '';
    autoResize(inputEl);
    appendMessage('user', question, mode, [], false);
  }
  const area = document.getElementById('messages-area');
  const statusRow = document.createElement('div');
  statusRow.className = 'msg-row';
  statusRow.innerHTML = `<div class="status-msg"><div class="status-dot"></div><span id="status-text">Searching knowledge base...</span></div>`;
  area.appendChild(statusRow);
  scrollBottom();
  let assistantRow = null;
  let msgEl = null;
  try {
    const res = await fetch(`${API}/chats/${currentChat.chat_id}/ask`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ question, mode }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      statusRow.remove();
      appendErrorMessage(err.detail || 'Request failed.');
      return;
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split('\n');
      buffer = parts.pop();
      for (const line of parts) {
        if (!line.startsWith('data: ')) continue;
        let event;
        try { event = JSON.parse(line.slice(6).trim()); } catch { continue; }
        if (event.type === 'status') {
          const st = document.getElementById('status-text');
          if (st) st.textContent = event.message;
        } else if (event.type === 'token') {
          if (!assistantRow) {
            statusRow.remove();
            assistantRow = appendMessage('assistant', '', mode, [], true);
            msgEl = assistantRow.querySelector('.msg-assistant-text');
          }
          msgEl.textContent += event.content;
          scrollBottom();
        } else if (event.type === 'done') {
          const sources = event.sources || [];
          if (msgEl) {
            msgEl.innerHTML = renderMarkdown(msgEl.textContent);
            msgEl.classList.remove('streaming');
          }
          if (assistantRow) {
            const msgId = assistantRow.querySelector('.msg-assistant-text')?.id;
            const srcEl = assistantRow.querySelector('.sources-row');
            if (srcEl && msgId) srcEl.innerHTML = renderSourceChips(sources, msgId);
          }
          if (!assistantRow) statusRow.remove();
          loadChats();
        } else if (event.type === 'error') {
          if (!assistantRow) statusRow.remove();
          appendErrorMessage(event.message);
        }
      }
    }
  } catch {
    statusRow.remove();
    appendErrorMessage('Connection lost. Please try again.');
  } finally {
    isStreaming = false;
    document.getElementById('send-btn').disabled = false;
    scrollBottom();
  }
}

function appendErrorMessage(msg) {
  const area = document.getElementById('messages-area');
  const row = document.createElement('div');
  row.className = 'msg-row';
  row.innerHTML = `<div style="background:#7f1d1d20;border:1px solid #ef444440;border-radius:8px;padding:12px 16px;color:#fca5a5;font-size:13px;max-width:80%;">⚠ ${escHtml(msg)}</div>`;
  area.appendChild(row);
  scrollBottom();
}

function useSuggestion(el) {
  document.getElementById('question-input').value = el.textContent.trim();
  autoResize(document.getElementById('question-input'));
  if (!currentChat) openNewChatModal();
  else sendQuestion();
}

function _pdfUpdateNav() {
  document.getElementById('pdf-prev').disabled = bookViewer.pageNumber <= 1;
  document.getElementById('pdf-next').disabled =
    bookViewer.totalPages && bookViewer.pageNumber >= bookViewer.totalPages;
  document.getElementById('pdf-page-input').value = bookViewer.pageNumber;
  document.getElementById('pdf-page-input').max = bookViewer.totalPages || 9999;
  document.getElementById('pdf-page-total').textContent =
    bookViewer.totalPages ? `of ${bookViewer.totalPages}` : 'of —';
  document.getElementById('book-panel-subtitle').textContent =
    bookViewer.totalPages
      ? `Page ${bookViewer.pageNumber} of ${bookViewer.totalPages}`
      : `Page ${bookViewer.pageNumber}`;
}

function _loadPageImage(bookId, page) {
  const img = document.getElementById('page-image');
  const placeholder = document.getElementById('page-placeholder');
  const loading = document.getElementById('page-loading');
  placeholder.style.display = 'none';
  loading.style.display = 'flex';
  img.style.display = 'none';
  const url = `${API}/pdf/${encodeURIComponent(bookId)}/page/${page}/image?token=${encodeURIComponent(token)}&v=${Date.now()}`;
  img.onload = () => {
    loading.style.display = 'none';
    img.style.display = 'block';
  };
  img.onerror = () => {
    loading.style.display = 'none';
    placeholder.style.display = 'flex';
    placeholder.textContent = 'Could not load this page.';
  };
  img.src = url;
}

async function openBookPanel(bookId, pageNumber, msgId) {
  document.querySelectorAll('.source-chip').forEach(c => c.classList.remove('active'));
  if (msgId) {
    document.querySelectorAll(`#src-${msgId} .source-chip`).forEach(c => {
      if (c.textContent.includes(`Pg ${pageNumber}`)) c.classList.add('active');
    });
  }
  document.getElementById('book-panel').classList.add('open');
  document.getElementById('book-panel-title').textContent = bookId;
  if (bookViewer.bookId !== bookId) {
    bookViewer.totalPages = 0;
    try {
      const res = await fetch(`${API}/pdf/${encodeURIComponent(bookId)}/info`, { headers: authHeaders() });
      const data = await res.json();
      bookViewer.totalPages = data.total_pages || 0;
    } catch { /* non-fatal */ }
  }
  bookViewer.bookId = bookId;
  bookViewer.pageNumber = Math.max(1, parseInt(pageNumber, 10) || 1);
  _pdfUpdateNav();
  _loadPageImage(bookId, bookViewer.pageNumber);
}

function pdfPrev() {
  if (bookViewer.pageNumber <= 1) return;
  bookViewer.pageNumber--;
  _pdfUpdateNav();
  _loadPageImage(bookViewer.bookId, bookViewer.pageNumber);
}

function pdfNext() {
  if (bookViewer.totalPages && bookViewer.pageNumber >= bookViewer.totalPages) return;
  bookViewer.pageNumber++;
  _pdfUpdateNav();
  _loadPageImage(bookViewer.bookId, bookViewer.pageNumber);
}

function pdfJumpTo(n) {
  if (!bookViewer.bookId) return;
  const page = Math.max(1, Math.min(bookViewer.totalPages || 99999, Math.floor(n) || 1));
  bookViewer.pageNumber = page;
  _pdfUpdateNav();
  _loadPageImage(bookViewer.bookId, page);
}

function closeBookPanel() {
  document.getElementById('book-panel').classList.remove('open');
  document.querySelectorAll('.source-chip').forEach(c => c.classList.remove('active'));
  const img = document.getElementById('page-image');
  if (img) img.removeAttribute('src');
  bookViewer = { bookId: null, pageNumber: 1, totalPages: 0 };
}

function scrollBottom() {
  const a = document.getElementById('messages-area');
  a.scrollTop = a.scrollHeight;
}

function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 160) + 'px';
}

function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendQuestion();
  }
}

window.addEventListener('load', () => {
  if (token && currentUser) {
    document.getElementById('login-screen').style.display = 'none';
    document.getElementById('app').style.display = 'flex';
    const ur = document.getElementById('user-role-display');
    if (ur) ur.textContent = `${currentUser.name} · ${currentUser.role}`;
    loadChats();
    checkHealth();
  }
  document.getElementById('login-password')?.addEventListener('keydown', e => {
    if (e.key === 'Enter') doLogin();
  });
  document.getElementById('signup-password')?.addEventListener('keydown', e => {
    if (e.key === 'Enter') doSignup();
  });
});
