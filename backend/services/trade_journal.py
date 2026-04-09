"""
Trade Journal Service - 매매일지 단일 파일 누적 저장 시스템

구조:
  trading_journals/
    trades.json                # 전체 매매 기록 (날짜 포함, 단일 파일에 누적)
    signals.json               # 전체 신호 기록 (날짜 포함, 단일 파일에 누적)
    20260301_매매일지.md        # 날짜별 보고서 파일 (폴더 없이 파일 1개)
    20260302_매매일지.md
    ...
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 매매일지 기본 저장 경로
JOURNAL_BASE_DIR = Path(__file__).parent.parent.parent / "trading_journals"


class TradeJournal:
    """매매일지 관리 서비스 - 단일 파일 누적 방식"""

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or JOURNAL_BASE_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._trades_file = self.base_dir / "trades.json"
        self._signals_file = self.base_dir / "signals.json"
        logger.info(f"[매매일지] 저장 경로: {self.base_dir}")

    # ── JSON 파일 읽기/쓰기 헬퍼 ──

    def _load_json(self, filepath: Path) -> list:
        if filepath.exists():
            try:
                return json.loads(filepath.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, Exception):
                return []
        return []

    def _save_json(self, filepath: Path, data: list):
        filepath.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    # ── 매매 기록 저장 ──

    def record_trade(self, trade_data: dict, engine_type: str = "auto_scalper"):
        """매매 청산 시 호출 - trades.json에 누적 추가"""
        trades = self._load_json(self._trades_file)

        record = {
            "id": len(trades) + 1,
            "date": datetime.now().strftime("%Y%m%d"),
            "timestamp": datetime.now().isoformat(),
            "engine": engine_type,
            "code": trade_data.get("code", ""),
            "side": trade_data.get("side", ""),
            "entry_price": trade_data.get("entry_price", 0),
            "exit_price": trade_data.get("exit_price", 0),
            "quantity": trade_data.get("quantity", 0),
            "gross_pnl": trade_data.get("gross_pnl", trade_data.get("pnl", 0)),
            "net_pnl": trade_data.get("net_pnl", trade_data.get("pnl", 0)),
            "commission": trade_data.get("commission", 0),
            "pnl_pct": trade_data.get("pnl_pct", 0),
            "strategy": trade_data.get("strategy", ""),
            "exit_reason": trade_data.get("exit_reason", ""),
            "hold_seconds": trade_data.get("hold_seconds", 0),
            "entry_time": trade_data.get("entry_time", ""),
            "exit_time": trade_data.get("exit_time", ""),
            "market_context": trade_data.get("market_context", {}),
        }

        trades.append(record)
        self._save_json(self._trades_file, trades)
        logger.info(f"[매매일지] 거래 #{record['id']} 기록: {record['code']} {record['side']} 손익={record['net_pnl']:+,.0f}원")
        return record

    # ── 신호 기록 저장 ──

    def record_signal(self, signal_data: dict, engine_type: str = "auto_scalper"):
        """신호 발생 시 호출 - signals.json에 누적 추가"""
        signals = self._load_json(self._signals_file)

        record = {
            "id": len(signals) + 1,
            "date": datetime.now().strftime("%Y%m%d"),
            "timestamp": datetime.now().isoformat(),
            "engine": engine_type,
            "time": signal_data.get("time", datetime.now().strftime("%H:%M:%S")),
            "code": signal_data.get("code", ""),
            "side": signal_data.get("side", ""),
            "strategy": signal_data.get("strategy", ""),
            "strength": signal_data.get("strength", ""),
            "reason": signal_data.get("reason", ""),
            "action": signal_data.get("action", ""),
            "price": signal_data.get("price", 0),
        }

        signals.append(record)
        self._save_json(self._signals_file, signals)
        return record

    # ── 날짜별 데이터 필터 ──

    def _get_trades_by_date(self, date_str: str) -> list:
        """특정 날짜의 매매 기록 필터링"""
        all_trades = self._load_json(self._trades_file)
        return [t for t in all_trades if t.get("date") == date_str]

    def _get_signals_by_date(self, date_str: str) -> list:
        """특정 날짜의 신호 기록 필터링"""
        all_signals = self._load_json(self._signals_file)
        return [s for s in all_signals if s.get("date") == date_str]

    # ── 일일 보고서 생성 (단일 .md 파일) ──

    def generate_daily_report(self, date: Optional[datetime] = None) -> str:
        """날짜별 매매일지 Markdown 파일 생성"""
        dt = date or datetime.now()
        date_str = dt.strftime("%Y%m%d")

        trades = self._get_trades_by_date(date_str)
        signals = self._get_signals_by_date(date_str)

        date_display = dt.strftime("%Y년 %m월 %d일")
        date_weekday = ["월", "화", "수", "목", "금", "토", "일"][dt.weekday()]

        # ── 통계 계산 ──
        total_trades = len(trades)
        wins = [t for t in trades if t.get("net_pnl", 0) > 0]
        losses = [t for t in trades if t.get("net_pnl", 0) <= 0]
        win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0

        total_gross_pnl = sum(t.get("gross_pnl", 0) for t in trades)
        total_net_pnl = sum(t.get("net_pnl", 0) for t in trades)
        total_commission = sum(t.get("commission", 0) for t in trades)

        max_win = max((t.get("net_pnl", 0) for t in trades), default=0)
        max_loss = min((t.get("net_pnl", 0) for t in trades), default=0)
        avg_hold = sum(t.get("hold_seconds", 0) for t in trades) / total_trades if total_trades > 0 else 0

        # 전략별 통계
        strategy_stats = {}
        for t in trades:
            strat = t.get("strategy", "unknown")
            if strat not in strategy_stats:
                strategy_stats[strat] = {"trades": 0, "wins": 0, "pnl": 0}
            strategy_stats[strat]["trades"] += 1
            strategy_stats[strat]["pnl"] += t.get("net_pnl", 0)
            if t.get("net_pnl", 0) > 0:
                strategy_stats[strat]["wins"] += 1

        # 종목별 통계
        stock_stats = {}
        for t in trades:
            code = t.get("code", "unknown")
            if code not in stock_stats:
                stock_stats[code] = {"trades": 0, "wins": 0, "pnl": 0}
            stock_stats[code]["trades"] += 1
            stock_stats[code]["pnl"] += t.get("net_pnl", 0)
            if t.get("net_pnl", 0) > 0:
                stock_stats[code]["wins"] += 1

        # 청산 사유별 통계
        exit_stats = {}
        for t in trades:
            reason = t.get("exit_reason", "unknown")
            if reason not in exit_stats:
                exit_stats[reason] = {"count": 0, "pnl": 0}
            exit_stats[reason]["count"] += 1
            exit_stats[reason]["pnl"] += t.get("net_pnl", 0)

        # 신호 통계
        total_signals = len(signals)
        entry_signals = len([s for s in signals if s.get("action") == "ENTRY"])
        no_consensus_signals = len([s for s in signals if s.get("action") == "no_consensus"])

        pnl_emoji = "+" if total_net_pnl >= 0 else ""
        result_text = "수익" if total_net_pnl >= 0 else "손실"

        # ── 보고서 작성 ──
        report = f"""# 스캘핑 매매일지 - {date_display} ({date_weekday})

