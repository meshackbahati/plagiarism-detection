import { useState } from 'react';
import { apiRequest } from '../utils/api';

const AIDetectionPage = () => {
    const [text, setText] = useState('');
    const [result, setResult] = useState<any>(null);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [provider, setProvider] = useState('local');
    const [threshold, setThreshold] = useState(0.5);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setIsLoading(true);
        setError(null);
        setResult(null);

        try {
            const data = await apiRequest('/api/v1/ai-detection', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text, provider, threshold }),
            });
            setResult(data);
        } catch (e: any) {
            setError(e.message);
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="container" style={{ padding: '40px 0' }}>
            <div style={{ marginBottom: '40px' }}>
                <h1 className="text-gradient-primary" style={{ fontSize: '36px', fontWeight: 700, marginBottom: '8px' }}>AI Detection</h1>
                <p style={{ color: 'var(--text-secondary)' }}>Analyze text for AI-generated content</p>
            </div>

            <div className="glass" style={{ padding: '32px' }}>
                <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                    {/* Provider Selection */}
                    <div>
                        <label style={{ display: 'block', marginBottom: '12px', fontSize: '14px', fontWeight: 500 }}>AI Detection Provider</label>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px' }}>
                            {[
                                { id: 'local', label: 'Local Model', desc: 'Free, Fast, Private' },
                                { id: 'openai', label: 'OpenAI', desc: 'High Accuracy, Paid' },
                                { id: 'together', label: 'Together AI', desc: 'Open Models, Fast' }
                            ].map(p => (
                                <label key={p.id} style={{ cursor: 'pointer' }}>
                                    <input
                                        type="radio"
                                        name="provider"
                                        value={p.id}
                                        checked={provider === p.id}
                                        onChange={(e) => setProvider(e.target.value)}
                                        style={{ display: 'none' }}
                                    />
                                    <div className={`glass card-hover ${provider === p.id ? 'active-card' : ''}`} style={{
                                        textAlign: 'center',
                                        padding: '12px',
                                        borderRadius: '12px',
                                        transition: 'var(--transition)',
                                        border: provider === p.id ? '2px solid var(--primary)' : '2px solid transparent'
                                    }}>
                                        <div style={{ fontWeight: 600, marginBottom: '4px' }}>{p.label}</div>
                                        <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{p.desc}</div>
                                    </div>
                                </label>
                            ))}
                        </div>
                        {provider !== 'local' && (
                            <div style={{ marginTop: '8px', fontSize: '12px', color: 'var(--warning)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                                ⚠️ External providers may incur costs
                            </div>
                        )}
                    </div>

                    {/* Threshold Slider */}
                    <div>
                        <label style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', fontSize: '13px', fontWeight: 500, color: 'var(--text-secondary)' }}>
                            <span>Detection Sensitivity</span>
                            <span>{Math.round(threshold * 100)}%</span>
                        </label>
                        <input
                            type="range"
                            min="0.1"
                            max="0.9"
                            step="0.05"
                            value={threshold}
                            onChange={(e) => setThreshold(parseFloat(e.target.value))}
                            style={{ width: '100%', accentColor: 'var(--primary)' }}
                        />
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '4px', fontSize: '11px', color: 'var(--text-muted)' }}>
                            <span>More Lenient</span>
                            <span>Stricter</span>
                        </div>
                    </div>

                    <div>
                        <label style={{ display: 'block', marginBottom: '12px', fontSize: '14px', fontWeight: 500 }}>Text to Analyze</label>
                        <textarea
                            value={text}
                            onChange={(e) => setText(e.target.value)}
                            placeholder="Paste the text you want to check for AI authorship..."
                            required
                            rows={10}
                            className="w-full bg-black/20 border border-white/10 rounded-xl p-4 text-white focus:outline-none focus:border-primary transition-colors"
                            style={{ width: '100%', background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '12px', padding: '16px', color: 'white' }}
                        />
                    </div>

                    <button type="submit" className="btn-primary" disabled={!text.trim() || isLoading} style={{ width: '100%', justifyContent: 'center' }}>
                        {isLoading ? (
                            <>
                                <div className="spinner" style={{ width: '20px', height: '20px', border: '2px solid rgba(255,255,255,0.3)', borderTopColor: 'white', borderRadius: '50%' }}></div>
                                <span>Analyzing...</span>
                            </>
                        ) : 'Analyze Text'}
                    </button>
                </form>

                {result && (
                    <div className="fade-in" style={{ marginTop: '32px' }}>
                        <div style={{ padding: '24px', background: 'rgba(99, 102, 241, 0.1)', border: '1px solid rgba(99, 102, 241, 0.3)', borderRadius: '12px' }}>
                            <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px' }}>Analysis Results</h3>
                            <div style={{ display: 'grid', gap: '16px' }}>
                                <div>
                                    <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '4px' }}>AI Probability</p>
                                    <p className="text-gradient-primary" style={{ fontSize: '28px', fontWeight: 700 }}>
                                        {(result.score * 100).toFixed(1)}%
                                    </p>
                                </div>
                                <div>
                                    <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '4px' }}>Classification</p>
                                    <p style={{ fontSize: '18px', fontWeight: 600 }}>{result.label || 'N/A'}</p>
                                </div>
                                <div>
                                    <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '4px' }}>Confidence</p>
                                    <p style={{ fontSize: '16px', fontWeight: 500 }}>{result.confidence ? `${(result.confidence * 100).toFixed(1)}%` : 'N/A'}</p>
                                </div>
                                <div>
                                    <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '4px' }}>Provider</p>
                                    <p style={{ fontSize: '16px', fontWeight: 500, textTransform: 'capitalize' }}>{result.provider || 'N/A'}</p>
                                </div>
                            </div>
                        </div>
                        <div style={{ marginTop: '24px', padding: '24px', background: 'rgba(255, 193, 7, 0.1)', border: '1px solid rgba(255, 193, 7, 0.3)', borderRadius: '12px', fontSize: '14px', color: '#ffc107' }}>
                            <h4 style={{ fontWeight: 600, marginBottom: '8px' }}>Important Disclaimer</h4>
                            <p>AI detection models are not perfect and can produce false positives. The results should be used as a guideline, not as a definitive conclusion. The model used here is `roberta-base-openai-detector`, which has known limitations.</p>
                        </div>
                    </div>
                )}

                {error && (
                    <div className="fade-in" style={{ marginTop: '24px', padding: '16px', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: '12px', color: '#ef4444', fontSize: '14px' }}>
                        {error}
                    </div>
                )}
            </div>
        </div>
    );
};

export default AIDetectionPage;
