"""BYD코리아 공식 홈페이지(www.bydauto.kr) → data/byd/*.json

- 가격·트림: 모델 페이지(/car/byd-<모델>) 첫 화면의 트림별 가격(만 원 단위). 공식 '견적내기'
  (/purchase/build-my-car/<모델>)는 트림 정보를 페이지 안에서 POST로 받아 와서, 내장 브라우저로 받아 둔
  raw/byd/build_my_car.json(원 단위 가격·기본 색상)으로 가격을 맞춰 보고 사진 주소를 만든다.
- 사양: 모델 페이지 '차량 제원 및 에너지 소비 효율'·'차량 기본 옵션 사양' 표(●사용 / -미사용 / 값)
- 사진: 견적내기의 배경 투명 렌더(/static/images/purchase/build_my_car/<모델>/<트림>/<색>_f.png)와
  실내 사진(<내장색>_f.jpg, _s.jpg). 받지 못하면 이전 실행에서 저장한 사진 정보를 그대로 둔다.
"""
import html as H
import json
import re
import sys
from pathlib import Path

from common import DATA, curl_get, save
from fetch_import_media import cut_from, load, save as save_img

BASE = "https://www.bydauto.kr"
RAW = Path(__file__).resolve().parent / "raw" / "byd"
PRICE_DATE = "2026-11-11"  # 홈페이지 가격에 날짜가 없다
# 홈페이지 모델 키 → (파일 이름, 차종 이름, segment, 변형 이름)
MODELS = {
    "dolphin": ("dolphin", "DOLPHIN", "전기 해치백", "전기"),
    "atto3": ("atto-3", "ATTO 3", "전기 SUV", "전기"),
    "seal": ("seal", "SEAL", "전기 세단", "전기"),
    "sealion7": ("sealion-7", "SEALION 7", "전기 SUV", "전기"),
    "sealion6": ("sealion-6-dm-i", "SEALION 6 DM-i", "SUV", "플러그인 하이브리드"),
}
# 가격 기준이 적힌 BYD코리아 공식 보도자료(브랜드 > 뉴스)
NEWS = {
    "dolphin": [103],
    "atto3": [],
    "seal": [98, 30],
    "sealion7": [128],
    "sealion6": [156, 179],
}
BASIS = {
    "dolphin": "가격 기준은 BYD코리아 출시 보도자료(2026-02-05)대로 '환경친화적자동차 세제혜택 적용 후, 보조금 적용 전'입니다.",
    "seal": "가격 기준은 BYD코리아 보도자료(씰·씰 플러스 2026-02-02, 다이내믹 AWD 2025-07-01)대로 '세제혜택 적용 후, 전기차 구매보조금 적용 전'입니다.",
    "sealion7": "가격 기준은 BYD코리아 보도자료(2026-04-16)대로 '환경친화적자동차 세제혜택 적용 후, 보조금 적용 전'입니다.",
    "atto3": "현재 가격(3,490만 원)의 세제 혜택 반영 여부는 공식 홈페이지·보도자료에 적혀 있지 않습니다(2025년 출시 보도자료의 가격은 '전기차 구매보조금 및 세제혜택 적용 전' 기준이었습니다). 전기차 보조금은 들어 있지 않은 가격입니다.",
    "sealion6": "플러그인 하이브리드 차종으로, 공식 보도자료(2026-06-26 FWD, 2026-10-06 AWD)에는 '권장소비자가격'으로만 적혀 있고 세제 혜택 반영 여부는 따로 적혀 있지 않습니다.",
}
CAT_ORDER = ["제원·성능", "일렉트릭 파워트레인", "파워트레인", "외장", "내장", "시트", "인포테인먼트", "안전 및 운전자 보조", "편의 사양"]
SPEC_TABLES = ("차량 제원 정보", "에너지 소비 효율 정보", "배터리 셀 정보")


def text(s):
    s = re.sub(r"<br\s*/?>", " ", s)
    return " ".join(H.unescape(re.sub(r"<[^>]+>", " ", s)).split())


def span(attrs, name):
    m = re.search(name + r'="(\d+)"', attrs)
    return int(m.group(1)) if m else 1


def prices(h):
    """모델 페이지 첫 화면 <dt>BYD …</dt><dd>4,690 만 원</dd> → [(트림, 원)]"""
    out = {}
    for n, p in re.findall(r"<dt>\s*(BYD [^<]+?)\s*</dt>\s*<dd>\s*([\d,]+)\s*만\s*원\s*</dd>", h):
        out.setdefault(text(n), int(p.replace(",", "")) * 10000)
    return list(out.items())


