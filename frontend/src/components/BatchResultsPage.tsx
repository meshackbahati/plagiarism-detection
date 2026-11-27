import { useState, useEffect, useCallback, type CSSProperties } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { apiRequest } from '../utils/api';

type BatchStatus = 'queued' | 'processing' | 'completed' | 'completed_with_errors' | 'failed';
type DocStatus = 'queued' | 'processing' | 'completed' | 'failed';

interface ChunkMatch {
    source_chunk: string;
    target_chunk: string;
    score: number;
    type: 'exact' | 'semantic';
}

interface PlagiarismResult {
    document_id: string;
    similar_document: string;
    similarity: number;
    lexical_similarity: number | null;
    semantic_similarity: number | null;
    cross_batch: boolean;
    matches: ChunkMatch[];
}

interface AIAnalysis {
    score: number | null;
    is_ai: boolean;
    confidence: number | null;
    provider: string | null;
    label: string | null;
}

interface DocumentResult {
    document_id: string;
    filename: string;
    status: DocStatus;
    error: string | null;
    word_count: number | null;
    ai_analysis: AIAnalysis | null;
    plagiarism_analysis: PlagiarismResult[];
}

interface BatchInfo {
    id: string;
    status: BatchStatus;
    analysis_type: string;
    total_docs: number;
    processed_docs: number;
    created_at: string | null;
}

interface BatchResultsResponse {
    status: string;
    batch: BatchInfo;
    data: DocumentResult[];
}

const POLL_MS = 3000;

const STATUS_LABELS: Record<string, string> = {
    queued: 'Queued',
    processing: 'Processing',
    completed: 'Completed',
    completed_with_errors: 'Completed with errors',
    failed: 'Failed',
};

const STATUS_COLORS: Record<string, string> = {
    queued: 'var(--text-secondary)',
    processing: 'var(--primary)',
    completed: 'var(--success)',
    completed_with_errors: 'var(--warning)',
    failed: 'var(--error)',
};

const isActive = (status: string | undefined) => status === 'queued' || status === 'processing';
const pct = (value: number) => `${(value * 100).toFixed(1)}%`;
const similarityColor = (value: number) =>
    value >= 0.5 ? 'var(--error)' : value >= 0.2 ? 'var(--warning)' : 'var(--text-secondary)';
const errorMessage = (e: unknown) => (e instanceof Error ? e.message : 'Something went wrong');

const StatusBadge = ({ status }: { status: string }) => {
    const color = STATUS_COLORS[status] || 'var(--text-secondary)';
    return (
        <span style={{
            display: 'inline-block',
            padding: '4px 10px',
            borderRadius: '9999px',
            fontSize: '12px',
            fontWeight: 600,
            color,
            border: `1px solid ${color}`,
            whiteSpace: 'nowrap',
        }}>
            {STATUS_LABELS[status] || status}
        </span>
    );
};

const sectionLabel: CSSProperties = {
    fontSize: '12px',
    fontWeight: 600,
    color: 'var(--text-secondary)',
    textTransform: 'uppercase',
    letterSpacing: '0.08em',
    marginBottom: '8px',
};

