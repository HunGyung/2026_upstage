"""FastAPI 백엔드.

엔드포인트:
  POST /upload   : 약관 PDF 업로드 -> 파싱 + 색인
  POST /ask      : 질문 -> 청구 가능성 판정
실행: uvicorn backend.main:app --reload  (프로젝트 루트에서)
"""
import os
import tempfile

from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel

from . import upstage, judge
from .rag import split_into_clauses, ClauseIndex

app = FastAPI(title="보험 청구판정 도우미 API")

# 데모용 전역 인덱스 (실서비스에서는 세션/사용자별로 관리해야 함)
INDEX: ClauseIndex | None = None


class AskRequest(BaseModel):
    question: str
    k: int = 5


@app.post("/upload")
async def upload(document: UploadFile = File(...)):
    global INDEX
    suffix = os.path.splitext(document.filename or "")[1] or ".pdf"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await document.read())
        tmp_path = tmp.name
    try:
        markdown = upstage.parse_document(tmp_path)
        clauses = split_into_clauses(markdown)
        if not clauses:
            raise HTTPException(400, "약관에서 조항을 추출하지 못했습니다.")
        INDEX = ClauseIndex()
        INDEX.build(clauses)
        return {"status": "ok", "clause_count": len(clauses)}
    finally:
        os.unlink(tmp_path)


@app.post("/ask")
async def ask(req: AskRequest):
    if INDEX is None:
        raise HTTPException(400, "먼저 /upload 로 약관을 업로드하세요.")
    clauses = INDEX.search(req.question, k=req.k)
    result = judge.judge(req.question, clauses)
    return {"result": result, "matched_clauses": clauses}


@app.get("/health")
async def health():
    return {"status": "alive"}
