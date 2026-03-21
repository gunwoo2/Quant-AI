import axios from 'axios';

/**
 * api.js — QUANT AI API Client v2
 *
 * 환경별 자동 분기:
 *   - 로컬 개발:  VITE_API_URL 환경변수 또는 localhost:8000
 *   - VM 배포:    같은 호스트의 :8000 (프론트 :3000, 백엔드 :8000)
 *   - 프로덕션:   VITE_API_URL 환경변수
 */

const getBaseURL = () => {
  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL;
  }
  const { hostname, protocol } = window.location;
  if (hostname !== 'localhost' && hostname !== '127.0.0.1') {
    return `${protocol}//${hostname}:8000`;
  }
  return 'http://localhost:8000';
};

const BASE_URL = getBaseURL();

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.code === 'ECONNABORTED') {
      console.error('⏰ API timeout:', err.config?.url);
    } else if (!err.response) {
      console.error('🔌 Network error — check backend:', BASE_URL);
    }
    return Promise.reject(err);
  }
);

console.log('📍 QUANT AI API:', BASE_URL);

export default api;
