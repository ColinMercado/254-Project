/**
 * CSV Doctor — Frontend Application
 * Vanilla JS, no build step required.
 */

'use strict';

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const state = {
  sessionId: null,
  csvText: null,
  profile: null,
  chatHistory: [],
  activeTab: 'upload',
};

// ---------------------------------------------------------------------------
// DOM references
// ---------------------------------------------------------------------------
const $ = (id) => document.getElementById(id);

const dom = {
  // Alert
  alertBanner: $('alert-banner'),
  alertMessage: $('alert-message'),
  alertDismiss: $('alert-dismiss-btn'),

  // Input
  tabUpload: $('tab-upload'),
  tabPaste: $('tab-paste'),
  panelUpload: $('panel-upload'),
  panelPaste: $('panel-paste'),
  dropZone: $('drop-zone'),
  fileInput: $('file-input'),
  fileNameDisplay: $('file-name-display'),
  csvPasteArea: $('csv-paste-area'),
  analyzeBtn: $('analyze-btn'),

  // Results
  resultsSection: $('results-section'),
  summaryBanner: $('summary-banner'),
  statRowsVal: $('stat-rows-val'),
  statColsVal: $('stat-cols-val'),
  statDupesVal: $('stat-dupes-val'),
  statIssuesVal: $('stat-issues-val'),
  profileTableBody: $('profile-table-body'),
  issuesList: $('issues-list'),

  // Code
  codeSection: $('code-section'),
  codeBlock: $('code-block'),
  copyCodeBtn: $('copy-code-btn'),
  runCodeBtn: $('run-code-btn'),
  downloadBtn: $('download-btn'),
  runResult: $('run-result'),
  runResultIcon: $('run-result-icon'),
  runResultMessage: $('run-result-message'),
  runResultStdout: $('run-result-stdout'),

  // Chat
  chatSection: $('chat-section'),
  chatThread: $('chat-thread'),
  chatInput: $('chat-input'),
  chatSendBtn: $('chat-send-btn'),
};

// ---------------------------------------------------------------------------
// Utility helpers
// ---------------------------------------------------------------------------

function showAlert(message) {
  dom.alertMessage.textContent = message;
  dom.alertBanner.classList.remove('hidden');
  dom.alertBanner.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function hideAlert() {
  dom.alertBanner.classList.add('hidden');
}

function setLoading(btn, loading) {
  const text = btn.querySelector('.btn-text');
  const spinner = btn.querySelector('.spinner');
  btn.disabled = loading;
  if (text) text.style.opacity = loading ? '0.6' : '1';
  if (spinner) spinner.classList.toggle('hidden', !loading);
}

function escapeHtml(str) {
  if (str === null || str === undefined) return '<em class="null-val">null</em>';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function formatSampleValues(values) {
  if (!values || values.length === 0) return '—';
  return values
    .map((v) => `<code>${escapeHtml(v)}</code>`)
    .join(', ');
}

// ---------------------------------------------------------------------------
// Tab switching
// ---------------------------------------------------------------------------

function switchTab(tab) {
  state.activeTab = tab;
  dom.tabUpload.classList.toggle('active', tab === 'upload');
  dom.tabPaste.classList.toggle('active', tab === 'paste');
  dom.tabUpload.setAttribute('aria-selected', tab === 'upload');
  dom.tabPaste.setAttribute('aria-selected', tab === 'paste');
  dom.panelUpload.classList.toggle('hidden', tab !== 'upload');
  dom.panelPaste.classList.toggle('hidden', tab !== 'paste');
}

dom.tabUpload.addEventListener('click', () => switchTab('upload'));
dom.tabPaste.addEventListener('click', () => switchTab('paste'));

// ---------------------------------------------------------------------------
// File upload — drag & drop + click
// ---------------------------------------------------------------------------

dom.dropZone.addEventListener('click', () => dom.fileInput.click());

dom.dropZone.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault();
    dom.fileInput.click();
  }
});

dom.dropZone.addEventListener('dragover', (e) => {
  e.preventDefault();
  dom.dropZone.classList.add('drag-over');
});

dom.dropZone.addEventListener('dragleave', () => {
  dom.dropZone.classList.remove('drag-over');
});

dom.dropZone.addEventListener('drop', (e) => {
  e.preventDefault();
  dom.dropZone.classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (file) handleFileSelected(file);
});

dom.fileInput.addEventListener('change', () => {
  if (dom.fileInput.files[0]) handleFileSelected(dom.fileInput.files[0]);
});

