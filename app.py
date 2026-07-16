"""MemoMate AI — 회의록을 귀여운 메모처럼 정리해주는 Streamlit 앱.

Ollama(로컬 LLM)를 호출해 회의록을 요약하고, 결과를 메모지 카드 UI로 보여준다.
"""

import base64
import io
import re
from pathlib import Path

import pandas as pd
import streamlit as st
from pypdf import PdfReader

from ai import LLMConnectionError, LLMGenerationError, answer_question, get_available_models, summarize_meeting
from image_export import render_summary_image

# ── 페이지 기본 설정 ──────────────────────────────────────────────
st.set_page_config(
    page_title="MemoMate AI",
    page_icon="💗",
    layout="wide",
)

# 타이틀 앞에 들어가는 마스코트 이미지 (하트 이모지 대신 사용)
MASCOT_IMAGE_PATH = Path(__file__).parent / "public" / "img" / "미룬일.png"

# AI에게 추가 질문하기 채팅의 아바타 이미지
USER_AVATAR_PATH = Path(__file__).parent / "public" / "img" / "음.png"
ASSISTANT_AVATAR_PATH = Path(__file__).parent / "public" / "img" / "똑똑이.png"

# 모델 드롭다운의 기본 선택값 (설치돼 있지 않으면 목록의 첫 번째 모델로 폴백)
DEFAULT_MODEL = "hermes3:8b"

# Action Item 표에서 담당자/마감일 열을 뽑아낼 때 쓰는 정규식 (헤더·구분선 행 제외)
_TABLE_ROW_PATTERN = re.compile(r"^\|(.+)\|(.+)\|(.+)\|$")
_TABLE_SEPARATOR_PATTERN = re.compile(r"^[\s\-:|]+$")

# 결과 Markdown에서 잘라낼 섹션 헤더와, 각 섹션을 표시할 카드 정보
SECTION_HEADERS = ["회의 제목", "참석자", "회의 요약", "핵심 내용", "Action Item", "키워드", "이메일 초안"]


