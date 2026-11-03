# 트림노트 — 국산차 트림·옵션 상담판

장기렌트 전화 상담 중에 국산차의 트림별 기본사양·선택옵션·가격을 바로 찾아 비교하는 정적 웹페이지입니다.

- 차종 화면: 트림 선택 카드, 트림 가격 사다리, 핵심 사양 18가지 요약, 전체 사양 비교표(차이만 보기·사양 찾기), 옵션 체크 시 합계 계산, 카톡용 요약 복사
- 비교함: 다른 차종의 트림까지 최대 4개를 나란히 비교
- 통합 검색: 차종 이름이나 사양 이름(예: HUD, 2열 통풍)으로 찾기 (단축키 `/`)

## 데이터 출처

| 브랜드 | 출처 |
| --- | --- |
| 현대 | hyundai.com 가격표(트림별 기본품목·선택품목), casper.hyundai.com, 선택품목 상세 API |
| 기아 | kia.com 자가용 가격표(트림별 전체 품목), 선택품목 상세 API |
| 제네시스 | genesis.com 견적(BTO) 데이터 + 공식 가격표 PDF의 주요 사양 |
| KGM | kg-mobility.com 간편견적 API(트림·구동별 가격, 기본품목, 선택품목·패키지 구성, 커스터마이징) |
| 르노코리아 | cdn.renault.co.kr 월별 가격표 PDF |
| 쉐보레 | chevrolet.co.kr 카탈로그/가격표 페이지의 가격표 PDF (국내 생산 차종) |

가격은 각 제조사가 공시한 자가용 가격표 기준이며 탁송료·등록비·프로모션은 들어 있지 않습니다.

## 데이터 갱신 (월 1회 권장)

```bash
pip install beautifulsoup4 lxml pypdf pymupdf pillow
cd scripts
python scrape_hyundai.py
python scrape_kia.py
python scrape_genesis.py
python scrape_kgm.py
python scrape_renault.py
python scrape_chevrolet.py
python fetch_images.py   # 차종 사진을 img/에 저장
python build_index.py
```

쉐보레 가격표 PDF는 달마다 파일 이름이 바뀌므로 `scrape_chevrolet.py`의 `MODELS` 주소를 카탈로그/가격표 페이지에서 확인해 바꿔 주세요. 르노코리아는 최근 6개월 안의 가격표를 자동으로 찾습니다.

갱신 후 `index.html`의 `?v=` 값을 바꾸고 커밋·푸시하면 GitHub Pages에 반영됩니다.

## 로컬에서 보기

```bash
python -m http.server 8765
```

브라우저에서 http://localhost:8765 를 엽니다.
