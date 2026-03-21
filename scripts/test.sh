#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../backend"
pytest tests/ -v --tb=short
