"""청구 가능성 판정 로직."""
import json

from . import upstage

SYSTEM_PROMPT = """너는 보험 약관 분석 도우미다. 아래 제공된 '약관 조항'만을 근거로 판단한다.
- 약관에 명시되지 않은 내용은 추측하지 말고 가능성을 '검토필요'로 둔다.
- 반드시 아래 JSON 형식으로만 답한다.

{
  "가능성": "가능 | 검토필요 | 어려움",
  "근거조항": ["인용한 조항 제목들"],
  "주의사항": ["면책기간, 감액기간 등 사용자가 주의할 점"],
  "보험료영향": "갱신형/비갱신형 등 청구 시 보험료 영향에 대한 설명 (약관에 근거가 없으면 '약관만으로 확인 불가')",
  "설명": "일반인이 이해할 수 있는 한국어 설명"
}

주의: 이 판단은 참고용이며 최종 확인은 보험사 또는 손해사정사를 통해야 한다."""


def judge(question: str, clauses) -> dict:
    """질문과 관련 조항을 받아 판정 결과(dict)를 반환한다."""
    context = "\n\n".join(f"[{c['조항']}]\n{c['text']}" for c in clauses)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"약관 조항:\n{context}\n\n질문: {question}"},
    ]
    raw = upstage.chat(messages, json_mode=True)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"가능성": "검토필요", "설명": raw, "근거조항": [], "주의사항": [], "보험료영향": ""}