def inject_custom_css() -> None:
    """핑크 파스텔 '귀여운 메모장' 컨셉의 커스텀 CSS를 주입한다.

    st.html + key= 스코프 선택자를 사용해 특정 위젯/컨테이너만 타겟팅한다.
    (config.toml의 네이티브 테마로는 표현할 수 없는 스티커 메모 질감, hover
    애니메이션, 카드 회전 등을 위해 사용자가 명시적으로 CSS 커스터마이징을 요청함.)
    """
    st.html(
        """
        <style>
        /* 본문 영역 좌우 여백을 조금 더 넉넉하게 */
        .block-container {
            padding-top: 2.5rem;
            padding-bottom: 3rem;
            max-width: 1100px;
        }

        /* 메인 타이틀: 마스코트 이미지 + 텍스트를 한 줄에 정렬
           Streamlit이 [data-testid="stMarkdownContainer"] 등에 거는 자체 CSS가
           클래스 선택자보다 명시도가 높아 line-height/overflow를 덮어써서 글씨가
           잘렸었다 — !important로 강제하고 잘릴 수 있는 조상 요소의 overflow도 함께 푼다. */
        .st-key-app_title,
        .st-key-app_title [data-testid="stMarkdownContainer"],
        .st-key-app_title [data-testid="stMarkdownContainer"] > div {
            overflow: visible !important;
        }
        .memo-title-row {
            display: flex !important;
            align-items: center !important;
            gap: 0.7rem !important;
            overflow: visible !important;
            padding: 0.35rem 0 !important;
        }
        .memo-title-icon {
            height: 5.6rem !important;
            width: auto !important;
            flex-shrink: 0 !important;
        }
        .memo-title-text {
            font-family: 'Jua', sans-serif !important;
            font-size: 2.6rem !important;
            font-weight: 700 !important;
            line-height: 1.6 !important;
            white-space: normal !important;
            overflow: visible !important;
            color: #444444 !important;
        }
        .st-key-app_subtitle p {
            color: #8a7076;
            font-size: 1.05rem;
            margin-top: 0.2rem;
        }

        /* 입력 카드: 메모지 느낌 */
        .st-key-input_card {
            background: #FFFFFF;
            border: 1.5px solid #F6C7D8;
            border-radius: 22px;
            padding: 1.6rem 1.8rem;
            box-shadow: 0 6px 18px rgba(255, 143, 177, 0.15);
            transition: box-shadow 0.25s ease, transform 0.25s ease;
        }
        .st-key-input_card:hover {
            box-shadow: 0 10px 26px rgba(255, 143, 177, 0.22);
        }

        /* 회의록 입력창: 노트 라인 느낌 */
        .st-key-transcript_input textarea {
            background: repeating-linear-gradient(
                #FFFDFE,
                #FFFDFE 31px,
                #FFE3ED 32px
            );
            border-radius: 16px !important;
            border: 1.5px dashed #F6C7D8 !important;
            line-height: 32px;
            padding-top: 10px !important;
            font-size: 0.98rem;
        }
        .st-key-transcript_input textarea:focus {
            border-color: #FF8FB1 !important;
            box-shadow: 0 0 0 3px rgba(255, 143, 177, 0.18) !important;
        }

        /* 요약하기 버튼 */
        .st-key-summarize_btn button {
            background: linear-gradient(135deg, #FF8FB1, #FFA9C4);
            color: white;
            border: none;
            border-radius: 999px;
            padding: 0.7rem 1.8rem;
            font-weight: 700;
            box-shadow: 0 6px 14px rgba(255, 143, 177, 0.35);
            transition: transform 0.18s ease, box-shadow 0.18s ease;
        }
        .st-key-summarize_btn button:hover {
            transform: translateY(-2px) scale(1.02);
            box-shadow: 0 10px 20px rgba(255, 143, 177, 0.45);
            color: white;
        }
        .st-key-summarize_btn button:active {
            transform: translateY(0) scale(0.99);
        }

        /* 이미지 저장 버튼 */
        .st-key-download_image_btn button {
            background: linear-gradient(135deg, #FF8FB1, #FFA9C4);
            color: white;
            border: none;
            border-radius: 999px;
            padding: 0.6rem 1.6rem;
            font-weight: 700;
            box-shadow: 0 6px 14px rgba(255, 143, 177, 0.3);
            transition: transform 0.18s ease, box-shadow 0.18s ease;
        }
        .st-key-download_image_btn button:hover {
            transform: translateY(-2px) scale(1.02);
            box-shadow: 0 10px 20px rgba(255, 143, 177, 0.4);
            color: white;
        }

        /* 결과 메모 카드 공통 스타일: 살짝 기울어진 스티커 노트 느낌 */
        [class*="st-key-card_"] {
            background: #FFFFFF;
            border: 1.5px solid #F6C7D8;
            border-radius: 18px;
            padding: 1.3rem 1.5rem 1.5rem 1.5rem;
            margin-bottom: 1rem;
            box-shadow: 0 4px 14px rgba(255, 143, 177, 0.14);
            animation: memo-pop-in 0.35s ease both;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        [class*="st-key-card_"]:hover {
            transform: translateY(-3px) rotate(-0.3deg);
            box-shadow: 0 10px 22px rgba(255, 143, 177, 0.22);
        }

        @keyframes memo-pop-in {
            from { opacity: 0; transform: translateY(10px); }
            to   { opacity: 1; transform: translateY(0); }
        }

        /* ── 카드별 종이 질감 (워시테이프 / 스프링노트 / 말린 모서리 / 체크무늬) ──
           손그림 메모지 레퍼런스를 CSS만으로 흉내낸다 — 이미지 파일 없이 가볍게. */

        /* 회의 요약: 핑크 체크(깅엄) 무늬 배경 */
        .st-key-card_summary {
            background-image:
                repeating-linear-gradient(0deg, rgba(255, 143, 177, 0.14) 0 5px, transparent 5px 22px),
                repeating-linear-gradient(90deg, rgba(255, 143, 177, 0.14) 0 5px, transparent 5px 22px);
            background-color: #FFFFFF;
        }

        /* 핵심 내용: 핑크 워시테이프 */
        .st-key-card_highlights {
            position: relative;
            overflow: visible !important;
        }
        .st-key-card_highlights::before {
            content: "";
            position: absolute;
            top: -12px;
            left: 28px;
            width: 64px;
            height: 24px;
            background: repeating-linear-gradient(45deg, #FFD6E7, #FFD6E7 6px, #FFE9F1 6px, #FFE9F1 12px);
            transform: rotate(-5deg);
            border-radius: 3px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            pointer-events: none;
        }

        /* 해야 할 일: 스프링노트 (보라 제본 라인 + 구멍) */
        .st-key-card_actions {
            position: relative;
            padding-left: 2.6rem !important;
        }
        .st-key-card_actions::before {
            content: "";
            position: absolute;
            left: 0;
            top: 0;
            bottom: 0;
            width: 1.9rem;
            background: #E7D5F5;
            border-radius: 18px 0 0 18px;
        }
        .st-key-card_actions::after {
            content: "";
            position: absolute;
            left: 0.5rem;
            top: 16px;
            bottom: 16px;
            width: 10px;
            background-image: radial-gradient(circle, #FFFFFF 4px, transparent 4.5px);
            background-size: 10px 24px;
            background-repeat: repeat-y;
        }

        /* 담당자: 말린 모서리 민트 메모지 */
        .st-key-card_assignees {
            background: #E9F7F5;
            position: relative;
        }
        .st-key-card_assignees::after {
            content: "";
            position: absolute;
            right: 0;
            bottom: 0;
            width: 30px;
            height: 30px;
            background: linear-gradient(135deg, transparent 50%, rgba(0, 0, 0, 0.08) 50%);
            border-bottom-right-radius: 18px;
            pointer-events: none;
        }

        /* 마감일: 크림색 배경 + 라벤더 워시테이프 */
        .st-key-card_deadlines {
            background: #FFFBEF;
            position: relative;
            overflow: visible !important;
        }
        .st-key-card_deadlines::before {
            content: "";
            position: absolute;
            top: -12px;
            right: 28px;
            width: 64px;
            height: 24px;
            background: repeating-linear-gradient(45deg, #D8CCF0, #D8CCF0 6px, #EFE9FA 6px, #EFE9FA 12px);
            transform: rotate(5deg);
            border-radius: 3px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            pointer-events: none;
        }

        /* 이메일 초안: 말린 모서리 핑크 편지지 */
        .st-key-card_email {
            position: relative;
        }
        .st-key-card_email::after {
            content: "";
            position: absolute;
            right: 0;
            bottom: 0;
            width: 30px;
            height: 30px;
            background: linear-gradient(135deg, transparent 50%, rgba(255, 143, 177, 0.25) 50%);
            border-bottom-right-radius: 18px;
            pointer-events: none;
        }

        /* 메모 카드 제목 */
        .memo-card-title {
            font-size: 1.15rem;
            font-weight: 700;
            color: #444444;
            margin-bottom: 0.6rem;
        }

        /* 회의 제목 (결과 화면 가장 상단) */
        .meeting-title-text {
            font-family: 'Jua', sans-serif;
            font-size: 1.9rem;
            font-weight: 700;
            line-height: 1.5;
            color: #444444;
            margin: 0.2rem 0 1rem 0;
        }

        /* 키워드 태그 */
        .keyword-tag-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
        }
        .keyword-tag {
            background: #FFD6E7;
            color: #a03a5c;
            border-radius: 999px;
            padding: 0.35rem 0.9rem;
            font-size: 0.9rem;
            font-weight: 600;
        }

        /* AI 추가 질문 섹션 제목 */
        .qa-section-title {
            font-family: 'Jua', sans-serif;
            font-size: 1.4rem;
            font-weight: 700;
            color: #444444;
            margin: 1.6rem 0 0.8rem 0;
        }

        /* 안내/에러 박스도 살짝 둥글게 */
        div[data-testid="stAlert"] {
            border-radius: 16px;
        }

        /* AI 추가 질문 채팅의 아바타(음.png / 똑똑이.png) 크게 */
        [data-testid="stChatMessageAvatarCustom"],
        [data-testid="stChatMessageAvatarUser"],
        [data-testid="stChatMessageAvatarAssistant"] {
            width: 3rem !important;
            height: 3rem !important;
            border: 2px solid #F6C7D8;
        }
        [data-testid="stChatMessageAvatarCustom"] img {
            width: 100% !important;
            height: 100% !important;
            object-fit: cover;
        }
        </style>
        """
    )


