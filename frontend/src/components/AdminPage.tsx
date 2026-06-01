import { useState, useEffect } from 'react';
import { apiRequest } from '../utils/api';

const AdminPage = () => {
    const [stats, setStats] = useState<any>(null);
    const [users, setUsers] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [newUserEmail, setNewUserEmail] = useState('');
    const [newUserPassword, setNewUserPassword] = useState('');
    const [showCreateForm, setShowCreateForm] = useState(false);

    useEffect(() => {
        fetchData();
    }, []);

    const fetchData = async () => {
        try {
            const statsData = await apiRequest('/api/admin/stats');
            setStats(statsData);

            const usersData = await apiRequest('/api/admin/users');
            setUsers(usersData);
        } catch (err: any) {
            setError(err.message || 'Failed to load admin data');
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    const handleCreateUser = async (e: React.FormEvent) => {
        e.preventDefault();

        try {
            await apiRequest('/api/admin/users', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    email: newUserEmail,
                    password: newUserPassword,
                }),
            });

            alert('User created successfully');
            setNewUserEmail('');
            setNewUserPassword('');
            setShowCreateForm(false);
            fetchData();
        } catch (err: any) {
            alert(`Error: ${err.message}`);
            console.error(err);
        }
    };

    const handleUpdateRole = async (userId: string, newRole: string) => {
        try {
            await apiRequest(`/api/admin/users/${userId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ role: newRole }),
            });

            alert('User role updated successfully');
            fetchData();
        } catch (err: any) {
            alert(`Error: ${err.message}`);
            console.error(err);
        }
    };

    const handleDeactivateUser = async (userId: string, userEmail: string) => {
        if (!window.confirm(`Are you sure you want to deactivate user ${userEmail}?`)) {
            return;
        }

        try {
            await apiRequest(`/api/admin/users/${userId}`, {
                method: 'DELETE',
            });

            alert('User deactivated successfully');
            fetchData();
        } catch (err: any) {
            alert(`Error: ${err.message}`);
            console.error(err);
        }
    };

    if (loading) {
        return (
            <div className="container" style={{ padding: '40px 0', textAlign: 'center' }}>
                <div className="spinner" style={{ width: '40px', height: '40px', margin: '0 auto', border: '4px solid rgba(255,255,255,0.3)', borderTopColor: '#fff', borderRadius: '50%' }} />
                <p style={{ marginTop: '16px', color: 'var(--text-secondary)' }}>Loading admin data...</p>
            </div>
        );
    }

    return (
        <div className="container" style={{ padding: '40px 0' }}>
            <div style={{ marginBottom: '40px' }}>
                <h1 className="text-gradient-primary" style={{ fontSize: '36px', fontWeight: 700, marginBottom: '8px' }}>Admin Dashboard</h1>
                <p style={{ color: 'var(--text-secondary)' }}>System administration panel</p>
            </div>

            {error && (
                <div style={{ marginBottom: '24px', padding: '16px', background: 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: '12px', color: '#ef4444', fontSize: '14px' }}>
                    {error}
                </div>
            )}

            {/* Stats Section */}
            {stats && (
                <div className="glass" style={{ padding: '24px', marginBottom: '24px' }}>
                    <h2 style={{ fontSize: '24px', fontWeight: 600, marginBottom: '20px' }}>System Statistics</h2>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '20px' }}>
                        <div style={{ textAlign: 'center', padding: '16px', background: 'rgba(16, 185, 129, 0.1)', borderRadius: '12px' }}>
                            <div style={{ fontSize: '24px', fontWeight: 700, color: '#10b981' }}>{stats.total_users}</div>
                            <div style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>Total Users</div>
                        </div>
                        <div style={{ textAlign: 'center', padding: '16px', background: 'rgba(59, 130, 246, 0.1)', borderRadius: '12px' }}>
                            <div style={{ fontSize: '24px', fontWeight: 700, color: '#3b82f6' }}>{stats.active_users}</div>
                            <div style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>Active Users</div>
                        </div>
                        <div style={{ textAlign: 'center', padding: '16px', background: 'rgba(245, 158, 11, 0.1)', borderRadius: '12px' }}>
                            <div style={{ fontSize: '24px', fontWeight: 700, color: '#f59e0b' }}>{stats.admins}</div>
                            <div style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>Admins</div>
                        </div>
                        <div style={{ textAlign: 'center', padding: '16px', background: 'rgba(139, 92, 246, 0.1)', borderRadius: '12px' }}>
                            <div style={{ fontSize: '24px', fontWeight: 700, color: '#8b5cf6' }}>{stats.regular_users}</div>
                            <div style={{ fontSize: '14px', color: 'var(--text-secondary)' }}>Regular Users</div>
                        </div>
                    </div>
                </div>
            )}

            {/* User Management Section */}
            <div className="glass" style={{ padding: '24px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                    <h2 style={{ fontSize: '24px', fontWeight: 600 }}>User Management</h2>
                    <button 
                        onClick={() => setShowCreateForm(!showCreateForm)}
                        className="btn-primary"
                        style={{ padding: '8px 16px', fontSize: '14px' }}
                    >
                        {showCreateForm ? 'Cancel' : 'Add User'}
                    </button>
                </div>

                {/* Create User Form */}
                {showCreateForm && (
                    <div className="glass" style={{ padding: '20px', marginBottom: '24px' }}>
                        <h3 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '16px' }}>Create New User</h3>
                        <form onSubmit={handleCreateUser} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                            <div>
                                <label style={{ display: 'block', marginBottom: '8px', fontSize: '14px' }}>Email</label>
                                <input
                                    type="email"
                                    value={newUserEmail}
                                    onChange={(e) => setNewUserEmail(e.target.value)}
                                    required
                                    className="w-full bg-black/20 border border-white/10 rounded-xl p-3 text-white focus:outline-none focus:border-primary transition-colors"
                                    style={{ width: '100%', background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '12px', padding: '12px', color: 'white' }}
                                    placeholder="user@example.com"
                                />
                            </div>
                            <div>
                                <label style={{ display: 'block', marginBottom: '8px', fontSize: '14px' }}>Password</label>
                                <input
                                    type="password"
                                    value={newUserPassword}
                                    onChange={(e) => setNewUserPassword(e.target.value)}
                                    required
                                    minLength={6}
                                    className="w-full bg-black/20 border border-white/10 rounded-xl p-3 text-white focus:outline-none focus:border-primary transition-colors"
                                    style={{ width: '100%', background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '12px', padding: '12px', color: 'white' }}
                                    placeholder="Enter password"
                                />
                            </div>
                            <button type="submit" className="btn-primary" style={{ padding: '12px', fontWeight: 600 }}>
                                Create User
                            </button>
                        </form>
                    </div>
                )}

                {/* Users List */}
                <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ borderBottom: '2px solid rgba(255,255,255,0.1)' }}>
                                <th style={{ textAlign: 'left', padding: '12px', fontSize: '14px' }}>Email</th>
                                <th style={{ textAlign: 'left', padding: '12px', fontSize: '14px' }}>Role</th>
                                <th style={{ textAlign: 'left', padding: '12px', fontSize: '14px' }}>Status</th>
                                <th style={{ textAlign: 'left', padding: '12px', fontSize: '14px' }}>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {users.map(user => (
                                <tr key={user.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                                    <td style={{ padding: '12px', fontSize: '14px' }}>{user.email}</td>
                                    <td style={{ padding: '12px', fontSize: '14px' }}>
                                        <select 
                                            value={user.role}
                                            onChange={(e) => handleUpdateRole(user.id, e.target.value)}
                                            style={{ background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', padding: '6px', color: 'white' }}
                                        >
                                            <option value="user">User</option>
                                            <option value="moderator">Moderator</option>
                                            <option value="admin">Admin</option>
                                        </select>
                                    </td>
                                    <td style={{ padding: '12px', fontSize: '14px' }}>
                                        <span style={{
                                            padding: '4px 8px',
                                            borderRadius: '6px',
                                            fontSize: '12px',
                                            backgroundColor: user.is_active ? 'rgba(16, 185, 129, 0.2)' : 'rgba(239, 68, 68, 0.2)',
                                            color: user.is_active ? '#10b981' : '#ef4444',
                                        }}>
                                            {user.is_active ? 'Active' : 'Inactive'}
                                        </span>
                                    </td>
                                    <td style={{ padding: '12px' }}>
                                        <button 
                                            onClick={() => handleDeactivateUser(user.id, user.email)}
                                            style={{
                                                background: 'rgba(239, 68, 68, 0.2)',
                                                border: '1px solid rgba(239, 68, 68, 0.3)',
                                                color: '#ef4444',
                                                padding: '6px 12px',
                                                borderRadius: '8px',
                                                cursor: 'pointer',
                                                fontSize: '12px',
                                            }}
                                        >
                                            Deactivate
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
};

export default AdminPage;