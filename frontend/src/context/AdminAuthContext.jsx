import { createContext, useContext, useMemo, useState } from 'react';

const AdminAuthContext = createContext(null);

function decodeToken(token) {
  try {
    const payload = token.split('.')[1];
    const normalized = payload.replace(/-/g, '+').replace(/_/g, '/');
    const padded = normalized.padEnd(normalized.length + ((4 - (normalized.length % 4)) % 4), '=');
    return JSON.parse(window.atob(padded));
  } catch {
    return null;
  }
}

function getStoredAdmin() {
  try {
    return JSON.parse(localStorage.getItem('admin_user')) || null;
  } catch {
    return null;
  }
}

function getStoredToken() {
  const token = localStorage.getItem('admin_token');
  const decoded = token ? decodeToken(token) : null;
  if (decoded?.exp && decoded.exp * 1000 < Date.now()) {
    localStorage.removeItem('admin_token');
    localStorage.removeItem('admin_user');
    return null;
  }
  return token;
}

export function AdminAuthProvider({ children }) {
  const [token, setToken] = useState(() => getStoredToken());
  const [admin, setAdmin] = useState(() => getStoredAdmin());

  const loginAdmin = (newToken, adminProfile = null) => {
    const decoded = decodeToken(newToken);
    const nextAdmin = adminProfile || decoded;
    localStorage.setItem('admin_token', newToken);
    localStorage.setItem('admin_user', JSON.stringify(nextAdmin));
    setToken(newToken);
    setAdmin(nextAdmin);
  };

  const logoutAdmin = () => {
    localStorage.removeItem('admin_token');
    localStorage.removeItem('admin_user');
    setToken(null);
    setAdmin(null);
  };

  const value = useMemo(
    () => ({
      token,
      admin,
      isAdminAuthenticated: Boolean(token),
      loginAdmin,
      logoutAdmin,
    }),
    [token, admin],
  );

  return <AdminAuthContext.Provider value={value}>{children}</AdminAuthContext.Provider>;
}

export function useAdminAuth() {
  const context = useContext(AdminAuthContext);
  if (!context) {
    throw new Error('useAdminAuth must be used inside AdminAuthProvider');
  }
  return context;
}
