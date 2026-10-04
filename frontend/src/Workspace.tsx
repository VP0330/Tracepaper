import { FormEvent, useEffect, useState } from 'react';
import './Workspace.css';

type User = { user_id: string; email: string; display_name: string; role: string };
type PageChunk = { chunk_id: string; doc_id: string; page: number; bbox: number[]; text: string; extraction_method: string };
type DocumentItem = { document_id: string; original_name: string; status: string; document_type: string | null; control_type: string | null; confidence: number | null; fields: Record<string, unknown>; summary: string; page_count: number };
type Rule = { rule_id: string; name: string; description: string; control_type: string; document_type: string; field_name: string; operator: string; expected_value: unknown; severity: string; enabled: boolean };
type Flag = { finding_id: string; document_id: string; rule_id: string; status: string; severity: string; message: string; observed_value: unknown; expected_value: unknown };
type View = 'documents' | 'rules' | 'flags' | 'team';

const controlOptions = [
  ['purchase_to_pay', 'Purchase to pay'],
  ['user_access_review', 'User access review'],
  ['journal_entry_review', 'Journal entry review'],
];
const documentOptions = ['invoice', 'purchase_order', 'approval_email', 'access_export', 'access_review_memo', 'journal_entry', 'journal_entry_explanation', 'other', '*'];
const operatorOptions = ['eq', 'neq', 'gt', 'gte', 'lt', 'lte', 'contains', 'missing', 'not_missing'];

async function request<T>(path: string, token?: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  const response = await fetch(path, { ...init, headers });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail ?? `Request failed (${response.status})`);
  return body as T;
}

function parseRuleValue(value: string): unknown {
  if (value === '') return null;
  try { return JSON.parse(value); } catch { return value; }
}

