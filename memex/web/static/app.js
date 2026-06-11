/**
 * MEMEX Web UI — Client-side JavaScript
 * All API calls to localhost:7700
 */

const API = 'http://127.0.0.1:7700';
let sessionId = crypto.randomUUID();

// ─── Initialization ───

document.addEventListener('DOMContentLoaded', () => {
    updateSessionBadge();
    loadHealth();
    loadStats();

    // Chat input: Enter to send, Shift+Enter for newline
    const chatInput = document.getElementById('chat-input');
    chatInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    // Search input: Enter to search
    const searchInput = document.getElementById('search-input');
    searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') searchMemory();
    });

    // Entity search: Enter to search
    const entitySearch = document.getElementById('entity-search');
    entitySearch.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') searchEntities();
    });

    // Auto-refresh health every 30s
    setInterval(loadHealth, 30000);
});

// ─── View Navigation ───

function showView(viewName) {
    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));

    const view = document.getElementById(`${viewName}-view`);
    if (view) view.classList.add('active');

    const btn = document.querySelector(`[data-view="${viewName}"]`);
    if (btn) btn.classList.add('active');

    // Load data for specific views
    if (viewName === 'timeline') loadTimeline();
    if (viewName === 'settings') { loadHealth(); loadStats(); }
}

function updateSessionBadge() {
    document.getElementById('session-id').textContent = `Session: ${sessionId.substring(0, 8)}`;
}

// ─── Chat ───

