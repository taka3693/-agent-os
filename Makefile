# Agent-OS Makefile
#
# Usage:
#   make safety   - Run guard safety tests

.PHONY: safety

safety:
	python3 -m pytest -m safety -q
