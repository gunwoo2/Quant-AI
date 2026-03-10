import React from 'react';
import Footer from './components/Footer'; // 푸터만 유지


export default function Layout({ children }) {
  return (
    <div style={{ 
      display: 'flex', 
      flexDirection: 'column', // 위(본문) 아래(푸터) 배치
      minHeight: '100vh', 
      backgroundColor: '#000000',
      width: '100%',
    }}>
      {/* 본문 영역: 본문이 짧아도 푸터를 바닥에 붙이기 위해 flex: 1 부여 */}
      <main style={{ 
        flex: 1,
        width: '100%',
        display: 'flex',
        flexDirection: 'column',
        boxSizing: 'border-box'
      }}>
        {children}
      </main>

      {/* 하단 푸터: 모든 페이지 하단에 고정 */}
      <Footer />
    </div>
  );
}


//#################### 이전 코드 #######################################
// import React, { useState } from 'react';
// import Sidebar from './components/Sidebar'; 
// import Header from './components/Header';   
// import Footer from './components/Footer';

// export default function Layout({ children }) {
//   const [isCollapsed, setIsCollapsed] = useState(false);
//   const sidebarWidth = isCollapsed ? '80px' : '260px';

//   return (
//     <div style={{ 
//       display: 'flex', 
//       minHeight: '100vh', 
//       backgroundColor: '#000',
//       width: '100%'
//     }}>
//       {/* 사이드바 고정 */}
//       <Sidebar isCollapsed={isCollapsed} setIsCollapsed={setIsCollapsed} />

//       {/* 메인 컨텐츠 영역 */}
//       <div style={{ 
//         flex: 1, 
//         marginLeft: sidebarWidth, 
//         transition: 'margin-left 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
//         display: 'flex',
//         flexDirection: 'column',
//         minWidth: 0 // 컨텐츠 넘침 방지
//       }}>
//         <Header />
        
//         {/* 본문: flex: 1을 주어 푸터를 아래로 밀어냄 */}
//         <main style={{ 
//           padding: '40px 40px 80px 40px', // 아래쪽 여백(80px)을 충분히 주어 푸터와 분리
//           color: '#fff', 
//           flex: 1,
//           width: '100%',
//           boxSizing: 'border-box'
//         }}>
//           {children}
//         </main>

//         {/* 하단 전문 푸터 */}
//         <Footer />
//       </div>
//     </div>
//   );
// }