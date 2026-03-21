"""
patch_numpy_adapter.py — NumPy 타입 psycopg2 자동 변환 패치
=============================================================
이 파일을 import하면 psycopg2가 np.float64, np.int64 등을
자동으로 Python 네이티브 타입으로 변환합니다.

사용법:
  db_pool.py 또는 main.py에서:
    import patch_numpy_adapter   # 한 줄이면 끝!
    
  또는 batch_ticker_item_daily.py 상단에:
    import patch_numpy_adapter
"""
import numpy as np

try:
    import psycopg2
    from psycopg2.extensions import register_adapter, AsIs

    # np.float64 → Python float
    def adapt_numpy_float(val):
        return AsIs(float(val))

    # np.int64 → Python int
    def adapt_numpy_int(val):
        return AsIs(int(val))

    # np.bool_ → Python bool
    def adapt_numpy_bool(val):
        return AsIs(bool(val))

    # 등록
    register_adapter(np.float64, adapt_numpy_float)
    register_adapter(np.float32, adapt_numpy_float)
    register_adapter(np.float16, adapt_numpy_float)
    register_adapter(np.int64, adapt_numpy_int)
    register_adapter(np.int32, adapt_numpy_int)
    register_adapter(np.int16, adapt_numpy_int)
    register_adapter(np.int8, adapt_numpy_int)
    register_adapter(np.bool_, adapt_numpy_bool)
    
    # np.ndarray 단일 원소도 처리
    register_adapter(np.uint64, adapt_numpy_int)
    register_adapter(np.uint32, adapt_numpy_int)

    print("[PATCH] ✅ NumPy→psycopg2 자동 변환 등록 완료")

except ImportError:
    print("[PATCH] ⚠️ psycopg2 없음 — NumPy 어댑터 미등록")
except Exception as e:
    print(f"[PATCH] ⚠️ NumPy 어댑터 등록 실패: {e}")
