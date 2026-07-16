"""LLM에게 전달할 프롬프트 템플릿을 관리한다.

app.py가 응답을 '## 헤더' 기준으로 파싱하므로, 여기서 요구하는 7개 헤더
(회의 제목 / 참석자 / 회의 요약 / 핵심 내용 / Action Item / 키워드 / 이메일 초안)는
절대 변경하지 않는다. 헤더 문구를 바꾸면 app.py의 SECTION_HEADERS도 함께 수정해야 한다.
"""

MEETING_SUMMARY_TEMPLATE = """당신은 회의록을 깔끔하게 정리해주는 유능한 비서입니다.

아래 [회의록 원문]을 분석해서, 반드시 아래 Markdown 형식 그대로 **한국어로** 정리해주세요.
- 헤더 문구(## 회의 제목, ## 참석자, ## 회의 요약, ## 핵심 내용, ## Action Item, ## 키워드, ## 이메일 초안)는
  절대 바꾸거나 생략하지 마세요.
- 형식 밖의 다른 설명, 인사말, 부연 설명은 절대 추가하지 마세요.
- 회의록에 없는 내용은 지어내지 말고, 정보가 없으면 "미정"이라고 쓰세요.

## 회의 제목
(회의 내용에 가장 어울리는 제목 한 줄. 너무 길지 않게 명사형으로 작성.
예: "2026 하반기 워크숍 준비 회의")

## 참석자
- (회의록에서 언급된 참석자를 이름 또는 역할로 bullet point 나열. 확인 불가하면 "미정" 한 줄만)

## 회의 요약
(회의 전체 내용을 3~5문장으로 요약)

## 핵심 내용
- (핵심 논의 내용을 bullet point 3~6개로 정리)

## Action Item
| 담당자 | 해야 할 일 | 마감일 |
|---|---|---|
| (담당자가 불명확하면 "미정", 마감일이 언급 안 되면 "미정") | | |

## 키워드
(회의 내용을 대표하는 핵심 키워드 5~10개를 쉼표로 구분해 한 줄로 나열하고, 각 키워드 앞에 #을 붙이세요.
예: #예산, #워크숍, #홍보, #참가자, #일정)

## 이메일 초안
제목: (회의 결과 공유용 이메일 제목)

(팀에게 회의 결과를 공유하는 정중하고 간결한 이메일 본문. 인사말과 맺음말 포함)

---
[회의록 원문]
{transcript}
"""

# 추가 질문(챗봇) 프롬프트: RAG/Vector DB 없이 회의록 원문을 그대로 컨텍스트로 넣는다.
FOLLOWUP_TEMPLATE = """당신은 아래 [회의록 원문]만 근거로 질문에 답하는 비서입니다.
회의록에 없는 내용은 추측하지 말고 "회의록에서 확인할 수 없어요"라고 답하세요.
답변은 간결하게 한국어로 작성하세요.

[회의록 원문]
{transcript}
{history_block}
[질문]
{question}

[답변]
"""


def build_meeting_summary_prompt(transcript: str) -> str:
    """회의록 원문을 프롬프트 템플릿에 채워 반환한다."""
    return MEETING_SUMMARY_TEMPLATE.format(transcript=transcript.strip())


def build_followup_prompt(
    transcript: str,
    question: str,
    chat_history: list[dict[str, str]] | None = None,
) -> str:
    """회의록 원문 + (있다면) 이전 대화를 컨텍스트로 삼아 추가 질문 프롬프트를 만든다."""
    history_block = ""
    if chat_history:
        history_lines = [
            f"{'질문' if turn['role'] == 'user' else '답변'}: {turn['content']}" for turn in chat_history
        ]
        history_block = "\n[이전 대화]\n" + "\n".join(history_lines) + "\n"

    return FOLLOWUP_TEMPLATE.format(
        transcript=transcript.strip(),
        history_block=history_block,
        question=question.strip(),
    )
