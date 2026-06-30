"""Streamlit UI - 백엔드 없이 단독 실행 가능한 데모.

실행: streamlit run app.py   (프로젝트 루트에서)
API 키: .env 의 UPSTAGE_API_KEY 사용
"""
import os
import tempfile
from datetime import date

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from backend import upstage, judge, qa
from backend.rag import split_into_clauses, ClauseIndex

st.set_page_config(page_title="보험 청구판정 도우미", page_icon="🩺")
st.title("🩺 보험 청구판정 도우미")
st.caption("내 약관으로 확인하는 “이 진단, 보험금 받을 수 있을까?”")

if not os.environ.get("UPSTAGE_API_KEY"):
    st.error(".env 에 UPSTAGE_API_KEY 를 설정한 뒤 다시 실행하세요.")
    st.stop()

# --- 사이드바: 내 가입 정보 (약관에 없는 개인 정보) ---
with st.sidebar:
    st.header("내 가입 정보")
    st.caption("약관에는 가입일·가입금액 같은 개인 정보가 없습니다. "
               "보험증권(가입증서)을 올리면 자동으로 추출하고, 직접 입력해도 됩니다.")

    # 1) 보험증권 자동 추출
    cert = st.file_uploader("보험증권/가입증서 업로드 (선택)", type=["pdf", "png", "jpg", "jpeg"], key="cert")
    if cert and st.button("증권에서 자동 추출"):
        with st.spinner("증권에서 가입 정보 추출 중..."):
            suffix = os.path.splitext(cert.name)[1] or ".pdf"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(cert.read())
                cpath = tmp.name
            try:
                st.session_state["contract"] = upstage.extract(cpath)
                st.success("추출 완료")
            except Exception as e:
                st.error(f"추출 실패: {e}")
            finally:
                os.unlink(cpath)

    contract = st.session_state.get("contract", {})
    # 2) 직접 입력 (추출값이 있으면 기본값으로 채움)
    join_date = st.text_input("가입일", value=contract.get("계약일", ""), placeholder="예: 2024-03-15")
    product = st.text_input("상품명", value=contract.get("상품명", ""), placeholder="예: OO암보험")
    extra = st.text_area("기타 정보", placeholder="예: 암진단비 3000만원 가입")

    if contract.get("담보목록"):
        st.markdown("**추출된 담보**")
        for d in contract["담보목록"]:
            st.markdown(f"- {d.get('담보명','')} : {d.get('가입금액','')}")

    담보_요약 = "; ".join(
        f"{d.get('담보명','')}({d.get('가입금액','')})" for d in contract.get("담보목록", [])
    )
    user_info = "\n".join(x for x in [
        f"오늘 날짜: {date.today().isoformat()} (면책기간 계산에 사용)",
        f"가입일: {join_date}" if join_date else "",
        f"상품명: {product}" if product else "",
        f"가입 담보: {담보_요약}" if 담보_요약 else "",
        extra,
    ] if x).strip()

# --- 1. 약관 업로드 & 색인 ---
uploaded = st.file_uploader("보험 약관 PDF 업로드", type=["pdf"])
max_pages = st.number_input(
    "분석할 최대 페이지 수 (속도 조절용, 0 = 전체)",
    min_value=0, max_value=2000, value=50, step=50,
    help="약관이 길면 전체 파싱·색인에 수 분이 걸립니다. 데모에서는 50페이지 정도를 권장합니다.",
)
if uploaded and st.button("약관 분석 시작"):
    with st.spinner("약관 파싱 + 색인 중... (페이지 수에 따라 수십 초~수 분 소요)"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded.read())
            path = tmp.name
        markdown = upstage.parse_document(path, max_pages=(int(max_pages) or None))
        os.unlink(path)
        clauses = split_into_clauses(markdown)
        index = ClauseIndex()
        index.build(clauses)
        st.session_state["index"] = index
        st.success(f"색인 완료: {len(clauses)}개 조각")

# --- 2. 모드별 사용 ---
if "index" in st.session_state:
    index = st.session_state["index"]
    mode = st.radio("무엇을 도와드릴까요?",
                    ["🩺 청구 가능 여부 판정", "💬 약관 질문·요약"], horizontal=True)

    if mode == "🩺 청구 가능 여부 판정":
        question = st.text_input("어떤 진단/상황인가요?", placeholder="예: 갑상선암 진단을 받았어요")
        if question:
            with st.spinner("판정 중..."):
                clauses = index.search(question, k=10)
                result = judge.judge(question, clauses, user_info=user_info)

            badge = {"가능": "🟢", "검토필요": "🟡", "어려움": "🔴", "정보부족": "⚪"}.get(result.get("가능성", ""), "⚪")
            st.subheader(f"{badge} 청구 가능성: {result.get('가능성', '?')}")
            if result.get("해당담보"):
                st.markdown(f"**해당 담보:** {result['해당담보']}")
            st.write(result.get("설명", ""))
            if result.get("근거조항"):
                st.markdown("**근거 조항**")
                for c in result["근거조항"]:
                    st.markdown(f"- {c}")
            if result.get("주의사항"):
                st.markdown("**⚠️ 주의사항**")
                for c in result["주의사항"]:
                    st.markdown(f"- {c}")
            if result.get("보험료영향"):
                st.markdown(f"**보험료 영향:** {result['보험료영향']}")
            with st.expander("검색된 약관 원문 보기"):
                for c in clauses:
                    st.markdown(f"**[{c['조항']}]**")
                    st.text(c["text"][:800])

    else:  # 약관 질문·요약
        if st.button("📋 내 보장 내용 한눈에 보기"):
            with st.spinner("보장 내용 정리 중..."):
                st.markdown(qa.summarize_coverage(index, user_info=user_info))

        question = st.text_input("약관에 대해 무엇이든 물어보세요",
                                 placeholder="예: 이 보험 무엇을 보장해? / 면책기간이 뭐야?")
        if question:
            with st.spinner("답변 중..."):
                clauses = index.search(question, k=10)
                st.write(qa.answer(question, clauses, user_info=user_info))
            with st.expander("검색된 약관 원문 보기"):
                for c in clauses:
                    st.markdown(f"**[{c['조항']}]**")
                    st.text(c["text"][:800])

st.divider()
st.caption("※ 본 결과는 참고용입니다. 약관에는 개인 가입 정보가 없으므로 가입일·가입금액 등은 보험증권을 확인하세요. "
           "최종 확인은 보험사 또는 손해사정사를 통해 진행하세요.")
