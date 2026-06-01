import { useState, useEffect, ReactNode } from 'react';
import { AuthContext, User } from '../contexts/AuthContext';

const FALLBACK_USER: User = {
    id: '00000000-0000-0000-0000-000000000000',
    email: 'local@example.com',
    role: 'admin'
};

export const AuthProvider = ({ children }: { children: ReactNode }) => {
    const token = 'local-tool-token';
    const [user, setUser] = useState<User | null>(null);
    const [isAuthenticated, setIsAuthenticated] = useState(true);

    useEffect(() => {
        fetchUserInfo();
    }, []);

    const fetchUserInfo = async () => {
        try {
            const response = await fetch('/api/v1/users/me');

            if (response.ok) {
                const contentType = response.headers.get('content-type') || '';
                if (contentType.includes('application/json')) {
                    const userData = await response.json();
                    setUser({
                        id: userData.id,
                        email: userData.email,
                        role: userData.role || 'admin'
                    });
                } else {
                    setUser(FALLBACK_USER);
                }
            } else {
                setUser(FALLBACK_USER);
            }
            setIsAuthenticated(true);
        } catch {
            setUser(FALLBACK_USER);
            setIsAuthenticated(true);
        }
    };

    const login = async (_newToken: string) => {};
    const logout = () => {};

    return (
        <AuthContext.Provider value={{ isAuthenticated, token, user, login, logout }}>
            {children}
        </AuthContext.Provider>
    );
};