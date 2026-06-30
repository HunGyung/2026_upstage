# 보험 청구판정 도우미

내 보험 약관 PDF를 올리면, 특정 진단/질병에 대해 **청구 가능 여부**와 **함정 조항(면책기간·감액·보험료 영향)**을 근거 조항과 함께 알려주는 소비자용 AI 서비스. 전 과정을 **Upstage API**(Document Parse + Embeddings + Solar Chat)로 처리한다.

## 빠른 시작

```bash
# 1. 가상환경 + 패키지
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. API 키 설정
cp .env.example .env        # .env 를 열어 UPSTAGE_API_KEY 입력

# 3. 연결 확인 (선택)
python -m backend.upstage   # Solar가 한 문장 응답하면 정상

# 4. 데모 실행 (Streamlit)
streamlit run app.py
```

브라우저에서 약관 PDF 업로드 → "갑상선암 진단받았어요" 입력 → 판정 결과 확인.

## API 서버로 실행 (선택)

```bash
uvicorn backend.main:app --reload
# POST /upload (PDF) -> 파싱+색인,  POST /ask {"question": "..."} -> 판정
```

## 프롬프트 정확도 평가 (promptfoo)

```bash
npm install -g promptfoo
cd eval
UPSTAGE_API_KEY=... promptfoo eval
promptfoo view      # 프롬프트 버전별 정확도 리더보드
```

## 구조

| 파일 | 역할 |
|------|------|
| `backend/upstage.py` | Upstage API 래퍼 (parse / embed / chat) |
| `backend/rag.py` | 약관 조항 분할 + ChromaDB 벡터 색인·검색 |
| `backend/judge.py` | 청구 가능성 판정 프롬프트 + 호출 |
| `backend/main.py` | FastAPI 엔드포인트 |
| `app.py` | Streamlit 데모 UI |
| `eval/` | promptfoo 평가 설정·테스트셋 |

## 개발 순서 (해커톤 권장)

1. **0단계** `python -m backend.upstage` 로 키 동작 확인
2. **1~2단계** 약관 PDF 1개로 파싱→조항 분할→색인이 되는지 확인 (가장 중요한 분기점)
3. **3~4단계** 판정 로직 + Streamlit UI 연결
4. **5단계** promptfoo 로 프롬프트 정확도 측정·개선
5. **6단계** 디스클레이머·데모 리허설·발표자료

## 범위 (MVP)

데모 안정성을 위해 보험 1종(실손 또는 암보험) + 대표 질병 3~5개로 한정 권장.

## 주의

본 서비스의 판정은 **참고용**이며, 최종 확인은 보험사 또는 손해사정사를 통해야 한다. 발표·UI에 디스클레이머를 명시할 것.
