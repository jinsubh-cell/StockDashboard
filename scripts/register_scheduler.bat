@echo off
REM ============================================================
REM  Windows 작업 스케줄러 등록 (관리자 권한 필요)
REM  평일 08:55에 자동매매 시작 스크립트 실행
REM  (9시 동시호가 직후 바로 매매 시작 가능하도록 5분 전 실행)
REM ============================================================

set TASK_NAME=StockDashboard_AutoTrade_Start
set SCRIPT_PATH=C:\Users\jinsu\vibecording\StockDashboard\scripts\start_autotrade.bat

echo 작업명: %TASK_NAME%
echo 스크립트: %SCRIPT_PATH%
echo 스케줄: 평일 (월~금) 오전 08:55
echo.

REM 기존 작업 삭제 (있으면)
schtasks /Delete /TN "%TASK_NAME%" /F >nul 2>&1

REM 작업 생성
schtasks /Create ^
    /TN "%TASK_NAME%" ^
    /TR "\"%SCRIPT_PATH%\"" ^
    /SC WEEKLY ^
    /D MON,TUE,WED,THU,FRI ^
    /ST 08:55 ^
    /RL HIGHEST ^
    /F

if %errorlevel% equ 0 (
    echo.
    echo ✓ 작업 등록 완료: %TASK_NAME%
    echo 다음 실행 확인:
    schtasks /Query /TN "%TASK_NAME%" /V /FO LIST | findstr /C:"다음 실행 시간" /C:"Next Run Time"
) else (
    echo.
    echo ✗ 작업 등록 실패 - 관리자 권한으로 실행하세요
    echo   [우클릭 → 관리자 권한으로 실행]
    pause
)
