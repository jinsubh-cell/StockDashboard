"""
Trading Journal Router - 매매일지 API 엔드포인트
"""
from fastapi import APIRouter, Query
from datetime import datetime
from typing import Optional
from services.trade_journal import trade_journal

router = APIRouter(prefix="/api/journal", tags=["journal"])


@router.get("/dates")
async def list_dates():
    """매매일지가 존재하는 날짜 목록"""
    return trade_journal.list_journal_dates()


@router.get("/trades")
async def get_trades(date: Optional[str] = Query(None, description="YYYYMMDD 형식, 미지정시 오늘")):
    """특정 날짜의 매매 기록 조회"""
    if date:
        return trade_journal.get_date_trades(date)
    return trade_journal.get_today_trades()


@router.get("/signals")
async def get_signals(date: Optional[str] = Query(None, description="YYYYMMDD 형식, 미지정시 오늘")):
    """특정 날짜의 신호 기록 조회"""
    if date:
        return trade_journal.get_date_signals(date)
    return trade_journal.get_today_signals()


@router.get("/report")
async def get_report(date: Optional[str] = Query(None, description="YYYYMMDD 형식, 미지정시 오늘")):
    """일일 보고서 조회 (없으면 자동 생성)"""
    date_str = date or datetime.now().strftime("%Y%m%d")

    # 기존 보고서 확인
    report = trade_journal.get_date_report(date_str)
    if report:
        return {"date": date_str, "report": report, "generated": False}

    # 없으면 새로 생성
    if date:
        dt = datetime.strptime(date, "%Y%m%d")
    else:
        dt = datetime.now()

    report = trade_journal.generate_daily_report(dt)
    return {"date": date_str, "report": report, "generated": True}


@router.post("/report/generate")
async def generate_report(date: Optional[str] = Query(None, description="YYYYMMDD 형식, 미지정시 오늘")):
    """일일 보고서 강제 재생성"""
    if date:
        dt = datetime.strptime(date, "%Y%m%d")
    else:
        dt = datetime.now()

    report = trade_journal.generate_daily_report(dt)
    return {"date": (date or datetime.now().strftime("%Y%m%d")), "report": report, "generated": True}


@router.get("/summary")
async def get_summary(days: int = Query(7, ge=1, le=90, description="최근 N일")):
    """최근 N일간 요약 통계"""
    return trade_journal.get_multi_day_summary(days)


@router.get("/today")
async def get_today_summary():
    """오늘의 매매 요약 (대시보드용)"""
    trades = trade_journal.get_today_trades()
    signals = trade_journal.get_today_signals()

    total = len(trades)
    wins = len([t for t in trades if t.get("net_pnl", 0) > 0])
    total_pnl = sum(t.get("net_pnl", 0) for t in trades)
    total_commission = sum(t.get("commission", 0) for t in trades)

    return {
        "date": datetime.now().strftime("%Y%m%d"),
        "total_trades": total,
        "wins": wins,
        "losses": total - wins,
        "win_rate": (wins / total * 100) if total > 0 else 0,
        "total_pnl": total_pnl,
        "total_commission": total_commission,
        "total_signals": len(signals),
        "recent_trades": trades[-5:],  # 최근 5건
    }