---

## 1. 일일 요약

| 항목 | 값 |
|------|-----|
| 총 매매 횟수 | {total_trades}회 |
| 승률 | {win_rate:.1f}% ({len(wins)}승 {len(losses)}패) |
| 총 세전 손익 | {total_gross_pnl:+,.0f}원 |
| 총 수수료/세금 | {total_commission:,.0f}원 |
| 총 순손익 | {total_net_pnl:+,.0f}원 ({result_text}) |
| 최대 수익 거래 | {max_win:+,.0f}원 |
| 최대 손실 거래 | {max_loss:+,.0f}원 |
| 평균 보유 시간 | {avg_hold:.1f}초 |

---

## 2. 전략별 성과

| 전략 | 매매수 | 승률 | 순손익 |
|------|--------|------|--------|
"""
        for strat, s in sorted(strategy_stats.items(), key=lambda x: x[1]["pnl"], reverse=True):
            sr = (s["wins"] / s["trades"] * 100) if s["trades"] > 0 else 0
            report += f"| {strat} | {s['trades']}회 | {sr:.0f}% | {s['pnl']:+,.0f}원 |\n"

        report += """
---

## 3. 종목별 성과

| 종목코드 | 매매수 | 승률 | 순손익 |
|----------|--------|------|--------|
"""
        for code, s in sorted(stock_stats.items(), key=lambda x: x[1]["pnl"], reverse=True):
            sr = (s["wins"] / s["trades"] * 100) if s["trades"] > 0 else 0
            report += f"| {code} | {s['trades']}회 | {sr:.0f}% | {s['pnl']:+,.0f}원 |\n"

        report += """
---

## 4. 청산 사유 분석

| 청산 사유 | 횟수 | 손익 합계 |
|-----------|------|-----------|
"""
        for reason, s in sorted(exit_stats.items(), key=lambda x: x[1]["count"], reverse=True):
            report += f"| {reason} | {s['count']}회 | {s['pnl']:+,.0f}원 |\n"

        report += f"""
---

## 5. 신호 분석

| 항목 | 값 |
|------|-----|
| 총 신호 수 | {total_signals}개 |
| 진입 실행 신호 | {entry_signals}개 |
| 컨센서스 미달 | {no_consensus_signals}개 |
| 신호 실행률 | {(entry_signals / total_signals * 100) if total_signals > 0 else 0:.1f}% |

---

## 6. 개별 매매 상세

"""
        for i, t in enumerate(trades, 1):
            side_kr = "매수->매도" if t.get("side") == "buy" else "매도->매수"
            report += f"""### 거래 #{i}
