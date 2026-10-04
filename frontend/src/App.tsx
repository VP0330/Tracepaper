import { useEffect, useState } from 'react';

type Engagement = { name: string; status: string; controls: string[] };
type Evidence = { doc_id: string; page: number; bbox: number[]; text: string; score: number; extraction_method: string };

type TraceStep = { step: string; status: string };

export function App() {
  const [engagement, setEngagement] = useState<Engagement | null>(null);
  const [query, setQuery] = useState('invoice approved');
  const [results, setResults] = useState<Evidence[]>([]);
  const [selected, setSelected] = useState<Evidence | null>(null);
  const [loading, setLoading] = useState(false);
  const [reviewStatus, setReviewStatus] = useState('pending');
  const [trace, setTrace] = useState<TraceStep[]>([]);
  const [agentResult, setAgentResult] = useState<{ disposition: string; rationale: string } | null>(null);

  useEffect(() => { fetch('/api/v1/engagements').then((r) => r.json()).then((d) => setEngagement(d.engagements[0])); }, []);

  async function search() {
    setLoading(true);
    const response = await fetch(`/api/v1/evidence/search?q=${encodeURIComponent(query)}&limit=10`);
    const data = await response.json();
    setResults(data.results ?? []);
    setSelected(data.results?.[0] ?? null);
    setLoading(false);
  }

  async function review(action: 'accept' | 'reject' | 'rerun') {
    if (!selected) return;
    const validation = await fetch('/api/v1/findings/validate', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ control_id: 'p2p_001', population_item_id: selected.doc_id, disposition: 'pass', rationale: 'Reviewer-selected evidence', citations: [{ doc_id: selected.doc_id, page: selected.page, bbox: selected.bbox, quoted_span: selected.text }] }),
    });
    const finding = await validation.json();
    if (!validation.ok) return;
    const response = await fetch(`/api/v1/findings/${finding.finding_id}/${action}`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ reviewer: 'reviewer' }) });
    const result = await response.json();
    setReviewStatus(result.status);
    const traceResponse = await fetch(`/api/v1/findings/${finding.finding_id}/trace`);
    setTrace((await traceResponse.json()).trace);
  }

  async function askAgent() {
    if (!selected) return;
    const response = await fetch('/api/v1/agent/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        task: `Review evidence for ${selected.doc_id}, page ${selected.page}. Source text: ${selected.text}`,
      }),
    });
    const data = await response.json();
    if (response.ok) setAgentResult(data.finding);
  }

  return <main className="shell">
    <header className="topbar"><div className="brand"><span className="mark">T</span><div><strong>Tracepaper</strong><small>Evidence review workspace</small></div></div><span className="status"><i /> API connected</span></header>
    <section className="intro"><div><p className="eyebrow">ACTIVE ENGAGEMENT</p><h1>{engagement?.name ?? 'Loading engagement...'}</h1><p className="muted">Review searchable evidence with every conclusion tied to a source location.</p></div><div className="engagement-meta"><span>2026 SOX cycle</span><b>{engagement?.status ?? 'loading'}</b></div></section>
    <section className="workspace">
      <aside className="rail"><div className="rail-head"><span>Controls</span><span className="count">{engagement?.controls.length ?? 0}</span></div>{(engagement?.controls ?? []).map((control) => <button className="control" key={control}><span className="control-dot" />{control}<span>›</span></button>)}<div className="rail-note"><strong>Provenance gate</strong><p>Findings cannot leave the workspace until citations resolve against extracted source text.</p></div></aside>
      <section className="results"><div className="section-head"><div><p className="eyebrow">EVIDENCE SEARCH</p><h2>Find supporting evidence</h2></div><span className="result-count">{results.length} results</span></div><div className="search"><input value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && search()} /><button onClick={search}>{loading ? 'Searching...' : 'Search'}</button></div><div className="result-list">{results.map((result) => <button className={`result ${selected?.doc_id === result.doc_id ? 'selected' : ''}`} key={`${result.doc_id}-${result.page}`} onClick={() => setSelected(result)}><div className="result-top"><strong>{result.doc_id}</strong><span>p. {result.page}</span></div><p>{result.text}</p><small>RRF {result.score.toFixed(4)} · {result.extraction_method}</small></button>)}{!results.length && <div className="empty">Search the evidence index to begin.</div>}</div></section>
      <section className="viewer"><div className="section-head"><div><p className="eyebrow">SOURCE VIEW</p><h2>{selected?.doc_id ?? 'No source selected'}</h2></div>{selected && <span className="page-chip">PAGE {selected.page}</span>}</div>{selected ? <><div className="paper"><div className="paper-label">EXTRACTED SOURCE TEXT</div><p>{selected.text}</p><div className="highlight" style={{ left: `${selected.bbox[0] * 100}%`, top: `${selected.bbox[1] * 100}%`, width: `${(selected.bbox[2] - selected.bbox[0]) * 100}%`, height: `${Math.max((selected.bbox[3] - selected.bbox[1]) * 100, 14)}%` }} /></div><div className="citation"><span className="check">✓</span><div><strong>Citation resolves</strong><p>{selected.doc_id} · page {selected.page} · normalized bounding box</p></div></div><div className="review-actions"><span>Review: {reviewStatus}</span><button onClick={askAgent}>Ask Ollama</button><button onClick={() => review('accept')}>Accept</button><button onClick={() => review('reject')}>Reject</button><button onClick={() => review('rerun')}>Rerun</button></div>{agentResult && <div className="agent-result"><p className="eyebrow">OLLAMA FINDING</p><strong>{agentResult.disposition}</strong><p>{agentResult.rationale}</p></div>}{trace.length > 0 && <div className="trace"><p className="eyebrow">DECISION TRACE</p>{trace.map((item) => <small key={`${item.step}-${item.status}`}>{item.step}: {item.status}</small>)}</div>}</> : <div className="empty viewer-empty">Select a result to inspect its source.</div>}</section>
    </section>
  </main>;
}
