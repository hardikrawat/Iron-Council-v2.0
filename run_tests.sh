#!/bin/bash
# Iron Council Phased Test Runner
# Phase 1: Parallel Non-LLM Tests (Fast)
# Phase 2: Sequential LLM Tests (GPU Safe)

VENV_PYTEST="./venv_stable/bin/pytest"

echo "🚀 Starting Phase 1: Parallel Non-LLM Tests..."
$VENV_PYTEST -m "not llm" -n auto

if [ $? -eq 0 ]; then
    echo "✅ Phase 1 Passed. Starting Phase 2: Sequential LLM Tests..."
    $VENV_PYTEST -m "llm" -n 0
    
    if [ $? -eq 0 ]; then
        echo "✨ All tests passed! Detailed report generated: assets/report.html"
    else
        echo "⚠️ Some sequential tests failed. Check assets/report.html for details."
    fi
else
    echo "❌ Phase 1 Failed. Skipping Phase 2."
    echo "Check assets/report.html for details."
    exit 1
fi
