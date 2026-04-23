@echo off
REM ============================================================
REM  스톡대시보드 자동매매 시작 스크립트
REM  평일 오전 9시 Windows 작업 스케줄러에 의해 실행됨
REM ============================================================
setlocal enabledelayedexpansion

set PROJECT_DIR=C:\Users\jinsu\vibecording\StockDashboard
set LOG_DIR=%PROJECT_DIR%\logs
set LOG_FILE=%LOG_DIR%\autotrade_%date:~0,4%%date:~5,2%%date:~8,2%.log
set BACKEND_URL=http://localhost:8000

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo ============================================================ >> "%LOG_FILE%"
echo [%date% %time%] 자동매매 시작 스크립트 실행 >> "%LOG_FILE%"
echo ============================================================ >> "%LOG_FILE%"

REM 1. 공휴일 체크 (간단 - 토/일 제외는 작업스케줄러가 처리)
REM   상세 공휴일 체크는 Python 스크립트로 처리 (아래)
python "%PROJECT_DIR%\scripts\check_market_day.py" >> "%LOG_FILE%" 2>&1
if %errorlevel% neq 0 (
    echo [%date% %time%] 오늘은 장이 열리지 않음 - 스킵 >> "%LOG_FILE%"
    exit /b 0
)

REM 2. 백엔드 상태 확인 (최대 10회 재시도)
echo [%date% %time%] 백엔드 상태 확인 중... >> "%LOG_FILE%"
set /a retry=0
:check_backend
curl -s -o nul -w "%%{http_code}" %BACKEND_URL%/api/auto-scalping/status > tmp_status.txt 2>nul
set /p STATUS=<tmp_status.txt
del tmp_status.txt 2>nul

if "%STATUS%"=="200" (
    echo [%date% %time%] 백엔드 정상 ^(HTTP 200^) >> "%LOG_FILE%"
    goto backend_ok
)

set /a retry+=1
if %retry% geq 3 (
    echo [%date% %time%] 백엔드 미실행 감지 - 백엔드 자동 시작 >> "%LOG_FILE%"
    REM 백엔드 시작 (detached)
    start "StockDashboard-Backend" /min cmd /c "cd /d %PROJECT_DIR% && python -m uvicorn main:app --reload --port 8000 --app-dir backend >> %LOG_DIR%\backend.log 2>&1"
    echo [%date% %time%] 백엔드 시작됨, 20초 대기... >> "%LOG_FILE%"
    timeout /t 20 /nobreak > nul
    set /a retry=0
    goto check_backend
)

timeout /t 3 /nobreak > nul
goto check_backend

:backend_ok

REM 3. 자동매매 시작 API 호출
echo [%date% %time%] 자동매매 start API 호출 >> "%LOG_FILE%"
curl -s -X POST %BACKEND_URL%/api/auto-scalping/start >> "%LOG_FILE%" 2>&1
echo. >> "%LOG_FILE%"

REM 4. 10초 대기 후 상태 확인
timeout /t 10 /nobreak > nul
echo [%date% %time%] 자동매매 상태 확인 >> "%LOG_FILE%"
curl -s %BACKEND_URL%/api/auto-scalping/status >> "%LOG_FILE%" 2>&1
echo. >> "%LOG_FILE%"

echo [%date% %time%] ✓ 자동매매 시작 완료 >> "%LOG_FILE%"
echo ============================================================ >> "%LOG_FILE%"

endlocal
exit /b 0
