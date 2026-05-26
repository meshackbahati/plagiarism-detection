import { useState, useEffect, ReactNode } from 'react';
import { AuthContext, User } from '../contexts/AuthContext';

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [token, setToken] = useState<string | null>('local-tool-token');
  const [user, setUser] = useState<User | null>(null);
  const [isAuthenticated, setIsAuthenticated] = useState(true);

  useEffect(() => {
    // Always fetch user info for the local tool
    fetchUserInfo();
  }, []);

  const fetchUserInfo = async () => {
    try {
      const response = await fetch('/api/v1/users/me');

      if (response.ok) {
        const userData = await response.json();
        const userObj: User = {
          id: userData.id,
          email: userData.email,
          role: userData.role || 'admin'
        };
        setUser(userObj);
        setIsAuthenticated(true);
      } else {
        console.error('Failed to fetch user info, using fallback');
        setUser({
          id: '00000000-0000-0000-0000-000000000000',
          email: 'admin@example.com',
          role: 'admin'
        });
      }
    } catch (error) {
      console.error('Error fetching user info:', error);
      setUser({
        id: '00000000-0000-0000-0000-000000000000',
        email: 'admin@example.com',
        role: 'admin'
      });
    }
  };

  const login = async (_newToken: string) => {
    // No-op for local tool
  };

  const logout = () => {
    // No-op for local tool
  };

  return (
    <AuthContext.Provider value={{ isAuthenticated, token, user, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
};