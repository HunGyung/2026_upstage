"""Streamlit UI - 백엔드 없이 단독 실행 가능한 데모.

실행: streamlit run app.py   (프로젝트 루트에서)
API 키: .env 의 UPSTAGE_API_KEY 사용
"""
import os
import tempfile

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from backend import upstage, judge
from backend.rag import split_into_clauses, ClauseIndex

st.set_page_config(page_title="보험 청구판정 도우미", page_icon="🩺")
st.title("🩺 보험 청구판정 도우미")
st.caption("내 약관으로 확인하는 “이 진단, 보험금 받을 수 있을까?”")

if not os.environ.get("UPSTAGE_API_KEY"):
    st.error(".env 에 UPSTAGE_API_KEY 를 설정한 뒤 다시 실행하세요.")
    st.stop()

# --- 1. 약관 업로드 & 색인 ---
uploaded = st.file_uploader("보험 약관 PDF 업로드", type=["pdf"])
if uploaded and st.button("약관 분석 시작"):
    with st.spinner("약관 파싱 + 색인 중... (수십 초 소요)"):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(uploaded.read())
            path = tmp.name
        markdown = upstage.parse_document(path)
        os.unlink(path)
        clauses = split_into_clauses(markdown)
        index = ClauseIndex()
        index.build(clauses)
        st.session_state["index"] = index
        st.success(f"색인 완료: {len(clauses)}개 조항")

# --- 2. 질문 & 판정 ---
if "index" in st.session_state:
    question = st.text_input("어떤 진단/상황인가요?", placeholder="예: 갑상선암 진단을 받았어요")
    if question:
        with st.spinner("판정 중..."):
            clauses = st.session_state["index"].search(question, k=5)
            result = judge.judge(question, clauses)

        badge = {"가능": "🟢", "검토필요": "🟡", "어려움": "🔴"}.get(result.get("가능성", ""), "⚪")
        st.subheader(f"{badge} 청구 가능성: {result.get('가능성', '?')}")
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

st.divider()
st.caption("※ 본 결과는 참고용입니다. 최종 확인은 보험사 또는 손해사정사를 통해 진행하세요.")
