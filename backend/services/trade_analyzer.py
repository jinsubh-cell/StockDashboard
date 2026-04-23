"""
Trade Brain - Claude AI가 매매할 때마다 자동 학습하고 진화하는 스캘핑 AI

작동 방식:
  1. 매매 청산 → learn(trade) → brain.json에 통계 누적
  2. 10거래마다 → Claude AI에게 전체 학습 데이터를 보내서 "사고" 요청
  3. Claude가 분석한 결과 → 엔진 설정 자동 변경
  4. 다음 매매부터 개선된 설정으로 실행

brain.json:
  - strategy_scores: 전략별 누적 성과
  - time_scores: 시간대별 성과
  - exit_patterns: 청산 사유별 패턴
  - ai_insights: Claude가 도출한 인사이트 (영구 기억)
  - evolution_log: 진화 이력
  - generation: 현재 세대
"""
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# .env 로드
_env_path = Path(__file__).resolve().parent.parent.parent / '.env'
if _env_path.exists():
    load_dotenv(_env_path)

logger = logging.getLogger(__name__)

BRAIN_DIR = Path(__file__).parent.parent.parent / "trading_journals"


class TradeBrain:
    """Claude AI가 매매마다 학습하고 스스로 진화하는 두뇌"""

    def __init__(self):
        self._brain_file = BRAIN_DIR / "brain.json"
        BRAIN_DIR.mkdir(parents=True, exist_ok=True)

        # 진화 설정 (승률 70% 목표)
        self.evolve_every_n = 10          # 10거래마다 Claude AI 호출
        self.min_trades_to_evolve = 10    # 최소 10거래 후 진화 시작
        self.deep_review_every_n = 30     # 30거래마다 심층 리뷰
        self.target_win_rate = 70.0       # 목표 승률 70%
        # 5거래마다는 룰 기반 자동 조정 (API 호출 없음)

        # Claude 클라이언트
        self._client = None

        # 두뇌 로드
        self.brain = self._load_brain()
        logger.info(f"[Brain] 세대 #{self.brain['generation']} | "
                     f"학습 {self.brain['total_learned']}건 | "
                     f"AI인사이트 {len(self.brain.get('ai_insights', []))}개")

    # ════════════════════════════════════════════
    #  Claude API 클라이언트
    # ════════════════════════════════════════════

    @property
    def client(self):
        if self._client is None:
            # .env를 매번 다시 로드 (키 변경 대응)
            if _env_path.exists():
                load_dotenv(_env_path, override=True)
            api_key = os.getenv("ANTHROPIC_API_KEY", "")
            if api_key:
                try:
                    import anthropic
                    self._client = anthropic.Anthropic(api_key=api_key)
                    logger.info("[Brain] Claude API 연결 완료")
                except ImportError:
                    logger.error("[Brain] anthropic 패키지 없음: pip install anthropic")
            else:
                logger.warning("[Brain] ANTHROPIC_API_KEY 미설정")
        return self._client

    def _reset_client(self):
        """API 키 변경 시 클라이언트 리셋"""
        self._client = None

    @property
    def ai_available(self) -> bool:
        return self.client is not None

    # ════════════════════════════════════════════
    #  두뇌 파일 관리
    # ════════════════════════════════════════════

    def _default_brain(self) -> dict:
        return {
            "generation": 0,
            "total_learned": 0,
            "since_last_evolve": 0,
            "created_at": datetime.now().isoformat(),
            "last_evolved": None,

            "strategy_scores": {},
            "time_scores": {},
            "exit_patterns": {},
            "price_bracket_scores": {},

            # Claude AI가 축적하는 인사이트 (영구 기억)
            "ai_insights": [],
            # [{timestamp, insight, confidence, applied}]

            # 현재 적용 중인 설정 변경분
            "active_adjustments": {},

            # 진화 이력
            "evolution_log": [],
        }

    def _load_brain(self) -> dict:
        if self._brain_file.exists():
            try:
                brain = json.loads(self._brain_file.read_text(encoding="utf-8"))
                default = self._default_brain()
                for key in default:
                    if key not in brain:
                        brain[key] = default[key]
                return brain
            except Exception as e:
                logger.error(f"[Brain] 로드 실패: {e}")
        return self._default_brain()

    def _save_brain(self):
        self._brain_file.write_text(
            json.dumps(self.brain, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    # ════════════════════════════════════════════
    #  매매마다 자동 학습
    # ════════════════════════════════════════════

    def learn(self, trade: dict):
        """매매 청산 시 자동 호출 - 이 거래에서 배운다"""
        strategy = trade.get("strategy", "unknown")
        net_pnl = trade.get("net_pnl", trade.get("pnl", 0))
        entry_time = trade.get("entry_time", "")
        hold_seconds = trade.get("hold_seconds", 0)
        exit_reason = trade.get("exit_reason", "")
        entry_price = trade.get("entry_price", 0)
        is_win = net_pnl > 0

        self._learn_strategy(strategy, net_pnl, hold_seconds, is_win)
        self._learn_time(entry_time, net_pnl, is_win)
        self._learn_exit(exit_reason, net_pnl, hold_seconds, is_win)
        self._learn_price_range(entry_price, net_pnl, is_win)

        self.brain["total_learned"] += 1
        self.brain["since_last_evolve"] += 1
        self._save_brain()

        # 5거래마다 룰 기반 미세 조정 (API 호출 없음, 무료)
        if self.brain["since_last_evolve"] % 5 == 0 and self.brain["total_learned"] >= 10:
            rule_result = self._rule_based_evolve()
            rule_changes = rule_result.get("config_changes", {})
            if rule_changes:
                self._apply_to_engine(rule_changes)
                logger.info(f"[Brain] 룰 기반 미세 조정: {rule_changes}")

        # 20거래마다 Claude AI 진화 (API 호출)
        if (self.brain["since_last_evolve"] >= self.evolve_every_n
                and self.brain["total_learned"] >= self.min_trades_to_evolve):
            self._evolve()

        remaining = self.evolve_every_n - self.brain["since_last_evolve"]
        logger.info(f"[Brain] 학습 #{self.brain['total_learned']}: "
                     f"{strategy} {'승' if is_win else '패'} {net_pnl:+,.0f}원 "
                     f"(AI진화까지 {remaining}거래)")

    def _learn_strategy(self, name, pnl, hold, is_win):
        scores = self.brain["strategy_scores"]
        if name not in scores:
            scores[name] = {"wins": 0, "losses": 0, "total_pnl": 0,
                            "hold_sum": 0, "trade_count": 0, "recent_pnls": []}
        s = scores[name]
        s["trade_count"] += 1
        s["total_pnl"] += pnl
        s["hold_sum"] += hold
        s["wins" if is_win else "losses"] += 1
        s["recent_pnls"].append(round(pnl, 0))
        if len(s["recent_pnls"]) > 30:
            s["recent_pnls"] = s["recent_pnls"][-30:]

    def _learn_time(self, entry_time, pnl, is_win):
        if not entry_time or ":" not in entry_time:
            return
        hour = entry_time.split(":")[0]
        scores = self.brain["time_scores"]
        if hour not in scores:
            scores[hour] = {"wins": 0, "losses": 0, "total_pnl": 0, "trade_count": 0}
        s = scores[hour]
        s["trade_count"] += 1
        s["total_pnl"] += pnl
        s["wins" if is_win else "losses"] += 1

    def _learn_exit(self, reason, pnl, hold, is_win):
        if not reason:
            return
        patterns = self.brain["exit_patterns"]
        if reason not in patterns:
            patterns[reason] = {"count": 0, "pnl": 0, "hold_sum": 0, "wins": 0}
        p = patterns[reason]
        p["count"] += 1
        p["pnl"] += pnl
        p["hold_sum"] += hold
        if is_win:
            p["wins"] += 1

    def _learn_price_range(self, price, pnl, is_win):
        if price <= 0:
            return
        if price < 5000:
            bracket = "~5천"
        elif price < 10000:
            bracket = "5천~1만"
        elif price < 30000:
            bracket = "1만~3만"
        elif price < 50000:
            bracket = "3만~5만"
        else:
            bracket = "5만~"
        scores = self.brain["price_bracket_scores"]
        if bracket not in scores:
            scores[bracket] = {"wins": 0, "losses": 0, "pnl": 0, "count": 0}
        s = scores[bracket]
        s["count"] += 1
        s["pnl"] += pnl
        s["wins" if is_win else "losses"] += 1

    # ════════════════════════════════════════════
    #  Claude AI 진화 (핵심)
    # ════════════════════════════════════════════

    def _evolve(self):
        """Claude AI에게 학습 데이터를 보내 사고하게 하고 설정을 조정한다"""
        gen = self.brain["generation"] + 1
        is_deep = (self.brain["total_learned"] % self.deep_review_every_n == 0)

        logger.info(f"[Brain] === 세대 #{gen} 진화 시작 {'(심층)' if is_deep else ''} ===")

        # Claude AI 호출
        if self.ai_available:
            ai_result = self._ask_claude(is_deep)
        else:
            ai_result = self._rule_based_evolve()

        changes = ai_result.get("config_changes", {})
        reasons = ai_result.get("reasons", [])
        insight = ai_result.get("insight", "")

        # 인사이트 저장 (영구 기억)
        if insight:
            self.brain["ai_insights"].append({
                "generation": gen,
                "timestamp": datetime.now().isoformat(),
                "insight": insight,
                "deep_review": is_deep,
            })
            # 최근 100개만 보관
            if len(self.brain["ai_insights"]) > 100:
                self.brain["ai_insights"] = self.brain["ai_insights"][-100:]

        # 엔진에 적용
        applied = False
        if changes:
            applied = self._apply_to_engine(changes)
            self.brain["active_adjustments"].update(changes)

        # 진화 로그
        self.brain["evolution_log"].append({
            "generation": gen,
            "timestamp": datetime.now().isoformat(),
            "changes": changes,
            "reasons": reasons,
            "insight": insight[:200] if insight else "",
            "applied": applied,
            "ai_used": self.ai_available,
            "deep_review": is_deep,
        })
        if len(self.brain["evolution_log"]) > 50:
            self.brain["evolution_log"] = self.brain["evolution_log"][-50:]

        self.brain["generation"] = gen
        self.brain["since_last_evolve"] = 0
        self.brain["last_evolved"] = datetime.now().isoformat()
        self._save_brain()

        # 진화 보고서 파일 저장
        self._save_evolution_report(gen, changes, reasons, insight, is_deep)

        for r in reasons:
            logger.info(f"  [진화] {r}")
        if changes:
            logger.info(f"  [적용] {changes}")

    def _ask_claude(self, is_deep: bool) -> dict:
        """Claude에게 학습 데이터를 보내 분석/설정 추천을 받는다"""
        try:
            current_config = self._get_current_config()
            prompt = self._build_evolution_prompt(current_config, is_deep)

            response = self.client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            ai_text = response.content[0].text

            # JSON 추출
            result = self._parse_ai_response(ai_text)
            result["insight"] = ai_text
            return result

        except Exception as e:
            logger.error(f"[Brain] Claude API 호출 실패: {e}")
            self._reset_client()  # 다음 시도 시 키 재로드
            # 실패 시 규칙 기반으로 폴백
            return self._rule_based_evolve()

    def _build_evolution_prompt(self, current_config: dict, is_deep: bool) -> str:
        brain = self.brain
        # 이전 인사이트 요약 (Claude의 기억)
        prev_insights = ""
        recent = brain["ai_insights"][-5:] if brain["ai_insights"] else []
        if recent:
            prev_insights = "\n".join(
                f"- 세대#{i['generation']}: {i['insight'][:150]}"
                for i in recent
            )

        deep_section = ""
        if is_deep:
            deep_section = """
## 심층 리뷰 모드 (50거래 주기)

이번은 심층 리뷰입니다. 평소보다 더 깊이 분석하세요:
- 전략 간 상관관계 (어떤 전략 조합이 효과적인지)
- 시간대별 전략 효과 차이 (오전에 강한 전략 vs 오후에 강한 전략)
- 손절/익절 비율의 근본적 재검토
- 현재 시장 환경에 맞는 전략 가중치 재배분
- 이전 인사이트들을 종합한 메타 분석
"""

        return f"""당신은 한국 주식 초단타 스캘핑 AI 트레이더입니다.
매매 데이터가 쌓일 때마다 호출되어 학습하고 진화합니다.

## 현재 세대: #{brain['generation']} → #{brain['generation']+1}
## 총 학습 거래: {brain['total_learned']}건

## 이전 인사이트 (당신의 기억)
{prev_insights if prev_insights else "첫 진화입니다. 기억이 없습니다."}

## 현재 엔진 설정
```json
{json.dumps(current_config, ensure_ascii=False, indent=2)}
```

## 전략별 누적 성과
```json
{json.dumps(brain['strategy_scores'], ensure_ascii=False, indent=2)}
```

## 시간대별 성과
```json
{json.dumps(brain['time_scores'], ensure_ascii=False, indent=2)}
```

## 청산 사유별 패턴
```json
{json.dumps(brain['exit_patterns'], ensure_ascii=False, indent=2)}
```

## 가격대별 성과
```json
{json.dumps(brain.get('price_bracket_scores', {}), ensure_ascii=False, indent=2)}
```

## 현재 적용 중인 조정값 (이전 진화에서 변경한 것)
```json
{json.dumps(brain['active_adjustments'], ensure_ascii=False, indent=2)}
```
{deep_section}
## 분석 요청

위 데이터를 분석하여 다음을 JSON으로 답하세요. 반드시 이 형식을 지키세요:

```json
{{
  "config_changes": {{
    "설정키": 값
  }},
  "reasons": [
    "변경 이유 1",
    "변경 이유 2"
  ],
  "keep_current": ["현행 유지할 설정과 이유"],
  "watch_list": ["다음 진화에서 주시할 항목"]
}}
```

### 변경 가능한 설정키:
- use_tick_momentum, use_vwap_deviation, use_orderbook_imbalance, use_bollinger_scalp (bool)
- use_ema_cross, use_stochastic, use_macd, use_alma, use_execution_strength (bool)
- use_rsi_extreme, use_volume_spike (bool)
- tick_momentum_threshold (0.5~0.9), vwap_entry_deviation (0.1~1.0)
- imbalance_threshold (1.5~5.0), bb_window (10~50), bb_std (1.5~3.0)
- min_consensus (1~4)
- stop_loss_pct (0.2~2.0), take_profit_pct (0.5~5.0)
- trailing_stop_pct (0.2~2.0), use_trailing_stop (bool)
- max_hold_seconds (30~600), cooldown_seconds (1~30)
- max_daily_loss (10000~200000), max_daily_trades (10~200)
- max_investment_per_trade (100000~2000000)

### 규칙:
1. 데이터가 부족하면 (전략별 5건 미만) 그 전략은 건드리지 마���요
2. 한 번에 너무 많이 바꾸지 마세요 (최대 3~4개 설정만 변경)
3. 이전 진화에서 바꾼 설정은 효과를 볼 시간이 필요하므로 신중하게
4. config_changes가 비어있어도 됩니다 (변경 불필요하면)
5. reasons는 한국어로 구체적 수치와 함께 설명하세요
"""

    def _parse_ai_response(self, ai_text: str) -> dict:
        """Claude 응답에서 JSON ��출"""
        import re
        result = {"config_changes": {}, "reasons": [], "insight": ""}

        json_blocks = re.findall(r'```json\s*(\{[^`]+\})\s*```', ai_text, re.DOTALL)
        for block in json_blocks:
            try:
                parsed = json.loads(block)
                if "config_changes" in parsed:
                    result["config_changes"] = parsed["config_changes"]
                    result["reasons"] = parsed.get("reasons", [])
                    return result
            except json.JSONDecodeError:
                continue

        # JSON 블록 실패 시 전체 텍스트에서 시도
        try:
            start = ai_text.index("{")
            end = ai_text.rindex("}") + 1
            parsed = json.loads(ai_text[start:end])
            if "config_changes" in parsed:
                result["config_changes"] = parsed["config_changes"]
                result["reasons"] = parsed.get("reasons", [])
        except (ValueError, json.JSONDecodeError):
            result["reasons"] = ["AI 응답 파싱 실패 - 규칙 기반 진화로 전환"]
            fallback = self._rule_based_evolve()
            result["config_changes"] = fallback.get("config_changes", {})
            result["reasons"].extend(fallback.get("reasons", []))

        return result

    # ════════════════════════════════════════════
    #  규칙 기반 폴백 (API 실패 시)
    # ════════════════════════════════════════════

    def _rule_based_evolve(self) -> dict:
        """Claude 없이 통계 규칙으로 진화 (수수료 고려 보수적 학습)"""
        changes = {}
        reasons = []

        strategy_to_config = {
            "tick_momentum": "use_tick_momentum",
            "vwap_deviation": "use_vwap_deviation",
            "orderbook_imbalance": "use_orderbook_imbalance",
            "bollinger_scalp": "use_bollinger_scalp",
            "ema_crossover": "use_ema_crossover",
            "rsi_extreme": "use_rsi_extreme",
            "volume_spike": "use_volume_spike",
            "trade_intensity": "use_trade_intensity",
            "tick_acceleration": "use_tick_acceleration",
        }

        # 1. 전략별 성과 분석 → 비활성화/활성화
        # 단일 전략별로 조합을 포함한 모든 통계 합산 후 판단 (조합명 오매칭 버그 방지)
        from collections import defaultdict
        single_strategy_stats = defaultdict(lambda: {
            "trade_count": 0, "wins": 0, "total_pnl": 0.0,
            "combo_appearances": 0,  # 조합에 포함된 횟수
        })

        for name, s in self.brain["strategy_scores"].items():
            tc = s.get("trade_count", 0)
            if tc < 1:
                continue
            # consensus(A,B,C) 형식에서 참여 전략 추출
            inner = name.replace("consensus(", "").replace(")", "").strip()
            parts = [p.strip() for p in inner.split(",") if p.strip()]
            is_combo = len(parts) >= 2

            for strat in parts:
                agg = single_strategy_stats[strat]
                agg["trade_count"] += tc
                agg["wins"] += s.get("wins", 0)
                agg["total_pnl"] += s.get("total_pnl", 0)
                if is_combo:
                    agg["combo_appearances"] += tc

        # 단일 전략별 종합 성과로 on/off 판정
        for strat, agg in single_strategy_stats.items():
            config_key = strategy_to_config.get(strat)
            if not config_key:
                continue
            tc = agg["trade_count"]
            if tc < 5:
                continue
            win_rate = agg["wins"] / tc
            total_pnl = agg["total_pnl"]
            combo_ratio = agg["combo_appearances"] / tc  # 조합 참여 비율

            # 조합에서 효과적이면 유지 (단일로 나빠도 조합에서 좋을 수 있음)
            if combo_ratio >= 0.5 and total_pnl > -3000:
                # 조합 중심 전략 → 유지
                continue

            # 매우 나쁜 전략만 비활성화 (승률 20% 미만 또는 누적 -3천원 초과 & 승률 30% 미만)
            if win_rate < 0.20 or (total_pnl < -3000 and win_rate < 0.30):
                changes[config_key] = False
                reasons.append(f"[전략비활성화] {strat}: 승률{win_rate*100:.0f}%, 누적{total_pnl:+,.0f}원 ({tc}건)")
            # 승률 55% 이상 + 누적 수익 양수 → 활성화
            elif win_rate >= 0.55 and total_pnl > 0:
                changes[config_key] = True
                reasons.append(f"[전략활성화] {strat}: 승률{win_rate*100:.0f}%, 누적{total_pnl:+,.0f}원 ({tc}건)")

        # 2. 손절/익절 비율 분석
        exit_p = self.brain["exit_patterns"]
        sl_count = 0
        tp_count = 0
        trail_count = 0
        timeout_count = 0
        for reason_key, data in exit_p.items():
            rk = reason_key.lower()
            count = data.get("count", 0)
            if "손절" in rk or "stop" in rk:
                sl_count += count
            elif "익절" in rk or "take" in rk or "profit" in rk:
                tp_count += count
            elif "트레일링" in rk or "trailing" in rk:
                trail_count += count
            elif "시간" in rk or "timeout" in rk:
                timeout_count += count

        total_exits = sl_count + tp_count + trail_count + timeout_count
        if total_exits >= 5:
            sl_ratio = sl_count / total_exits
            timeout_ratio = timeout_count / total_exits

            # 손절 비율 40% 이상 → 손절폭 확대 (기준 낮춤: 0.6→0.4)
            if sl_ratio > 0.40:
                current_sl = self._get_config_val("stop_loss_pct", 0.8)
                new_sl = round(min(1.5, current_sl * 1.15), 2)
                changes["stop_loss_pct"] = new_sl
                reasons.append(f"[손절] 비율 {sl_ratio:.0%} → 손절폭 확대 {current_sl}→{new_sl}%")

            # 시간초과 비율 30% 이상 → 보유시간 확대
            if timeout_ratio > 0.30:
                current_hold = self._get_config_val("max_hold_seconds", 300)
                new_hold = min(600, int(current_hold * 1.3))
                changes["max_hold_seconds"] = new_hold
                reasons.append(f"[시간] 시간초과비율 {timeout_ratio:.0%} → 보유시간 {current_hold}→{new_hold}초")

            # 손절+시간초과 합산 비율이 80% 이상 → 쿨다운 대폭 확대 (과매매 방지)
            if (sl_ratio + timeout_ratio) > 0.80:
                current_cd = self._get_config_val("cooldown_seconds", 10)
                new_cd = min(30, int(current_cd * 1.5))
                changes["cooldown_seconds"] = new_cd
                reasons.append(f"[과매매] 손절+시간초과 {(sl_ratio+timeout_ratio):.0%} → 쿨다운 {new_cd}초")

        # 3. 전체 승률 체크 → 거래 빈도 조정 (컨센서스 대신 일일거래한도 조정)
        total_trades = self.brain["total_learned"]
        total_wins = sum(s.get("wins", 0) for s in self.brain["strategy_scores"].values())
        if total_trades >= 10:
            overall_win_rate = total_wins / total_trades

            # 승률 40% 미만 → 일일 거래 수 축소
            if overall_win_rate < 0.40:
                current_max = self._get_config_val("max_daily_trades", 20)
                new_max = max(10, int(current_max * 0.8))
                changes["max_daily_trades"] = new_max
                reasons.append(f"[거래제한] 전체 승률 {overall_win_rate:.0%} → 일일 최대 {new_max}건으로 축소")

        return {"config_changes": changes, "reasons": reasons, "insight": "규칙 기반 진화 (수수료 고려 보수적)"}

    # ════════════════════════════════════════════
    #  엔진 설정 적용
    # ════════════════════════════════════════════

    def _get_current_config(self) -> dict:
        try:
            from services.auto_scalper import auto_scalper
            return auto_scalper.config.to_dict()
        except Exception:
            return {}

    def _get_config_val(self, key, default):
        try:
            from services.auto_scalper import auto_scalper
            return getattr(auto_scalper.config, key, default)
        except Exception:
            return default

    def _apply_to_engine(self, changes: dict) -> bool:
        try:
            from services.auto_scalper import auto_scalper
            auto_scalper.update_config(changes)
            logger.info(f"[Brain] 엔진 설정 적용: {changes}")
            return True
        except Exception as e:
            logger.error(f"[Brain] 엔진 적용 실패: {e}")
            return False

    # ════════════════════════════════════════════
    #  진화 보고서 저장
    # ════════════════════════════════════════════

    def _save_evolution_report(self, gen, changes, reasons, insight, is_deep):
        """진화 결과를 Markdown으로 저장"""
        date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = BRAIN_DIR / f"{date_str}_진화#{gen}.md"

        md = f"""# AI 진화 보고서 - 세대 #{gen} {'(심층)' if is_deep else ''}

시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
총 학습 거래: {self.brain['total_learned']}건
AI 사용: {'Claude Sonnet' if self.ai_available else '규칙 기반'}

---

## 변경 사항

"""
        if changes:
            for k, v in changes.items():
                md += f"- `{k}` → `{v}`\n"
        else:
            md += "변경 없음 (현행 유지)\n"

        md += "\n## 변경 이유\n\n"
        for r in reasons:
            md += f"- {r}\n"

        if insight and self.ai_available:
            md += f"\n## AI 분석 원문\n\n{insight}\n"

        md += f"\n---\n*자동 생성됨*\n"
        report_file.write_text(md, encoding="utf-8")

    # ════════════════════════════════════════════
    #  외부 API
    # ════════════════════════════════════════════

    def get_status(self) -> dict:
        b = self.brain
        strategy_summary = []
        for name, s in b["strategy_scores"].items():
            wr = (s["wins"] / s["trade_count"] * 100) if s["trade_count"] > 0 else 0
            recent = s["recent_pnls"][-10:]
            strategy_summary.append({
                "strategy": name,
                "trades": s["trade_count"],
                "win_rate": round(wr, 1),
                "total_pnl": s["total_pnl"],
                "recent_10_pnl": sum(recent),
                "trend": "상승" if sum(recent) > 0 else ("하락" if recent else "데이터없음"),
            })

        time_summary = []
        for hour, s in sorted(b["time_scores"].items()):
            wr = (s["wins"] / s["trade_count"] * 100) if s["trade_count"] > 0 else 0
            time_summary.append({
                "hour": f"{hour}시",
                "trades": s["trade_count"],
                "win_rate": round(wr, 1),
                "total_pnl": s["total_pnl"],
            })

        return {
            "ai_available": self.ai_available,
            "generation": b["generation"],
            "total_learned": b["total_learned"],
            "next_evolve_in": self.evolve_every_n - b["since_last_evolve"],
            "last_evolved": b["last_evolved"],
            "active_adjustments": b["active_adjustments"],
            "strategy_scores": strategy_summary,
            "time_scores": time_summary,
            "price_scores": b.get("price_bracket_scores", {}),
            "exit_patterns": b["exit_patterns"],
            "ai_insights_count": len(b.get("ai_insights", [])),
            "recent_insights": [
                {"gen": i["generation"], "text": i["insight"][:200]}
                for i in b.get("ai_insights", [])[-3:]
            ],
            "recent_evolutions": b["evolution_log"][-5:],
        }

    def get_evolution_log(self) -> list:
        return self.brain["evolution_log"]

    def get_insights(self) -> list:
        return self.brain.get("ai_insights", [])

    def reset(self):
        self.brain = self._default_brain()
        self._save_brain()
        logger.info("[Brain] 초기화 완료")

    def force_evolve(self) -> dict:
        self._evolve()
        return {
            "generation": self.brain["generation"],
            "ai_used": self.ai_available,
            "result": self.brain["evolution_log"][-1] if self.brain["evolution_log"] else {},
        }


# 싱글톤 인스턴스
trade_brain = TradeBrain()
