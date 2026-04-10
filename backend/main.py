"""
StockPick Quant API Server
FastAPI application with market data, technical analysis, backtesting, and factor analysis
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import market, analysis, backtest, factor, screener, trading, scalping, auto_scalping, journal, analyzer
import logging
import asyncio
from services.kiwoom_ws import kiwoom_ws_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

app = FastAPI(
    title="StockPick Quant API",
    description="한국 주식 시장 퀀트 분석 API — 실시간 시세, 기술적 분석, 백테스팅, 팩터 분석",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS - Allow frontend dev server and common local origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:5500",
        "http://localhost:8080",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5500",
        "http://127.0.0.1:8080",
        "*", # Fallback for local dev
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(market.router)
app.include_router(analysis.router)
app.include_router(backtest.router)
app.include_router(factor.router)
app.include_router(screener.router)
app.include_router(trading.router)
app.include_router(scalping.router)
app.include_router(auto_scalping.router)
app.include_router(journal.router)
app.include_router(analyzer.router)

async def _warm_cache():
    """Pre-fetch market data on startup so the first user request is instant."""
    try:
        from services.data_collector import get_top_stocks, get_market_indices, get_krx_stock_list
        loop = asyncio.get_event_loop()
        # Warm all caches in parallel (stock list + top 30 stocks + indices)
        list_future = loop.run_in_executor(None, get_krx_stock_list)
        top_future = loop.run_in_executor(None, get_top_stocks, 30)
        idx_future = loop.run_in_executor(None, get_market_indices)
        
        stock_list = await list_future
        top_stocks = await top_future
        indices = await idx_future
        
        logging.info(f"Cache warmed: {len(stock_list)} listed, {len(top_stocks)} top stocks, {len(indices)} indices")

        # Subscribe to WS if available
        codes = [s["code"] for s in top_stocks]
        if codes and kiwoom_ws_manager.connected:
            await kiwoom_ws_manager.subscribe_stocks(codes)
            logging.info(f"Subscribed to RT execution for {len(codes)} top stocks.")
    except Exception as e:
        logging.error(f"Cache warming failed (non-fatal): {e}")

@app.on_event("startup")
async def startup_event():
    # Run the Kiwoom WebSocket background task
    asyncio.create_task(kiwoom_ws_manager.run())
    # Warm cache immediately (non-blocking)
    asyncio.create_task(_warm_cache())

@app.on_event("shutdown")
async def shutdown_event():
    await kiwoom_ws_manager.disconnect()


@app.get("/health")
async def health():
    return {"status": "ok", "ai_model": "claude-opus-4-20250514"}

@app.get("/")
async def root():
    return {
        "name": "StockPick Quant API",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": {
            "market": "/api/market",
            "analysis": "/api/analysis",
            "backtest": "/api/backtest",
            "factor": "/api/factor",
            "trading": "/api/trading",
            "scalping": "/api/scalping",
            "auto_scalping": "/api/auto-scalping",
            "journal": "/api/journal",
            "analyzer": "/api/analyzer",
        },
    }
