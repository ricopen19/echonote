"""設定管理 — プラットフォーム・HWティア検出と環境変数ベースの設定。"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from enum import Enum

import psutil


class Platform(str, Enum):
    MAC = "mac"
    WINDOWS = "windows"
    LINUX = "linux"


class HWTier(str, Enum):
    LIGHT = "light"        # ~8GB RAM
    STANDARD = "standard"  # ~16GB RAM
    PERFORMANCE = "performance"  # 32GB+ RAM


_TIER_MODELS = {
    HWTier.LIGHT: "small",
    HWTier.STANDARD: "medium",
    HWTier.PERFORMANCE: "large-v3-turbo",
}

_DEFAULT_LLM_URL = {
    Platform.MAC: "http://localhost:8080/v1",
    Platform.WINDOWS: "http://localhost:11434/v1",
    Platform.LINUX: "http://localhost:11434/v1",
}

_DEFAULT_LLM_MODEL = {
    HWTier.LIGHT: "qwen3:1.7b",
    HWTier.STANDARD: "qwen3:4b-q4_K_M",
    HWTier.PERFORMANCE: "qwen3:14b-q4_K_M",
}


@dataclass
class Settings:
    platform: Platform
    hw_tier: HWTier
    default_whisper_model: str
    llm_url: str
    llm_model: str
    hf_token: str
    language: str = "ja"
    # UI からの上書き値（UI入力 > 環境変数 > デフォルト）
    ui_overrides: dict = field(default_factory=dict)

    def effective_llm_url(self) -> str:
        return self.ui_overrides.get("llm_url", self.llm_url)

    def effective_llm_model(self) -> str:
        return self.ui_overrides.get("llm_model", self.llm_model)

    def effective_hf_token(self) -> str:
        return self.ui_overrides.get("hf_token", self.hf_token)

    def effective_language(self) -> str:
        return self.ui_overrides.get("language", self.language)


def _detect_platform() -> Platform:
    if sys.platform == "darwin":
        return Platform.MAC
    if sys.platform == "win32":
        return Platform.WINDOWS
    return Platform.LINUX


def _detect_hw_tier() -> HWTier:
    override = os.environ.get("ECHONOTE_HW_TIER", "").lower()
    if override in (t.value for t in HWTier):
        return HWTier(override)
    ram_gb = psutil.virtual_memory().total / (1024 ** 3)
    if ram_gb < 10:
        return HWTier.LIGHT
    if ram_gb < 20:
        return HWTier.STANDARD
    return HWTier.PERFORMANCE


def load_settings() -> Settings:
    platform = _detect_platform()
    hw_tier = _detect_hw_tier()
    return Settings(
        platform=platform,
        hw_tier=hw_tier,
        default_whisper_model=_TIER_MODELS[hw_tier],
        llm_url=os.environ.get("ECHONOTE_LLM_URL", _DEFAULT_LLM_URL[platform]),
        llm_model=os.environ.get("ECHONOTE_LLM_MODEL", _DEFAULT_LLM_MODEL[hw_tier]),
        hf_token=os.environ.get("HF_TOKEN", ""),
        language=os.environ.get("ECHONOTE_LANGUAGE", "ja"),
    )