function formatFieldValue(value: unknown): string {
  if (value == null || value === '') return 'Not found';
  if (typeof value === 'object') return JSON.stringify(value, null, 1).replace(/[{}"\[\]]/g, '').replace(/,\n/g, '\n').trim();
  return String(value);
}

export function Workspace() {
  const inviteFromUrl = new URLSearchParams(window.location.search).get('invite') ?? '';
  const [token, setToken] = useState(localStorage.getItem('tracepaper_session'));
  const [user, setUser] = useState<User | null>(null);
  const [inviteToken, setInviteToken] = useState(inviteFromUrl);
  const [authMode, setAuthMode] = useState<'login' | 'accept'>('login');
  const [view, setView] = useState<View>('documents');
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [rules, setRules] = useState<Rule[]>([]);
  const [flags, setFlags] = useState<Flag[]>([]);
  const [selected, setSelected] = useState<DocumentItem | null>(null);
  const [pageChunks, setPageChunks] = useState<PageChunk[]>([]);
  const [query, setQuery] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (inviteFromUrl) setAuthMode('accept');
  }, [inviteFromUrl]);

  useEffect(() => {
    if (!token) return;
    request<{ user: User }>('/api/v1/auth/me', token)
      .then((data) => setUser(data.user))
      .catch(() => { localStorage.removeItem('tracepaper_session'); setToken(null); setUser(null); });
  }, [token]);

  async function refreshWorkspace(session = token) {
    if (!session) return;
    const [docData, ruleData, flagData] = await Promise.all([
      request<{ documents: DocumentItem[] }>('/api/v1/documents', session),
      request<{ rules: Rule[] }>('/api/v1/audit-rules', session),
      request<{ findings: Flag[] }>('/api/v1/audit-findings', session),
    ]);
    setDocuments(docData.documents);
    setRules(ruleData.rules);
    setFlags(flagData.findings);
    if (selected) {
      const updated = docData.documents.find((document) => document.document_id === selected.document_id);
      if (updated) setSelected(updated);
    }
  }

  useEffect(() => {
    if (user && token) refreshWorkspace().catch((reason: Error) => setError(reason.message));
  }, [user, token]);

  async function submitLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(''); setBusy(true);
    const form = new FormData(event.currentTarget);
    try {
      if (authMode === 'accept') {
        await request('/api/v1/auth/accept-invite', undefined, { method: 'POST', body: JSON.stringify({ token: inviteToken, password: form.get('password') }) });
        setMessage('Invitation accepted. Sign in with your new password.');
        setAuthMode('login');
        window.history.replaceState({}, '', window.location.pathname);
      } else {
        const result = await request<{ access_token: string; user: User }>('/api/v1/auth/login', undefined, { method: 'POST', body: JSON.stringify({ email: form.get('email'), password: form.get('password') }) });
        localStorage.setItem('tracepaper_session', result.access_token);
        setToken(result.access_token); setUser(result.user); setMessage('');
      }
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy(false); }
  }

  async function signOut() {
    try { await request('/api/v1/auth/logout', token ?? undefined, { method: 'POST' }); } catch { /* Local session is removed regardless. */ }
    localStorage.removeItem('tracepaper_session'); setToken(null); setUser(null); setDocuments([]); setRules([]); setFlags([]);
  }

  async function uploadFile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(''); setMessage(''); setBusy(true);
    const form = new FormData(event.currentTarget);
    try {
      const result = await request<{ document: DocumentItem; flags: unknown[] }>('/api/v1/documents/upload', token ?? undefined, { method: 'POST', body: form });
      setSelected(result.document); setMessage(`Classified as ${result.document.document_type} for ${result.document.control_type}. ${result.flags.length} discrepancy flags created.`);
      await refreshWorkspace();
      event.currentTarget.reset();
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy(false); }
  }

  async function openDocument(document: DocumentItem) {
    setSelected(document); setError('');
    try {
      const result = await request<{ chunks: PageChunk[] }>(`/api/v1/documents/${document.document_id}/pages/1`, token ?? undefined);
      setPageChunks(result.chunks);
    } catch (reason) { setPageChunks([]); setError((reason as Error).message); }
  }

  async function createRule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(''); setMessage(''); setBusy(true);
    const form = new FormData(event.currentTarget);
    try {
      const result = await request<{ flags_created: number }>('/api/v1/audit-rules', token ?? undefined, {
        method: 'POST', body: JSON.stringify({
          name: form.get('name'), description: form.get('description'), control_type: form.get('control_type'),
          document_type: form.get('document_type'), field_name: form.get('field_name'), operator: form.get('operator'),
          expected_value: parseRuleValue(String(form.get('expected_value') ?? '')),
          severity: form.get('severity'), enabled: true,
        }),
      });
      setMessage(`Rule saved; ${result.flags_created} discrepancy flags found in existing uploads.`);
      event.currentTarget.reset(); await refreshWorkspace();
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy(false); }
  }

  async function toggleRule(rule: Rule) {
    try {
      await request(`/api/v1/audit-rules/${rule.rule_id}?enabled=${!rule.enabled}`, token ?? undefined, { method: 'PATCH' });
      await refreshWorkspace();
    } catch (reason) { setError((reason as Error).message); }
  }

  async function updateFlag(flag: Flag, status: 'accepted' | 'dismissed') {
    try {
      await request(`/api/v1/audit-findings/${flag.finding_id}`, token ?? undefined, { method: 'PATCH', body: JSON.stringify({ status }) });
      await refreshWorkspace();
    } catch (reason) { setError((reason as Error).message); }
  }

  async function sendInvite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(''); setMessage('');
    const form = new FormData(event.currentTarget);
    try {
      const data = await request<{ invite: { accept_url: string; email: string } }>('/api/v1/admin/invites', token ?? undefined, {
        method: 'POST', body: JSON.stringify({ email: form.get('email'), display_name: form.get('display_name'), role: form.get('role') }),
      });
      setMessage(`Invite for ${data.invite.email}: ${window.location.origin}${data.invite.accept_url}`);
    } catch (reason) { setError((reason as Error).message); }
  }

  if (!token || !user) {
    return <main className="auth-shell">
      <div className="auth-brand"><span className="brand-mark">T</span><span>TRACEPAPER <i>CONTROL ASSURANCE</i></span></div>
      <section className="auth-panel"><p className="eyebrow">SECURE REVIEW WORKSPACE</p><h1>{authMode === 'accept' ? 'Accept your invitation' : 'Sign in to Tracepaper'}</h1><p className="muted">Evidence review with source-linked audit findings.</p>
        {message && <div className="notice success">{message}</div>}{error && <div className="notice error">{error}</div>}
        <form onSubmit={submitLogin} className="form-stack">
          {authMode === 'accept' ? <><label>Invitation token<input value={inviteToken} onChange={(event) => setInviteToken(event.target.value)} required /></label><label>Create password<input type="password" name="password" minLength={12} required autoComplete="new-password" /></label></> : <><label>Work email<input name="email" type="email" required autoComplete="username" placeholder="you@company.com" /></label><label>Password<input name="password" type="password" required autoComplete="current-password" /></label></>}
          <button className="primary-button" disabled={busy}>{busy ? 'Working...' : authMode === 'accept' ? 'Create account' : 'Sign in'}</button>
        </form>
        <button className="text-button" onClick={() => { setAuthMode(authMode === 'login' ? 'accept' : 'login'); setError(''); }}> {authMode === 'login' ? 'Have an invitation? Accept it' : 'Back to sign in'}</button>
      </section><footer className="auth-foot">POSTGRESQL · OLLAMA DOCUMENT UNDERSTANDING · PROVENANCE REQUIRED</footer>
    </main>;
  }

  return <main className="app-shell">
    <header className="app-header"><div className="app-brand"><span className="brand-mark">T</span><div><strong>Tracepaper</strong><small>Audit evidence workspace</small></div></div><div className="header-right"><span className="db-status"><i /> PostgreSQL connected</span><div className="user-pill"><span className="avatar">{user.display_name.slice(0, 1).toUpperCase()}</span><span>{user.display_name}<small>{user.role}</small></span></div><button className="quiet-button" onClick={signOut}>Sign out</button></div></header>
    <section className="page-intro"><div><p className="eyebrow">AUDIT WORKSPACE / 2026 CYCLE</p><h1>Evidence, rules, and exceptions.</h1><p className="muted">Classify uploaded support with Ollama. Apply your control rules. Review only the exceptions.</p></div><div className="intro-stats"><span><b>{documents.length}</b> documents</span><span><b>{flags.filter((flag) => flag.status === 'needs_review').length}</b> open flags</span></div></section>
    <nav className="workspace-nav">{([['documents', 'Documents'], ['rules', 'Audit rules'], ['flags', 'Discrepancies'], ...(user.role === 'admin' ? [['team', 'Team'] as [View, string]] : [])] as [View, string][]).map(([key, label]) => <button key={key} className={view === key ? 'active' : ''} onClick={() => { setView(key); setError(''); }}>{label}{key === 'flags' && flags.some((flag) => flag.status === 'needs_review') && <b className="nav-badge">{flags.filter((flag) => flag.status === 'needs_review').length}</b>}</button>)}</nav>
    {message && <div className="notice success workspace-notice">{message}</div>}{error && <div className="notice error workspace-notice">{error}</div>}

    {view === 'documents' && <section className="content-grid">
      <div className="main-column"><div className="section-title"><div><p className="eyebrow">SOURCE INTAKE</p><h2>Upload evidence</h2></div><span className="model-tag">OLLAMA · {import.meta.env.VITE_OLLAMA_MODEL ?? 'configured model'}</span></div>
        <form className="upload-zone" onSubmit={uploadFile}><label className="file-pick"><span className="upload-glyph">↑</span><span><b>Choose evidence file</b><small>PDF, CSV, or EML · up to 25 MB</small></span><input type="file" name="upload" accept=".pdf,.csv,.eml" required /></label><button className="primary-button" disabled={busy}>{busy ? 'Classifying and extracting...' : 'Upload and classify'}</button><p className="upload-note">Ollama assigns document/control types and extracts only values present in the source.</p></form>
        <div className="section-title list-title"><div><p className="eyebrow">POSTGRESQL RECORDS</p><h2>Uploaded documents</h2></div><span className="subtle-count">{documents.length} total</span></div>
        {documents.length ? <div className="document-table"><div className="table-head"><span>Document</span><span>Classification</span><span>Confidence</span><span>Status</span></div>{documents.map((document) => <button key={document.document_id} className={`document-row ${selected?.document_id === document.document_id ? 'selected' : ''}`} onClick={() => openDocument(document)}><span><b>{document.original_name}</b><small>{document.page_count} page{document.page_count === 1 ? '' : 's'}</small></span><span>{document.document_type ?? 'Unclassified'}<small>{document.control_type ?? 'Control unknown'}</small></span><span>{document.confidence == null ? 'n/a' : `${Math.round(document.confidence * 100)}%`}</span><span className={`status-label ${document.status}`}>{document.status}</span></button>)}</div> : <div className="empty-state">No uploaded evidence yet. Add a PDF, CSV, or EML to begin.</div>}
      </div>
      <aside className="detail-column"><div className="section-title"><div><p className="eyebrow">CLASSIFICATION & SOURCE</p><h2>{selected?.original_name ?? 'Select a document'}</h2></div></div>{selected ? <><div className="classify-block"><span className="eyebrow">OLLAMA CLASSIFICATION</span><strong>{selected.document_type}</strong><small>{selected.control_type} · confidence {Math.round((selected.confidence ?? 0) * 100)}%</small><p>{selected.summary}</p></div><div className="field-list"><span className="eyebrow">EXTRACTED FIELDS</span>{Object.entries(selected.fields ?? {}).map(([key, value]) => <div className="field-row" key={key}><span>{key.replace(/_/g, ' ')}</span><b style={{ whiteSpace: 'pre-wrap' }}>{formatFieldValue(value)}</b></div>)}</div><div className="source-snippets"><span className="eyebrow">EXTRACTED SOURCE · PAGE 1</span>{pageChunks.map((chunk) => <p key={chunk.chunk_id}>{chunk.text}</p>)}</div></> : <div className="empty-state">Choose an upload to review its model classification, fields, and source text.</div>}</aside>
    </section>}

    {view === 'rules' && <section className="rules-layout"><div className="main-column"><div className="section-title"><div><p className="eyebrow">DETERMINISTIC EVALUATION</p><h2>Set audit rules</h2></div></div><p className="section-copy">Rules run against Ollama-extracted fields. A failed condition creates a discrepancy for human review.</p><form className="rule-form" onSubmit={createRule}><label>Rule name<input name="name" placeholder="Invoice needs approval over threshold" required /></label><label>Description<input name="description" placeholder="Optional reviewer context" /></label><div className="form-grid"><label>Control<select name="control_type">{controlOptions.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>Document type<select name="document_type">{documentOptions.map((value) => <option key={value} value={value}>{value === '*' ? 'Any document' : value.replace(/_/g, ' ')}</option>)}</select></label></div><div className="form-grid"><label>Extracted field<input name="field_name" placeholder="amount" required /></label><label>Condition<select name="operator">{operatorOptions.map((operator) => <option key={operator} value={operator}>{operator}</option>)}</select></label></div><div className="form-grid"><label>Expected value<input name="expected_value" placeholder="10000 or ISO date" /></label><label>Severity<select name="severity"><option>high</option><option>critical</option><option>medium</option><option>low</option></select></label></div><button className="primary-button" disabled={busy}>{busy ? 'Evaluating...' : 'Save rule and evaluate uploads'}</button></form></div><aside className="detail-column"><div className="section-title"><div><p className="eyebrow">YOUR RULES</p><h2>{rules.length} configured</h2></div></div>{rules.length ? rules.map((rule) => <article className="rule-card" key={rule.rule_id}><div className="rule-card-head"><strong>{rule.name}</strong><button className={`toggle ${rule.enabled ? 'on' : ''}`} aria-label="Toggle rule" onClick={() => toggleRule(rule)}>{rule.enabled ? 'On' : 'Off'}</button></div><p>{rule.description || `${rule.field_name} ${rule.operator} ${String(rule.expected_value ?? '')}`}</p><small>{rule.control_type.replace(/_/g, ' ')} · {rule.document_type}</small></article>) : <div className="empty-state">No rules yet. Create the first one to evaluate uploaded evidence.</div>}</aside></section>}

    {view === 'flags' && <section className="flag-view"><div className="section-title"><div><p className="eyebrow">HUMAN REVIEW QUEUE</p><h2>Discrepancies</h2></div><span className="subtle-count">{flags.length} total</span></div>{flags.length ? <div className="flag-list">{flags.map((flag) => <article className="flag-row" key={flag.finding_id}><span className={`severity-dot ${flag.severity}`} /><div className="flag-body"><div className="flag-heading"><b>{flag.message}</b><span className={`status-label ${flag.status}`}>{flag.status.replace(/_/g, ' ')}</span></div><p>Observed: <b>{String(flag.observed_value ?? 'missing')}</b> · Expected: <b>{String(flag.expected_value ?? 'not specified')}</b></p><small>Document {documents.find((document) => document.document_id === flag.document_id)?.original_name ?? flag.document_id}</small></div><div className="flag-actions"><button onClick={() => { const document = documents.find((item) => item.document_id === flag.document_id); if (document) { setView('documents'); void openDocument(document); } }}>Inspect</button>{flag.status === 'needs_review' && <><button onClick={() => updateFlag(flag, 'accepted')}>Accept</button><button onClick={() => updateFlag(flag, 'dismissed')}>Dismiss</button></>}</div></article>)}</div> : <div className="empty-state">No discrepancies to review. Add a rule or upload another document.</div>}</section>}

    {view === 'team' && user.role === 'admin' && <section className="team-view"><div className="section-title"><div><p className="eyebrow">INVITE ONLY</p><h2>Invite a teammate</h2></div></div><form className="rule-form team-form" onSubmit={sendInvite}><label>Work email<input name="email" type="email" required placeholder="reviewer@company.com" /></label><label>Display name<input name="display_name" required placeholder="Morgan Lee" /></label><label>Role<select name="role"><option value="reviewer">Reviewer</option><option value="admin">Administrator</option></select></label><button className="primary-button">Create expiring invitation</button></form><p className="upload-note">Invitations expire after {72} hours and can only be used once.</p></section>}
  </main>;
}
