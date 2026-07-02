"""Gemini Live voice agent configuration."""

from __future__ import annotations

import os

from .gemini_tools import get_function_declarations
from .prompts import SYSTEM_PROMPT


def get_gemini_api_key() -> str:
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        raise ValueError("GEMINI_API_KEY environment variable is required")
    return key


def get_live_model() -> str:
    model = os.getenv(
        "GEMINI_LIVE_MODEL", "gemini-2.5-flash-native-audio-preview-12-2025"
    )
    if not model.startswith("models/"):
        model = f"models/{model}"
    return model


def get_live_config() -> dict:
    """Live API session config for CLI / SDK usage."""
    voice = os.getenv("GEMINI_VOICE", "Aoede")
    return {
        "response_modalities": ["AUDIO"],
        "system_instruction": SYSTEM_PROMPT,
        "tools": get_function_declarations(),
        "speech_config": {
            "voice_config": {
                "prebuilt_voice_config": {"voice_name": voice},
            },
        },
    }