@st.cache_data(show_spinner=False)
def extract_pdf_text(file_bytes: bytes) -> str:
    """PDF 바이트에서 텍스트를 추출한다.

    스캔 이미지로만 이루어진 PDF는 pypdf가 텍스트를 뽑아내지 못해 빈 문자열을
    반환할 수 있다 (OCR은 지원하지 않음).
    """
    reader = PdfReader(io.BytesIO(file_bytes))
    pages_text = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages_text).strip()


def handle_pdf_upload(uploaded_file) -> None:
    """새로 업로드된 PDF에서 텍스트를 추출해 회의록 입력창에 채운다.

    파일이 계속 업로드된 상태로 남아있는 매 rerun마다 다시 채우면 사용자가
    입력창에서 직접 고친 내용을 덮어써버리므로, 파일이 '새로' 바뀐 경우에만 채운다.
    """
    if st.session_state.get("_last_pdf_id") == uploaded_file.file_id:
        return

    try:
        extracted_text = extract_pdf_text(uploaded_file.getvalue())
    except Exception:
        st.error("PDF에서 텍스트를 추출하지 못했어요. 다른 파일로 시도해주세요.", icon="📄")
        return

    st.session_state["_last_pdf_id"] = uploaded_file.file_id

    if not extracted_text:
        st.warning(
            "PDF에서 텍스트를 찾지 못했어요. 스캔된 이미지 PDF는 지원하지 않아요.",
            icon="🔍",
        )
        return

    st.session_state["transcript_input"] = extracted_text
    st.toast("PDF에서 회의록 텍스트를 불러왔어요!", icon="📄")


