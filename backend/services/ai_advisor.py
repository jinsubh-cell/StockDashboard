"""
AI Advisor - Claude AI가 스캘핑 매매 전체를 실시간 제어

개입 지점:
1. 종목 탐색: AI가 종목 후보를 검토하고 순위 재조정
2. 진입 판단: 컨센서스 시그널 발생 시 AI가 진입 승인/거부
3. 포지션 관리: 익절/손절 기준을 포지션별로 동적 조정
4. 시장 분석: 주기적으로 시장 상황 판단, 공격/방어 모드 전환

안전 규칙 (절대 위반 불가):
- 계좌 잔고 이내에서만 거래
- ���수/신용거래 절대 금지
- 일일 손실한도 준수
"""
import json
import logging
import os
import time
import asyncio
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parent.parent.parent / '.env'
if _env_path.exists():
    load_dotenv(_env_path)

logger = logging.getLogger(__name__)


# AI 판�� 결과 캐시 (같은 종목에 대�� 짧은 시간 내 중복 호출 방지)
class _Cache:
    def __init__(self, ttl=5):
        self._data = {}
        self._ttl = ttl

    def get(self, key):
        entry = self._data.get(key)
        if entry and time.time() - entry["time"] < self._ttl:
            return entry["value"]
        return None

    def set(self, key, value):
        self._data[key] = {"value": value, "time": time.time()}

    def clear(self):
        self._data.clear()


