import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { apiRequest } from '../utils/api';

interface Metrics {
    num_batches: number;
    num_documents: number;
}

interface BatchItem {
    id: string;
    status: string;
    analysis_type: string;
    total_docs: number;
    processed_docs: number;
    document_count: number;
    created_at: string | null;
}

const STATUS_COLORS: Record<string, string> = {
    completed: '#22c55e',
    completed_with_errors: '#f59e0b',
    processing: '#6366f1',
    queued: '#94a3b8',
    failed: '#ef4444',
};

const DashboardPage = () => {
    const [metrics, setMetrics] = useState<Metrics | null>(null);
    const [batches, setBatches] = useState<BatchItem[]>([]);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const fetchData = async () => {
            try {
                const [metricsData, batchesData] = await Promise.all([
                    apiRequest<{ data: Metrics }>('/api/v1/users/me/dashboard'),
                    apiRequest<{ data: BatchItem[]; total: number }>('/api/v1/batches?limit=10'),
                ]);
                setMetrics(metricsData.data);
                setBatches(batchesData.data || []);
            } catch (e: any) {
                setError(e.message);
            }
        };

        fetchData();
    }, []);

    const avg = metrics ? (metrics.num_documents / metrics.num_batches || 0).toFixed(1) : 0;

    return (
        <div className="container fade-in" style={{ padding: '60px 0' }}>
            <div style={{ marginBottom: '60px' }}>
                <h1 style={{ fontSize: '48px', fontWeight: 800, marginBottom: '12px', letterSpacing: '-0.02em' }}>
                    Welcome Back
                </h1>
                <p style={{ color: 'var(--text-secondary)', fontSize: '18px' }}>
                    Here's an overview of your analysis activity.
                </p>
            </div>

            {error && (
                <div className="glass" style={{ padding: '20px', background: 'rgba(239, 68, 68, 0.05)', borderColor: 'rgba(239, 68, 68, 0.2)', borderRadius: '16px', marginBottom: '40px' }}>
                    <p style={{ color: 'var(--error)', fontWeight: 500 }}>Error: {error}</p>
                </div>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '32px', marginBottom: '60px' }}>
                {[
                    { label: 'Total Batches', value: metrics?.num_batches || 0, icon: '📦', color: 'var(--primary)' },
                    { label: 'Documents Analyzed', value: metrics?.num_documents || 0, icon: '📄', color: 'var(--secondary)' },
                    { label: 'Avg. per Batch', value: avg, icon: '📊', color: 'var(--accent)' }
                ].map((stat, i) => (
                    <div key={i} className="glass card-hover" style={{ padding: '32px', position: 'relative', overflow: 'hidden' }}>
                        <div style={{
                            position: 'absolute',
                            top: '-10px',
                            right: '-10px',
                            fontSize: '80px',
                            opacity: 0.05,
                            transform: 'rotate(15deg)'
                        }}>
                            {stat.icon}
                        </div>
                        <h3 style={{ fontSize: '14px', color: 'var(--text-secondary)', marginBottom: '12px', textTransform: 'uppercase', letterSpacing: '0.1em', fontWeight: 600 }}>
                            {stat.label}
                        </h3>
                        <p style={{ fontSize: '48px', fontWeight: 800, color: 'white' }}>{stat.value}</p>
                    </div>
                ))}
            </div>

            {/* Recent Batches */}
            {batches.length > 0 && (
                <div style={{ marginBottom: '60px' }}>
                    <h2 style={{ fontSize: '24px', fontWeight: 700, marginBottom: '20px' }}>Recent Batches</h2>
                    <div className="glass" style={{ borderRadius: '16px', overflow: 'hidden' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
                                    <th style={{ padding: '14px 20px', textAlign: 'left', fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-secondary)', fontWeight: 600 }}>Type</th>
                                    <th style={{ padding: '14px 20px', textAlign: 'left', fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-secondary)', fontWeight: 600 }}>Documents</th>
                                    <th style={{ padding: '14px 20px', textAlign: 'left', fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-secondary)', fontWeight: 600 }}>Status</th>
                                    <th style={{ padding: '14px 20px', textAlign: 'left', fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-secondary)', fontWeight: 600 }}>Date</th>
                                    <th style={{ padding: '14px 20px', textAlign: 'right', fontSize: '12px', textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-secondary)', fontWeight: 600 }}></th>
                                </tr>
                            </thead>
                            <tbody>
                                {batches.map((batch) => (
                                    <tr key={batch.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                                        <td style={{ padding: '14px 20px', textTransform: 'capitalize' }}>{batch.analysis_type || 'N/A'}</td>
                                        <td style={{ padding: '14px 20px' }}>{batch.processed_docs}/{batch.total_docs}</td>
                                        <td style={{ padding: '14px 20px' }}>
                                            <span style={{
                                                display: 'inline-block',
                                                padding: '4px 10px',
                                                borderRadius: '9999px',
                                                fontSize: '12px',
                                                fontWeight: 600,
                                                color: STATUS_COLORS[batch.status] || '#94a3b8',
                                                background: `${STATUS_COLORS[batch.status] || '#94a3b8'}20`,
                                            }}>
                                                {batch.status?.replace(/_/g, ' ') || 'unknown'}
                                            </span>
                                        </td>
                                        <td style={{ padding: '14px 20px', color: 'var(--text-secondary)', fontSize: '14px' }}>
                                            {batch.created_at ? new Date(batch.created_at).toLocaleDateString() : 'N/A'}
                                        </td>
                                        <td style={{ padding: '14px 20px', textAlign: 'right' }}>
                                            <Link to={`/batch/${batch.id}`} style={{ color: 'var(--primary)', textDecoration: 'none', fontWeight: 600, fontSize: '14px' }}>
                                                View
                                            </Link>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(350px, 1fr))', gap: '32px' }}>
                <Link to="/upload" className="glass card-hover" style={{ textDecoration: 'none', color: 'inherit', padding: '40px', display: 'flex', alignItems: 'center', gap: '24px' }}>
                    <div style={{ fontSize: '40px', background: 'rgba(99, 102, 241, 0.1)', width: '80px', height: '80px', borderRadius: '20px', display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid rgba(99, 102, 241, 0.2)' }}>
                        📤
                    </div>
                    <div>
                        <h3 style={{ fontSize: '22px', fontWeight: 700, marginBottom: '8px' }}>Upload Documents</h3>
                        <p style={{ fontSize: '15px', color: 'var(--text-secondary)' }}>Check for plagiarism & AI content</p>
                    </div>
                </Link>

                <Link to="/ai-check" className="glass card-hover" style={{ textDecoration: 'none', color: 'inherit', padding: '40px', display: 'flex', alignItems: 'center', gap: '24px' }}>
                    <div style={{ fontSize: '40px', background: 'rgba(236, 72, 153, 0.1)', width: '80px', height: '80px', borderRadius: '20px', display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid rgba(236, 72, 153, 0.2)' }}>
                        🤖
                    </div>
                    <div>
                        <h3 style={{ fontSize: '22px', fontWeight: 700, marginBottom: '8px' }}>AI Detection</h3>
                        <p style={{ fontSize: '15px', color: 'var(--text-secondary)' }}>Analyze text for AI authorship</p>
                    </div>
                </Link>
            </div>
        </div>
    );
};

export default DashboardPage;
