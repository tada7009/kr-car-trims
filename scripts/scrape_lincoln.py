"""링컨 국내 공식 홈페이지 → data/lincoln/*.json (사진 포함)

- 홈페이지: 공식 수입원 에프엘오토코리아의 flak.co.kr/lincoln (ford.co.kr에서도 연결된다. lincoln.co.kr은 접속되지 않는다)
- 가격·트림: 차종 페이지의 '소비자 가격' — 내장 브라우저에서 렌더링한 본문을 raw/lincoln/pages.json에 저장해 두고 읽는다.
- 사양: 공식 브로슈어 PDF(mediaflak.co.kr)의 제원·사양표. 표 읽기·조립은 scrape_ford.py와 같다.
- 사진: 차종 페이지의 공식 이미지(배경 투명 색상 렌더가 있으면 cut, 없으면 사진)
"""
import sys

from scrape_ford import build, load_pages, matrix, sheet, sheet_items, trim_items

AVIATOR = ["Reserve", "Black Label"]


def nautilus_spec(doc):
    return {"Hybrid": sheet_items(sheet(doc[8], 570))}


def navigator_spec(doc):
    return {"Black Label": sheet_items(sheet(doc[8], 570))}


def aviator_spec(doc):
    st, lines = {}, []
    for pn in range(15, 20):  # MECHANICAL · EXTERIOR · INTERIOR/COMFORT(두 칸) · SAFETY · DRIVER-ASSIST
        for a, b in (((0, 420), (420, 1e4)) if pn == 17 else ((0, 1e4),)):
            lines += matrix(doc[pn], a, b, AVIATOR, [AVIATOR], st)
    feats = trim_items(lines, AVIATOR, warn="aviator")
    dims = []
    for a, b in ((0, 430), (430, 1e4)):  # 제원(왼쪽)·엔진(오른쪽), 아래에 정부 공인 연비
        dims += sheet_items(sheet(doc[20], a, b))
    return {k: dims + feats[k] for k in AVIATOR}


LINCOLN = {
    "nautilus": {
        "name": "Nautilus", "segment": "SUV", "page": "/lincoln/vehicle/nautilus", "brochure": "NAUTILUS",
        "trims": [("하이브리드", None, "Hybrid")],
        "spec": nautilus_spec,
        "photos": {"cut": "nautilus/nat_whisper_blue.png",
                   "int": ["nautilus/hybrid/img--interior1.png", "nautilus/hybrid/img--interior2.png"]},
        "notes": ["공식 브로슈어의 편의·안전 사양은 사진으로만 실려 있어, 글자로 확인되는 제원·엔진·연비·휠만 넣었습니다.",
                  "홈페이지에 등급 이름이 따로 없어 트림 이름을 'Hybrid'(노틸러스 하이브리드)로 적었습니다."],
    },
    "navigator": {
        "name": "Navigator", "segment": "SUV", "page": "/lincoln/vehicle/navigator", "brochure": "NAVIGATOR",
        "trims": [("가솔린", None, "Black Label")],
        "spec": navigator_spec,
        "photos": {"cut": "navigator/2026/sunrise_copper.png",
                   "int": ["navigator/2026/in1.jpg", "navigator/2026/in2.jpg"]},
        "notes": ["공식 브로슈어의 편의·안전 사양은 사진으로만 실려 있어, 글자로 확인되는 제원·엔진·연비·휠만 넣었습니다."],
    },
    "aviator": {
        "name": "Aviator", "segment": "SUV", "page": "/lincoln/vehicle/aviator", "brochure": "AVIATOR",
        "trims": [("가솔린", "Aviator Reserve", "Reserve"), ("가솔린", "Aviator Black Label", "Black Label")],
        "spec": aviator_spec,
        "photos": {"photos": ["aviator/gal-ext-overlay-1.jpg", "aviator/visual-01.png", "aviator/gal-ext-overlay-9.jpg"],
                   "int": ["aviator/gal-int-overlay-1.jpg", "aviator/gal-int-overlay-5.jpg"]},
    },
}


def main(only=None, no_photo=False):
    pages, pdate = load_pages("lincoln")
    for slug, cfg in LINCOLN.items():
        if only and slug not in only:
            continue
        build("lincoln", slug, cfg, pages, pdate, "링컨", no_photo)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    main(set(args) or None, "--no-photo" in sys.argv)