| 항목 | 내용 |
|------|------|
| 종목 | {t.get('code', '')} |
| 방향 | {side_kr} |
| 진입가 | {t.get('entry_price', 0):,}원 ({t.get('entry_time', '')}) |
| 청산가 | {t.get('exit_price', 0):,}원 ({t.get('exit_time', '')}) |
| 수량 | {t.get('quantity', 0):,}주 |
| 순손익 | {t.get('net_pnl', 0):+,.0f}원 ({t.get('pnl_pct', 0):+.2f}%) |
| 수수료 | {t.get('commission', 0):,.0f}원 |
| 진입전략 | {t.get('strategy', '')} |
| 청산사유 | {t.get('exit_reason', '')} |
| 보유시간 | {t.get('hold_seconds', 0):.1f}초 |
| 엔진 | {t.get('engine', '')} |

"""
            ctx = t.get("market_context", {})
            if ctx:
                report += "진입 시 시장 상황:\n"
                if ctx.get("bid"):
                    report += f"- 매수호가: {ctx['bid']:,}원 (잔량 {ctx.get('bid_qty', 0):,})\n"
                if ctx.get("ask"):
                    report += f"- 매도호가: {ctx['ask']:,}원 (잔량 {ctx.get('ask_qty', 0):,})\n"
                if ctx.get("orderbook_imbalance"):
                    report += f"- 호가 불균형: {ctx['orderbook_imbalance']:.2f}\n"
                if ctx.get("vwap"):
                    report += f"- VWAP: {ctx['vwap']:,.0f}원\n"
                if ctx.get("volume"):
                    report += f"- 거래량: {ctx['volume']:,}\n"
                if ctx.get("consensus_strategies"):
                    report += f"- 합의 전략: {', '.join(ctx['consensus_strategies'])}\n"
                report += "\n"

        report += f"""---

생성 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
이 보고서는 StockDashboard 스캘핑 매매일지 시스템에 의해 자동 생성되었습니다.
"""
        # 파일 저장: trading_journals/20260410_매매일지.md
        report_file = self.base_dir / f"{date_str}_매매일지.md"
        report_file.write_text(report, encoding="utf-8")
        logger.info(f"[매매일지] 보고서 생성: {report_file}")

        return report

    # ── 조회 기능 ──

    def get_today_trades(self) -> list:
        return self._get_trades_by_date(datetime.now().strftime("%Y%m%d"))

    def get_today_signals(self) -> list:
        return self._get_signals_by_date(datetime.now().strftime("%Y%m%d"))

    def get_date_trades(self, date_str: str) -> list:
        return self._get_trades_by_date(date_str)

    def get_date_signals(self, date_str: str) -> list:
        return self._get_signals_by_date(date_str)

    def list_journal_dates(self) -> list:
        """매매 기록이 존재하는 날짜 목록 (trades.json에서 추출)"""
        all_trades = self._load_json(self._trades_file)

        # 날짜별 그룹핑
        date_map = {}
        for t in all_trades:
            d = t.get("date", "")
            if not d:
                continue
            if d not in date_map:
                date_map[d] = {"trades": 0, "pnl": 0}
            date_map[d]["trades"] += 1
            date_map[d]["pnl"] += t.get("net_pnl", 0)

        result = []
        for d in sorted(date_map.keys(), reverse=True):
            report_file = self.base_dir / f"{d}_매매일지.md"
            result.append({
                "date": d,
                "trade_count": date_map[d]["trades"],
                "total_pnl": date_map[d]["pnl"],
                "has_report": report_file.exists(),
            })
        return result

    def get_date_report(self, date_str: str) -> Optional[str]:
        report_file = self.base_dir / f"{date_str}_매매일지.md"
        if report_file.exists():
            return report_file.read_text(encoding="utf-8")
        return None

    def get_multi_day_summary(self, days: int = 7) -> dict:
        """최근 N일간 요약 통계"""
        all_dates = self.list_journal_dates()
        recent = all_dates[:days]

        total_trades = 0
        total_pnl = 0
        total_wins = 0
        daily_results = []

        for d in recent:
            trades = self._get_trades_by_date(d["date"])
            day_trades = len(trades)
            day_pnl = sum(t.get("net_pnl", 0) for t in trades)
            day_wins = len([t for t in trades if t.get("net_pnl", 0) > 0])

            total_trades += day_trades
            total_pnl += day_pnl
            total_wins += day_wins

            daily_results.append({
                "date": d["date"],
                "trades": day_trades,
                "pnl": day_pnl,
                "win_rate": (day_wins / day_trades * 100) if day_trades > 0 else 0,
            })

        return {
            "period_days": len(recent),
            "total_trades": total_trades,
            "total_pnl": total_pnl,
            "win_rate": (total_wins / total_trades * 100) if total_trades > 0 else 0,
            "daily_results": daily_results,
        }


# 싱글톤 인스턴스
trade_journal = TradeJournal()
