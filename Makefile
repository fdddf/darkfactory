.PHONY: demo run verify replay selftest quarantine seed platform dev api build reset clean

demo: clean
	@python3 -m darkfactory.cli run --all
	@echo
	@python3 -m darkfactory.cli verify

run:
	@python3 -m darkfactory.cli run --all

verify:
	@python3 -m darkfactory.cli verify

replay:
	@python3 -m darkfactory.cli replay $(BUG) -v

tamper:
	@python3 -c "from pathlib import Path; p=Path('audit/trail.jsonl'); p.write_text(p.read_text().replace('rejected','cleared',1))"
	@python3 -m darkfactory.cli verify || true

selftest:
	@python3 selftest.py

# Real PHPUnit against the checkout in wp/
real:
	@python3 -m darkfactory.cli run --all --runner phpunit --repo wp

# Find tests that cannot serve as an oracle. SEL=tests/phpunit/tests/formatting
quarantine:
	@python3 -m darkfactory.cli quarantine $(SEL) --repo wp --rounds 3

# The platform. Build once, then serve the React app and the API together.
platform: build
	@python3 -m darkfactory.cli serve --repo wp --runner phpunit

# Frontend on Vite with hot reload, API proxied to the Python service.
# Run `make api` in another shell.
dev:
	@cd web && npm run dev

api:
	@python3 -m darkfactory.cli serve --repo wp --runner phpunit

build:
	@cd web && npm install --no-fund --no-audit --silent && npm run build

seed:
	@python3 -m darkfactory.cli seed --repo wp

# Back to a clean stage. Keeps repositories and credentials - only the
# trail and the scan history go.
reset:
	@python3 -m darkfactory.cli reset

clean:
	@rm -rf audit