@st.cache_data(show_spinner=False)
def load_image_base64(path: str) -> str | None:
    """이미지를 base64 문자열로 읽어 <img src="data:..."> 형태로 바로 쓸 수 있게 한다.

    static 파일 서빙 설정 없이도 HTML에 이미지를 인라인으로 넣기 위해 사용한다.
    파일이 없으면 None을 반환해서 호출부가 대체 UI(이모지)로 폴백할 수 있게 한다.
    """
    image_path = Path(path)
    if not image_path.exists():
        return None
    encoded = base64.b64encode(image_path.read_bytes()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"


def parse_sections(markdown_text: str) -> dict[str, str]:
    """LLM이 반환한 Markdown을 '## 헤더' 기준으로 잘라 섹션 딕셔너리로 만든다.

    LLM이 형식을 완벽히 지키지 않는 경우를 대비해, 알려진 헤더만 인식하고
    나머지는 가장 가까운 이전 섹션에 붙인다.
    """
    sections: dict[str, str] = {}
    current_header = None
    buffer: list[str] = []

    def flush() -> None:
        if current_header is not None:
            sections[current_header] = "\n".join(buffer).strip()

    for line in markdown_text.splitlines():
        stripped = line.strip()
        matched_header = None
        if stripped.startswith("#"):
            for header in SECTION_HEADERS:
                if header in stripped:
                    matched_header = header
                    break

        if matched_header:
            flush()
            current_header = matched_header
            buffer = []
        else:
            buffer.append(line)

    flush()
    return sections


def extract_action_item_rows(action_item_markdown: str) -> list[list[str]]:
    """Action Item 표 Markdown에서 (담당자, 해야 할 일, 마감일) 행 리스트를 뽑는다."""
    rows: list[list[str]] = []
    for line in action_item_markdown.splitlines():
        stripped = line.strip()
        match = _TABLE_ROW_PATTERN.match(stripped)
        if not match:
            continue
        cells = [cell.strip() for cell in match.groups()]
        if _TABLE_SEPARATOR_PATTERN.match(cells[0]):
            continue  # 헤더 구분선(---) 스킵
        if cells[0] in ("담당자", "Assignee"):
            continue  # 헤더 행 스킵
        rows.append(cells)
    return rows


def extract_keywords(raw: str) -> list[str]:
    """'#키워드1, #키워드2' 형태의 텍스트를 키워드 문자열 리스트로 만든다."""
    if not raw:
        return []
    keywords = []
    for token in re.split(r"[,\n]", raw):
        cleaned = token.strip().lstrip("#").strip()
        if cleaned:
            keywords.append(cleaned)
    return keywords


def extract_bullet_items(raw: str) -> list[str]:
    """'- 항목' 형태로 나열된 텍스트에서 항목 리스트를 뽑는다 (참석자 등에 재사용)."""
    items = []
    for line in raw.splitlines():
        stripped = line.strip().lstrip("-•").strip()
        if stripped and stripped != "미정":
            items.append(stripped)
    return items


def sanitize_filename(text: str) -> str:
    """회의 제목을 다운로드 파일명으로 쓸 수 있게 정리한다 (금지 문자 제거, 공백은 밑줄로)."""
    cleaned = re.sub(r'[\\/:*?"<>|]', "", text).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned or "회의_메모"


def render_memo_card(icon: str, title: str, render_body, key_suffix: str | None = None) -> None:
    """아이콘 + 제목 + 본문(콜백)을 메모지 카드 하나로 렌더링한다.

    key_suffix: CSS에서 카드별 종이 질감(워시테이프/스프링노트 등)을 정확히
    타겟팅하기 위한 영문 슬러그. 생략하면 title을 그대로 써서(기존 동작 유지).
    """
    card_key = f"card_{key_suffix or title}"
    with st.container(key=card_key, border=False):
        st.markdown(f'<div class="memo-card-title">{icon} {title}</div>', unsafe_allow_html=True)
        render_body()


def render_meeting_title(title: str) -> None:
    """회의 제목을 결과 화면 가장 위에 큼직하게 보여준다."""
    st.markdown(f'<div class="meeting-title-text">📋 {title}</div>', unsafe_allow_html=True)


def render_stats_metrics(participant_count: int, action_item_count: int, deadline_count: int, keyword_count: int) -> None:
    """회의 통계 4개를 st.metric으로 나란히 보여준다."""
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("참석자 수", participant_count)
    col2.metric("Action Item", action_item_count)
    col3.metric("마감일", deadline_count)
    col4.metric("키워드", keyword_count)


def render_stats_chart(participant_count: int, action_item_count: int, deadline_count: int, keyword_count: int) -> None:
    """회의 통계 4개를 막대그래프로 한눈에 비교할 수 있게 보여준다."""
    chart_data = pd.DataFrame(
        {
            "항목": ["참석자 수", "Action Item", "마감일", "키워드"],
            "개수": [participant_count, action_item_count, deadline_count, keyword_count],
        }
    ).set_index("항목")
    st.bar_chart(chart_data, color="#FF8FB1", height=220)


def render_keyword_tags(keywords: list[str]) -> None:
    """키워드 리스트를 Tag(pill) 스타일 카드로 보여준다."""
    if not keywords:
        st.markdown("_추출된 키워드가 없어요._")
        return
    tags_html = "".join(f'<span class="keyword-tag">#{kw}</span>' for kw in keywords)
    st.markdown(f'<div class="keyword-tag-row">{tags_html}</div>', unsafe_allow_html=True)


def render_qa_chat(transcript: str, model: str) -> None:
    """요약이 끝난 회의록을 컨텍스트로, 추가 질문에 답하는 채팅 섹션을 보여준다.

    RAG나 Vector DB 없이 transcript 원문을 그대로 컨텍스트로 사용한다
    (ai.answer_question 참고). 대화 내역은 st.session_state에 누적된다.
    """
    st.markdown('<div class="qa-section-title">💬 AI에게 추가 질문하기</div>', unsafe_allow_html=True)

    user_avatar = str(USER_AVATAR_PATH) if USER_AVATAR_PATH.exists() else None
    assistant_avatar = str(ASSISTANT_AVATAR_PATH) if ASSISTANT_AVATAR_PATH.exists() else None
    avatars = {"user": user_avatar, "assistant": assistant_avatar}

    chat_history = st.session_state.setdefault("qa_history", [])
    for turn in chat_history:
        with st.chat_message(turn["role"], avatar=avatars[turn["role"]]):
            st.markdown(turn["content"])

    question = st.chat_input("예) 결정 사항만 정리해줘 / 담당자별 업무만 알려줘")
    if not question:
        return

    chat_history.append({"role": "user", "content": question})
    with st.chat_message("user", avatar=avatars["user"]):
        st.markdown(question)

    with st.chat_message("assistant", avatar=avatars["assistant"]):
        with st.spinner("답변을 준비하고 있어요... 🩷"):
            try:
                answer = answer_question(transcript, question, chat_history[:-1], model=model)
            except (LLMConnectionError, LLMGenerationError) as exc:
                answer = f"⚠️ {exc}"
        st.markdown(answer)

    chat_history.append({"role": "assistant", "content": answer})


def render_results(raw_markdown: str) -> None:
    """LLM 응답 전체를 파싱해서 메모 카드들로 렌더링한다."""
    sections = parse_sections(raw_markdown)

    title = sections.get("회의 제목", "").strip() or "회의 메모"
    participants = extract_bullet_items(sections.get("참석자", ""))
    summary = sections.get("회의 요약", "").strip()
    highlights = sections.get("핵심 내용", "").strip()
    action_item_md = sections.get("Action Item", "").strip()
    keywords = extract_keywords(sections.get("키워드", ""))
    email_draft = sections.get("이메일 초안", "").strip()
    action_rows = extract_action_item_rows(action_item_md)
    real_deadline_count = len({row[2] for row in action_rows if row[2] and row[2] != "미정"})

    render_meeting_title(title)

    def render_stats_body() -> None:
        render_stats_metrics(len(participants), len(action_rows), real_deadline_count, len(keywords))
        render_stats_chart(len(participants), len(action_rows), real_deadline_count, len(keywords))

    render_memo_card("📊", "회의 통계", render_stats_body, key_suffix="stats")
    render_memo_card("🏷️", "키워드", lambda: render_keyword_tags(keywords), key_suffix="keywords")

    col1, col2 = st.columns(2)
    with col1:
        render_memo_card(
            "📒", "회의 요약", lambda: st.markdown(summary or "_요약 내용이 없어요._"), key_suffix="summary"
        )
    with col2:
        render_memo_card(
            "🩷", "핵심 내용", lambda: st.markdown(highlights or "_핵심 내용이 없어요._"), key_suffix="highlights"
        )

    render_memo_card(
        "📌",
        "해야 할 일",
        lambda: st.markdown(action_item_md or "_Action Item이 없어요._"),
        key_suffix="actions",
    )

    col3, col4 = st.columns(2)
    with col3:
        assignees = sorted({row[0] for row in action_rows if row[0]}) or ["미정"]
        render_memo_card(
            "👤",
            "담당자",
            lambda: st.markdown("  \n".join(f"- {name}" for name in assignees)),
            key_suffix="assignees",
        )
    with col4:
        deadlines = sorted({row[2] for row in action_rows if row[2]}) or ["미정"]
        render_memo_card(
            "📅",
            "마감일",
            lambda: st.markdown("  \n".join(f"- {date}" for date in deadlines)),
            key_suffix="deadlines",
        )

    render_memo_card(
        "💌",
        "이메일 초안",
        lambda: st.markdown(email_draft or "_이메일 초안이 없어요._"),
        key_suffix="email",
    )

    st.write("")
    try:
        image_bytes = render_summary_image(sections, action_rows, meeting_title=title)
    except Exception as exc:
        st.warning("이미지를 만드는 데 실패했어요. 텍스트 결과는 위에서 그대로 확인할 수 있어요.", icon="🖼️")
        with st.expander("에러 내용 보기"):
            st.code(f"{type(exc).__name__}: {exc}")
        return

    st.download_button(
        "🖼️ 메모 이미지로 저장",
        data=image_bytes,
        file_name=f"{sanitize_filename(title)}.png",
        mime="image/png",
        key="download_image_btn",
    )


def main() -> None:
    inject_custom_css()

    with st.container(key="app_title"):
        mascot_src = load_image_base64(str(MASCOT_IMAGE_PATH))
        mascot_html = (
            f'<img src="{mascot_src}" class="memo-title-icon" alt="견뎌 이겨내 마스코트" />'
            if mascot_src
            else '<span class="memo-title-icon">💗</span>'
        )
        st.markdown(
            f'<div class="memo-title-row">{mascot_html}'
            '<span class="memo-title-text">MemoMate AI</span></div>',
            unsafe_allow_html=True,
        )
    with st.container(key="app_subtitle"):
        st.markdown("회의록을 귀여운 메모처럼 정리해드려요.")

    st.write("")

    available_models = get_available_models()
    if not available_models:
        st.warning(
            "Ollama에 연결하지 못했어요. 로컬에서 `ollama serve`가 실행 중인지 확인해주세요.",
            icon="⚠️",
        )
        available_models = [DEFAULT_MODEL]  # 입력 UI는 계속 보여주기 위한 폴백

    default_index = available_models.index(DEFAULT_MODEL) if DEFAULT_MODEL in available_models else 0

    with st.container(key="input_card"):
        selected_model = st.selectbox(
            "사용할 모델",
            options=available_models,
            index=default_index,
            help="로컬 Ollama에 설치된 모델 중 하나를 선택하세요.",
        )
        uploaded_pdf = st.file_uploader(
            "회의록 PDF 업로드 (선택)",
            type=["pdf"],
            key="pdf_uploader",
            help="PDF를 올리면 텍스트를 자동으로 추출해서 아래 입력창에 채워줘요.",
        )
        if uploaded_pdf is not None:
            handle_pdf_upload(uploaded_pdf)

        transcript = st.text_area(
            "회의록을 붙여넣거나 파일을 업로드 해주세요 📝",
            key="transcript_input",
            height=260,
            placeholder="예) 오늘 회의에서는 3분기 마케팅 전략에 대해 논의했습니다...",
        )
        summarize_clicked = st.button("메모 요약하기 💌", key="summarize_btn")

    if summarize_clicked:
        if not transcript.strip():
            st.warning("회의록을 먼저 입력해주세요!", icon="✍️")
        else:
            with st.spinner("메모를 정리하고 있어요... 🩷"):
                try:
                    result_markdown = summarize_meeting(transcript, model=selected_model)
                except LLMConnectionError as exc:
                    st.error(str(exc), icon="🔌")
                    result_markdown = None
                except LLMGenerationError as exc:
                    st.error(str(exc), icon="😥")
                    result_markdown = None

            if result_markdown:
                # 결과와 컨텍스트를 세션에 저장해둔다 — 채팅 입력 등 다른 위젯이 이후에
                # rerun을 일으켜도(summarize_clicked가 다시 False가 되어도) 결과가
                # 화면에서 사라지지 않도록 "버튼 클릭 여부"가 아니라 "저장된 결과 유무"로 그린다.
                st.session_state["last_result_markdown"] = result_markdown
                st.session_state["last_transcript"] = transcript
                st.session_state["qa_history"] = []  # 새 회의록이면 이전 대화는 초기화

    if st.session_state.get("last_result_markdown"):
        st.write("")
        render_results(st.session_state["last_result_markdown"])
        render_qa_chat(st.session_state["last_transcript"], selected_model)


if __name__ == "__main__":
    main()
