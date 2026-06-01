/**
 * Safe API fetch wrapper.
 * Handles non-JSON responses (e.g., nginx HTML error pages) gracefully.
 */
export async function apiRequest<T = any>(
    url: string,
    options: RequestInit = {}
): Promise<T> {
    const token = localStorage.getItem('token');
    const headers = {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options.headers,
    };

    const response = await fetch(url, { ...options, headers });

    if (!response.ok) {
        let errorMessage = `Request failed (${response.status})`;

        // Map common HTTP status codes to user-friendly messages
        if (response.status === 413) {
            errorMessage = 'File is too large. Maximum size is 200MB.';
        } else if (response.status === 504 || response.status === 502) {
            errorMessage = 'Server timed out. The file may be too large to process.';
        } else if (response.status === 404) {
            errorMessage = 'Resource not found.';
        } else if (response.status === 500) {
            errorMessage = 'Internal server error.';
        }

        // Try to parse JSON error detail from the API
        const contentType = response.headers.get('content-type') || '';
        if (contentType.includes('application/json')) {
            try {
                const data = await response.json();
                if (data.detail) {
                    errorMessage = data.detail;
                }
            } catch {
                // Response body is not valid JSON, use status-based message
            }
        }

        throw new Error(errorMessage);
    }

    // For successful responses, safely parse JSON
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
        return response.json();
    }

    // Non-JSON success response (e.g., file download)
    return response as unknown as T;
}
