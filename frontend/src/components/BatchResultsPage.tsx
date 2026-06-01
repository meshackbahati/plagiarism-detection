import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { apiRequest } from '../utils/api';

const BatchResultsPage = () => {
    const { batchId } = useParams();
    const [results, setResults] = useState<any[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [isLoading, setIsLoading] = useState(false);

    useEffect(() => {
        const fetchResults = async () => {
            setIsLoading(true);
            try {
                const data = await apiRequest<{ data: any[] }>(`/api/v1/batches/${batchId}/results`);
                setResults(data.data);
            } catch (e: any) {
                setError(e.message);
            } finally {
                setIsLoading(false);
            }
        };

        if (batchId) {
            fetchResults();
        }
    }, [batchId]);

    return (
        <div className="container" style={{ padding: '40px 0' }}>
            <h1 style={{ fontSize: '36px', fontWeight: 700, marginBottom: '24px' }}>
                Analysis Results for Batch <span className="text-gradient-primary">{batchId}</span>
            </h1>

            {isLoading && <p>Loading results...</p>}
            {error && <p style={{ color: 'var(--error)' }}>Error: {error}</p>}

            <div className="glass" style={{ padding: '32px' }}>
                {results.length > 0 ? (
                    <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'grid', gap: '16px' }}>
                        {results.map((result, index) => (
                            <li key={index} className="glass card-hover" style={{ padding: '24px', borderRadius: '16px' }}>
                                <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '12px' }}>
                                    {result.filename}
                                </h3>
                                {result.plagiarism_analysis?.length > 0 ? (
                                    <p style={{ color: 'var(--text-secondary)' }}>
                                        Top similarity: {(result.plagiarism_analysis[0].similarity * 100).toFixed(1)}% compared to {result.plagiarism_analysis[0].similar_document}
                                    </p>
                                ) : (
                                    <p style={{ color: 'var(--text-secondary)' }}>No plagiarism matches found.</p>
                                )}
                            </li>
                        ))}
                    </ul>
                ) : (
                    <p>No results found for this batch.</p>
                )}
            </div>
        </div>
    );
};

export default BatchResultsPage;
