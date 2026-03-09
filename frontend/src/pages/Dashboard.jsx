import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
// axios 대신 설정된 api 인스턴스를 가져옵니다.
import api from '../api'; 

export default function Dashboard() {
  const { sectorId } = useParams();
  const [stocks, setStocks] = useState([]);

  useEffect(() => {
    const load = async () => {
      try {
        // api.js의 baseURL을 활용하여 경로를 단순화합니다.
        // query parameter(?sector=...)는 그대로 유지합니다.
        const res = await api.get(`/api/stocks?sector=${sectorId || 'all'}`);
        setStocks(res.data);
      } catch (e) {
        console.error("대시보드 데이터 로드 실패:", e);
        setStocks([]);
      }
    };
    load();
  }, [sectorId]);

  return (
    <div className="page-container">
      {/* 사용자 정의 색상 테마(--yolk) 사용 유지 */}
      <h2 style={{ marginBottom: '20px', color: 'var(--yolk)' }}>
        {sectorId ? sectorId.toUpperCase() : 'Watchlist'}
      </h2>
      <table className="sa-table">
        <thead>
          <tr>
            <th>SYMBOL</th>
            <th>PRICE</th>
            <th>DAY CHANGE</th>
            <th>QUANT SCORE</th>
            <th>RATING</th>
          </tr>
        </thead>
        <tbody>
          {stocks.map(s => (
            <tr key={s.ticker}>
              {/* 사용자 정의 색상 테마(--orange) 사용 유지 */}
              <td style={{ color: 'var(--orange)', fontWeight: 'bold' }}>{s.ticker}</td>
              <td>${s.price?.toLocaleString() || '0'}</td>
              <td className={s.change >= 0 ? 'up' : 'down'}>{s.change}%</td>
              <td><span className="score-tag">{s.score}</span></td>
              <td style={{ color: 'var(--golden)' }}>{s.signal}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}