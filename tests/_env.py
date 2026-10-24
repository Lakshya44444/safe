"""Imported first by every test module: isolated data dir and the offline mock LLM."""

import os
import tempfile

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="kachra-test-")
os.environ["GRADER_PROVIDER"] = "mock"
os.environ["LLM_FALLBACKS"] = ""
os.environ.pop("LANGSMITH_TRACING", None)
for key in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY", "RENDER_WORKFLOW_SLUG"):
    os.environ.pop(key, None)
os.environ["LOG_LEVEL"] = "WARNING"
