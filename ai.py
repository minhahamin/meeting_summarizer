"""AI 제공자(provider) 호출 모듈.

app.py는 provider가 무엇인지 몰라도 되도록 summarize_meeting() 하나만 호출한다.
실제로 어떤 클라이언트를 쓸지는 get_client()가 MEMOMATE_PROVIDER 환경변수를
보고 결정한다 — 개발 중에는 OllamaClient(로컬, API Key 불필요), 배포 시에는
환경변수 하나만 바꿔서 GeminiClient로 전환할 수 있다. app.py나 prompts.py는
전혀 건드릴 필요가 없다.
"""

import os
from abc import ABC, abstractmethod
from pathlib import Path

import requests
from dotenv import load_dotenv

from prompts import build_followup_prompt, build_meeting_summary_prompt

# .env는 로컬 개발용 설정 파일이라 git에는 커밋하지 않는다 (.gitignore 참고).
# 프로젝트 루트 기준 경로로 명시해서, streamlit을 어느 위치에서 실행하든 항상 찾도록 한다.
load_dotenv(Path(__file__).parent / ".env")


class LLMConnectionError(Exception):
    """AI 제공자 서버 자체에 연결할 수 없을 때 발생한다."""


class LLMGenerationError(Exception):
    """연결은 됐지만 응답 생성 과정에서 문제가 생겼을 때 발생한다."""


class LLMClient(ABC):
    """텍스트 생성 제공자가 공통으로 구현해야 하는 인터페이스."""

    @abstractmethod
    def generate(self, prompt: str, model: str | None = None) -> str:
        """프롬프트를 받아 생성된 텍스트를 반환한다."""

    def get_available_models(self) -> list[str]:
        """선택 가능한 모델 이름 목록. 지원하지 않는 제공자는 빈 리스트를 반환한다."""
        return []


class OllamaClient(LLMClient):
    """로컬에서 실행 중인 Ollama(localhost:11434)를 호출하는 클라이언트.

    OpenAI API나 API Key 없이 개발용으로 쓰기 위한 기본 provider.
    """

    BASE_URL = "http://localhost:11434"
    TAGS_TIMEOUT = 5  # 모델 목록 조회는 가벼우니 짧게
    GENERATE_TIMEOUT = 180  # 긴 회의록 요약은 오래 걸릴 수 있어 넉넉하게
    DEFAULT_MODEL = "hermes3:8b"

    def get_available_models(self) -> list[str]:
        """로컬에 설치된 Ollama 모델 이름 목록을 반환한다.

        Ollama가 꺼져 있거나 응답이 없으면 예외를 던지지 않고 빈 리스트를 반환한다
        (앱 UI는 이 경우를 직접 안내 메시지로 처리한다).
        """
        try:
            response = requests.get(f"{self.BASE_URL}/api/tags", timeout=self.TAGS_TIMEOUT)
            response.raise_for_status()
        except requests.exceptions.RequestException:
            return []

        data = response.json()
        return [model["name"] for model in data.get("models", [])]

    def generate(self, prompt: str, model: str | None = None) -> str:
        """Ollama의 /api/generate를 호출해 완성된 텍스트 응답을 반환한다.

        스트리밍 없이(stream=False) 한 번에 전체 응답을 받는다 — 결과를 Markdown
        섹션으로 파싱해야 하므로 부분 응답보다 완성된 응답이 다루기 쉽다.
        """
        model = model or self.DEFAULT_MODEL
        try:
            response = requests.post(
                f"{self.BASE_URL}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=self.GENERATE_TIMEOUT,
            )
            response.raise_for_status()
        except requests.exceptions.ConnectionError as exc:
            raise LLMConnectionError(
                "Ollama 서버에 연결할 수 없어요. 터미널에서 'ollama serve'가 실행 중인지 확인해주세요."
            ) from exc
        except requests.exceptions.Timeout as exc:
            raise LLMGenerationError(
                f"{self.GENERATE_TIMEOUT}초 안에 응답을 받지 못했어요. 회의록을 더 짧게 나누거나 "
                "더 가벼운 모델로 다시 시도해보세요."
            ) from exc
        except requests.exceptions.HTTPError as exc:
            raise LLMGenerationError(
                f"'{model}' 모델 호출에 실패했어요. "
                f"설치되어 있는지 확인해주세요 (터미널에서 'ollama pull {model}')."
            ) from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise LLMGenerationError("Ollama 응답을 해석하지 못했어요. 잠시 후 다시 시도해주세요.") from exc

        return data.get("response", "").strip()


