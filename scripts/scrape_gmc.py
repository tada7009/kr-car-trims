"""GMC 코리아 공식 사이트 → data/gmc/*.json (사진까지 한 번에)

- 가격·트림: 온라인 견적(구성기) 페이지 /purchase/onlineshop/car-configuration.gm?dmsModelCd=..
  (시에라는 별도 사이트 sierra.gmckorea.co.kr). 캐딜락과 같은 GM 한국사업장 구성기라 scrape_cadillac의 함수를 쓴다.
- 사양: '카탈로그' 페이지(/e-catalog-price-list)에 걸린 차종별 카탈로그 PDF
  · 아카디아·캐니언·허머 EV SUV: 가격 없는 4쪽 카탈로그 — '사양' 쪽(구역별 사양 목록)과 'FEATURES & SPEC' 쪽(엔진·치수 표)
  · 시에라: 미니 카탈로그 안의 가격표(트림별 판매 가격과 ●/― 사양 표, 개별 액세서리 가격)
- 사진: 구성기의 트림별 렌더(배경 투명)와 실내 사진
"""
import json
import re

import fitz

from common import DATA, curl_get, save
from scrape_cadillac import CFG, configurator, norm, photos

WWW = "https://www.gmckorea.co.kr"
SIERRA = "https://sierra.gmckorea.co.kr"
# 구성기 차종 코드 → (파일 키, 이름, 차급, 연료, 사이트, 모델 페이지, 카탈로그 파일 이름에 든 말)
MODELS = {
    "TL": ("acadia", "Acadia", "SUV", "가솔린", WWW, "/suvs/acadia", "acadia"),
    "T4": ("canyon", "Canyon", "픽업", "가솔린", WWW, "/trucks/canyon", "canyon"),
    "T2": ("hummer-ev-suv", "Hummer EV SUV", "전기 SUV", "전기", WWW, "/electric/hummer-ev/suv", "hummer"),
    "T1": ("sierra", "Sierra", "픽업", "가솔린", SIERRA, "/trucks/sierra-denali", "sierra"),
}
SEATS = {"TL": "4RS", "T4": "4AE", "T2": "4BK", "T1": "4AA"}  # 구성기 실내 사진의 시트 색 코드
RED = 0xCD2027


def catalogs():
    """카탈로그 페이지의 PDF 주소 {파일 이름: 주소}"""
    found = {}
    for base in (WWW, SIERRA):
        h = curl_get(base + "/e-catalog-price-list", cache=False)
        for p in re.findall(r'["\'](/content/dam/[^"\']+?\.pdf)', h):
            found.setdefault(p.rsplit("/", 1)[-1].lower(), base + p)
    return found


def lines(page):
    out = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            t = "".join(s["text"] for s in l["spans"]).strip()
            if t:
                x0, y0, x1, y1 = l["bbox"]
                sp = l["spans"][0]
                out.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1, "cy": (y0 + y1) / 2, "size": sp["size"],
                            "color": sp["color"], "t": " ".join(t.split())})
    return out


# ---------- 아카디아·캐니언·허머: 구역별 사양 목록 ----------
def feature_page(page):
    """'사양' 쪽 → [(구역, 사양)]. 왼쪽 칸에 구역 이름, 오른쪽 칸에 한 줄씩 사양(가로선으로 칸이 나뉜다)"""
    L = lines(page)
    heads = [l for l in L if 9.0 <= l["size"] < 10.0]
    if not any("파워트레인" in h["t"] for h in heads):
        return []
    segs = [(d["rect"].x0, d["rect"].y0, d["rect"].x1) for d in page.get_drawings()
            if d["rect"].height < 3 and d["rect"].width > 50]
    out = []
    for cx in sorted({round(h["x0"]) for h in heads}):
        hl = [s for s in segs if abs(s[0] - cx) < 3]  # 구역 칸의 가로선 = 구역 경계
        if not hl:
            continue
        hx1 = max(s[2] for s in hl)
        il = [s for s in segs if abs(s[0] - hx1) < 3]  # 사양 칸의 가로선 = 줄 경계
        if not il:
            continue
        ix1 = max(s[2] for s in il)
        sb = sorted({round(s[1], 1) for s in hl})
        rb = sorted({round(s[1], 1) for s in il} | set(sb))
        names = {}
        for k in range(len(sb) - 1):
            h = next((h for h in heads if abs(h["x0"] - cx) < 3 and sb[k] <= h["cy"] < sb[k + 1]), None)
            names[k] = h["t"] if h else ""
        cells = {}
        for l in L:
            if not (7.5 <= l["size"] < 9.0 and ix1 - 15 < l["x1"] < ix1 + 6 and sb[0] <= l["cy"] < sb[-1]):
                continue
            r = max(i for i, y in enumerate(rb) if y <= l["cy"])
            cells.setdefault(r, []).append(l)
        for r in sorted(cells):
            y = rb[r]
            k = max(i for i, v in enumerate(sb) if v <= y)
            t = " ".join(x["t"] for x in sorted(cells[r], key=lambda x: x["y0"]))
            if names.get(k):
                out.append((names[k], t))
    return out


