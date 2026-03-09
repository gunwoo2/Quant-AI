// import { defineConfig } from 'vite'
// import react from '@vitejs/plugin-react'

// // https://vite.dev/config/
// export default defineConfig({
//   plugins: [react()],
// })

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // 프론트에서 /api로 시작하는 요청을 보내면 8080 포트(백엔드)로 전달합니다.
      '/api': {
        target: 'http://localhost:8080',
        changeOrigin: true,
        secure: false,
        // 필요하다면 경로 재작성 (현재 구조에서는 그대로 두시면 됩니다)
        // rewrite: (path) => path.replace(/^\/api/, '/api'),
      },
    },
  },
})