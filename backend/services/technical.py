"""
Technical Analysis Service
Computes indicators using TA-Lib (industry standard C-based library)
and generates trade signals with enhanced accuracy
"""
import pandas as pd
import talib
import numpy as np
from typing import Optional
import logging

logger = logging.getLogger(__name__)


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all technical indicators on OHLCV DataFrame using TA-Lib"""
    if df.empty or len(df) < 30:
        return df

    close = df["Close"].values.astype(float)
    high = df["High"].values.astype(float)
    low = df["Low"].values.astype(float)
    volume = df["Volume"].values.astype(float)
    open_ = df["Open"].values.astype(float)

    # --- Moving Averages (TA-Lib SMA/EMA) ---
    df["SMA_5"] = talib.SMA(close, timeperiod=5)
    df["SMA_20"] = talib.SMA(close, timeperiod=20)
    df["SMA_60"] = talib.SMA(close, timeperiod=60)
    df["SMA_120"] = talib.SMA(close, timeperiod=120)
    df["SMA_224"] = talib.SMA(close, timeperiod=224)
    df["SMA_448"] = talib.SMA(close, timeperiod=448)
    df["EMA_12"] = talib.EMA(close, timeperiod=12)
    df["EMA_26"] = talib.EMA(close, timeperiod=26)

    # --- Ichimoku Cloud (manual - TA-Lib doesn't include it) ---
    tenkan_period, kijun_period, senkou_period = 9, 26, 52
    tenkan_high = pd.Series(high).rolling(tenkan_period).max()
    tenkan_low = pd.Series(low).rolling(tenkan_period).min()
    df["ITS_9"] = ((tenkan_high + tenkan_low) / 2).values

    kijun_high = pd.Series(high).rolling(kijun_period).max()
    kijun_low = pd.Series(low).rolling(kijun_period).min()
    df["IKS_26"] = ((kijun_high + kijun_low) / 2).values

    df["ISA_9"] = ((df["ITS_9"] + df["IKS_26"]) / 2)
    senkou_high = pd.Series(high).rolling(senkou_period).max()
    senkou_low = pd.Series(low).rolling(senkou_period).min()
    df["ISB_26"] = ((senkou_high + senkou_low) / 2).values

    # --- RSI (TA-Lib uses Wilder's smoothing - more accurate than pandas-ta) ---
    df["RSI_14"] = talib.RSI(close, timeperiod=14)

    # --- MACD ---
    macd, macd_signal, macd_hist = talib.MACD(close, fastperiod=12, slowperiod=26, signalperiod=9)
    df["MACD_12_26_9"] = macd
    df["MACDs_12_26_9"] = macd_signal
    df["MACDh_12_26_9"] = macd_hist

    # --- Bollinger Bands ---
    bb_upper, bb_middle, bb_lower = talib.BBANDS(close, timeperiod=20, nbdevup=2, nbdevdn=2, matype=0)
    df["BBU_20_2.0"] = bb_upper
    df["BBM_20_2.0"] = bb_middle
    df["BBL_20_2.0"] = bb_lower

    # --- ATR (Average True Range) ---
    df["ATR_14"] = talib.ATR(high, low, close, timeperiod=14)

    # --- OBV (On-Balance Volume) ---
    df["OBV"] = talib.OBV(close, volume)

    # --- Stochastic ---
    slowk, slowd = talib.STOCH(high, low, close, fastk_period=14, slowk_period=3, slowk_matype=0, slowd_period=3, slowd_matype=0)
    df["STOCHk_14_3_3"] = slowk
    df["STOCHd_14_3_3"] = slowd

    # --- CCI (Commodity Channel Index) ---
    df["CCI_20"] = talib.CCI(high, low, close, timeperiod=20)

    # --- Additional indicators (TA-Lib exclusive, higher accuracy) ---

    # Williams %R
    df["WILLR_14"] = talib.WILLR(high, low, close, timeperiod=14)

    # ADX (Average Directional Index) - trend strength
    df["ADX_14"] = talib.ADX(high, low, close, timeperiod=14)
    df["PLUS_DI_14"] = talib.PLUS_DI(high, low, close, timeperiod=14)
    df["MINUS_DI_14"] = talib.MINUS_DI(high, low, close, timeperiod=14)

    # MFI (Money Flow Index) - volume-weighted RSI
    df["MFI_14"] = talib.MFI(high, low, close, volume, timeperiod=14)

    # VWAP approximation (Typical Price * Volume cumulative)
    typical_price = (high + low + close) / 3
    cum_tp_vol = np.cumsum(typical_price * volume)
    cum_vol = np.cumsum(volume)
    df["VWAP"] = np.where(cum_vol > 0, cum_tp_vol / cum_vol, np.nan)

    # Parabolic SAR
    df["SAR"] = talib.SAR(high, low, acceleration=0.02, maximum=0.2)

    # Candlestick pattern recognition (TA-Lib unique feature)
    df["CDL_DOJI"] = talib.CDLDOJI(open_, high, low, close)
    df["CDL_HAMMER"] = talib.CDLHAMMER(open_, high, low, close)
    df["CDL_ENGULFING"] = talib.CDLENGULFING(open_, high, low, close)
    df["CDL_MORNINGSTAR"] = talib.CDLMORNINGSTAR(open_, high, low, close, penetration=0)
    df["CDL_EVENINGSTAR"] = talib.CDLEVENINGSTAR(open_, high, low, close, penetration=0)

    return df


def generate_signals(df: pd.DataFrame) -> list[dict]:
    """Generate buy/sell/neutral signals from indicators with enhanced analysis"""
    if df.empty or len(df) < 30:
        return []

    signals = []
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) >= 2 else last

    # 1. SMA Golden/Death Cross
    sma5 = last.get("SMA_5")
    sma20 = last.get("SMA_20")
    prev_sma5 = prev.get("SMA_5")
    prev_sma20 = prev.get("SMA_20")
    if _valid(sma5, sma20, prev_sma5, prev_sma20):
        if prev_sma5 <= prev_sma20 and sma5 > sma20:
            signals.append({"indicator": "골든크로스 (SMA5/20)", "signal": "buy",
                            "value": round(float(sma5), 2),
                            "description": "단기 이동평균이 장기 이동평균을 상향 돌파"})
        elif prev_sma5 >= prev_sma20 and sma5 < sma20:
            signals.append({"indicator": "데드크로스 (SMA5/20)", "signal": "sell",
                            "value": round(float(sma5), 2),
                            "description": "단기 이동평균이 장기 이동평균을 하향 돌파"})
        else:
            sig = "buy" if sma5 > sma20 else "sell"
            signals.append({"indicator": "이동평균 배열", "signal": sig,
                            "value": round(float(sma5 - sma20), 2),
                            "description": f"SMA5={round(float(sma5)):,} {'>' if sma5 > sma20 else '<'} SMA20={round(float(sma20)):,}"})

    # 2. RSI
    rsi = last.get("RSI_14")
    if _valid(rsi):
        rsi_val = float(rsi)
        if rsi_val < 30:
            signals.append({"indicator": "RSI (14)", "signal": "buy",
                            "value": round(rsi_val, 2),
                            "description": f"RSI {rsi_val:.1f}으로 과매도 구간 (30 미만)"})
        elif rsi_val > 70:
            signals.append({"indicator": "RSI (14)", "signal": "sell",
                            "value": round(rsi_val, 2),
                            "description": f"RSI {rsi_val:.1f}으로 과매수 구간 (70 초과)"})
        else:
            signals.append({"indicator": "RSI (14)", "signal": "neutral",
                            "value": round(rsi_val, 2),
                            "description": f"RSI {rsi_val:.1f}으로 중립 구간"})

    # 3. MACD
    macd_val = last.get("MACD_12_26_9")
    macd_signal = last.get("MACDs_12_26_9")
    macd_hist = last.get("MACDh_12_26_9")
    prev_macd = prev.get("MACD_12_26_9")
    prev_signal = prev.get("MACDs_12_26_9")

    if _valid(macd_val, macd_signal):
        if _valid(prev_macd, prev_signal) and prev_macd <= prev_signal and macd_val > macd_signal:
            signals.append({"indicator": "MACD", "signal": "buy",
                            "value": round(float(macd_val), 2),
                            "description": "MACD가 시그널 라인을 상향 돌파"})
        elif _valid(prev_macd, prev_signal) and prev_macd >= prev_signal and macd_val < macd_signal:
            signals.append({"indicator": "MACD", "signal": "sell",
                            "value": round(float(macd_val), 2),
                            "description": "MACD가 시그널 라인을 하향 돌파"})
        else:
            sig = "buy" if macd_val > macd_signal else "sell"
            signals.append({"indicator": "MACD", "signal": sig,
                            "value": round(float(macd_hist or 0), 2),
                            "description": f"MACD 히스토그램: {float(macd_hist or 0):.2f}"})

    # 4. Bollinger Bands
    bb_upper = last.get("BBU_20_2.0")
    bb_lower = last.get("BBL_20_2.0")
    close = float(last.get("Close", 0))

    if _valid(bb_upper, bb_lower) and close > 0:
        if close <= float(bb_lower):
            signals.append({"indicator": "볼린저밴드", "signal": "buy",
                            "value": round(close, 2),
                            "description": f"현재가가 하단밴드({round(float(bb_lower)):,}) 이하로 반등 기대"})
        elif close >= float(bb_upper):
            signals.append({"indicator": "볼린저밴드", "signal": "sell",
                            "value": round(close, 2),
                            "description": f"현재가가 상단밴드({round(float(bb_upper)):,}) 이상으로 과열"})
        else:
            signals.append({"indicator": "볼린저밴드", "signal": "neutral",
                            "value": round(close, 2),
                            "description": "밴드 중간 구간에서 거래 중"})

    # 5. Stochastic
    stoch_k = last.get("STOCHk_14_3_3")
    stoch_d = last.get("STOCHd_14_3_3")
    if _valid(stoch_k, stoch_d):
        stk = float(stoch_k)
        if stk < 20:
            signals.append({"indicator": "스토캐스틱", "signal": "buy",
                            "value": round(stk, 2),
                            "description": f"%K={stk:.1f}, 과매도 구간"})
        elif stk > 80:
            signals.append({"indicator": "스토캐스틱", "signal": "sell",
                            "value": round(stk, 2),
                            "description": f"%K={stk:.1f}, 과매수 구간"})
        else:
            signals.append({"indicator": "스토캐스틱", "signal": "neutral",
                            "value": round(stk, 2),
                            "description": f"%K={stk:.1f}, 중립"})

    # 6. CCI
    cci = last.get("CCI_20")
    if _valid(cci):
        cci_val = float(cci)
        if cci_val < -100:
            signals.append({"indicator": "CCI (20)", "signal": "buy",
                            "value": round(cci_val, 2),
                            "description": f"CCI={cci_val:.1f}, 과매도"})
        elif cci_val > 100:
            signals.append({"indicator": "CCI (20)", "signal": "sell",
                            "value": round(cci_val, 2),
                            "description": f"CCI={cci_val:.1f}, 과매수"})
        else:
            signals.append({"indicator": "CCI (20)", "signal": "neutral",
                            "value": round(cci_val, 2),
                            "description": f"CCI={cci_val:.1f}, 중립"})

    # 7. ADX (Trend Strength) - NEW
    adx = last.get("ADX_14")
    plus_di = last.get("PLUS_DI_14")
    minus_di = last.get("MINUS_DI_14")
    if _valid(adx, plus_di, minus_di):
        adx_val = float(adx)
        if adx_val > 25:
            sig = "buy" if float(plus_di) > float(minus_di) else "sell"
            signals.append({"indicator": "ADX (14)", "signal": sig,
                            "value": round(adx_val, 2),
                            "description": f"ADX={adx_val:.1f}, 강한 {'상승' if sig == 'buy' else '하락'} 추세"})
        else:
            signals.append({"indicator": "ADX (14)", "signal": "neutral",
                            "value": round(adx_val, 2),
                            "description": f"ADX={adx_val:.1f}, 추세 약함 (횡보)"})

    # 8. MFI (Money Flow Index) - NEW
    mfi = last.get("MFI_14")
    if _valid(mfi):
        mfi_val = float(mfi)
        if mfi_val < 20:
            signals.append({"indicator": "MFI (14)", "signal": "buy",
                            "value": round(mfi_val, 2),
                            "description": f"MFI={mfi_val:.1f}, 자금 유출 과다 (반등 기대)"})
        elif mfi_val > 80:
            signals.append({"indicator": "MFI (14)", "signal": "sell",
                            "value": round(mfi_val, 2),
                            "description": f"MFI={mfi_val:.1f}, 자금 유입 과다 (과열)"})
        else:
            signals.append({"indicator": "MFI (14)", "signal": "neutral",
                            "value": round(mfi_val, 2),
                            "description": f"MFI={mfi_val:.1f}, 중립"})

    # 9. Parabolic SAR - NEW
    sar = last.get("SAR")
    if _valid(sar) and close > 0:
        sar_val = float(sar)
        if close > sar_val:
            signals.append({"indicator": "Parabolic SAR", "signal": "buy",
                            "value": round(sar_val, 2),
                            "description": f"현재가가 SAR({round(sar_val):,}) 위, 상승 추세"})
        else:
            signals.append({"indicator": "Parabolic SAR", "signal": "sell",
                            "value": round(sar_val, 2),
                            "description": f"현재가가 SAR({round(sar_val):,}) 아래, 하락 추세"})

    # 10. Candlestick Patterns - NEW
    cdl_signals = []
    if last.get("CDL_HAMMER", 0) != 0:
        cdl_signals.append(("망치형", "buy", "반전 상승 패턴"))
    if last.get("CDL_ENGULFING", 0) > 0:
        cdl_signals.append(("상승 장악형", "buy", "강한 매수 반전 패턴"))
    elif last.get("CDL_ENGULFING", 0) < 0:
        cdl_signals.append(("하락 장악형", "sell", "강한 매도 반전 패턴"))
    if last.get("CDL_MORNINGSTAR", 0) != 0:
        cdl_signals.append(("모닝스타", "buy", "바닥 반전 패턴"))
    if last.get("CDL_EVENINGSTAR", 0) != 0:
        cdl_signals.append(("이브닝스타", "sell", "천장 반전 패턴"))
    if last.get("CDL_DOJI", 0) != 0:
        cdl_signals.append(("도지", "neutral", "추세 전환 가능성"))

    if cdl_signals:
        names = ", ".join(c[0] for c in cdl_signals)
        # Use first pattern's signal direction
        signals.append({"indicator": "캔들스틱 패턴", "signal": cdl_signals[0][1],
                        "value": 0,
                        "description": f"감지된 패턴: {names}"})

    return signals


def _valid(*values) -> bool:
    """Check if all values are not NaN/None"""
    for v in values:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return False
        try:
            if pd.isna(v):
                return False
        except (TypeError, ValueError):
            pass
    return True
