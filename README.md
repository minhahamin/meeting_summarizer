# 💗 MemoMate AI

회의록을 붙여넣으면 AI가 귀여운 메모 카드로 정리해주는 회의록 요약기입니다.
**OpenAI API나 API Key 없이, 로컬에서 실행 중인 [Ollama](https://ollama.com)만으로 동작합니다.**

## 주요 기능

회의록 원문을 입력하면 아래 내용을 자동으로 추출합니다.

- 📒 회의 요약
- 🩷 핵심 내용
- 📌 Action Item (해야 할 일)
- 👤 담당자
- 📅 마감일
- 💌 회의 결과 공유용 이메일 초안

## 기술 스택

| 영역 | 기술 |
|---|---|
| UI | Streamlit |
| LLM | Ollama (로컬 실행, 예: `llama3.2`, `qwen2.5`, `gemma3` 등) |
| 통신 | `requests`로 `http://localhost:11434` 직접 호출 |

## AI 제공자(provider) 전환

`ai.py`는 특정 AI 제공자에 종속되지 않도록 `LLMClient` 인터페이스로 추상화돼
있습니다. `app.py`는 `summarize_meeting()` 하나만 호출하고, 실제로 어떤
제공자를 쓸지는 `MEMOMATE_PROVIDER` 환경변수가 결정합니다.

| 값 | 클라이언트 | 용도 |
|---|---|---|
| `ollama` (기본값) | `OllamaClient` | 로컬 개발 — API Key 불필요 |
| `gemini` | `GeminiClient` | 배포 — `pip install google-genai` + `GEMINI_API_KEY` 필요 |

배포 시 전환 방법:

```bash
pip install google-genai
export MEMOMATE_PROVIDER=gemini
export GEMINI_API_KEY=your-api-key-here
```

`app.py`나 `prompts.py`는 전혀 건드릴 필요가 없습니다.

## 프로젝트 구조

```
meeting_summarizer/
├── app.py                  # Streamlit UI, 결과 파싱 및 메모 카드 렌더링
├── ai.py                   # LLMClient 추상화 (OllamaClient / GeminiClient)
├── prompts.py               # 요약 프롬프트 템플릿
├── image_export.py          # 결과를 핑크 메모 카드 PNG로 렌더링
├── requirements.txt
├── README.md
├── public/
│   └── img/                 # 타이틀 마스코트 이미지
└── .streamlit/
    └── config.toml          # 핑크 파스텔 테마
```

## 실행 방법

### 1. Ollama 설치 및 모델 준비

[ollama.com](https://ollama.com)에서 Ollama를 설치한 뒤, 사용할 모델을 하나 이상 받아둡니다.

```bash
ollama pull llama3.2
# 또는
ollama pull qwen2.5
# 또는
ollama pull gemma3
```

Ollama 서버가 실행 중인지 확인하세요 (설치 시 보통 자동으로 백그라운드에서 실행됩니다).
앱은 `http://localhost:11434`로 접속합니다.

### 2. 패키지 설치

```bash
cd meeting_summarizer
python -m venv .venv
.venv\Scripts\activate      # Windows
pip install -r requirements.txt
```

### 3. 앱 실행

```bash
streamlit run app.py
```

브라우저에서 `http://localhost:8501`이 자동으로 열립니다.

## 사용 방법

1. 상단 드롭다운에서 로컬에 설치된 Ollama 모델을 선택합니다.
2. 회의록 원문을 텍스트박스에 붙여넣습니다.
3. "메모 요약하기 💌" 버튼을 클릭합니다.
4. 잠시 후 회의 요약, 핵심 내용, Action Item, 담당자, 마감일, 이메일 초안이
   메모 카드 형태로 표시됩니다.

## 참고

- 완전히 로컬에서 동작하므로 회의록이 외부 서버로 전송되지 않습니다.
- 모델 성능에 따라 Action Item의 담당자/마감일 추출 정확도가 달라질 수 있습니다.
  회의록에 담당자·기한이 명확히 언급될수록 결과가 정확해집니다.
- Ollama가 꺼져 있으면 앱 상단에 안내 메시지가 표시됩니다.
