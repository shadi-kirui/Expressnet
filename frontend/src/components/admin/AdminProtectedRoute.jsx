import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAdminAuth } from '../../context/AdminAuthContext';
import { ADMIN_LOGIN_PATH } from '../../config/adminPaths';

export default function AdminProtectedRoute() {
  const { isAdminAuthenticated } = useAdminAuth();
  const location = useLocation();

  if (!isAdminAuthenticated) {
    return <Navigate to={ADMIN_LOGIN_PATH} replace state={{ from: location }} />;
  }

  return <Outlet />;
}
