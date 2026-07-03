# 简单的测试运行脚本（PowerShell）
# 用于避免路径规范化问题

# 切换到项目根目录
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

# 运行测试，使用最简单的配置
python -m pytest tests/unit/services/test_base_service.py -v --no-cov

