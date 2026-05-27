"""Setup ambiente di test: settings minime, no DB richiesto per gran parte dei test unitari."""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "")  # non chiamiamo davvero il provider
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("GOOGLE_API_KEY", "")
os.environ.setdefault("DEEPSEEK_API_KEY", "")