class AIAdvisor:
    """Claude AI 실시간 매매 어드바이저"""

    def __init__(self):
        self._client = None
        self._cache = _Cache(ttl=10)  # 10초 캐시

        # 시장 판단 상태
        self.market_mode = "normal"  # normal / aggressive / defensive
        self.last_market_analysis = None
        self.market_analysis_interval = 300  # 5분마다 시장 분석

        # 포지션별 AI 조정값
        self.position_overrides = {}
        # {code: {"take_profit_pct": 2.0, "stop_loss_pct": 0.3, "reason": "..."}}

        # AI ���단 로그
        self._log_file = Path(__file__).parent.parent.parent / "trading_journals" / "ai_decisions.json"
        self._decisions = self._load_decisions()

        logger.info(f"[AIAdvisor] 초기화 | API 사용 가능: {self.available}")

    @property
    def client(self):
        if self._client is None:
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
    #  1. 종목 탐색 개입
    # ════════════════════════════════════════════

    def evaluate_stock_candidates(self, candidates: list, brain_data: dict) -> list:
        """
        종목 후보 리스트를 AI가 검토하여 재순위화

        Parameters:
            candidates: [(code, score, name), ...]
            brain_data: trade_brain의 학습 데이터

        Returns:
            재순위화된 candidates 리스트
        """
        if not self.available or not candidates:
            return candidates

        cache_key = f"scan_{','.join(c[0] for c in candidates[:5])}"
        cached = self._cache.get(cache_key)
        if cached:
            return cached

        try:
            # brain에서 종목별 과거 성과 추출
            price_scores = brain_data.get("price_bracket_scores", {})
            strategy_scores = brain_data.get("strategy_scores", {})

            prompt = f"""당신은 한국 주식 초단타 스캘핑 종목 선정 AI��니다.

## 종목 후보 (스캔 결과)
{json.dumps([(c[0], c[2], round(c[1], 1)) for c in candidates[:10]], ensure_ascii=False)}
형식: [코드, 종목명, 기존점수]

## 과거 가격대별 성과
{json.dumps(price_scores, ensure_ascii=False)}

## 전략별 최근 성과
{json.dumps({{k: {{"승률": round(v["wins"]/v["trade_count"]*100 if v["trade_count"]>0 else 0, 1), "거래수": v["trade_count"]}} for k, v in strategy_scores.items()}}, ensure_ascii=False)}

## 현재 시장 모드: {self.market_mode}

## 요청
상위 5개 종목을 선정하세요. 반드시 아래 JSON만 답하세요:
```json
{{"selected": ["코드1", "코드2", ...], "reason": "선정 이유"}}
```

규칙:
- 후보 목록에 있는 코드만 선택
- 과거 성과에서 해당 가격대가 불리하면 제외
- defensive 모드면 변동성 낮은 종목 우선
- aggressive 모드면 거래량 많고 추세 강한 종목 우선
"""
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
            result = self._parse_json(response.content[0].text)

            if "selected" in result:
                selected_codes = result["selected"]
                # 원래 candidates에서 AI가 선택한 순서로 재배열
                code_map = {c[0]: c for c in candidates}
                reordered = []
                for code in selected_codes:
                    if code in code_map:
                        reordered.append(code_map[code])
                # 나머지 추가
                for c in candidates:
                    if c[0] not in selected_codes:
                        reordered.append(c)

                self._log_decision("stock_scan", {
                    "original": [c[0] for c in candidates[:5]],
                    "ai_selected": selected_codes,
                    "reason": result.get("reason", ""),
                })
                self._cache.set(cache_key, reordered)
                logger.info(f"[AIAdvisor] 종목 선정: {selected_codes} ({result.get('reason', '')})")
                return reordered

        except Exception as e:
            logger.error(f"[AIAdvisor] 종목 평가 실패: {e}")

        return candidates

    # ════════════════════════════════��═══════════
    #  2. 진입 판단 개입
    # ════════════════════════════════════════════

    def should_enter(self, code: str, consensus: dict, tick_data: dict,
                     current_positions: dict, brain_data: dict) -> dict:
        """
        컨센서스 시그널 발생 시 AI가 진입 승인/거부/조건 수정

        Returns:
            {"approve": True/False, "adjust": {설정 조정}, "reason": "사유"}
        """
        if not self.available:
            return {"approve": True, "adjust": {}, "reason": "AI 미사용"}

        cache_key = f"entry_{code}_{consensus.get('side', '')}"
        cached = self._cache.get(cache_key)
        if cached:
            return cached

        try:
            strategy_perf = brain_data.get("strategy_scores", {}).get(
                consensus.get("strategy", ""), {})

            prompt = f"""당신은 초단타 스캘핑 진입 판단 AI입니다.

## 진입 시그널
- 종목: {code}
- 방향: {consensus.get('side', '')}
- 전략: {consensus.get('strategy', '')}
- 사유: {consensus.get('reason', '')}

## 현재 틱 데이터
- 현재가: {tick_data.get('price', 0):,}원
- 매수호가: {tick_data.get('bid', 0):,} (잔량 {tick_data.get('bid_qty', 0):,})
- 매도호가: {tick_data.get('ask', 0):,} (잔량 {tick_data.get('ask_qty', 0):,})

## 이 전략의 과거 성과
- 거래수: {strategy_perf.get('trade_count', 0)}
- 승률: {round(strategy_perf.get('wins', 0) / max(strategy_perf.get('trade_count', 1), 1) * 100, 1)}%
- 최근10건 손익합: {sum(strategy_perf.get('recent_pnls', [])[-10:]):+,.0f}원

## 현재 보유 포지션: {len(current_positions)}개
## 시장 모드: {self.market_mode}

## 안전 규칙 (절대 위반 불가)
- 미수거래 불가
- 신용거래 불가
- 계좌 잔고 이내에서만 거래

반드시 아래 JSON만 답하세요:
```json
{{
  "approve": true 또는 false,
  "adjust": {{
    "take_profit_pct": 숫자 (선택, 이 거래에만 적용할 익절률),
    "stop_loss_pct": 숫자 (선택, 이 거래에만 적용할 손절률),
    "max_hold_seconds": 숫자 (선택)
  }},
  "reason": "판단 이유"
}}
```

판단 기준:
- 전략 과거 성��가 나쁘면 거부
- defensive 모드면 기준을 엄격하게
- 호가 스프레드가 넓으면 거부
- 승인 시 상황에 따라 익절/손절 조정 가능 (수익 끌고갈 수 있으면 익절률 높임)
"""
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}],
            )
            result = self._parse_json(response.content[0].text)

            decision = {
                "approve": result.get("approve", True),
                "adjust": result.get("adjust", {}),
                "reason": result.get("reason", ""),
            }

            # 포지션별 오버라이드 저장
            if decision["approve"] and decision["adjust"]:
                self.position_overrides[code] = {
                    **decision["adjust"],
                    "reason": decision["reason"],
                    "set_at": datetime.now().isoformat(),
                }

            self._log_decision("entry", {
                "code": code,
                "side": consensus.get("side", ""),
                "strategy": consensus.get("strategy", ""),
                **decision,
            })
            self._cache.set(cache_key, decision)

            action = "승인" if decision["approve"] else "거부"
            logger.info(f"[AIAdvisor] 진입 {action}: {code} {consensus.get('side', '')} - {decision['reason']}")
            return decision

        except Exception as e:
            logger.error(f"[AIAdvisor] 진입 판단 실패: {e}")
            return {"approve": True, "adjust": {}, "reason": f"AI 오류 (기본 승인): {e}"}

    # ════════════════════════════════════════════
    #  3. 포지션 관리 - 동적 익절/손절 조정
    # ════════════════════════════════════════════

    def get_position_override(self, code: str) -> dict:
        """포지션별 AI 조정값 반환"""
        return self.position_overrides.get(code, {})

    def should_hold_longer(self, code: str, pos_data: dict, tick_data: dict) -> dict:
        """
        익절 시점에 도달했을 때 AI가 더 홀딩할지 판단

        Returns:
            {"hold": True/False, "new_take_profit_pct": float, "reason": str}
        """
        if not self.available:
            return {"hold": False, "reason": "AI 미사용"}

        cache_key = f"hold_{code}_{int(time.time() / 5)}"  # 5초 캐시
        cached = self._cache.get(cache_key)
        if cached:
            return cached

        try:
            prompt = f"""당신은 초단타 스캘핑 포지션 관리 AI입니다.

## 현재 포지션
- 종목: {code}
- 방향: {pos_data.get('side', '')}
- 진입가: {pos_data.get('entry_price', 0):,}원
- 현재가: {tick_data.get('price', 0):,}원
- 현재 수익률: {pos_data.get('pnl_pct', 0):+.2f}%
- 보유 시간: {pos_data.get('hold_seconds', 0):.0f}초
- 고점 이후 하락: {pos_data.get('drawdown_from_high', 0):.2f}%

## 호가 상황
- 매수잔량: {tick_data.get('bid_qty', 0):,}
- 매도잔량: {tick_data.get('ask_qty', 0):,}

## 시장 모드: {self.market_mode}

수익을 더 끌고 갈 수 있는 상황인지 판단하세요.
반드시 아래 JSON만 답하세요:
```json
{{
  "hold": true 또는 false,
  "new_take_profit_pct": 숫자 (���딩 시 새 익절률, 예: 2.5),
  "new_trailing_stop_pct": 숫자 (선택, 트레일링 조정),
  "reason": "판단 이유"
}}
```

판단 기준:
- 매수잔량이 매도잔량보다 많으면 → 상승 여력, 홀딩
- 보유시간이 이미 길면 → 정리
- 고점에서 하락 추세면 → 정리
- 수익이 충분하면 → 트레일링 스탑 좁���서 수익 보전하며 홀딩
"""
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            result = self._parse_json(response.content[0].text)

            decision = {
                "hold": result.get("hold", False),
                "new_take_profit_pct": result.get("new_take_profit_pct"),
                "new_trailing_stop_pct": result.get("new_trailing_stop_pct"),
                "reason": result.get("reason", ""),
            }

            # 오버라이드 업데이트
            if decision["hold"]:
                override = self.position_overrides.get(code, {})
                if decision.get("new_take_profit_pct"):
                    override["take_profit_pct"] = decision["new_take_profit_pct"]
                if decision.get("new_trailing_stop_pct"):
                    override["trailing_stop_pct"] = decision["new_trailing_stop_pct"]
                override["reason"] = f"홀��� 연장: {decision['reason']}"
                self.position_overrides[code] = override

            self._log_decision("hold_check", {"code": code, **decision})
            self._cache.set(cache_key, decision)

            action = "홀딩 연장" if decision["hold"] else "익절 실행"
            logger.info(f"[AIAdvisor] {action}: {code} - {decision['reason']}")
            return decision

        except Exception as e:
            logger.error(f"[AIAdvisor] 홀딩 판단 실패: {e}")
            return {"hold": False, "reason": f"AI 오류: {e}"}

    # ════════════════════════════════════════════
    #  4. 시장 상황 분석 (주기적)
    # ════════════════════════════════════════════

    async def analyze_market(self, positions: dict, stats: dict, brain_data: dict):
        """
        시장 상황을 분석하여 공격/방어 모드 결정
        _monitor_loop에서 주기적으로 호출
        """
        if not self.available:
            return

        now = time.time()
        if self.last_market_analysis and now - self.last_market_analysis < self.market_analysis_interval:
            return

        self.last_market_analysis = now

        try:
            recent_pnls = []
            for s in brain_data.get("strategy_scores", {}).values():
                recent_pnls.extend(s.get("recent_pnls", [])[-5:])

            prompt = f"""당신은 초단타 스캘핑 시장 분석 AI입니다.

## 현재 상태
- 시각: {datetime.now().strftime('%H:%M')}
- 보유 포지션: {len(positions)}개
- 오늘 거래: {stats.get('total_trades', 0)}회
- 오늘 순손익: {stats.get('total_net_pnl', 0):+,.0f}원
- 승: {stats.get('wins', 0)} / 패: {stats.get('losses', 0)}

## 최근 거래 손익 추이 (최근 순)
{recent_pnls[-20:] if recent_pnls else '데이터 없음'}

## 안전 규칙 (절대 위반 불가)
- 미수거래 불가, 신용거래 불가
- 계좌 잔고 이내에서만

현재 시장 상황을 판단하세요. 반드시 아래 JSON만 답하세요:
```json
{{
  "mode": "aggressive" 또는 "normal" 또는 "defensive",
  "reason": "판단 이유",
  "config_adjust": {{}}
}}
```

판단 기준:
- 연속 수익 + 승률 높음 → aggressive (투자금/포지션 확대)
- 보통 → normal (현행 유지)
- 연속 손��� + 오늘 손실 누적 → defensive (투자금 축소, 컨센서스 상향)
- aggressive에서도 max_investment_per_trade는 2,000,000원을 절대 초과 금지
- defensive에서 min은 100,000원
"""
            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}],
            )
            result = self._parse_json(response.content[0].text)

            new_mode = result.get("mode", "normal")
            if new_mode in ("aggressive", "normal", "defensive"):
                old_mode = self.market_mode
                self.market_mode = new_mode

                if old_mode != new_mode:
                    logger.info(f"[AIAdvisor] 시장 모드 전환: {old_mode} → {new_mode} ({result.get('reason', '')})")

                # 설정 조정 적용
                config_adjust = result.get("config_adjust", {})
                if config_adjust:
                    self._safe_apply_config(config_adjust)

                self._log_decision("market_analysis", {
                    "mode": new_mode,
                    "reason": result.get("reason", ""),
                    "config_adjust": config_adjust,
                })

        except Exception as e:
            logger.error(f"[AIAdvisor] 시장 분석 실패: {e}")

    def _safe_apply_config(self, changes: dict):
        """안전 규칙을 강제한 후 설정 적용"""
        safe = {}
        for k, v in changes.items():
            # 절대 제한
            if k == "max_investment_per_trade":
                v = max(100_000, min(2_000_000, int(v)))
            if k == "stop_loss_pct":
                v = max(0.2, min(2.0, float(v)))
            if k == "take_profit_pct":
                v = max(0.3, min(5.0, float(v)))
            if k == "max_position_count":
                v = max(1, min(5, int(v)))
            if k == "min_consensus":
                v = max(1, min(4, int(v)))
            if k == "max_hold_seconds":
                v = max(30, min(600, float(v)))
            if k == "max_daily_loss":
                v = max(10_000, min(200_000, float(v)))
            if k == "max_daily_trades":
                v = max(10, min(200, int(v)))
            safe[k] = v

        if safe:
            try:
                from services.auto_scalper import auto_scalper
                auto_scalper.update_config(safe)
                logger.info(f"[AIAdvisor] 안전 검증 후 설정 적용: {safe}")
            except Exception as e:
                logger.error(f"[AIAdvisor] 설정 적용 실패: {e}")

    def on_position_closed(self, code: str):
        """포지션 청산 시 오버라이드 제거"""
        self.position_overrides.pop(code, None)

    # ════════════════════════════════════════════
    #  유틸리티
    # ════════════════════════════════════════════

    def _parse_json(self, text: str) -> dict:
        import re
        # ```json ... ``` 블록 추출
        blocks = re.findall(r'```json\s*(\{[^`]+\})\s*```', text, re.DOTALL)
        for block in blocks:
            try:
                return json.loads(block)
            except json.JSONDecodeError:
                continue
        # 블록 없으면 전체에서 시도
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            return json.loads(text[start:end])
        except (ValueError, json.JSONDecodeError):
            return {}

    def _load_decisions(self) -> list:
        if self._log_file.exists():
            try:
                return json.loads(self._log_file.read_text(encoding="utf-8"))
            except Exception:
                return []
        return []

    def _log_decision(self, decision_type: str, data: dict):
        self._decisions.append({
            "type": decision_type,
            "timestamp": datetime.now().isoformat(),
            **data,
        })
        # 최근 500건만 보관
        if len(self._decisions) > 500:
            self._decisions = self._decisions[-500:]
        try:
            self._log_file.parent.mkdir(parents=True, exist_ok=True)
            self._log_file.write_text(
                json.dumps(self._decisions, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception:
            pass

    def get_status(self) -> dict:
        return {
            "available": self.available,
            "market_mode": self.market_mode,
            "last_market_analysis": self.last_market_analysis,
            "position_overrides": self.position_overrides,
            "recent_decisions": self._decisions[-10:],
            "total_decisions": len(self._decisions),
        }

    def get_decisions(self, limit: int = 50) -> list:
        return self._decisions[-limit:]


# 싱글톤
ai_advisor = AIAdvisor()
