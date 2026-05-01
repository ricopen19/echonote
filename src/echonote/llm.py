"""OpenAI互換 LLM クライアント。Ollama / mlx-lm サーバーを想定。"""

from __future__ import annotations

import json
from collections.abc import Generator

import requests

_CONNECT_TIMEOUT = 5
_READ_TIMEOUT = 180


class LLMConnectionError(Exception):
    """LLM サーバーに接続できない場合。"""


class LLMError(Exception):
    """LLM からエラーレスポンスが返った場合。"""


def check_endpoint(base_url: str) -> bool:
    """エンドポイントに到達できるか確認する。"""
    try:
        resp = requests.get(
            f"{base_url.rstrip('/')}/models",
            timeout=_CONNECT_TIMEOUT,
        )
        return resp.status_code == 200
    except requests.exceptions.ConnectionError:
        return False
    except requests.exceptions.Timeout:
        return False


def _raise_if_unreachable(base_url: str) -> None:
    if not check_endpoint(base_url):
        raise LLMConnectionError(
            f"LLM サーバーに接続できません ({base_url})。\n"
            "  Ollama: ollama serve\n"
            "  mlx-lm: uv run mlx_lm.server --model <モデル名>"
        )


def complete(
    prompt: str,
    base_url: str,
    model: str,
    stream: bool = True,
) -> Generator[str, None, None]:
    """プロンプトを送信してレスポンスをストリーミングで yield する。"""
    _raise_if_unreachable(base_url)

    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": stream,
    }

    try:
        with requests.post(
            url,
            json=payload,
            stream=stream,
            timeout=(_CONNECT_TIMEOUT, _READ_TIMEOUT),
        ) as resp:
            if resp.status_code != 200:
                raise LLMError(f"LLM エラー (HTTP {resp.status_code}): {resp.text[:200]}")

            if not stream:
                data = resp.json()
                yield data["choices"][0]["message"]["content"]
                return

            for line in resp.iter_lines():
                if not line:
                    continue
                text = line.decode("utf-8")
                if not text.startswith("data: "):
                    continue
                payload_str = text[6:]
                if payload_str.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(payload_str)
                    delta = chunk["choices"][0]["delta"].get("content", "")
                    if delta:
                        yield delta
                except (json.JSONDecodeError, KeyError):
                    continue

    except requests.exceptions.ConnectionError as e:
        raise LLMConnectionError(f"LLM サーバーへの接続が切れました: {e}") from e
    except requests.exceptions.Timeout as e:
        raise LLMError(f"LLM レスポンスがタイムアウトしました ({_READ_TIMEOUT}s)") from e
