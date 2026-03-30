import React, { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';

interface PlagiarismMatch {
    similar_document: string;
    similarity: number;
    matches: Array<{
        source_chunk: string;
        target_chunk: string;
        score: number;
    }>;
}

interface DocumentResult {
    document_id: string;
    filename: string;
    status: string;
    ai_analysis: {
        score: number;
        is_ai: boolean;
    };
    plagiarism_analysis: PlagiarismMatch[];
}

const ResultsPage: React.FC = () => {
    const { batchId } = useParams<{ batchId: string }>();
    const [results, setResults] = useState<DocumentResult[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [expandedDoc, setExpandedDoc] = useState<string | null>(null);

    useEffect(() => {
        const fetchResults = async () => {
            if (!batchId) return;

            try {
                const token = localStorage.getItem('token');
                const response = await fetch(`/api/v1/batches/${batchId}/results`, {
                    headers: { 'Authorization': `Bearer ${token}` },
                });

                if (!response.ok) {
                    const data = await response.json();
                    throw new Error(data.detail || 'Failed to fetch results');
                }

                const data = await response.json();
                setResults(data.data);
            } catch (e: any) {
                setError(e.message || 'An unexpected error occurred');
            } finally {
                setLoading(false);
            }
        };

        fetchResults();
    }, [batchId]);

    if (loading) {
        return (
            <div className="fade-in" style={{ padding: '100px 0', textAlign: 'center' }}>
                <div className="spinner" style={{ width: '60px', height: '60px', border: '4px solid rgba(99, 102, 241, 0.1)', borderTopColor: 'var(--primary)', borderRadius: '50%', margin: '0 auto 24px' }} />
                <h2 style={{ fontSize: '24px', fontWeight: 700 }}>Analyzing results...</h2>
            </div>
        );
    }

    if (error) {
        return (
            <div className="fade-in" style={{ padding: '60px 0', maxWidth: '600px', margin: '0 auto' }}>
                <div className="glass" style={{ padding: '40px', textAlign: 'center', border: '1px solid var(--error)' }}>
                    <h2 style={{ color: 'var(--error)' }}>Analysis Failed</h2>
                    <p>{error}</p>
                </div>
            </div>
        );
    }

    const handleExport = async (type: 'pdf' | 'csv') => {
        try {
            const token = localStorage.getItem('token');
            const response = await fetch(`/api/v1/batches/${batchId}/export/${type}`, {
                headers: { 'Authorization': `Bearer ${token}` },
            });

            if (!response.ok) throw new Error('Export failed');

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `report_${batchId}.${type}`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
        } catch (e: any) {
            alert(`Error exporting: ${e.message}`);
        }
    };

    return (
        <div className="fade-in" style={{ padding: '60px 0', maxWidth: '1000px', margin: '0 auto' }}>
            <div style={{ marginBottom: '40px', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
                <div>
                    <h1 className="text-gradient" style={{ fontSize: '48px', fontWeight: 800 }}>Analysis Report</h1>
                    <p style={{ color: 'var(--text-secondary)' }}>Batch ID: {batchId}</p>
                </div>
                <div style={{ display: 'flex', gap: '12px' }}>
                    <button onClick={() => handleExport('pdf')} className="btn-secondary" style={{ padding: '10px 20px', fontSize: '14px' }}>
                        PDF Export
                    </button>
                    <button onClick={() => handleExport('csv')} className="btn-secondary" style={{ padding: '10px 20px', fontSize: '14px' }}>
                        CSV Export
                    </button>
                </div>
            </div>

            <div style={{ display: 'grid', gap: '32px' }}>
                {results.map((doc) => (
                    <div key={doc.document_id} className="glass" style={{ padding: '32px', borderRadius: '24px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                            <h3 style={{ fontSize: '24px', fontWeight: 700 }}>{doc.filename}</h3>
                            <span style={{
                                padding: '6px 12px',
                                borderRadius: '100px',
                                background: doc.status === 'completed' ? 'rgba(16, 185, 129, 0.2)' : 'rgba(239, 68, 68, 0.2)',
                                color: doc.status === 'completed' ? 'var(--success)' : 'var(--error)',
                                fontSize: '12px', fontWeight: 700
                            }}>
                                {doc.status.toUpperCase()}
                            </span>
                        </div>

                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px', marginBottom: '32px' }}>
                            {/* AI Score */}
                            <div style={{ background: 'rgba(255,255,255,0.03)', padding: '20px', borderRadius: '16px' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                                    <span style={{ fontWeight: 600 }}>AI Probability</span>
                                    <span style={{ fontWeight: 700, color: doc.ai_analysis.is_ai ? 'var(--error)' : 'var(--success)' }}>
                                        {(doc.ai_analysis.score * 100).toFixed(1)}%
                                    </span>
                                </div>
                                <div style={{ height: '8px', background: 'rgba(255,255,255,0.1)', borderRadius: '100px', overflow: 'hidden' }}>
                                    <div style={{
                                        width: `${doc.ai_analysis.score * 100}%`,
                                        height: '100%',
                                        background: doc.ai_analysis.is_ai ? 'var(--error)' : 'var(--success)',
                                        transition: 'width 1s ease'
                                    }} />
                                </div>
                                <p style={{ fontSize: '13px', marginTop: '8px', color: 'var(--text-muted)' }}>
                                    {doc.ai_analysis.is_ai ? 'Likely AI-Generated' : 'Likely Human-Written'}
                                </p>
                            </div>

                            {/* Plagiarism Score */}
                            <div style={{ background: 'rgba(255,255,255,0.03)', padding: '20px', borderRadius: '16px' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                                    <span style={{ fontWeight: 600 }}>Max Plagiarism</span>
                                    <span style={{ fontWeight: 700 }}>
                                        {doc.plagiarism_analysis.length > 0
                                            ? `${(Math.max(...doc.plagiarism_analysis.map(p => p.similarity)) * 100).toFixed(1)}%`
                                            : '0%'}
                                    </span>
                                </div>
                                <div style={{ height: '8px', background: 'rgba(255,255,255,0.1)', borderRadius: '100px', overflow: 'hidden' }}>
                                    <div style={{
                                        width: `${doc.plagiarism_analysis.length > 0 ? Math.max(...doc.plagiarism_analysis.map(p => p.similarity)) * 100 : 0}%`,
                                        height: '100%',
                                        background: 'var(--warning)',
                                        transition: 'width 1s ease'
                                    }} />
                                </div>
                                <p style={{ fontSize: '13px', marginTop: '8px', color: 'var(--text-muted)' }}>
                                    {doc.plagiarism_analysis.length} document matches found
                                </p>
                            </div>
                        </div>

                        {/* Plagiarism Details */}
                        {doc.plagiarism_analysis.length > 0 && (
                            <div>
                                <button
                                    onClick={() => setExpandedDoc(expandedDoc === doc.document_id ? null : doc.document_id)}
                                    className="btn-secondary"
                                    style={{ width: '100%', textAlign: 'left', display: 'flex', justifyContent: 'space-between' }}
                                >
                                    <span>View Plagiarism Details</span>
                                    <span>{expandedDoc === doc.document_id ? '▲' : '▼'}</span>
                                </button>

                                {expandedDoc === doc.document_id && (
                                    <div style={{ marginTop: '16px', display: 'grid', gap: '16px' }}>
                                        {doc.plagiarism_analysis.map((match, idx) => (
                                            <div key={idx} style={{ background: 'rgba(0,0,0,0.2)', padding: '16px', borderRadius: '12px' }}>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
                                                    <span style={{ fontWeight: 600, color: 'var(--warning)' }}>Match with: {match.similar_document}</span>
                                                    <span style={{ fontWeight: 700 }}>{(match.similarity * 100).toFixed(1)}%</span>
                                                </div>
                                                {match.matches && match.matches.length > 0 ? (
                                                    <div style={{ display: 'grid', gap: '8px' }}>
                                                        {match.matches.map((chunk, cIdx) => (
                                                            <div key={cIdx} style={{ fontSize: '13px', background: 'rgba(255,255,255,0.05)', padding: '8px', borderRadius: '8px' }}>
                                                                <div style={{ color: 'var(--error)', marginBottom: '4px' }}>"{chunk.source_chunk.substring(0, 100)}..."</div>
                                                                <div style={{ color: 'var(--text-muted)' }}>Matches: "{chunk.target_chunk.substring(0, 100)}..."</div>
                                                            </div>
                                                        ))}
                                                    </div>
                                                ) : (
                                                    <p style={{ fontSize: '13px', color: 'var(--text-muted)' }}>High semantic similarity detected across document.</p>
                                                )}
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                ))}
            </div>
        </div>
    );
};

export default ResultsPage;
