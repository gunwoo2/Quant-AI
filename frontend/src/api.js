import axios from 'axios';

// 1. 끝에 붙은 /api 를 과감하게 지웁니다.
// const LOCAL_API_URL = 'https://8080-cs-1007043672332-default.cs-asia-east1-duck.cloudshell.dev';
const LOCAL_API_URL = 'http://localhost:8080';
const PROD_API_URL = 'https://stock-api-759997754570.asia-northeast3.run.app';

const isLocal = window.location.hostname.includes('cloudshell.dev') || window.location.hostname === 'localhost';

// 2. 여기서 딱 한 번만 /api를 붙여줍니다.
const BASE_URL = `${isLocal ? LOCAL_API_URL : PROD_API_URL}`;

const api = axios.create({
  baseURL: BASE_URL,
  withCredentials: true 
});

// 콘솔에서 주소가 한 번만 찍히는지 확인용
console.log("📍 현재 설정된 BASE_URL:", BASE_URL);

export default api;