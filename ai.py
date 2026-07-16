"""로컬 Ollama 서버 호출 모듈.

OpenAI API나 API Key 없이, localhost:11434에서 실행 중인 Ollama만 사용한다.
"""

import requests

from prompts import build_meeting_summary_prompt

OLLAMA_BASE_URL = "http://localhost:11434"
TAGS_TIMEOUT = 5  # 모델 목록 조회는 가벼우니 짧게
GENERATE_TIMEOUT = 180  # 긴 회의록 요약은 오래 걸릴 수 있어 넉넉하게


class OllamaConnectionError(Exception):
    """Ollama 서버 자체에 연결할 수 없을 때 발생한다."""


class OllamaGenerationError(Exception):
    """연결은 됐지만 응답 생성 과정에서 문제가 생겼을 때 발생한다."""


def get_available_models() -> list[str]:
    """로컬에 설치된 Ollama 모델 이름 목록을 반환한다.

    Ollama가 꺼져 있거나 응답이 없으면 예외를 던지지 않고 빈 리스트를 반환한다
    (앱 UI는 이 경우를 직접 안내 메시지로 처리한다).
    """
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=TAGS_TIMEOUT)
        response.raise_for_status()
    except requests.exceptions.RequestException:
        return []

    data = response.json()
    return [model["name"] for model in data.get("models", [])]


def generate(model: str, prompt: str, timeout: int = GENERATE_TIMEOUT) -> str:
    """Ollama의 /api/generate를 호출해 완성된 텍스트 응답을 반환한다.

    스트리밍 없이(stream=False) 한 번에 전체 응답을 받는다 — 결과를 Markdown
    섹션으로 파싱해야 하므로 부분 응답보다 완성된 응답이 다루기 쉽다.
    """
    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.exceptions.ConnectionError as exc:
        raise OllamaConnectionError(
            "Ollama 서버에 연결할 수 없어요. 터미널에서 'ollama serve'가 실행 중인지 확인해주세요."
        ) from exc
    except requests.exceptions.Timeout as exc:
        raise OllamaGenerationError(
            f"{timeout}초 안에 응답을 받지 못했어요. 회의록을 더 짧게 나누거나 "
            "더 가벼운 모델로 다시 시도해보세요."
        ) from exc
    except requests.exceptions.HTTPError as exc:
        raise OllamaGenerationError(
            f"'{model}' 모델 호출에 실패했어요. "
            f"설치되어 있는지 확인해주세요 (터미널에서 'ollama pull {model}')."
        ) from exc

    try:
        data = response.json()
    except ValueError as exc:
        raise OllamaGenerationError("Ollama 응답을 해석하지 못했어요. 잠시 후 다시 시도해주세요.") from exc

    return data.get("response", "").strip()


def summarize_meeting(transcript: str, model: str) -> str:
    """회의록 원문을 받아 구조화된 Markdown 요약 결과를 반환한다."""
    prompt = build_meeting_summary_prompt(transcript)
    return generate(model=model, prompt=prompt)
