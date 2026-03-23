import axios from 'axios';

/**
 * api.js — QUANT AI API Client v3
 *
 * 환경별 자동 분기:
 *   - Vercel 배포:  /api 프록시 (vercel.json rewrites)
 *   - VM 배포:      같은 호스트의 :8000
 *   - 로컬 개발:    VITE_API_URL 또는 localhost:8000
 */

const getBaseURL = () => {
  // 1. 환경변수 명시 지정 (최우선)
  if (import.meta.env.VITE_API_URL) {
    return import.meta.env.VITE_API_URL;
  }

  const { hostname, protocol } = window.location;

  // 2. Vercel 배포: .vercel.app 도메인이면 프록시 사용 (빈 문자열)
  if (hostname.includes('vercel.app')) {
    return '';
  }

  // 3. VM 배포: 같은 호스트 :8000
  if (hostname !== 'localhost' && hostname !== '127.0.0.1') {
    return `${protocol}//${hostname}:8000`;
  }

  // 4. 로컬 개발
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

console.log('📍 QUANT AI API:', BASE_URL || '(proxy)');

export default api;
