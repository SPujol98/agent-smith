# Compiler / Tools
UV = uv

# Main entrypoints / configs
CLI_SANDBOX = sandbox_template.json
MAIN_MBPP    = agent_mbpp.py
MAIN_SWEB    = agent_swebench.py
SRC_DIRS = agent_smith tests
SRC_FILES = agent_mbpp.py agent_swebench.py mcp_tools_mbpp.py mcp_tools_swebench.py main.py
ALL_PYTHON_TARGETS = $(SRC_DIRS) $(wildcard $(SRC_FILES))

# Marker file: touched by install, checked by everything else
INSTALL_MARKER = .venv/.installed

# MyPy Flags
MYPY_FLAGS = --warn-return-any --warn-unused-ignores --ignore-missing-imports \
             --disallow-untyped-defs --check-untyped-defs --exclude .venv

# Terminal colors
GREEN = \033[0;32m
CYAN  = \033[0;36m
RED   = \033[0;31m
NC    = \033[0m

.PHONY: all install run run-mbpp run-swebench debug clean lint lint-strict test check-install

all: run

install:
	$(UV) sync
	@touch $(INSTALL_MARKER)
	@echo "$(GREEN)Install completed.$(NC)"

check-install:
	@test -f $(INSTALL_MARKER) || \
		(echo "$(RED)Dependencies not installed. Run 'make install' first.$(NC)" && exit 1)

run: check-install
	$(UV) run sandbox $(CLI_SANDBOX)

run-mbpp: check-install
	$(UV) run python3 $(MAIN_MBPP) --help

run-swebench: check-install
	$(UV) run python3 $(MAIN_SWEB) --help

debug: check-install
	$(UV) run python3 -m pdb -m agent_smith.sandbox.cli $(CLI_SANDBOX)

test: check-install
	$(UV) run python -m pytest -v -s -o pythonpath=. tests/

lint: check-install
	@echo "$(CYAN)Executing flake8...$(NC)"
	$(UV) run flake8 $(ALL_PYTHON_TARGETS)
	@echo "$(CYAN)Executing mypy...$(NC)"
	$(UV) run mypy $(ALL_PYTHON_TARGETS) $(MYPY_FLAGS)

lint-strict: check-install
	@echo "$(CYAN)Executing flake8...$(NC)"
	$(UV) run flake8 $(ALL_PYTHON_TARGETS)
	@echo "$(CYAN)Executing mypy strict...$(NC)"
	$(UV) run mypy $(ALL_PYTHON_TARGETS) --exclude .venv --strict --ignore-missing-imports

clean:
	@echo "$(CYAN)Cleaning temporary files...$(NC)"
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf .venv