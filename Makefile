# ─────────────────────────────────────────────────────────────────────────────
# DocForge — named one-liners over the compose/ scenario files. Every target is just the
# exact `docker compose -f ... up -d` line spelled out — see compose/README.md for the full
# usage matrix and when to use each scenario / add-on.
# ─────────────────────────────────────────────────────────────────────────────

COMPOSE       := docker compose
PROFILE       := --profile full

SCENARIO_DIR  := compose
PROXY         := $(SCENARIO_DIR)/overlays/proxy.yml
TELEMETRY     := $(SCENARIO_DIR)/overlays/telemetry.yml

.PHONY: up-prod-cpu up-prod-gpu up-dev-cpu up-dev-gpu \
        up-prod-cpu-proxy up-prod-gpu-proxy up-dev-cpu-proxy up-dev-gpu-proxy \
        up-prod-cpu-telemetry up-prod-gpu-telemetry up-dev-cpu-telemetry up-dev-gpu-telemetry \
        down-prod-cpu down-prod-gpu down-dev-cpu down-dev-gpu \
        logs config-check-all

# ── Plain scenarios ──────────────────────────────────────────────────────────
up-prod-cpu:
	$(COMPOSE) -f $(SCENARIO_DIR)/prod-cpu.yml $(PROFILE) up -d

up-prod-gpu:
	$(COMPOSE) -f $(SCENARIO_DIR)/prod-gpu.yml $(PROFILE) up -d

up-dev-cpu:
	$(COMPOSE) -f $(SCENARIO_DIR)/dev-cpu.yml $(PROFILE) up -d --build

up-dev-gpu:
	$(COMPOSE) -f $(SCENARIO_DIR)/dev-gpu.yml $(PROFILE) up -d --build

# ── + TLS proxy add-on ───────────────────────────────────────────────────────
up-prod-cpu-proxy:
	$(COMPOSE) -f $(SCENARIO_DIR)/prod-cpu.yml -f $(PROXY) $(PROFILE) up -d

up-prod-gpu-proxy:
	$(COMPOSE) -f $(SCENARIO_DIR)/prod-gpu.yml -f $(PROXY) $(PROFILE) up -d

up-dev-cpu-proxy:
	$(COMPOSE) -f $(SCENARIO_DIR)/dev-cpu.yml -f $(PROXY) $(PROFILE) up -d --build

up-dev-gpu-proxy:
	$(COMPOSE) -f $(SCENARIO_DIR)/dev-gpu.yml -f $(PROXY) $(PROFILE) up -d --build

# ── + telemetry add-on (Prometheus/Loki/Promtail/Grafana) ───────────────────
up-prod-cpu-telemetry:
	$(COMPOSE) -f $(SCENARIO_DIR)/prod-cpu.yml -f $(TELEMETRY) $(PROFILE) up -d

up-prod-gpu-telemetry:
	$(COMPOSE) -f $(SCENARIO_DIR)/prod-gpu.yml -f $(TELEMETRY) $(PROFILE) up -d

up-dev-cpu-telemetry:
	$(COMPOSE) -f $(SCENARIO_DIR)/dev-cpu.yml -f $(TELEMETRY) $(PROFILE) up -d --build

up-dev-gpu-telemetry:
	$(COMPOSE) -f $(SCENARIO_DIR)/dev-gpu.yml -f $(TELEMETRY) $(PROFILE) up -d --build

# ── Teardown (add -f compose/overlays/proxy.yml / telemetry.yml manually if you layered them) ──
down-prod-cpu:
	$(COMPOSE) -f $(SCENARIO_DIR)/prod-cpu.yml $(PROFILE) down

down-prod-gpu:
	$(COMPOSE) -f $(SCENARIO_DIR)/prod-gpu.yml $(PROFILE) down

down-dev-cpu:
	$(COMPOSE) -f $(SCENARIO_DIR)/dev-cpu.yml $(PROFILE) down

down-dev-gpu:
	$(COMPOSE) -f $(SCENARIO_DIR)/dev-gpu.yml $(PROFILE) down

# ── Operator helpers ─────────────────────────────────────────────────────────
logs:
	$(COMPOSE) -f $(SCENARIO_DIR)/prod-cpu.yml $(PROFILE) logs -f

# Validation gate: every scenario file, alone and combined with every add-on, must resolve to
# valid config. Run this after touching anything under compose/.
config-check-all:
	@set -e; \
	for scenario in prod-cpu prod-gpu dev-cpu dev-gpu; do \
		for addons in "" "-f $(PROXY)" "-f $(TELEMETRY)" "-f $(PROXY) -f $(TELEMETRY)"; do \
			echo "== $$scenario $$addons =="; \
			DOCFORGE_DOMAIN=example.com DOCFORGE_ACME_EMAIL=ops@example.com \
			$(COMPOSE) -f $(SCENARIO_DIR)/$$scenario.yml $$addons $(PROFILE) config -q && echo OK; \
		done; \
	done
