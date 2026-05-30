@echo off
chcp 65001 > nul
setlocal enabledelayedexpansion

echo ===================================================
echo   kencom 歩数自動入力スクリプト 起動バッチ
echo ===================================================
echo.

:: uv の存在確認
where uv >nul 2>nul
if %errorlevel% neq 0 (
    echo [!] 警告: 'uv' コマンドが見つかりません。
    echo     Python仮想環境を使用して直接実行を試みます...
    
    if exist ".venv\Scripts\python.exe" (
        .venv\Scripts\python.exe kencom_auto_fill.py %*
    ) else (
        echo [-] エラー: .venv が見つかりません。
        echo     README.md に従って環境構築を行ってください。
        pause
        exit /b 1
    )
) else (
    echo [*] 'uv' を使用してスクリプトを実行します...
    uv run python kencom_auto_fill.py %*
)

echo.
echo ===================================================
echo   処理が終了しました。
echo ===================================================
pause