function handleFileSelected(file) {
  if (!file.name.endsWith('.csv') && file.type !== 'text/csv') {
    showAlert('Please select a CSV file (.csv).');
    return;
  }
  if (file.size > 5 * 1024 * 1024) {
    showAlert('File is too large. Maximum size is 5 MB.');
    return;
  }
  const reader = new FileReader();
  reader.onload = (e) => {
    state.csvText = e.target.result;
    dom.fileNameDisplay.textContent = `✓ ${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
    hideAlert();
  };
  reader.onerror = () => showAlert('Could not read the file. Please try again.');
  reader.readAsText(file);
}

// ---------------------------------------------------------------------------
// Analyze button
// ---------------------------------------------------------------------------

dom.analyzeBtn.addEventListener('click', handleAnalyze);

async function handleAnalyze() {
  hideAlert();

  let csvText = null;
  let requestBody = null;
  let fetchOptions = {};

  if (state.activeTab === 'upload') {
    if (!state.csvText) {
      showAlert('Please select a CSV file first.');
      return;
    }
    // Send as JSON (simpler than multipart for text we already have)
    csvText = state.csvText;
    requestBody = JSON.stringify({ csv_text: csvText });
    fetchOptions = {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: requestBody,
    };
  } else {
    csvText = dom.csvPasteArea.value.trim();
    if (!csvText) {
      showAlert('Please paste some CSV data first.');
      return;
    }
    requestBody = JSON.stringify({ csv_text: csvText });
    fetchOptions = {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: requestBody,
    };
  }

  setLoading(dom.analyzeBtn, true);

  try {
    const res = await fetch('/api/analyze', fetchOptions);
    const data = await res.json();

    if (!res.ok) {
      showAlert(data.error || 'Analysis failed. Please try again.');
      return;
    }

    // Store state
    state.sessionId = data.session_id;
    state.profile = data.profile;
    state.csvText = csvText;
    state.chatHistory = [];

    // Render results
    renderResults(data);

  } catch (err) {
    showAlert('Network error. Is the server running?');
    console.error(err);
  } finally {
    setLoading(dom.analyzeBtn, false);
  }
}

// ---------------------------------------------------------------------------
// Render results
// ---------------------------------------------------------------------------

function renderResults(data) {
  const { profile, issues, cleaning_code, summary } = data;

  // Summary banner
  dom.summaryBanner.textContent = summary || 'Analysis complete.';

  // Stats
  dom.statRowsVal.textContent = profile.shape?.rows ?? '—';
  dom.statColsVal.textContent = profile.shape?.cols ?? '—';
  dom.statDupesVal.textContent = profile.duplicate_rows ?? '—';
  dom.statIssuesVal.textContent = issues?.length ?? '—';

  // Color-code duplicate stat
  const dupVal = profile.duplicate_rows ?? 0;
  $('stat-dupes').style.borderTop = dupVal > 0 ? '3px solid var(--color-error)' : '3px solid var(--color-success)';

  // Profile table
  renderProfileTable(profile.columns || []);

  // Issues
  renderIssues(issues || []);

  // Code
  dom.codeBlock.textContent = cleaning_code || '# No cleaning code generated';

  // Show sections
  dom.resultsSection.classList.remove('hidden');
  dom.codeSection.classList.remove('hidden');
  dom.chatSection.classList.remove('hidden');

  // Reset run result
  dom.runResult.classList.add('hidden');
  dom.downloadBtn.classList.add('hidden');

  // Scroll to results
  dom.resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function renderProfileTable(columns) {
  dom.profileTableBody.innerHTML = '';
  columns.forEach((col) => {
    const nullClass = col.null_pct > 20 ? 'null-high' : col.null_pct > 5 ? 'null-medium' : '';
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><strong>${escapeHtml(col.name)}</strong></td>
      <td><code>${escapeHtml(col.dtype)}</code></td>
      <td class="${nullClass}">${col.null_count}</td>
      <td class="${nullClass}">${col.null_pct}%</td>
      <td>${col.unique_count}</td>
      <td>${formatSampleValues(col.sample_values)}</td>
    `;
    dom.profileTableBody.appendChild(tr);
  });
}

function renderIssues(issues) {
  dom.issuesList.innerHTML = '';

  if (issues.length === 0) {
    dom.issuesList.innerHTML = '<p style="color:var(--color-text-muted);font-size:0.9rem;">No significant data quality issues detected. Your dataset looks clean!</p>';
    return;
  }

  // Sort: high → medium → low
  const order = { high: 0, medium: 1, low: 2 };
  const sorted = [...issues].sort((a, b) => (order[a.severity] ?? 3) - (order[b.severity] ?? 3));

  sorted.forEach((issue) => {
    const card = document.createElement('div');
    card.className = `issue-card severity-${issue.severity || 'low'}`;
    card.innerHTML = `
      <div class="issue-header">
        <span class="issue-column">${escapeHtml(issue.column || 'Dataset')}</span>
        <span class="severity-badge ${issue.severity || 'low'}">${issue.severity || 'low'}</span>
        <span class="issue-type-badge">${escapeHtml(issue.issue_type || 'other')}</span>
      </div>
      <p class="issue-description">${escapeHtml(issue.description || '')}</p>
      ${issue.suggested_fix ? `<p class="issue-fix"><strong>Fix:</strong> ${escapeHtml(issue.suggested_fix)}</p>` : ''}
    `;
    dom.issuesList.appendChild(card);
  });
}

// ---------------------------------------------------------------------------
// Copy code
// ---------------------------------------------------------------------------