def short(name):
    return re.sub(r"^BYD\s+", "", name).strip()


def tables(h):
    """[(캡션, thead 칸 [(글, colspan)], tbody 줄 [[(글, colspan, rowspan)]])]"""
    out = []
    for x in re.findall(r"<table.*?</table>", h, re.S):
        cap = re.search(r"<caption>(.*?)</caption>", x, re.S)
        thead = re.search(r"<thead>(.*?)</thead>", x, re.S)
        tbody = re.search(r"<tbody>(.*?)</tbody>", x, re.S)
        ths = [(text(c), span(a, "colspan")) for a, c in re.findall(r"<th([^>]*)>(.*?)</th>", thead.group(1), re.S)] if thead else []
        rows = []
        for r in re.findall(r"<tr[^>]*>(.*?)</tr>", tbody.group(1) if tbody else "", re.S):
            cells = []
            for a, c in re.findall(r"<td([^>]*)>(.*?)</td>", r, re.S):
                c = re.sub(r'<span class="blind">.*?</span>', "", c, flags=re.S)  # '●<span class="blind">사용</span>'
                cells.append((text(c), span(a, "colspan"), span(a, "rowspan")))
            if cells:
                rows.append(cells)
        out.append((text(cap.group(1)) if cap else "", ths, rows))
    return out


def by_trim(ths, rows, trims):
    """제원·사양 표 → {트림: [품목 문구]}. 머리글 칸이 'SEAL / SEAL Plus'처럼 여러 트림을 묶기도 한다."""
    label_span = ths[0][1]
    cols, pos = [], label_span  # (시작 위치, 트림 이름들)
    for t, sp in ths[1:]:
        cols.append((pos, [x.strip() for x in t.split(" / ")]))
        pos += sp
    col_of = {}
    for tr in trims:
        for start, names in cols:
            if short(tr) in names:
                col_of[tr] = start
    out = {tr: [] for tr in trims}
    for cells in rows:
        lab, acc, i = [], 0, 0
        while i < len(cells) and acc < label_span:
            lab.append(cells[i][0])
            acc += cells[i][1]
            i += 1
        label = " ".join(x for x in lab if x)
        at = {}
        p = acc
        for t, sp, _ in cells[i:]:
            for q in range(p, p + sp):
                at[q] = t
            p += sp
        for tr in trims:
            if tr not in col_of:
                continue
            v = at.get(col_of[tr], "")
            if v.startswith("●"):
                out[tr].append(label)
            elif v and v not in ("-", "–", "—") and not v.startswith("○"):
                out[tr].append(f"{label}: {v}")
    return out


def tires(ths, rows, trims):
    """타이어 에너지 소비 효율 등급 표 → {트림: [품목]} ('모델' 칸이 없으면 모든 트림 공통)"""
    has_model = ths and ths[0][0] == "모델"
    out = {tr: [] for tr in trims}
    cur = list(trims)
    for cells in rows:
        vals = [c[0] for c in cells]
        if has_model and len(vals) == 5:
            names = [short(x) for x in re.split(r"\s*(?=BYD )", vals[0]) if x.strip()]
            cur = [tr for tr in trims if short(tr) in names]
            vals = vals[1:]
        if len(vals) < 4:
            continue
        maker, size, rrc, wet = vals[:4]
        for tr in cur:
            out[tr] += [f"타이어 규격: {size} ({maker})",
                        f"타이어 에너지 소비 효율 등급: 회전 저항 (RRC) {rrc} / 젖은 노면 제동력 (G) {wet}"]
    return out