const PlagiarismRow = ({ item }: { item: PlagiarismResult }) => {
    const [open, setOpen] = useState(false);
    const hasMatches = item.matches.length > 0;

    return (
        <li style={{ background: 'rgba(255,255,255,0.03)', borderRadius: '12px', padding: '14px 16px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
                <span style={{ fontWeight: 600, wordBreak: 'break-word' }}>{item.similar_document}</span>
                {item.cross_batch && (
                    <span style={{ fontSize: '11px', padding: '2px 8px', borderRadius: '9999px', border: '1px solid var(--glass-border)', color: 'var(--text-secondary)' }}>
                        cross-batch
                    </span>
                )}
                <span style={{ marginLeft: 'auto', fontWeight: 700, color: similarityColor(item.similarity) }}>
                    {pct(item.similarity)}
                </span>
            </div>

            {(item.lexical_similarity !== null || item.semantic_similarity !== null) && (
                <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '6px' }}>
                    {item.lexical_similarity !== null && <>Word-for-word {pct(item.lexical_similarity)}</>}
                    {item.lexical_similarity !== null && item.semantic_similarity !== null && ' · '}
                    {item.semantic_similarity !== null && <>Paraphrased {pct(item.semantic_similarity)}</>}
                </p>
            )}

            {hasMatches && (
                <button
                    type="button"
                    onClick={() => setOpen(!open)}
                    aria-expanded={open}
                    style={{ marginTop: '10px', background: 'none', border: 'none', padding: 0, color: 'var(--primary)', fontWeight: 600, fontSize: '13px', cursor: 'pointer' }}
                >
                    {open ? 'Hide' : 'Show'} matched passages ({item.matches.length})
                </button>
            )}

            {open && (
                <div style={{ marginTop: '12px', display: 'grid', gap: '10px' }}>
                    {item.matches.map((m, i) => (
                        <div key={i} style={{ background: 'rgba(0,0,0,0.2)', borderRadius: '10px', padding: '12px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '8px' }}>
                                <span>{m.type === 'exact' ? 'Word-for-word' : 'Paraphrase'} match</span>
                                <span style={{ fontWeight: 600, color: similarityColor(m.score) }}>{pct(m.score)}</span>
                            </div>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px', fontSize: '13px', lineHeight: 1.5 }}>
                                <div>
                                    <div style={{ ...sectionLabel, fontSize: '11px', marginBottom: '4px' }}>This document</div>
                                    <p style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{m.source_chunk}</p>
                                </div>
                                <div>
                                    <div style={{ ...sectionLabel, fontSize: '11px', marginBottom: '4px' }}>{item.similar_document}</div>
                                    <p style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', color: 'var(--text-secondary)' }}>{m.target_chunk}</p>
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </li>
    );
};

const DocumentCard = ({ doc, showAI, showPlagiarism }: { doc: DocumentResult; showAI: boolean; showPlagiarism: boolean }) => {
    const ai = doc.ai_analysis;
    const sorted = [...(doc.plagiarism_analysis || [])].sort((a, b) => b.similarity - a.similarity);
    const done = doc.status === 'completed';

    return (
        <li className="glass card-hover" style={{ padding: '24px', borderRadius: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px', marginBottom: '8px' }}>
                <h3 style={{ fontSize: '18px', fontWeight: 600, wordBreak: 'break-word' }}>{doc.filename}</h3>
                <StatusBadge status={doc.status} />
            </div>
            {doc.word_count !== null && (
                <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>{doc.word_count.toLocaleString()} words</p>
            )}
            {doc.status === 'failed' && doc.error && (
                <p style={{ color: 'var(--error)', fontSize: '14px', marginTop: '8px' }}>{doc.error}</p>
            )}

            {done && showAI && (
                <div style={{ marginTop: '20px' }}>
                    <div style={sectionLabel}>AI detection</div>
                    {ai && ai.score !== null ? (
                        <div style={{ display: 'flex', alignItems: 'baseline', gap: '12px', flexWrap: 'wrap' }}>
                            <span style={{ fontSize: '24px', fontWeight: 700, color: ai.is_ai ? 'var(--error)' : 'var(--success)' }}>
                                {pct(ai.score)}
                            </span>
                            <span>{ai.label || (ai.is_ai ? 'Likely AI-generated' : 'Likely human-written')}</span>
                            {ai.provider && (
                                <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>via {ai.provider}</span>
                            )}
                        </div>
                    ) : (
                        <p style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>No AI result available.</p>
                    )}
                </div>
            )}

            {done && showPlagiarism && (
                <div style={{ marginTop: '20px' }}>
                    <div style={sectionLabel}>Similar documents</div>
                    {sorted.length > 0 ? (
                        <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'grid', gap: '10px' }}>
                            {sorted.map((item, i) => (
                                <PlagiarismRow key={`${item.similar_document}-${i}`} item={item} />
                            ))}
                        </ul>
                    ) : (
                        <p style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>No similar documents found.</p>
                    )}
                </div>
            )}
        </li>
    );
};

const BatchResultsPage = () => {
    const { batchId } = useParams<{ batchId: string }>();
    const navigate = useNavigate();
    const [batch, setBatch] = useState<BatchInfo | null>(null);
    const [results, setResults] = useState<DocumentResult[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(true);
    const [exporting, setExporting] = useState<'pdf' | 'csv' | null>(null);
    const [actionError, setActionError] = useState<string | null>(null);
    const [confirmDelete, setConfirmDelete] = useState(false);
    const [deleting, setDeleting] = useState(false);

    const fetchResults = useCallback(async () => {
        if (!batchId) return;
        try {
            const res = await apiRequest<BatchResultsResponse>(`/api/v1/batches/${batchId}/results`);
            setBatch(res.batch);
            setResults(res.data || []);
            setError(null);
        } catch (e) {
            setError(errorMessage(e));
        } finally {
            setIsLoading(false);
        }
    }, [batchId]);

    useEffect(() => {
        setIsLoading(true);
        fetchResults();
    }, [fetchResults]);

    const active = isActive(batch?.status);
    useEffect(() => {
        if (!active) return;
        const timer = window.setInterval(fetchResults, POLL_MS);
        return () => window.clearInterval(timer);
    }, [active, fetchResults]);

    const handleExport = async (type: 'pdf' | 'csv') => {
        setExporting(type);
        setActionError(null);
        try {
            const response = await apiRequest<Response>(`/api/v1/batches/${batchId}/export/${type}`);
            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `report_${batchId}.${type}`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
        } catch (e) {
            setActionError(`Export failed: ${errorMessage(e)}`);
        } finally {
            setExporting(null);
        }
    };

    const handleDelete = async () => {
        setDeleting(true);
        setActionError(null);
        try {
            await apiRequest(`/api/v1/batches/${batchId}`, { method: 'DELETE' });
            navigate('/dashboard');
        } catch (e) {
            setActionError(`Delete failed: ${errorMessage(e)}`);
            setDeleting(false);
            setConfirmDelete(false);
        }
    };

    if (isLoading && !batch) {
        return (
            <div className="container fade-in" style={{ padding: '100px 0', textAlign: 'center' }}>
                <div className="spinner" style={{ width: '48px', height: '48px', border: '4px solid rgba(99, 102, 241, 0.1)', borderTopColor: 'var(--primary)', borderRadius: '50%', margin: '0 auto 20px' }} />
                <p style={{ color: 'var(--text-secondary)' }}>Loading results...</p>
            </div>
        );
    }

    if (error && !batch) {
        return (
            <div className="container fade-in" style={{ padding: '60px 0', maxWidth: '600px' }}>
                <div className="glass" style={{ padding: '32px', textAlign: 'center', borderColor: 'rgba(239, 68, 68, 0.3)' }}>
                    <h2 style={{ color: 'var(--error)', fontSize: '22px', fontWeight: 700, marginBottom: '8px' }}>Could not load results</h2>
                    <p style={{ color: 'var(--text-secondary)', marginBottom: '20px' }}>{error}</p>
                    <button type="button" className="btn-secondary" onClick={() => { setIsLoading(true); fetchResults(); }}>Try again</button>
                </div>
            </div>
        );
    }

    const type = batch?.analysis_type || '';
    const showAI = type === 'ai' || type === 'both';
    const showPlagiarism = type === 'plagiarism' || type === 'both';
    const total = batch?.total_docs || 0;
    const processed = batch?.processed_docs || 0;
    const progress = total > 0 ? Math.min(100, (processed / total) * 100) : 0;
    const shortId = (batch?.id || batchId || '').slice(0, 8);
    const finished = !active;

    return (
        <div className="container fade-in" style={{ padding: '40px 0' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: '16px', flexWrap: 'wrap', marginBottom: '24px' }}>
                <div>
                    <h1 style={{ fontSize: '36px', fontWeight: 700, marginBottom: '8px' }}>
                        Batch <span className="text-gradient-primary" title={batch?.id || batchId}>{shortId}</span>
                    </h1>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap', color: 'var(--text-secondary)', fontSize: '14px' }}>
                        {batch && <StatusBadge status={batch.status} />}
                        <span>{processed} / {total} documents processed</span>
                        {batch?.created_at && <span>{new Date(batch.created_at).toLocaleString()}</span>}
                    </div>
                </div>

                <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'center' }}>
                    <button type="button" className="btn-secondary" style={{ padding: '10px 18px', fontSize: '14px' }} disabled={!finished || exporting !== null} onClick={() => handleExport('pdf')}>
                        {exporting === 'pdf' ? 'Exporting...' : 'Export PDF'}
                    </button>
                    <button type="button" className="btn-secondary" style={{ padding: '10px 18px', fontSize: '14px' }} disabled={!finished || exporting !== null} onClick={() => handleExport('csv')}>
                        {exporting === 'csv' ? 'Exporting...' : 'Export CSV'}
                    </button>
                    {confirmDelete ? (
                        <span style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '14px' }}>
                            <span style={{ color: 'var(--text-secondary)' }}>Are you sure?</span>
                            <button type="button" className="btn-secondary" style={{ padding: '10px 18px', fontSize: '14px', color: 'var(--error)', borderColor: 'var(--error)' }} disabled={deleting} onClick={handleDelete}>
                                {deleting ? 'Deleting...' : 'Delete'}
                            </button>
                            <button type="button" className="btn-secondary" style={{ padding: '10px 18px', fontSize: '14px' }} disabled={deleting} onClick={() => setConfirmDelete(false)}>
                                Cancel
                            </button>
                        </span>
                    ) : (
                        <button type="button" className="btn-secondary" style={{ padding: '10px 18px', fontSize: '14px', color: 'var(--error)' }} onClick={() => setConfirmDelete(true)}>
                            Delete batch
                        </button>
                    )}
                </div>
            </div>

            {active && (
                <div style={{ height: '6px', background: 'rgba(255,255,255,0.08)', borderRadius: '9999px', overflow: 'hidden', marginBottom: '24px' }}>
                    <div style={{ width: `${progress}%`, height: '100%', background: 'var(--primary)', transition: 'width 0.5s ease' }} />
                </div>
            )}

            {actionError && <p style={{ color: 'var(--error)', marginBottom: '16px' }}>{actionError}</p>}
            {error && <p style={{ color: 'var(--error)', marginBottom: '16px' }}>Could not refresh: {error}</p>}

            {results.length > 0 ? (
                <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'grid', gap: '16px' }}>
                    {results.map((doc) => (
                        <DocumentCard key={doc.document_id} doc={doc} showAI={showAI} showPlagiarism={showPlagiarism} />
                    ))}
                </ul>
            ) : (
                <div className="glass" style={{ padding: '32px', textAlign: 'center', color: 'var(--text-secondary)' }}>
                    {active ? 'Documents are being processed. Results will appear here.' : 'No documents in this batch.'}
                </div>
            )}
        </div>
    );
};

export default BatchResultsPage;
