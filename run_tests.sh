#!/bin/bash
# Iron Council Phased Test Runner
# Phase 1: Parallel Non-LLM Tests (Fast)
# Phase 2: Sequential LLM Tests (GPU Safe)

VENV_PYTEST="./venv_stable/bin/pytest"

echo "🚀 Starting Phase 1: Parallel Non-LLM Tests..."
$VENV_PYTEST -m "not llm" -n auto --html=assets/report_fast.html

if [ $? -eq 0 ]; then
    echo "✅ Phase 1 Passed. Starting Phase 2: Sequential LLM Tests..."
    $VENV_PYTEST -m "llm" -n 0 --html=assets/report_llm.html
    
    if [ $? -eq 0 ]; then
        echo "✨ All tests passed!"
        echo "   - Fast Report: assets/report_fast.html"
        echo "   - LLM Report:  assets/report_llm.html"
    else
        echo "⚠️ Some sequential tests failed."
        echo "   - Check assets/report_llm.html for details."
    fi
else
    echo "❌ Phase 1 Failed. Skipping Phase 2."
    echo "Check assets/report_fast.html for details."
    exit 1
fi
