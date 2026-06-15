"""
LLM configuration for Level 2 sanity checks.
Default: local llama-server at localhost:8080.
Override via environment variables or direct assignment.
"""
import os

# LLM Settings — override via env vars or edit directly
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:8080/v1")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "not-needed")  # local server doesn't need a key
LLM_MODEL = os.environ.get("LLM_MODEL", "LOCAL")
LLM_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "4096"))
LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0.1"))