class GeminiClient(LLMClient):
    """Google Gemini API를 호출하는 클라이언트 (배포 환경용).

    'google-genai' 패키지와 GEMINI_API_KEY가 필요하다. 개발 중에는 쓰지 않으므로
    실제로 이 클래스가 생성되는 시점(get_client()가 provider="gemini"를 고를 때)에만
    패키지/키 유무를 확인한다 — 기본(Ollama) 경로에는 아무 영향이 없다.
    """

    DEFAULT_MODEL = "gemini-2.5-flash"
    # Gemini는 Ollama의 /api/tags 같은 '설치된 모델 목록' 개념이 없어 고정 목록으로 제공한다.
    AVAILABLE_MODELS = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"]

    def __init__(self, api_key: str | None = None) -> None:
        try:
            from google import genai
        except ImportError as exc:
            raise LLMConnectionError(
                "'google-genai' 패키지가 설치되어 있지 않아요. 'pip install google-genai'로 설치해주세요."
            ) from exc

        api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise LLMConnectionError(
                "GEMINI_API_KEY가 설정되어 있지 않아요. 배포 환경의 환경변수나 secrets에 넣어주세요."
            )

        self._client = genai.Client(api_key=api_key)

    def get_available_models(self) -> list[str]:
        return list(self.AVAILABLE_MODELS)

    def generate(self, prompt: str, model: str | None = None) -> str:
        model = model or self.DEFAULT_MODEL
        try:
            response = self._client.models.generate_content(model=model, contents=prompt)
        except Exception as exc:
            raise LLMGenerationError(f"Gemini 호출에 실패했어요: {exc}") from exc

        return (response.text or "").strip()


def get_client() -> LLMClient:
    """MEMOMATE_PROVIDER 환경변수를 보고 사용할 LLM 클라이언트를 결정한다.

    기본값은 'ollama' — API Key 없이 바로 로컬 개발을 시작할 수 있다.
    배포 시에는 MEMOMATE_PROVIDER=gemini와 GEMINI_API_KEY만 설정하면 되고,
    app.py나 prompts.py는 코드 한 줄도 바꿀 필요가 없다.
    """
    provider = os.environ.get("MEMOMATE_PROVIDER", "ollama").strip().lower()
    if provider == "gemini":
        return GeminiClient()
    return OllamaClient()


def get_available_models() -> list[str]:
    """현재 활성화된 provider가 지원하는 모델 이름 목록을 반환한다."""
    return get_client().get_available_models()


def summarize_meeting(transcript: str, model: str | None = None) -> str:
    """회의록 원문을 받아 구조화된 Markdown 요약 결과를 반환한다.

    어떤 AI 제공자를 쓸지는 get_client()가 결정하므로, 호출하는 쪽(app.py)은
    Ollama인지 Gemini인지 몰라도 된다.
    """
    prompt = build_meeting_summary_prompt(transcript)
    return get_client().generate(prompt, model=model)


def answer_question(
    transcript: str,
    question: str,
    chat_history: list[dict[str, str]] | None = None,
    model: str | None = None,
) -> str:
    """회의록 원문을 컨텍스트로 삼아 추가 질문에 답한다.

    RAG나 Vector DB 없이, 현재 회의록 원문을 그대로 프롬프트에 넣는다.
    summarize_meeting()과 동일하게 get_client()가 고른 provider를 그대로 재사용한다.
    """
    prompt = build_followup_prompt(transcript, question, chat_history)
    return get_client().generate(prompt, model=model)
