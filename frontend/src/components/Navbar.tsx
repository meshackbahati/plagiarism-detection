import { Link } from 'react-router-dom';

const Navbar = () => {
  return (
    <nav className="glass fixed top-5 left-1/2 -translate-x-1/2 w-[calc(100%-40px)] max-w-[1200px] z-[1000] p-3 px-6 rounded-[20px] shadow-2xl" style={{
      background: 'rgba(17, 24, 39, 0.7)',
      backdropFilter: 'blur(16px)',
      border: '1px solid rgba(255, 255, 255, 0.08)'
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Link to="/" style={{ display: 'flex', alignItems: 'center', gap: '12px', textDecoration: 'none' }}>
          <div style={{
            width: '36px',
            height: '36px',
            background: 'linear-gradient(135deg, var(--primary), var(--accent))',
            borderRadius: '10px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            boxShadow: '0 4px 12px rgba(99, 102, 241, 0.3)'
          }}>
            <span style={{ fontSize: '18px' }}>🛡️</span>
          </div>
          <span className="text-gradient" style={{ fontSize: '22px', fontWeight: 800, letterSpacing: '-0.02em' }}>
            PlagDetect
          </span>
        </Link>

        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <Link to="/dashboard" className="btn-secondary" style={{ textDecoration: 'none', padding: '10px 20px', fontSize: '14px' }}>Dashboard</Link>
          <Link to="/upload" className="btn-secondary" style={{ textDecoration: 'none', padding: '10px 20px', fontSize: '14px' }}>Upload</Link>
          <Link to="/ai-check" className="btn-secondary" style={{ textDecoration: 'none', padding: '10px 20px', fontSize: '14px' }}>AI Check</Link>
          <Link to="/admin" className="btn-secondary" style={{ textDecoration: 'none', padding: '10px 20px', fontSize: '14px' }}>Admin</Link>
        </div>
      </div>
    </nav>
  );
};

export default Navbar;