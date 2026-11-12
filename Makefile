.DEFAULT_GOAL := help

# Each Prism process serves one OpenAPI specification.
SERVICE ?= fns
HOST ?= 127.0.0.1
PORT ?= 4010
DYNAMIC ?= 0
PRISM_VERSION ?= 5.5.0
PRISM_FLAGS ?=

SERVICES := fns rosstat banks scoring procurement arbitration fssp spk

.PHONY: help prism $(addprefix prism-,$(SERVICES)) sync check test build push

help:
	@printf '%s\n' \
		'make prism [SERVICE=fns] [PORT=4010] [HOST=127.0.0.1] [DYNAMIC=1]' \
		'make prism-<service> [PORT=4010] [HOST=127.0.0.1] [DYNAMIC=1]' \
		'Services: $(SERVICES)' \
		'Press Ctrl+C to stop the server.' \
		'make sync  - install project and development dependencies' \
		'make test  - run tests (Prism tests require RUN_PRISM_TESTS=1)' \
		'make check - run lint, formatting, type checks and tests' \
		'make build - build distributions in dist/' \
		'make push  - check, build and publish the current version to PyPI'

prism:
	@case "$(SERVICE)" in \
		fns|rosstat|banks|scoring|procurement|arbitration|fssp|spk) ;; \
		*) printf '%s\n' 'Unknown SERVICE: $(SERVICE). Choose: $(SERVICES)' >&2; exit 1 ;; \
	esac
	@case "$(DYNAMIC)" in 0|1) ;; *) printf '%s\n' 'DYNAMIC must be 0 or 1.' >&2; exit 1 ;; esac
	@npx --yes @stoplight/prism-cli@$(PRISM_VERSION) mock \
		"docs/swagger/$(SERVICE)/openapi.yaml" \
		--host "$(HOST)" --port "$(PORT)" $(if $(filter 1,$(DYNAMIC)),--dynamic,) $(PRISM_FLAGS)

$(addprefix prism-,$(SERVICES)):
	@$(MAKE) --no-print-directory prism SERVICE=$(patsubst prism-%,%,$@)

sync:
	uv sync --locked

test:
	uv run --locked pytest

check:
	uv run --locked ruff check src tests
	uv run --locked ruff format --check src tests
	uv run --locked mypy
	uv run --locked pytest

build:
	uv build

# Build in a fresh temporary directory so stale files in dist/ cannot be uploaded.
push: check
	@set -eu; \
	build_dir=$$(mktemp -d); \
	trap 'rm -rf "$$build_dir"' EXIT HUP INT TERM; \
	uv build --out-dir "$$build_dir"; \
	uv publish "$$build_dir"/*
