import axios from 'axios';
import { ADMIN_API_PATH, ADMIN_LOGIN_PATH } from '../config/adminPaths';

const adminApi = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 60000,
});

adminApi.interceptors.request.use((config) => {
  const token = localStorage.getItem('admin_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  if (typeof config.url === 'string' && config.url.startsWith('/admin')) {
    config.url = `${ADMIN_API_PATH}${config.url.slice('/admin'.length)}`;
  }
  return config;
});

adminApi.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.code === 'ECONNABORTED') {
      return Promise.reject(new Error('The server took too long to respond. Please try again.'));
    }

    if ([401, 403].includes(error.response?.status)) {
      localStorage.removeItem('admin_token');
      localStorage.removeItem('admin_user');
      if (window.location.pathname !== ADMIN_LOGIN_PATH) {
        window.location.assign(ADMIN_LOGIN_PATH);
      }
    }
    return Promise.reject(error);
  },
);

export default adminApi;
