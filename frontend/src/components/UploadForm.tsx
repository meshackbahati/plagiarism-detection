import { useState } from 'react';
import { Link } from 'react-router-dom';
import { apiRequest } from '../utils/api';

const UploadForm = () => {
    const [files, setFiles] = useState<File[]>([]);
    const [batchId, setBatchId] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [isUploading, setIsUploading] = useState(false);
    const [analysisType, setAnalysisType] = useState('plagiarism');

    // New Options
    const [provider, setProvider] = useState('local');
    const [aiThreshold, setAiThreshold] = useState(0.5);

    const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        if (e.target.files) setFiles(Array.from(e.target.files));
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (files.length === 0) return;

        setIsUploading(true);
        setError(null);
        setBatchId(null);

        const formData = new FormData();
        files.forEach(file => formData.append('files', file));

        // Add options
        const options = {
            provider,
            ai_threshold: aiThreshold,
            check_plagiarism: analysisType === 'plagiarism' || analysisType === 'both',
            check_ai: analysisType === 'ai' || analysisType === 'both'
        };
        formData.append('options', JSON.stringify(options));

        try {
            // Client-side file size check (200MB limit)
            const MAX_SIZE = 200 * 1024 * 1024;
            const oversized = files.find(f => f.size > MAX_SIZE);
            if (oversized) {
                throw new Error(`File "${oversized.name}" is too large (${(oversized.size / 1024 / 1024).toFixed(1)}MB). Maximum is 200MB.`);
            }

            const response = await apiRequest<{ batch_id: string }>(`/api/v1/analyze`, {
                method: 'POST',
                body: formData,
            });

            setBatchId(response.batch_id);
            setFiles([]);
        } catch (e: any) {
            setError(e.message);
        } finally {
            setIsUploading(false);
        }
    };

    return (
        <div className="container fade-in" style={{ padding: '60px 0' }}>
            <div style={{ marginBottom: '60px', textAlign: 'center' }}>
                <h1 className="text-gradient" style={{ fontSize: '56px', fontWeight: 800, marginBottom: '16px', letterSpacing: '-0.02em' }}>
                    Analyze Content
                </h1>
                <p style={{ color: 'var(--text-secondary)', fontSize: '18px' }}>
                    Upload documents, images, or archives for deep analysis.
                </p>
            </div>

            <div className="glass" style={{ padding: '48px', borderRadius: '32px', boxShadow: '0 30px 60px rgba(0,0,0,0.4)' }}>
                <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '40px' }}>

                    {/* Provider Selection */}
                    <div>
                        <label style={{ display: 'block', marginBottom: '20px', fontSize: '16px', fontWeight: 700, color: 'white', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                            AI Detection Provider
                        </label>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '20px' }}>
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
                                        padding: '20px',
                                        borderRadius: '16px',
                                        transition: 'var(--transition)',
                                        border: provider === p.id ? '2px solid var(--primary)' : '2px solid transparent'
                                    }}>
                                        <div style={{ fontWeight: 700, marginBottom: '4px' }}>{p.label}</div>
                                        <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{p.desc}</div>
                                    </div>
                                </label>
                            ))}
                        </div>
                        {provider !== 'local' && (
                            <div style={{ marginTop: '12px', fontSize: '13px', color: 'var(--warning)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                                ⚠️ External providers may incur costs and send data to third parties.
                            </div>
                        )}
                    </div>

                    {/* Analysis Type */}
                    <div>
                        <label style={{ display: 'block', marginBottom: '20px', fontSize: '16px', fontWeight: 700, color: 'white', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                            Analysis Mode
                        </label>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '20px' }}>
                            {[
                                { id: 'plagiarism', label: 'Plagiarism', icon: '🔍' },
                                { id: 'ai', label: 'AI Detection', icon: '🤖' },
                                { id: 'both', label: 'Full Scan', icon: '✨' }
                            ].map(type => (
                                <label key={type.id} style={{ cursor: 'pointer' }}>
                                    <input
                                        type="radio"
                                        name="analysisType"
                                        value={type.id}
                                        checked={analysisType === type.id}
                                        onChange={(e) => setAnalysisType(e.target.value)}
                                        style={{ display: 'none' }}
                                    />
                                    <div className={`glass card-hover ${analysisType === type.id ? 'active-card' : ''}`} style={{
                                        textAlign: 'center',
                                        padding: '24px 16px',
                                        borderRadius: '20px',
                                        transition: 'var(--transition)'
                                    }}>
                                        <div style={{ fontSize: '32px', marginBottom: '12px' }}>{type.icon}</div>
                                        <span style={{ fontSize: '15px', fontWeight: 700 }}>{type.label}</span>
                                    </div>
                                </label>
                            ))}
                        </div>
                    </div>

                    {/* AI Threshold Slider */}
                    {(analysisType === 'ai' || analysisType === 'both') && (
                        <div>
                            <label style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px', fontSize: '14px', fontWeight: 600, color: 'var(--text-secondary)' }}>
                                <span>AI Detection Sensitivity</span>
                                <span>{Math.round(aiThreshold * 100)}%</span>
                            </label>
                            <input
                                type="range"
                                min="0.1"
                                max="0.9"
                                step="0.05"
                                value={aiThreshold}
                                onChange={(e) => setAiThreshold(parseFloat(e.target.value))}
                                style={{ width: '100%', accentColor: 'var(--primary)' }}
                            />
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '4px', fontSize: '12px', color: 'var(--text-muted)' }}>
                                <span>More Lenient</span>
                                <span>Stricter</span>
                            </div>
                        </div>
                    )}

                    {/* Upload Area */}
                    <div>
                        <label style={{ display: 'block', marginBottom: '20px', fontSize: '16px', fontWeight: 700, color: 'white', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
                            Documents
                        </label>
                        <label className="glass upload-zone" style={{
                            display: 'block',
                            padding: '80px 40px',
                            border: '2px dashed var(--glass-border)',
                            borderRadius: '24px',
                            textAlign: 'center',
                            cursor: 'pointer',
                            transition: 'var(--transition)'
                        }}>
                            <div style={{ fontSize: '64px', marginBottom: '24px' }}>📤</div>
                            <h3 style={{ fontSize: '20px', fontWeight: 700, marginBottom: '12px' }}>
                                <span className="text-gradient-primary">Select files</span> or drag & drop
                            </h3>
                            <p style={{ fontSize: '15px', color: 'var(--text-muted)' }}>
                                Supports PDF, DOCX, TXT, PNG, JPG, ZIP, TAR
                            </p>
                            <input
                                type="file"
                                multiple
                                onChange={handleFileChange}
                                style={{ display: 'none' }}
                            />
                        </label>
                    </div>

                    {/* File List */}
                    {files.length > 0 && (
                        <div className="fade-in">
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '16px', alignItems: 'center' }}>
                                <p style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-secondary)' }}>
                                    Selected Files ({files.length})
                                </p>
                                <button type="button" onClick={() => setFiles([])} style={{ fontSize: '13px', color: 'var(--error)', background: 'none', border: 'none', cursor: 'pointer', fontWeight: 600 }}>
                                    Clear All
                                </button>
                            </div>
                            <div style={{ maxHeight: '240px', overflowY: 'auto', display: 'grid', gap: '12px', paddingRight: '8px' }}>
                                {files.map((file, i) => (
                                    <div key={i} className="glass" style={{
                                        padding: '16px 20px',
                                        fontSize: '14px',
                                        display: 'flex',
                                        justifyContent: 'space-between',
                                        alignItems: 'center',
                                        borderRadius: '16px'
                                    }}>
                                        <span style={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '70%' }}>
                                            {file.name}
                                        </span>
                                        <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>
                                            {(file.size / 1024).toFixed(1)} KB
                                        </span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    <button type="submit" className="btn-primary" disabled={files.length === 0 || isUploading} style={{
                        width: '100%',
                        padding: '20px',
                        fontSize: '18px',
                        fontWeight: 800,
                        borderRadius: '18px'
                    }}>
                        {isUploading ? (
                            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                                <div className="spinner" style={{ width: '24px', height: '24px', border: '3px solid rgba(255,255,255,0.3)', borderTopColor: '#fff', borderRadius: '50%' }} />
                                Processing...
                            </div>
                        ) : 'Start Deep Analysis'}
                    </button>
                </form>

                {batchId && (
                    <div className="fade-in" style={{ marginTop: '40px', padding: '32px', background: 'rgba(16, 185, 129, 0.1)', border: '1px solid rgba(16, 185, 129, 0.2)', borderRadius: '24px', textAlign: 'center' }}>
                        <div style={{ fontSize: '32px', marginBottom: '16px' }}>✅</div>
                        <p style={{ fontSize: '18px', marginBottom: '24px', color: 'var(--success)', fontWeight: 700 }}>
                            Upload successful! Analysis in progress.
                        </p>
                        <Link to={`/dashboard`} className="btn-secondary" style={{ display: 'inline-flex', padding: '14px 32px', borderRadius: '14px', textDecoration: 'none', fontWeight: 700 }}>
                            Go to Dashboard →
                        </Link>
                    </div>
                )}

                {error && (
                    <div className="fade-in" style={{ marginTop: '40px', padding: '24px', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.2)', borderRadius: '20px', color: 'var(--error)', fontSize: '15px', fontWeight: 600, textAlign: 'center' }}>
                        ⚠️ {error}
                    </div>
                )}
            </div>
        </div>
    );
};

export default UploadForm;