def spec_page(page):
    """'FEATURES & SPEC' 쪽의 ENGINE·DIMENSION 표 → ['항목: 값']"""
    L = lines(page)
    if not any(l["t"] == "DIMENSION" for l in L):
        return []
    top = min(l["y0"] for l in L if l["t"] in ("ENGINE", "DIMENSION"))
    out = []
    for l in sorted(L, key=lambda x: x["y0"]):
        if l["x0"] < 40 and 8.0 <= l["size"] < 9.0 and l["y0"] > top and not l["t"].startswith("*"):
            v = [x for x in L if abs(x["cy"] - l["cy"]) < 2 and x["x0"] > 150 and x["x1"] < 430 and 8.0 <= x["size"] < 9.0]
            if v:
                out.append(f"{l['t']}: {' '.join(x['t'] for x in sorted(v, key=lambda x: x['x0']))}")
    return out


# ---------- 시에라: 가격표 ----------
def price_table(doc):
    """가격표 쪽들 → ({트림: 가격}, {트림: [(구역, 사양)]}, 제원, 액세서리 [(이름, 가격)])"""
    prices, rows, spec, acc = {}, {}, [], []
    for page in doc:
        L = lines(page)
        text = page.get_text()
        if "엔진 배기량" in text and not spec:  # 가격표 위 한 줄 제원(칸 사이가 공백 여러 개)
            line = next(t for t in text.split("\n") if t.strip().startswith("엔진 배기량"))
            for x in re.split(r"\s{2,}", line):
                x = x.strip()
                if x:
                    spec.append(f"에너지소비효율 {x}" if re.fullmatch(r"\d등급", x) else x)
        if "개별 액세서리 품목" in text:
            for n, p in re.findall(r"\n([^\n:※*]+?)\s*\n?:\s*(\d{1,3}(?:,\d{3})+)", text):
                acc.append((" ".join(n.split()), int(p.replace(",", ""))))
        pr = next((l for l in L if l["t"] == "판매 가격 (원)"), None)
        tr = next((l for l in L if l["t"] == "트림"), None)
        if not (pr and tr):
            continue
        pcols = sorted((l for l in L if abs(l["cy"] - pr["cy"]) < 3 and re.fullmatch(r"[\d,]{7,}", l["t"])), key=lambda x: x["x0"])
        ncols = sorted((l for l in L if abs(l["cy"] - tr["cy"]) < 4 and l["x0"] > 200), key=lambda x: x["x0"])
        if len(pcols) != len(ncols):
            continue
        names = [n["t"] for n in ncols]
        centers = [(p["x0"] + p["x1"]) / 2 for p in pcols]
        for n, p in zip(names, pcols):
            prices[n] = int(p["t"].replace(",", ""))
            rows.setdefault(n, [])
        cat = None
        for l in sorted(L, key=lambda x: x["y0"]):
            if l["y0"] <= pr["y1"] or l["x0"] > 40:
                continue
            if l["color"] == RED and l["size"] >= 7.5:
                cat = l["t"]
                continue
            if 6.0 <= l["size"] < 7.5 and cat:
                marks = [m for m in L if m["t"] in ("●", "―", "-") and abs(m["cy"] - l["cy"]) < 4 and m["x0"] > 300]
                for m in marks:
                    mx = (m["x0"] + m["x1"]) / 2
                    i = min(range(len(centers)), key=lambda k: abs(centers[k] - mx))
                    if m["t"] == "●":
                        rows[names[i]].append((cat, l["t"]))
    for page in doc:  # 'PERFORMANCE' 소개 쪽의 견인력
        for t in page.get_text().split("\n"):
            if t.strip().startswith("최대견인력") and t.strip() not in spec:
                spec.append(t.strip())
    return prices, rows, spec, acc


def to_cats(pairs):
    cats = {}
    for c, n in pairs:
        lst = cats.setdefault(c, [])
        if n not in lst:
            lst.append(n)
    return [{"cat": c, "items": [{"n": n} for n in v]} for c, v in cats.items()]


