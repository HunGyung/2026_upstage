"""일반 질문 답변 + 보장 내용 요약 (청구 판정과 별개 모드)."""
from . import upstage

ANSWER_SYSTEM = """너는 보험 약관 안내 도우미다. 아래 제공된 '약관 조항'을 근거로 사용자 질문에 한국어로 답한다.
- 약관 조항에 근거해 구체적으로 답하고, 인용한 조항 번호를 함께 밝힌다.
- 약관에 없는 내용(예: 가입일, 가입금액 등 개인 정보)은 "약관에는 해당 정보가 없으며 보험증권에서 확인해야 한다"고 안내한다.
- 추측하지 말고, 모르면 모른다고 말한다.
이 안내는 참고용이며 최종 확인은 보험사를 통해야 한다."""

SUMMARY_SYSTEM = """너는 보험 약관에서 보장 내용을 정리하는 도우미다.
아래 약관 조항들을 바탕으로 이 보험이 '무엇을 보장하는지'를 표 형태로 정리하라.

가능하면 아래 항목을 담아라(약관에 있는 것만):
- 담보(보장) 이름
- 지급사유(어떤 경우 보험금이 나오는가)
- 지급금액 또는 지급방식
- 면책기간·감액기간 등 주의사항

마지막에 한 줄 요약을 덧붙여라. 약관에 근거가 없는 내용은 지어내지 마라.
이 정리는 참고용이며 실제 보장 금액은 보험증권을 확인해야 한다."""


def answer(question: str, clauses, user_info: str = "") -> str:
    """약관 기반 자유형 질의응답."""
    if not clauses:
        return "관련 약관 조항을 찾지 못했습니다. 질문을 더 구체적으로 입력해보세요."
    context = "\n\n".join(f"[{c['조항']}]\n{c['text']}" for c in clauses)
    info = f"\n\n[사용자 가입 정보]\n{user_info}" if user_info.strip() else ""
    messages = [
        {"role": "system", "content": ANSWER_SYSTEM},
        {"role": "user", "content": f"약관 조항:\n{context}{info}\n\n질문: {question}"},
    ]
    return upstage.chat(messages)


def summarize_coverage(index, user_info: str = "") -> str:
    """보장 담보 관련 조항을 모아 보장 내용을 표로 요약한다."""
    # 보장 관련 조항을 폭넓게 수집
    queries = ["보장하는 담보와 지급사유", "보험금 지급금액 가입금액", "면책기간 감액기간 보장 제외"]
    seen, clauses = set(), []
    for q in queries:
        for c in index.search(q, k=10):
            key = (c["조항"], c["text"][:40])
            if key not in seen:
                seen.add(key)
                clauses.append(c)
    if not clauses:
        return "보장 관련 조항을 찾지 못했습니다."
    context = "\n\n".join(f"[{c['조항']}]\n{c['text']}" for c in clauses[:25])
    info = f"\n\n[사용자 가입 정보]\n{user_info}" if user_info.strip() else ""
    messages = [
        {"role": "system", "content": SUMMARY_SYSTEM},
        {"role": "user", "content": f"약관 조항:\n{context}{info}\n\n이 보험의 보장 내용을 정리해줘."},
    ]
    return upstage.chat(messages)
