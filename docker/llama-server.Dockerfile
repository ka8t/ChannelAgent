# Minimal runtime for a prebuilt llama-server binary (#21, production
# VPS topology). The binary and model are bind-mounted in (see
# docker-compose.prod.yml), not COPYed into the image, so updating
# either needs no rebuild — just replacing the file and restarting the
# service.
#
# Containerized llama-server, not Ollama/vLLM: mirrors the legacy
# Hermes project's own production setup (same binary, same flags,
# same OpenAI-compatible endpoint app/graph.py already talks to). That
# choice there followed a real incident — Hermes previously ran
# llama-swap in front of llama-server for a "swap models at runtime"
# feature this project never uses, and llama-swap's own separate,
# untracked update lifecycle let a VPS silently run a two-week-stale
# llama-server through it. A single always-loaded model needs none of
# that, so a plain runtime for the same binary loses nothing.
#
# ubuntu:24.04: matches the glibc/libstdc++ ABI the official llama.cpp
# ubuntu-x64 prebuilt release is built against.
FROM ubuntu:24.04

# ca-certificates: TLS trust store (unused at runtime once a model is
# loaded locally — kept only in case a future --hf-repo flag needs it).
# curl: this Dockerfile's own HEALTHCHECK. libgomp1: llama.cpp's CPU
# backend uses OpenMP for multi-threading.
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl libgomp1 \
    && rm -rf /var/lib/apt/lists/*

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=20 \
    CMD curl -sf http://localhost:8080/health || exit 1