def photos(d, key, old, cfg):
    """견적내기 렌더(배경 투명) + 실내 사진. 실패하면 이전 사진 정보를 돌려준다."""
    keep = {k: old[k] for k in ("image", "media", "imageSource") if old.get(k)}
    trims = [t for t in cfg.values() if t.get("modelCode") == key]
    if not trims:  # 견적내기 자료가 없으면 메인 화면의 모델 렌더(배경 투명)
        urls, inner = [f"{BASE}/static/images/main/model_{key}.png"], []
    else:
        t = trims[-1]  # 최상위 트림의 기본 색상
        base = f"{BASE}/static/images/purchase/build_my_car/{key}/{t['trimCode']}/"
        st = t.get("stColorCode") or t["exteriorColors"][0]["code"]
        si = t.get("stInteriorColorCode") or t["interiorColors"][0]["code"]
        urls = [base + f"{st}_f.png", f"{BASE}/static/images/main/model_{key}.png"]
        inner = [base + f"{si}_f.jpg", base + f"{si}_s.jpg"]
    r = None
    for u in urls:
        try:
            r = cut_from(d, u)
        except Exception as e:
            print("  사진 실패", u, e)
        if r:
            break
    if not r:
        return keep
    ints = []
    for n, u in enumerate(inner, 1):
        try:
            ints.append(save_img(load(u), f"{d['id']}-i{len(ints) + 1}.webp", False, 1600))
        except Exception as e:
            print("  실내 사진 실패", u, e)
    r["media"]["int"] = ints or (old.get("media") or {}).get("int", [])
    return {"image": r["image"], "media": r["media"], "imageSource": r["src"]}


def main(only=None):
    out_dir = DATA / "byd"
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = RAW / "build_my_car.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
    for key, (slug, name, seg, fuel) in MODELS.items():
        if only and key not in only:
            continue
        page = f"{BASE}/car/byd-{key}"
        h = curl_get(page, cache=False)
        plist = prices(h)
        if not plist:
            print("가격 없음", key)
            continue
        trims = [n for n, _ in plist]
        for n, p in plist:  # 견적내기 원 단위 가격과 맞춰 본다
            c = next((t for t in cfg.values() if t.get("trimName") == n), None)
            if c and c.get("trimPrice") != p:
                print(f"  ! 가격 다름 {n}: 모델 페이지 {p:,} / 견적내기 {c['trimPrice']:,}")
            if cfg and not c:
                print(f"  ! 견적내기 자료에 없는 트림 {n}")
        cats = {tr: {} for tr in trims}
        for cap, ths, rows in tables(h):
            if not ths or not rows or cap == "소비자 판매가격 정보":
                continue
            if cap.startswith("타이어"):
                got, cname = tires(ths, rows, trims), "제원·성능"
            else:
                got = by_trim(ths, rows, trims)
                cname = "제원·성능" if cap in SPEC_TABLES else re.sub(r"\s*정보$", "", cap)
            for tr, items in got.items():
                lst = cats[tr].setdefault(cname, [])
                lst.extend(x for x in items if x not in lst)
        tlist = []
        for n, p in plist:
            cs = [{"cat": c, "items": [{"n": x} for x in cats[n][c]]}
                  for c in sorted(cats[n], key=lambda c: CAT_ORDER.index(c) if c in CAT_ORDER else 99) if cats[n][c]]
            tlist.append({"name": short(n), "price": p, "cats": cs, "adds": [], "opts": []})
        empty = [t["name"] for t in tlist if not t["cats"]]
        notes = ["BYD코리아 공식 홈페이지(bydauto.kr) 모델 페이지와 '견적내기'의 판매 가격, 모델 페이지 '차량 제원 및 에너지 소비 효율'·"
                 "'차량 기본 옵션 사양' 표의 트림별 사양입니다. 연식 표기는 없습니다.", BASIS[key],
                 "공식 견적내기에는 유료 선택 품목과 유료 색상이 없습니다(모든 색상 0원)."]
        if empty:
            notes.append("사양이 비어 있는 트림(" + ", ".join(empty) + ")은 공식 사양표에서 찾지 못해 가격만 실었습니다.")
        d = {"id": f"byd-{slug}", "brand": "byd", "name": name, "segment": seg, "image": "", "imageSource": "",
             "lowPrice": min(p for _, p in plist), "priceDate": PRICE_DATE,
             "sources": [page, f"{BASE}/purchase/build-my-car/{key}"] + [f"{BASE}/brand/news-view/{i}" for i in NEWS[key]],
             "structure": "web", "variants": [{"name": fuel, "code": key, "trims": tlist}], "notes": notes}
        path = out_dir / f"{slug}.json"
        old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        d.update(photos(d, key, old, cfg))
        if not d.get("media"):
            d["media"] = {"hero": "", "heroType": "cut", "ext": [], "int": []}
        save(path, d)
        print(d["id"], [(t["name"], t["price"], sum(len(c["items"]) for c in t["cats"])) for t in tlist],
              d["media"].get("heroType"), len(d["media"].get("int", [])))


if __name__ == "__main__":
    main(set(sys.argv[1:]) or None)