async function sendMessage() {
    const input = document.getElementById('chat-input');
    const query = input.value.trim();
    if (!query) return;

    input.value = '';
    appendMessage('user', query);

    const sendBtn = document.getElementById('send-btn');
    sendBtn.disabled = true;
    sendBtn.textContent = 'Thinking...';

    try {
        const response = await fetch(`${API}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: sessionId, query }),
        });

        const result = await response.json();

        if (result.success && result.data) {
            appendMessage('assistant', result.data.answer, result.data.citations);
        } else {
            appendMessage('assistant', 'Error: ' + (result.error?.message || 'Unknown error'));
        }
    } catch (err) {
        appendMessage('assistant', `Connection error: ${err.message}. Is MEMEX running?`);
    } finally {
        sendBtn.disabled = false;
        sendBtn.textContent = 'Send ↵';
    }
}

function appendMessage(role, content, citations = []) {
    const container = document.getElementById('chat-messages');
    const msg = document.createElement('div');
    msg.className = `message ${role}`;

    let html = escapeHtml(content);

    // Convert [Source N] to styled badges
    html = html.replace(/\[Source (\d+)\]/g, '<span class="source-ref">[$1]</span>');

    if (citations.length > 0) {
        html += '<div class="citations">';
        citations.forEach(c => {
            html += `<div class="citation-card">
                <span class="source-type">${c.source_type}</span>
                <div class="path">${escapeHtml(c.source_path)}</div>
                <div>${escapeHtml(c.snippet)}</div>
            </div>`;
        });
        html += '</div>';
    }

    msg.innerHTML = html;
    container.appendChild(msg);
    container.scrollTop = container.scrollHeight;
}

// ─── Search ───

async function searchMemory() {
    const query = document.getElementById('search-input').value.trim();
    if (!query) return;

    const source = document.getElementById('filter-source').value;
    const after = document.getElementById('filter-after').value;
    const before = document.getElementById('filter-before').value;

    const params = new URLSearchParams({ q: query, limit: '20' });
    if (source) params.set('source_type', source);
    if (after) params.set('after', after);
    if (before) params.set('before', before);

    const resultsDiv = document.getElementById('search-results');
    resultsDiv.innerHTML = '<div style="color: var(--text-dim); text-align: center; padding: 40px;">Searching...</div>';

    try {
        const response = await fetch(`${API}/api/memory/search?${params}`);
        const result = await response.json();

        if (result.success && result.data.results.length > 0) {
            resultsDiv.innerHTML = `<p style="color: var(--text-dim); margin-bottom: 12px;">${result.data.count} results</p>`;
            result.data.results.forEach(r => {
                resultsDiv.innerHTML += renderResultCard(r);
            });
        } else {
            resultsDiv.innerHTML = '<div style="color: var(--text-dim); text-align: center; padding: 40px;">No results found</div>';
        }
    } catch (err) {
        resultsDiv.innerHTML = `<div style="color: var(--red); text-align: center; padding: 40px;">Error: ${err.message}</div>`;
    }
}

function renderResultCard(r) {
    const date = r.captured_at ? new Date(r.captured_at).toLocaleDateString() : '';
    return `<div class="result-card">
        <span class="source-badge">${r.source_type}</span>
        <span class="score">Score: ${r.score.toFixed(4)}</span>
        <div class="path">${escapeHtml(r.source_path)}</div>
        <div class="content">${escapeHtml(r.content.substring(0, 300))}${r.content.length > 300 ? '...' : ''}</div>
    </div>`;
}

// ─── Timeline ───

async function loadTimeline() {
    const source = document.getElementById('timeline-source').value;
    const params = new URLSearchParams({ limit: '50' });
    if (source) params.set('source_type', source);

    const listDiv = document.getElementById('timeline-list');
    listDiv.innerHTML = '<div style="color: var(--text-dim); text-align: center; padding: 40px;">Loading...</div>';

    try {
        const response = await fetch(`${API}/api/memory/timeline?${params}`);
        const result = await response.json();

        if (result.success && result.data.documents.length > 0) {
            listDiv.innerHTML = '';
            result.data.documents.forEach(doc => {
                const date = doc.captured_at ? new Date(doc.captured_at).toLocaleString() : '';
                listDiv.innerHTML += `<div class="timeline-item">
                    <span class="date">${date}</span>
                    <span class="source-badge">${doc.source_type}</span>
                    <span class="path">${escapeHtml(doc.source_path)}</span>
                </div>`;
            });
        } else {
            listDiv.innerHTML = '<div style="color: var(--text-dim); text-align: center; padding: 40px;">No documents yet</div>';
        }
    } catch (err) {
        listDiv.innerHTML = `<div style="color: var(--red);">Error: ${err.message}</div>`;
    }
}

// ─── Graph (Entities) ───

async function searchEntities() {
    const query = document.getElementById('entity-search').value.trim();
    if (!query) return;

    const listDiv = document.getElementById('entity-list');
    listDiv.innerHTML = '<div style="color: var(--text-dim); text-align: center; padding: 40px;">Searching...</div>';

    try {
        const response = await fetch(`${API}/api/graph/entities?q=${encodeURIComponent(query)}`);
        const result = await response.json();

        if (result.success && result.data.entities.length > 0) {
            listDiv.innerHTML = '';
            result.data.entities.forEach(ent => {
                listDiv.innerHTML += `<div class="entity-card">
                    <span class="entity-name">${escapeHtml(ent.canonical_name)}</span>
                    <span class="entity-type">${ent.entity_type}</span>
                    <span class="entity-count">${ent.mention_count} mentions</span>
                </div>`;
            });
        } else {
            listDiv.innerHTML = '<div style="color: var(--text-dim); text-align: center; padding: 40px;">No entities found</div>';
        }
    } catch (err) {
        listDiv.innerHTML = `<div style="color: var(--red);">Error: ${err.message}</div>`;
    }
}

// ─── Health & Stats ───

async function loadHealth() {
    try {
        const response = await fetch(`${API}/api/health`);
        const health = await response.json();

        // Update sidebar status
        const statusEl = document.getElementById('health-status');
        if (health.status === 'healthy') {
            statusEl.className = 'health-ok';
            statusEl.textContent = '● Healthy';
        } else if (health.status === 'degraded') {
            statusEl.className = 'health-degraded';
            statusEl.textContent = '● Degraded';
        } else {
            statusEl.className = 'health-error';
            statusEl.textContent = '● Error';
        }

        // Update settings view
        const details = document.getElementById('health-details');
        if (details) {
            let html = '<h3>System Health</h3><div class="status-grid">';
            html += `<div class="status-item"><div class="label">Daemon</div><div class="value ${health.daemon_running ? 'ok' : 'error'}">${health.daemon_running ? 'Running' : 'Stopped'}</div></div>`;
            html += `<div class="status-item"><div class="label">Queue Depth</div><div class="value">${health.queue_depth}/${health.queue_max}</div></div>`;

            for (const [name, store] of Object.entries(health.stores || {})) {
                html += `<div class="status-item"><div class="label">${name}</div><div class="value ${store.status === 'ok' ? 'ok' : 'error'}">${store.status}</div></div>`;
            }

            if (health.ollama) {
                html += `<div class="status-item"><div class="label">Ollama</div><div class="value ${health.ollama.status === 'ok' ? 'ok' : 'error'}">${health.ollama.status}</div></div>`;
            }

            html += '</div>';
            details.innerHTML = html;
        }
    } catch (err) {
        const statusEl = document.getElementById('health-status');
        if (statusEl) {
            statusEl.className = 'health-error';
            statusEl.textContent = '● Offline';
        }
    }
}

async function loadStats() {
    try {
        const response = await fetch(`${API}/api/stats`);
        const result = await response.json();

        if (!result.success) return;
        const stats = result.data;

        // Sidebar summary
        const summary = document.getElementById('stats-summary');
        if (summary) {
            summary.innerHTML = `${stats.total_documents} docs · ${stats.total_chunks} chunks · ${stats.total_entities} entities`;
        }

        // Settings view
        const details = document.getElementById('stats-details');
        if (details) {
            let html = '<h3>Ingestion Stats</h3><div class="status-grid">';
            html += `<div class="status-item"><div class="label">Total Documents</div><div class="value">${stats.total_documents}</div></div>`;
            html += `<div class="status-item"><div class="label">Total Chunks</div><div class="value">${stats.total_chunks}</div></div>`;
            html += `<div class="status-item"><div class="label">Embedding Coverage</div><div class="value">${stats.embedding_coverage_pct}%</div></div>`;
            html += `<div class="status-item"><div class="label">Entities</div><div class="value">${stats.total_entities}</div></div>`;
            html += `<div class="status-item"><div class="label">Relations</div><div class="value">${stats.total_relations}</div></div>`;
            html += `<div class="status-item"><div class="label">Conversations</div><div class="value">${stats.conversations}</div></div>`;

            if (stats.by_source_type) {
                for (const [source, count] of Object.entries(stats.by_source_type)) {
                    html += `<div class="status-item"><div class="label">${source}</div><div class="value">${count}</div></div>`;
                }
            }

            html += '</div>';
            details.innerHTML = html;
        }
    } catch (err) {
        // Silently fail — daemon might be offline
    }
}

// ─── Utilities ───

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text || '';
    return div.innerHTML;
}
