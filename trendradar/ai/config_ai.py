"""Configuracion de proveedores de IA para TrendRadar."""

import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[2]


def _read_secret_file(path: Path) -> str | None:
    """Lee archivos con formato VAR=valor o solo valor."""
    if not path.exists():
        return None

    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return None

    if "=" in raw:
        return raw.split("=", 1)[1].strip()
    return raw


def _split_models(value: str | None, fallback: list[str]) -> list[str]:
    if not value:
        return fallback
    models = [item.strip() for item in value.split(",") if item.strip()]
    return models or fallback


def load_ai_credentials() -> dict:
    """Carga credenciales desde .env, variables del sistema o archivos locales."""
    load_dotenv(BASE_DIR / ".env")

    groq_env_path = BASE_DIR / "GROQ_API_KEY.env"
    hf_env_path = BASE_DIR / "HF_API_KEY.env"

    if groq_env_path.exists():
        load_dotenv(groq_env_path)
    if hf_env_path.exists():
        load_dotenv(hf_env_path)

    groq_key = (os.getenv("GROQ_API_KEY") or _read_secret_file(groq_env_path) or "").strip()
    hf_key = (os.getenv("HF_API_KEY") or _read_secret_file(hf_env_path) or "").strip()

    groq_models = _split_models(
        os.getenv("GROQ_MODELS") or os.getenv("GROQ_MODEL"),
        ["llama-3.3-70b-versatile", "llama3-70b-8192"],
    )

    return {
        "groq_api_key": groq_key or None,
        "hf_api_key": hf_key or None,
        "groq_models": groq_models,
        "groq_model": groq_models[0],
        "hf_model": os.getenv("HF_MODEL", "mistralai/Mistral-7B-Instruct-v0.2"),
    }


AI_CONFIG = load_ai_credentials()