def build(code, pdfs, old):
    key, name, seg, fuel, base, page, kw = MODELS[code]
    _, trims = configurator(base, code)
    if not trims:
        print("트림 없음", code)
        return None
    pdf = next((u for f, u in sorted(pdfs.items()) if kw in f), None)
    doc = fitz.open(stream=curl_get(pdf, binary=True, cache=False), filetype="pdf") if pdf else None
    title = ""
    if doc:
        m = re.search(r"(20\d\d) GMC\s*\n?\s*([A-Z][A-Z \n]+)", doc[0].get_text())
        title = m.group(1) if m else ""
    out, notes, missing = [], [], []
    if code == "T1" and doc:  # 시에라: 카탈로그 가격표
        prices, rows, spec, acc = price_table(doc)
        by = {norm(n): n for n in prices}
        for t in trims:
            n = by.get(norm(t["name"]))
            if n is None:
                missing.append(t["name"])
                price, pairs = t["price"], []
            else:
                price, pairs = prices[n], rows[n]
                if price != t["price"]:
                    print(f"  가격 다름 {t['name']}: 카탈로그 {price:,} / 구성기 {t['price']:,}")
            cats = ([{"cat": "제원", "items": [{"n": x} for x in spec]}] if spec else []) + to_cats(pairs)
            opts = [{"n": a, "p": p, "g": "GM 순정 액세서리"} for a, p in acc]
            out.append({"name": t["name"], "price": price, "cats": cats, "adds": [], "opts": opts})
        ym = re.search(r"(20\d\d)(\d\d)", pdf.rsplit("/", 1)[-1])
        pdate = f"{ym.group(1)}-{ym.group(2)}-01" if ym else "2026-11-11"
        notes.append(f"GMC 시에라 공식 미니 카탈로그({ym.group(1)}년 {int(ym.group(2))}월호, PDF) 가격표의 판매 가격과 트림별 사양입니다"
                     f"{f'({title}년형)' if title else ''}." if ym else "GMC 시에라 공식 카탈로그 가격표의 판매 가격과 트림별 사양입니다.")
        notes.append("카탈로그에 따르면 화물차 세금이 적용되어 개별소비세·교육세가 면제되고, 개인사업자는 부가세 10% 환급을 받을 수 있습니다.")
        notes.append("DENALI Scarlet Night는 지엠 순정 액세서리 패키지를 적용한 스페셜 에디션입니다. "
                     "개별 액세서리 가격은 차량과 함께 살 때의 장착 공임·부가세 포함 가격이며, 판매·보증은 지엠 공식 액세서리 총판이 맡습니다.")
        structure = "price-list"
    else:  # 아카디아·캐니언·허머: 구성기 가격 + 카탈로그 사양
        feats, spec = [], []
        for p in doc or []:
            feats = feats or feature_page(p)
            spec = spec or spec_page(p)
        cat_title = ""
        if doc:
            for p in doc:
                m = re.search(r"20\d\d [A-Z][A-Z ]+", p.get_text())
                if m and "사양" in p.get_text() and feature_page(p):
                    cat_title = m.group(0).strip()
        for t in trims:
            cats = [{"cat": "주요 사양", "items": [{"n": k} for k in t["keys"]]}] if t["keys"] else []
            # 카탈로그는 한 트림 기준이라, 트림이 여럿이 되면 카탈로그 제목에 이름이 든 트림에만 붙인다
            fits = len(trims) == 1 or (cat_title and norm(t["name"]) in norm(cat_title))
            if fits and spec:
                cats.append({"cat": "제원", "items": [{"n": x} for x in spec]})
            if fits and feats:
                cats += to_cats(feats)
            else:
                missing.append(t["name"])
            out.append({"name": t["name"], "price": t["price"], "cats": cats, "adds": [], "opts": []})
        pdate = "2026-11-11"
        basis = "개별소비세 5.0% 기준, 부가세 포함" if code != "T4" else "부가세 포함"
        notes.append(f"GMC 공식 온라인 견적(구성기)의 판매 가격({basis})과 GMC 공식 카탈로그({cat_title or name}, PDF)의 사양·제원입니다. "
                     "가격표 날짜가 없어 조회일 기준입니다.")
        if code == "T4":
            notes.append("캐니언(픽업) 가격에는 공식 사이트의 '개별소비세 5.0% 적용 기준' 표시가 붙어 있지 않습니다.")
        if fuel == "전기":
            notes.append("전기차 구매 보조금은 반영되지 않은 가격입니다.")
        structure = "configurator"
    if missing:
        notes.append("카탈로그에서 사양을 찾지 못한 트림(" + ", ".join(missing) + ")은 구성기 주요 사양만 실었습니다.")
    out.sort(key=lambda t: t["price"])
    src = [base + CFG.format(code), base + page] + ([pdf] if pdf else [])
    d = {"id": f"gmc-{key}", "brand": "gmc", "name": name, "segment": seg, "image": "", "imageSource": "",
         "lowPrice": min(t["price"] for t in out), "priceDate": pdate, "sources": src, "structure": structure,
         "variants": [{"name": fuel, "code": code, "trims": out}],
         "media": {"hero": "", "heroType": "cut", "ext": [], "int": []}, "notes": notes}
    photos(d, sorted(trims, key=lambda t: t["price"]), SEATS.get(code), old)
    return d


def main():
    out = DATA / "gmc"
    out.mkdir(parents=True, exist_ok=True)
    pdfs = catalogs()
    known = dict(configurator(WWW, "T2")[0])
    known.update(configurator(SIERRA, "T1")[0])
    for c in known:
        if c not in MODELS:
            print("구성기에 새 차종이 있음(MODELS에 추가 필요):", c, known[c])
    for code in MODELS:
        f = out / f"{MODELS[code][0]}.json"
        old = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        d = build(code, pdfs, old)
        if not d:
            continue
        save(f, d)
        print(d["id"], d["structure"], d["media"]["heroType"],
              [(t["name"], t["price"], sum(len(c["items"]) for c in t["cats"]), len(t["opts"])) for t in d["variants"][0]["trims"]])


if __name__ == "__main__":
    main()
