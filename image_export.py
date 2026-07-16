"""요약 결과를 핑크 메모 카드 스타일의 PNG 이미지로 렌더링한다.

브라우저 화면 캡처 라이브러리 없이 Pillow로 직접 그린다 — 추가 JS/외부 서비스
없이 오프라인에서도 항상 동일하게 동작하게 하기 위함.
"""

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BG_COLOR = (255, 247, 250)  # #FFF7FA
CARD_COLOR = (255, 255, 255)  # #FFFFFF
BORDER_COLOR = (246, 199, 216)  # #F6C7D8
ACCENT_COLOR = (255, 143, 177)  # #FF8FB1
TEXT_COLOR = (68, 68, 68)  # #444444
MUTED_COLOR = (138, 112, 118)

CANVAS_WIDTH = 900
PADDING = 40
CARD_PADDING = 24
CARD_GAP = 20
LINE_HEIGHT = 30
TITLE_LINE_HEIGHT = 40
SUBTITLE_LINE_HEIGHT = 26
TITLE_SUBTITLE_GAP = 12

# Windows(맑은 고딕) / macOS / Linux(나눔고딕) 순으로 한글 지원 폰트를 찾는다.
_FONT_CANDIDATES_REGULAR = [
    "C:/Windows/Fonts/malgun.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
]
_FONT_CANDIDATES_BOLD = [
    "C:/Windows/Fonts/malgunbd.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
]


def _load_font(candidates: list[str], size: int) -> ImageFont.FreeTypeFont:
    """후보 경로 중 존재하는 첫 폰트를 로드한다. 하나도 없으면 PIL 기본 폰트로 폴백한다."""
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _clean_line(line: str) -> str:
    """Markdown 강조/불릿 기호를 이미지에 어울리는 plain text로 바꾼다."""
    cleaned = line.strip().replace("**", "")
    if cleaned.startswith("- "):
        cleaned = "• " + cleaned[2:]
    return cleaned


def _prepare_lines(text: str) -> list[str]:
    """여러 줄 텍스트를 줄 단위로 정리한다. 빈 텍스트는 안내 문구로 대체한다."""
    text = text.strip()
    if not text:
        return ["내용이 없어요."]
    return [_clean_line(line) for line in text.splitlines()]


def _wrap_line(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    """공백 기준으로 줄바꿈한다. 공백 없이 긴 단어는 글자 단위로 강제 분할한다."""
    if text == "":
        return [""]

    lines: list[str] = []
    current = ""
    for word in text.split(" "):
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
            continue

        if current:
            lines.append(current)

        if draw.textlength(word, font=font) <= max_width:
            current = word
            continue

        chunk = ""
        for char in word:
            if draw.textlength(chunk + char, font=font) <= max_width:
                chunk += char
            else:
                lines.append(chunk)
                chunk = char
        current = chunk

    if current:
        lines.append(current)
    return lines or [""]


def _build_blocks(sections: dict[str, str], action_rows: list[list[str]]) -> list[tuple[str, list[str]]]:
    """앱 화면의 6개 메모 카드와 동일한 구성으로 (제목, 본문 줄 리스트) 블록을 만든다."""
    if action_rows:
        action_lines = [
            f"• {row[1] or '(내용 없음)'}  (담당자: {row[0] or '미정'} · 마감일: {row[2] or '미정'})"
            for row in action_rows
        ]
    else:
        action_lines = ["등록된 Action Item이 없어요."]

    assignees = sorted({row[0] for row in action_rows if row[0]}) or ["미정"]
    deadlines = sorted({row[2] for row in action_rows if row[2]}) or ["미정"]

    return [
        ("회의 요약", _prepare_lines(sections.get("회의 요약", ""))),
        ("핵심 내용", _prepare_lines(sections.get("핵심 내용", ""))),
        ("해야 할 일", action_lines),
        ("담당자", [f"• {name}" for name in assignees]),
        ("마감일", [f"• {date}" for date in deadlines]),
        ("이메일 초안", _prepare_lines(sections.get("이메일 초안", ""))),
    ]


def render_summary_image(
    sections: dict[str, str],
    action_rows: list[list[str]],
    meeting_title: str | None = None,
) -> bytes:
    """회의 요약 결과를 핑크 메모 카드 스타일의 PNG 이미지 바이트로 렌더링한다.

    meeting_title이 주어지면(AI가 생성한 회의 제목) 이미지 맨 위 큰 제목으로 쓰고,
    없으면 "회의 메모"로 대체한다.
    """
    font_title = _load_font(_FONT_CANDIDATES_BOLD, 32)
    font_heading = _load_font(_FONT_CANDIDATES_BOLD, 21)
    font_body = _load_font(_FONT_CANDIDATES_REGULAR, 17)

    measure_draw = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    max_text_width = CANVAS_WIDTH - 2 * PADDING - 2 * CARD_PADDING - 18  # 아이콘 원 만큼 빼기

    display_title = (meeting_title or "").strip() or "회의 메모"
    title_lines = _wrap_line(display_title, font_title, CANVAS_WIDTH - 2 * PADDING, measure_draw)
    title_area_height = (
        len(title_lines) * TITLE_LINE_HEIGHT + TITLE_SUBTITLE_GAP + SUBTITLE_LINE_HEIGHT
    )

    blocks = _build_blocks(sections, action_rows)

    prepared_blocks: list[tuple[str, list[str], int]] = []
    total_height = PADDING + title_area_height
    for card_title, raw_lines in blocks:
        wrapped: list[str] = []
        for raw_line in raw_lines:
            wrapped.extend(_wrap_line(raw_line, font_body, max_text_width, measure_draw))
        card_height = CARD_PADDING * 2 + 34 + len(wrapped) * LINE_HEIGHT
        prepared_blocks.append((card_title, wrapped, card_height))
        total_height += card_height + CARD_GAP

    total_height += PADDING

    image = Image.new("RGB", (CANVAS_WIDTH, total_height), BG_COLOR)
    draw = ImageDraw.Draw(image)

    title_y = PADDING
    for line in title_lines:
        draw.text((PADDING, title_y), line, font=font_title, fill=TEXT_COLOR)
        title_y += TITLE_LINE_HEIGHT
    draw.text(
        (PADDING, title_y + TITLE_SUBTITLE_GAP),
        "MemoMate AI가 정리한 회의 메모예요",
        font=font_body,
        fill=MUTED_COLOR,
    )

    y = PADDING + title_area_height
    for card_title, wrapped, card_height in prepared_blocks:
        card_box = (PADDING, y, CANVAS_WIDTH - PADDING, y + card_height)
        draw.rounded_rectangle(card_box, radius=18, fill=CARD_COLOR, outline=BORDER_COLOR, width=2)

        text_x = PADDING + CARD_PADDING
        text_y = y + CARD_PADDING

        # 이모지 대신 작은 원형 포인트로 카드 제목을 장식한다 (일부 환경에서 컬러 이모지 폰트 미지원 대응).
        dot_diameter = 10
        dot_y = text_y + 7
        draw.ellipse(
            (text_x, dot_y, text_x + dot_diameter, dot_y + dot_diameter),
            fill=ACCENT_COLOR,
        )
        draw.text((text_x + dot_diameter + 8, text_y), card_title, font=font_heading, fill=TEXT_COLOR)
        text_y += 34

        for line in wrapped:
            draw.text((text_x, text_y), line, font=font_body, fill=TEXT_COLOR)
            text_y += LINE_HEIGHT

        y += card_height + CARD_GAP

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
