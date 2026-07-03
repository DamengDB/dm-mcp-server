@echo off
REM Windows 测试运行脚本

echo ==========================================
echo 运行单元测试
echo ==========================================

REM 运行所有测试
python -m pytest tests/unit/ -v

echo.
echo ==========================================
echo 生成覆盖率报告
echo ==========================================

REM 生成覆盖率报告
python -m pytest --cov=src/dm_mcp --cov-report=html --cov-report=term

echo.
echo ==========================================
echo 测试完成！
echo 覆盖率报告已生成到 htmlcov/index.html
echo ==========================================
pause

