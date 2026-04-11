"""
AI Advisor - Claude AI 감독관 모드 (1일 1~2회 전략 리뷰)

아키텍처:
  [실시간 데이터] → [경량 룰 기반 엔진] → [주문 실행]
       ↑                                      ↓
  [Claude API: 1일 1~2회 전략 리뷰]       [거래 로그 축적]

핵심 판단은 룰 기반 엔진(if/else + 기술적 지표)이 담당하고,
Claude는 일간/주간 단위로 전략 성과를 리뷰하고 파라미터를 조정하는 "감독관" 역할.

안전 규칙 (절대 위반 불가):
- 계좌 잔고 이내에서만 거래
- 미수/신용거래 절대 금지
- 일일 손실한도 준수
"""
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parent.parent.parent / '.env'
if _env_path.exists():
    load_dotenv(_env_path)

logger = logging.getLogger(__name__)


class AIAdvisor:
    """Claude AI 감독관 - 일간/주간 전략 리뷰 및 파라미터 조정"""

    def __init__(self):
        self._client = None

        # 리뷰 상태
        self.last_review_time = None
        self.last_review_result = None
        self.review_history = self._load_review_history()

        # 리뷰 로그 파일
        self._log_file = Path(__file__).parent.parent.parent / "trading_journals" / "ai_reviews.json"

        logger.info(f"[AIAdvisor] 감독관 모드 초기화 | API 사용 가능: {self.available}")
        logger.info(f"[AIAdvisor] 과거 리뷰 {len(self.review_history)}건 로드")

    def _reset_client(self):
        """API 키 변경 시 클라이언트 리셋"""
        self._client = None

    @property
    def client(self):
        if self._client is None:
            if _env_path.exists():
                load_dotenv(_env_path, override=True)
            api_key = os.getenv("ANTHROPIC_API_KEY", "")
            if api_key:
                try:
                    import anthropic
                    self._client = anthropic.Anthropic(api_key=api_key)
                except ImportError:
                    logger.error("[AIAdvisor] pip install anthropic 필요")
        return self._client

    @property
    def available(self) -> bool:
        return self.client is not None

    # ════════════════════════════════════════════
    #  1. 일간 전략 리뷰 (하루 1~2회 수동/스케줄 호출)
    # ════════════════════════════════════════════

    def daily_strategy_review(self, trade_history: list, stats: dict,
                               brain_data: dict, current_config: dict) -> dict:
        """
        일간 전략 리뷰: 오늘 거래 성과를 분석하고 파라미터 조정안 제시

        Parameters:
            trade_history: 오늘의 거래 내역 리스트
            stats: 오늘의 통계 (wins, losses, total_net_pnl, total_trades 등)
            brain_data: trade_brain의 학습 데이터
            current_config: 현재 엔진 설정 (AutoScalpConfig.to_dict())

        Returns:
            {
                "review_type": "daily",
                "timestamp": "...",
                "performance_summary": "...",
                "parameter_changes": {...},
                "strategy_recommendations": [...],
                "risk_assessment": "...",
                "next_action": "..."
            }
        """
        if not self.available:
            return {"error": "Claude API 미사용", "parameter_changes": {}}

        try:
            # 거래 내역 요약 (최근 50건)
            recent_trades = trade_history[-50:] if trade_history else []
            trade_summary = []
            for t in recent_trades:
                entry = t if isinstance(t, dict) else t.__dict__
                trade_summary.append({
                    "strategy": entry.get("strategy", ""),
                    "net_pnl": entry.get("net_pnl", 0),
                    "pnl_pct": entry.get("pnl_pct", 0),
                    "hold_seconds": entry.get("hold_seconds", 0),
                    "exit_reason": entry.get("exit_reason", ""),
                })

            # 전략별 성과 집계
            strategy_perf = brain_data.get("strategy_scores", {})
            strategy_summary = {}
            for name, s in strategy_perf.items():
                tc = s.get("trade_count", 0)
                if tc == 0:
                    continue
                strategy_summary[name] = {
                    "거래수": tc,
                    "승률": round(s.get("wins", 0) / tc * 100, 1),
                    "총손익": round(s.get("total_pnl", 0)),
                    "평균보유": round(s.get("hold_sum", 0) / tc, 1),
                    "최근5건": s.get("recent_pnls", [])[-5:],
                }

            # 시간대별 성과
            time_scores = brain_data.get("time_scores", {})

            # 청산사유별 패턴
            exit_patterns = brain_data.get("exit_patterns", {})

            # 과거 AI 리뷰 인사이트 (최근 3건)
            past_insights = [r.get("performance_summary", "") for r in self.review_history[-3:]]

            prompt = f"""당신은 한국 주식(KRX) 초단타 스캘핑 전략의 감독관 AI입니다.
1일 1~2회 호출되어 전략 성과를 리뷰하고 파라미터를 조정합니다.

## 오늘 거래 통계
- 총 거래: {stats.get('total_trades', 0)}회
- 승: {stats.get('wins', 0)} / 패: {stats.get('losses', 0)}
- 순손익: {stats.get('total_net_pnl', 0):+,.0f}원
- 수수료 합계: {stats.get('total_commission', 0):,.0f}원

## 전략별 누적 성과
{json.dumps(strategy_summary, ensure_ascii=False, indent=2)}

## 시간대별 성과
{json.dumps(time_scores, ensure_ascii=False)}

## 청산사유 패턴
{json.dumps(exit_patterns, ensure_ascii=False)}

## 최근 거래 내역 (최대 50건)
{json.dumps(trade_summary, ensure_ascii=False)}

## 현재 엔진 설정
{json.dumps(current_config, ensure_ascii=False, indent=2)}

## 과거 리뷰 인사이트
{json.dumps(past_insights, ensure_ascii=False)}

## 요청
오늘의 전략 성과를 종합 분석하고, 내일 적용할 파라미터 조정안을 제시하세요.

반드시 아래 JSON 형식으로만 답하세요:
```json
{{
  "performance_summary": "오늘 성과 요약 (2~3문장)",
  "parameter_changes": {{
    "파라미터명": 값,
    ...
  }},
  "strategy_recommendations": [
    "전략 조정 권고 1",
    "전략 조정 권고 2"
  ],
  "risk_assessment": "리스크 평가 (1문장)",
  "next_action": "내일 핵심 실행 사항 (1문장)"
}}
```

파라미터 조정 규칙:
- stop_loss_pct: 0.2 ~ 2.0 (왕복수수료 0.21% 고려)
- take_profit_pct: 0.3 ~ 5.0
- trailing_stop_pct: 0.15 ~ 2.0
- max_investment_per_trade: 100,000 ~ 2,000,000
- max_position_count: 1 ~ 5
- min_consensus: 1 ~ 4
- max_hold_seconds: 30 ~ 600
- max_daily_loss: 10,000 ~ 200,000
- max_daily_trades: 10 ~ 200
- tick_momentum_threshold: 0.5 ~ 0.9
- vwap_entry_deviation: 0.1 ~ 1.0
- imbalance_threshold: 1.5 ~ 5.0
- bb_std: 1.5 ~ 3.0
- rsi_oversold: 15 ~ 35
- rsi_overbought: 65 ~ 85
- volume_spike_mult: 2.0 ~ 5.0
- scan_interval_seconds: 30 ~ 300
- 승률이 30% 미만인 전략은 비활성화 권고 (use_xxx: false)
- 변경이 필요 없으면 빈 객체 {{}}
"""

            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}],
            )
            result = self._parse_json(response.content[0].text)

            review = {
                "review_type": "daily",
                "timestamp": datetime.now().isoformat(),
                "performance_summary": result.get("performance_summary", ""),
                "parameter_changes": self._validate_params(result.get("parameter_changes", {})),
                "strategy_recommendations": result.get("strategy_recommendations", []),
                "risk_assessment": result.get("risk_assessment", ""),
                "next_action": result.get("next_action", ""),
                "stats_snapshot": {
                    "trades": stats.get("total_trades", 0),
                    "wins": stats.get("wins", 0),
                    "losses": stats.get("losses", 0),
                    "net_pnl": stats.get("total_net_pnl", 0),
                },
            }

            self.last_review_time = time.time()
            self.last_review_result = review
            self._save_review(review)

            logger.info(f"[AIAdvisor] 일간 리뷰 완료: {review['performance_summary']}")
            logger.info(f"[AIAdvisor] 파라미터 조정: {review['parameter_changes']}")
            return review

        except Exception as e:
            logger.error(f"[AIAdvisor] 일간 리뷰 실패: {e}")
            return {"error": str(e), "parameter_changes": {}}

    # ════════════════════════════════════════════
    #  2. 주간 심층 리뷰
    # ════════════════════════════════════════════

    def weekly_deep_review(self, brain_data: dict, current_config: dict,
                           weekly_trades: list) -> dict:
        """
        주간 심층 리뷰: 일주일 전략 트렌드 분석 및 근본적 전략 재설계 검토

        Parameters:
            brain_data: trade_brain의 전체 학습 데이터
            current_config: 현재 엔진 설정
            weekly_trades: 이번 주 전체 거래 내역

        Returns:
            리뷰 결과 dict
        """
        if not self.available:
            return {"error": "Claude API 미사용", "parameter_changes": {}}

        try:
            strategy_scores = brain_data.get("strategy_scores", {})
            time_scores = brain_data.get("time_scores", {})
            price_brackets = brain_data.get("price_bracket_scores", {})
            ai_insights = brain_data.get("ai_insights", [])
            evolution_log = brain_data.get("evolution_log", [])

            # 일주일 거래 집계
            weekly_pnl = sum(
                (t.get("net_pnl", 0) if isinstance(t, dict) else getattr(t, "net_pnl", 0))
                for t in weekly_trades
            )
            weekly_count = len(weekly_trades)

            # 일별 리뷰 히스토리 (이번 주)
            recent_reviews = self.review_history[-7:]

            prompt = f"""당신은 한국 주식(KRX) 초단타 스캘핑 전략의 주간 감독관 AI입니다.
일주일치 데이터를 기반으로 전략의 근본적인 방향을 리뷰합니다.

## 주간 실적
- 총 거래: {weekly_count}회
- 주간 순손익: {weekly_pnl:+,.0f}원

## 전략별 누적 성과
{json.dumps(strategy_scores, ensure_ascii=False, indent=2)}

## 시간대별 성과
{json.dumps(time_scores, ensure_ascii=False)}

## 가격대별 성과
{json.dumps(price_brackets, ensure_ascii=False)}

## 과거 AI 인사이트
{json.dumps(ai_insights[-5:], ensure_ascii=False)}

## 이번 주 일간 리뷰 요약
{json.dumps([r.get("performance_summary", "") for r in recent_reviews], ensure_ascii=False)}

## 현재 엔진 설정
{json.dumps(current_config, ensure_ascii=False, indent=2)}

## 진화 이력
{json.dumps(evolution_log[-5:], ensure_ascii=False)}

## 요청
일주일 전략 성과를 심층 분석하고, 근본적인 전략 재설계 방향을 제시하세요.

반드시 아래 JSON 형식으로만 답하세요:
```json
{{
  "weekly_summary": "주간 성과 총평 (3~5문장)",
  "parameter_changes": {{
    "파라미터명": 값,
    ...
  }},
  "strategy_overhaul": [
    "전략 구조 변경 권고 1",
    "전략 구조 변경 권고 2"
  ],
  "best_performing": "가장 성과 좋은 전략/시간대/가격대",
  "worst_performing": "가장 성과 나쁜 전략/시간대/가격대",
  "insight": "이번 주에서 배운 핵심 인사이트 (1문장, 영구 기록용)"
}}
```
"""

            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}],
            )
            result = self._parse_json(response.content[0].text)

            review = {
                "review_type": "weekly",
                "timestamp": datetime.now().isoformat(),
                "weekly_summary": result.get("weekly_summary", ""),
                "parameter_changes": self._validate_params(result.get("parameter_changes", {})),
                "strategy_overhaul": result.get("strategy_overhaul", []),
                "best_performing": result.get("best_performing", ""),
                "worst_performing": result.get("worst_performing", ""),
                "insight": result.get("insight", ""),
                "stats_snapshot": {
                    "weekly_trades": weekly_count,
                    "weekly_pnl": weekly_pnl,
                },
            }

            self.last_review_time = time.time()
            self.last_review_result = review
            self._save_review(review)

            logger.info(f"[AIAdvisor] 주간 심층 리뷰 완료: {review['weekly_summary'][:100]}")
            return review

        except Exception as e:
            logger.error(f"[AIAdvisor] 주간 리뷰 실패: {e}")
            return {"error": str(e), "parameter_changes": {}}

    # ════════════════════════════════════════════
    #  3. 파라미터 자동 적용
    # ════════════════════════════════════════════

    def apply_review_changes(self, parameter_changes: dict) -> dict:
        """
        리뷰 결과의 파라미터 변경을 엔진에 적용

        Returns:
            {"applied": {...}, "rejected": {...}, "reason": "..."}
        """
        if not parameter_changes:
            return {"applied": {}, "rejected": {}, "reason": "변경 사항 없음"}

        validated = self._validate_params(parameter_changes)
        rejected = {k: v for k, v in parameter_changes.items() if k not in validated}

        if validated:
            try:
                from services.auto_scalper import auto_scalper
                auto_scalper.update_config(validated)
                logger.info(f"[AIAdvisor] 리뷰 결과 적용: {validated}")
            except Exception as e:
                logger.error(f"[AIAdvisor] 적용 실패: {e}")
                return {"applied": {}, "rejected": parameter_changes, "reason": str(e)}

        return {
            "applied": validated,
            "rejected": rejected,
            "reason": f"{len(validated)}개 적용, {len(rejected)}개 거부" if rejected else "전체 적용",
        }

    # ════════════════════════════════════════════
    #  4. AI 프리셋 최적화
    # ════════════════════════════════════════════

    def optimize_preset(self, preset_name: str) -> dict:
        """
        특정 프리셋의 파라미터를 AI가 분석하여 최적화된 새 버전 생성

        Returns:
            {"success": bool, "new_preset_name": str, "changes": dict, "reason": str}
        """
        if not self.available:
            return {"success": False, "reason": "Claude API 미사용"}

        try:
            from services.skill_preset import preset_manager, SkillPreset
            preset = preset_manager.load_preset(preset_name)
            if not preset:
                return {"success": False, "reason": f"프리셋 '{preset_name}'을 찾을 수 없음"}

            perf = preset.performance
            from services.trade_analyzer import trade_brain
            brain_data = trade_brain.brain if trade_brain else {}

            prompt = f"""당신은 한국 주식(KRX) 초단타 스캘핑 프리셋 최적화 AI입니다.

## 최적화 대상 프리셋
- 이름: {preset.display_name} ({preset.name})
- 설명: {preset.description}
- 버전: v{preset.version}

## 현재 전략 조합
{json.dumps(preset.strategies, ensure_ascii=False, indent=2)}

## 리스크 설정
{json.dumps(preset.risk, ensure_ascii=False, indent=2)}

## 주문 설정
{json.dumps(preset.order, ensure_ascii=False, indent=2)}

## 종목 필터
{json.dumps(preset.stock_filter, ensure_ascii=False, indent=2)}

## 성과 데이터
- 총 거래: {perf.get('total_trades', 0)}회
- 승률: {perf.get('win_rate', 0)}%
- 최근 20건 승률: {perf.get('recent_win_rate', 0)}%
- 순손익: {perf.get('total_net_pnl', 0):+,.0f}원
- 최근 20건 손익: {json.dumps(perf.get('recent_20_trades', []))}

## 전략별 누적 성과 (Brain 데이터)
{json.dumps(brain_data.get('strategy_scores', {}), ensure_ascii=False, indent=2)}

## 시간대별 성과
{json.dumps(brain_data.get('time_scores', {}), ensure_ascii=False)}

## 요청
이 프리셋의 파라미터를 최적화하세요.
성과가 나쁜 전략은 비활성화하고, 좋은 전략은 가중치를 높이세요.
리스크/주문 설정도 성과에 맞게 조정하세요.

반드시 아래 JSON 형식으로만 답하세요:
```json
{{
  "strategies": {{
    "전략명": {{"enabled": bool, "weight": float, "params": {{...}}}},
    ...
  }},
  "risk": {{"설정키": 값, ...}},
  "order": {{"설정키": 값, ...}},
  "stock_filter": {{"설정키": 값, ...}},
  "reason": "최적화 사유 요약"
}}
```

규칙:
- 최소 2개 전략은 활성화 유지
- stop_loss_pct: 0.2~2.0, take_profit_pct: 0.3~5.0
- weight: 0.5~2.0
- min_consensus: 1~4
- 데이터 부족한 전략(5건 미만)은 변경하지 마세요
"""

            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1500,
                messages=[{"role": "user", "content": prompt}],
            )
            result = self._parse_json(response.content[0].text)

            if not result:
                return {"success": False, "reason": "AI 응답 파싱 실패"}

            # 새 프리셋 버전 생성
            new_version = preset.version + 1
            new_preset = SkillPreset(
                name=f"{preset_name}_v{new_version}",
                display_name=f"{preset.display_name} v{new_version}",
                description=f"AI 최적화 ({result.get('reason', '')})",
                version=new_version,
                created_by="ai",
                strategies=result.get("strategies", preset.strategies),
                risk=result.get("risk", preset.risk),
                order=result.get("order", preset.order),
                stock_filter=result.get("stock_filter", preset.stock_filter),
            )

            preset_manager.save_preset(new_preset)

            self._save_review({
                "review_type": "preset_optimize",
                "timestamp": datetime.now().isoformat(),
                "preset_name": preset_name,
                "new_preset_name": new_preset.name,
                "reason": result.get("reason", ""),
            })

            logger.info(f"[AIAdvisor] 프리셋 최적화 완료: {preset_name} → {new_preset.name}")
            return {
                "success": True,
                "new_preset_name": new_preset.name,
                "changes": result,
                "reason": result.get("reason", ""),
            }

        except Exception as e:
            logger.error(f"[AIAdvisor] 프리셋 최적화 실패: {e}")
            return {"success": False, "reason": str(e)}

    # ════════════════════════════════════════════
    #  파라미터 검증
    # ════════════════════════════════════════════

    _PARAM_RULES = {
        "stop_loss_pct": (0.2, 2.0, float),
        "take_profit_pct": (0.3, 5.0, float),
        "trailing_stop_pct": (0.15, 2.0, float),
        "max_investment_per_trade": (100_000, 2_000_000, int),
        "max_position_count": (1, 5, int),
        "min_consensus": (1, 4, int),
        "max_hold_seconds": (30, 600, float),
        "max_daily_loss": (10_000, 200_000, float),
        "max_daily_trades": (10, 200, int),
        "tick_momentum_threshold": (0.5, 0.9, float),
        "vwap_entry_deviation": (0.1, 1.0, float),
        "imbalance_threshold": (1.5, 5.0, float),
        "bb_std": (1.5, 3.0, float),
        "bb_window": (15, 60, int),
        "rsi_period": (5, 20, int),
        "rsi_oversold": (15.0, 35.0, float),
        "rsi_overbought": (65.0, 85.0, float),
        "volume_spike_mult": (2.0, 5.0, float),
        "scan_interval_seconds": (30, 300, float),
        "tick_window": (10, 50, int),
        "vwap_window": (30, 120, int),
        "cooldown_seconds": (0.5, 10, float),
        "rotation_interval_seconds": (120, 1800, float),
        # 전략 on/off 토글
        "use_tick_momentum": (None, None, bool),
        "use_vwap_deviation": (None, None, bool),
        "use_orderbook_imbalance": (None, None, bool),
        "use_bollinger_scalp": (None, None, bool),
        "use_rsi_extreme": (None, None, bool),
        "use_volume_spike": (None, None, bool),
        "use_trailing_stop": (None, None, bool),
    }

    def _validate_params(self, changes: dict) -> dict:
        """안전 규칙을 강제하여 허용 범위 내 값만 반환"""
        safe = {}
        for k, v in changes.items():
            rule = self._PARAM_RULES.get(k)
            if not rule:
                continue
            lo, hi, typ = rule
            try:
                v = typ(v)
                if typ == bool:
                    safe[k] = v
                else:
                    safe[k] = max(lo, min(hi, v))
            except (ValueError, TypeError):
                continue
        return safe

    # ════════════════════════════════════════════
    #  리뷰 히스토리 관리
    # ════════════════════════════════════════════

    def _load_review_history(self) -> list:
        log_file = Path(__file__).parent.parent.parent / "trading_journals" / "ai_reviews.json"
        if log_file.exists():
            try:
                return json.loads(log_file.read_text(encoding="utf-8"))
            except Exception:
                return []
        return []

    def _save_review(self, review: dict):
        self.review_history.append(review)
        # 최근 100건만 보관
        if len(self.review_history) > 100:
            self.review_history = self.review_history[-100:]
        try:
            self._log_file.parent.mkdir(parents=True, exist_ok=True)
            self._log_file.write_text(
                json.dumps(self.review_history, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception:
            pass

    # ════════════════════════════════════════════
    #  유틸리티
    # ════════════════════════════════════════════

    def _parse_json(self, text: str) -> dict:
        import re
        blocks = re.findall(r'```json\s*(\{[^`]+\})\s*```', text, re.DOTALL)
        for block in blocks:
            try:
                return json.loads(block)
            except json.JSONDecodeError:
                continue
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            return json.loads(text[start:end])
        except (ValueError, json.JSONDecodeError):
            return {}

    def get_status(self) -> dict:
        return {
            "available": self.available,
            "mode": "supervisor",
            "last_review_time": self.last_review_time,
            "last_review_result": self.last_review_result,
            "total_reviews": len(self.review_history),
            "recent_reviews": self.review_history[-5:],
        }

    def get_reviews(self, limit: int = 20) -> list:
        return self.review_history[-limit:]


# 싱글톤
ai_advisor = AIAdvisor()
