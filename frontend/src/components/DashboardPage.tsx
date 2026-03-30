import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';

interface Metrics {
    num_batches: number;
    num_documents: number;
}

const DashboardPage = () => {
    const [metrics, setMetrics] = useState<Metrics | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const fetchMetrics = async () => {
            try {
                const token = localStorage.getItem('token');
                const response = await fetch('/api/v1/users/me/dashboard', {
                    headers: { 'Authorization': `Bearer ${token}` },
                });

                if (!response.ok) throw new Error('Failed to fetch');
                const data = await response.json();
                setMetrics(data.data);
            } catch (e: any) {
                setError(e.message);
            }
        };

        fetchMetrics();
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
                    <p style={{ color: 'var(--error)', fontWeight: 500 }}>⚠️ Error: {error}</p>
                </div>
            )}

            {/* Dashboard level exports removed to avoid ambiguity without a batch context. */}

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
