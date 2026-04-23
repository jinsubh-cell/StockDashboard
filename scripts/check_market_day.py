"""
한국 주식시장 개장일 확인
- 주말 (토/일) 제외
- 2026년 한국 공휴일 하드코딩 (간단 버전)
- 개장일이면 exit 0, 휴장일이면 exit 1
"""
import sys
from datetime import date

# 2026년 한국 주식시장 휴장일 (공휴일 + 임시공휴일)
# 출처: 한국거래소 2026년 휴장일 일정
HOLIDAYS_2026 = {
    # 1월
    date(2026, 1, 1),   # 신정
    date(2026, 2, 16),  # 설날 (2/17이 화)
    date(2026, 2, 17),  # 설날
    date(2026, 2, 18),  # 설날
    # 3월
    date(2026, 3, 1),   # 삼일절 (일) - 대체없음
    date(2026, 3, 2),   # 대체공휴일 (월) - 삼일절 대체
    # 5월
    date(2026, 5, 1),   # 근로자의 날
    date(2026, 5, 5),   # 어린이날
    date(2026, 5, 25),  # 부처님오신날
    # 6월
    date(2026, 6, 3),   # 대선일 (추정)
    date(2026, 6, 6),   # 현충일 (토)
    # 8월
    date(2026, 8, 15),  # 광복절 (토)
    date(2026, 8, 17),  # 대체공휴일 (월)
    # 9월
    date(2026, 9, 24),  # 추석
    date(2026, 9, 25),  # 추석
    date(2026, 9, 26),  # 추석 (토) - 대체없음 관행
    # 10월
    date(2026, 10, 3),  # 개천절 (토)
    date(2026, 10, 5),  # 대체공휴일 (월)
    date(2026, 10, 9),  # 한글날
    # 12월
    date(2026, 12, 25), # 크리스마스
    date(2026, 12, 31), # 연말 휴장
}


def is_market_day(today: date) -> bool:
    """오늘이 장 개장일인지"""
    # 주말 제외
    if today.weekday() >= 5:  # 5=토, 6=일
        return False
    # 공휴일 제외
    if today in HOLIDAYS_2026:
        return False
    return True


if __name__ == "__main__":
    today = date.today()
    if is_market_day(today):
        print(f"{today} - 장 개장일 (요일: {['월','화','수','목','금','토','일'][today.weekday()]})")
        sys.exit(0)
    else:
        reason = "주말" if today.weekday() >= 5 else "공휴일"
        print(f"{today} - 휴장일 ({reason})")
        sys.exit(1)
