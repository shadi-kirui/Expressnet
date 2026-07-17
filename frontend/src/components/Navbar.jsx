import { LogOut, Menu, UserCircle } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export default function Navbar({ onMenuClick }) {
  const { tenant, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login', { replace: true });
  };

  return (
    <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-slate-200 px-4 lg:px-8">
      <div className="flex items-center gap-3">
        <button
          type="button"
          className="rounded-md p-2 text-slate-600 hover:bg-slate-100 lg:hidden"
          onClick={onMenuClick}
          aria-label="Open navigation"
        >
          <Menu size={22} />
        </button>
        <div>
          <p className="text-[11px] font-medium uppercase tracking-wide text-slate-500">Business</p>
          <h2 className="text-base font-medium text-slate-950">
            {tenant?.business_name || 'Tenant Dashboard'}
          </h2>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <button type="button" className="btn-secondary" onClick={() => navigate('/profile')}>
          <UserCircle size={17} />
          <span className="hidden sm:inline">Profile</span>
        </button>
        <button type="button" className="btn-secondary" onClick={handleLogout}>
          <LogOut size={17} />
          <span className="hidden sm:inline">Logout</span>
        </button>
      </div>
    </header>
  );
}