dom.copyCodeBtn.addEventListener('click', async () => {
  const code = dom.codeBlock.textContent;
  try {
    await navigator.clipboard.writeText(code);
    dom.copyCodeBtn.textContent = '✓ Copied!';
    setTimeout(() => { dom.copyCodeBtn.innerHTML = '📋 Copy'; }, 2000);
  } catch {
    showAlert('Could not copy to clipboard. Please select and copy manually.');
  }
});

// ---------------------------------------------------------------------------
// Run code
// ---------------------------------------------------------------------------

dom.runCodeBtn.addEventListener('click', handleRunCode);

async function handleRunCode() {
  if (!state.sessionId) {
    showAlert('Please analyze a dataset first.');
    return;
  }

  const code = dom.codeBlock.textContent;
  if (!code.trim()) {
    showAlert('No code to run.');
    return;
  }

  setLoading(dom.runCodeBtn, true);
  dom.runResult.classList.add('hidden');

  try {
    const res = await fetch('/api/run-code', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: state.sessionId, code }),
    });
    const data = await res.json();

    if (!res.ok) {
      showRunResult(false, data.error || 'Code execution failed.', '');
      return;
    }

    showRunResult(data.success, data.error, data.stdout);

    if (data.success && data.has_cleaned_csv) {
      dom.downloadBtn.href = `/api/download/${state.sessionId}`;
      dom.downloadBtn.classList.remove('hidden');
    }

  } catch (err) {
    showRunResult(false, 'Network error. Is the server running?', '');
    console.error(err);
  } finally {
    setLoading(dom.runCodeBtn, false);
  }
}

function showRunResult(success, errorMsg, stdout) {
  dom.runResult.classList.remove('hidden', 'success', 'error');
  dom.runResult.classList.add(success ? 'success' : 'error');
  dom.runResultIcon.textContent = success ? '✅' : '❌';
  dom.runResultMessage.textContent = success
    ? 'Code ran successfully! Your cleaned CSV is ready to download.'
    : `Error: ${errorMsg || 'Unknown error'}`;

  if (stdout && stdout.trim()) {
    dom.runResultStdout.textContent = stdout;
    dom.runResultStdout.classList.remove('hidden');
  } else if (!success && errorMsg) {
    dom.runResultStdout.textContent = errorMsg;
    dom.runResultStdout.classList.remove('hidden');
  } else {
    dom.runResultStdout.classList.add('hidden');
  }

  dom.runResult.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------

dom.chatSendBtn.addEventListener('click', handleChatSend);

dom.chatInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    handleChatSend();
  }
});

async function handleChatSend() {
  const message = dom.chatInput.value.trim();
  if (!message) return;

  dom.chatInput.value = '';
  appendChatMessage('user', message);

  // Add typing indicator
  const typingEl = appendTypingIndicator();

  setLoading(dom.chatSendBtn, true);

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: state.sessionId || '',
        history: state.chatHistory,
        message,
      }),
    });
    const data = await res.json();

    typingEl.remove();

    if (!res.ok) {
      appendChatMessage('assistant', `Error: ${data.error || 'Something went wrong.'}`);
      return;
    }

    const reply = data.reply || '';
    appendChatMessage('assistant', reply);

    // Update history
    state.chatHistory.push({ role: 'user', content: message });
    state.chatHistory.push({ role: 'assistant', content: reply });

    // Keep history bounded
    if (state.chatHistory.length > 20) {
      state.chatHistory = state.chatHistory.slice(-20);
    }

  } catch (err) {
    typingEl.remove();
    appendChatMessage('assistant', 'Network error. Is the server running?');
    console.error(err);
  } finally {
    setLoading(dom.chatSendBtn, false);
  }
}

function appendChatMessage(role, content) {
  const wrapper = document.createElement('div');
  wrapper.className = `chat-message ${role}`;

  const label = document.createElement('div');
  label.className = 'chat-label';
  label.textContent = role === 'user' ? 'You' : 'CSV Doctor';

  const bubble = document.createElement('div');
  bubble.className = 'chat-bubble';
  bubble.textContent = content;

  wrapper.appendChild(label);
  wrapper.appendChild(bubble);
  dom.chatThread.appendChild(wrapper);
  dom.chatThread.scrollTop = dom.chatThread.scrollHeight;
  return wrapper;
}

function appendTypingIndicator() {
  const wrapper = document.createElement('div');
  wrapper.className = 'chat-message assistant';

  const label = document.createElement('div');
  label.className = 'chat-label';
  label.textContent = 'CSV Doctor';

  const typing = document.createElement('div');
  typing.className = 'chat-typing';
  typing.setAttribute('aria-label', 'CSV Doctor is typing');
  typing.innerHTML = '<span></span><span></span><span></span>';

  wrapper.appendChild(label);
  wrapper.appendChild(typing);
  dom.chatThread.appendChild(wrapper);
  dom.chatThread.scrollTop = dom.chatThread.scrollHeight;
  return wrapper;
}

// ---------------------------------------------------------------------------
// Alert dismiss
// ---------------------------------------------------------------------------

dom.alertDismiss.addEventListener('click', hideAlert);

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

// Ensure upload tab is active on load
switchTab('upload');
