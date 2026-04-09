"""
AI Trade Brain + Advisor Router
"""
from fastapi import APIRouter, Query
from pydantic import BaseModel
from services.trade_analyzer import trade_brain
from services.ai_advisor import ai_advisor

router = APIRouter(prefix="/api/analyzer", tags=["analyzer"])


class ForceConfigRequest(BaseModel):
    config: dict


# ── Brain (학습/진화) ─���

@router.get("/brain")
async def get_brain_status():
    """AI 두뇌 상태 - 학습 현황, 전략 점수, 인사이트, 진화 이력"""
    return trade_brain.get_status()


@router.get("/evolution")
async def get_evolution_log():
    """전체 진화 이력"""
    return trade_brain.get_evolution_log()


@router.get("/insights")
async def get_insights():
    """Claude AI가 축적한 인사이트"""
    return trade_brain.get_insights()


@router.post("/evolve")
async def force_evolve():
    """강제 진화 - Claude AI에게 즉시 분석 요청"""
    return trade_brain.force_evolve()


@router.post("/reset")
async def reset_brain():
    """AI 두뇌 초기화"""
    trade_brain.reset()
    return {"success": True, "message": "AI 두뇌 초기화 완료"}


# ── Advisor (실시간 매매 제어) ──

@router.get("/advisor")
async def get_advisor_status():
    """AI 어드바이저 상태 - 시장 모드, 포지션 오버라이드, 최근 판단"""
    return ai_advisor.get_status()


@router.get("/decisions")
async def get_decisions(limit: int = Query(50, ge=1, le=500)):
    """AI 판단 이력 (종목선정, 진입승인/거부, 홀딩판단, 시장분석)"""
    return ai_advisor.get_decisions(limit)


@router.post("/apply")
async def apply_manual_config(req: ForceConfigRequest):
    """수동 설정 변경"""
    result = trade_brain._apply_to_engine(req.config)
    return {"success": result, "applied": req.config}
