"""랜드로버 코리아 공식 가격표 PDF(전 차종 한 장) + 차종별 '모델 및 제원' 페이지(트림별 사양) → data/landrover/*.json

- 가격·트림: 디펜더·디스커버리 페이지에 걸린 'PRICE CHART' PDF(블랙박스·하이패스·ONE CARE 포함 권장 소비자 가격)
- 사양: /<라인>/<차종>/models-and-specifications.html 의 트림 카드(주요 사양 + 기본 사양)
  가격표 트림과 이름이 같은 카드만 붙인다. 이름이 다르면(홈페이지 카드가 다른 트림) 사양을 비워 둔다.
"""
import html as H
import re

import fitz

from common import DATA, curl_get, save

BASE = "https://www.landroverkorea.co.kr"
SPEC = "/models-and-specifications.html"
# 가격표 차종 이름 → (파일 키, 사양 페이지들 {차체: 경로})
MODELS = {
    "Defender": ("defender", {"90": "/defender/defender-90", "110": "/defender/defender-110",
                              "130": "/defender/defender-130", "OCTA": "/defender/defender-octa"}),
    "Discovery": ("discovery", {"": "/discovery/discovery"}),
    "Discovery Sport": ("discovery-sport", {"": "/discovery/discovery-sport"}),
    "Range Rover": ("range-rover", {"": "/range-rover/range-rover"}),
    "Range Rover Sport": ("range-rover-sport", {"": "/range-rover/range-rover-sport"}),
    "Range Rover Velar": ("range-rover-velar", {"": "/range-rover/range-rover-velar"}),
    "Range Rover Evoque": ("range-rover-evoque", {"": "/range-rover/range-rover-evoque"}),
}
PREFIX = ["RANGE ROVER SPORT ", "RANGE ROVER VELAR ", "RANGE ROVER EVOQUE ", "RANGE ROVER ",
          "DISCOVERY SPORT ", "DISCOVERY ", "DEFENDER "]
ENGINE = {"D": "디젤 마일드 하이브리드", "P250": "가솔린", "P300": "가솔린",
          "PHEV": "가솔린 플러그인 하이브리드(PHEV)", "P": "가솔린 마일드 하이브리드(MHEV)"}
ORDER = ["90", "110", "130", "OCTA", "가솔린", "디젤", "플러그인 하이브리드"]
PRICE = re.compile(r"^\d{2,3},\d{3},\d{3}$")
ENG = re.compile(r"^(?:(90|110|130) )?([PD]\d{3}e?)(?: (SV))?$")
YEAR = re.compile(r"\((\d{4}(?:\.\d)?)년형\)")


def chart_url():
    found = set()
    for p in ("/defender/index.html", "/discovery/index.html", "/defender/defender-110/index.html"):
        found.update(re.findall(r'(/content/dam/lrdx/pdfs/kr/(\d{6})_[^"\']*PRICE[^"\']*\.pdf)', curl_get(BASE + p, cache=False)))
    path, ymd = max(found, key=lambda x: x[1])
    return BASE + path.replace(" ", "%20"), f"20{ymd[:2]}-{ymd[2:4]}-{ymd[4:]}"


def chart(pdf):
    """가격표 → {차종: {"year": 연식, "rows": [(차체, 엔진, 트림, 가격)]}}"""
    lines = [l.strip() for p in fitz.open(stream=pdf, filetype="pdf") for l in p.get_text().split("\n") if l.strip()]
    out, model, body, eng, trim, pend = {}, None, "", "", None, None
    for i, l in enumerate(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if l.startswith("*") or l in ("모델", "엔진", "트림", "권장 소비자 판매 가격") or l.startswith("(대시캠") or l.startswith("(단위"):
            continue
        if l == "Range Rover" and re.match(r"^(Velar|Evoque)\b", nxt):
            pend = "Range Rover"
            continue
        if pend:
            l, pend = f"{pend} {l}", None
        name = YEAR.sub("", l).strip()
        if name in MODELS:
            model, body, eng = name, "", ""
            out[model] = {"year": None, "rows": []}
            if YEAR.search(l):
                out[model]["year"] = YEAR.search(l).group(1)
            continue
        if YEAR.fullmatch(l):
            if model and not out[model]["year"]:
                out[model]["year"] = YEAR.match(l).group(1)
            continue
        m = ENG.match(l)
        if m:
            body, eng = m.group(1) or "", m.group(2)
            trim = "SV" if m.group(3) else None  # 'P635 SV' 아래 'Black'·'Carbon' → 'SV Black'
            continue
        if PRICE.match(l):
            out[model]["rows"].append((body, eng, trim, int(l.replace(",", ""))))
            trim = "SV" if trim and trim.startswith("SV") else None
            continue
        if model:
            t = " ".join(l.split())
            trim = t if not trim or t == trim else f"{trim} {t}"
    return out


def text(s):
    return " ".join(H.unescape(re.sub(r"<[^>]+>", " ", s)).split())


def spec_page(path):
    """트림 카드 → [{"sid", "name", "img", "key": [...], "cats": {제목: [...]}}]"""
    h = curl_get(BASE + path + SPEC)
    marks = list(re.finditer(r'<div class="([^"]*DerivativeViewer__spec-column--column-(\d+)[^"]*)"([^>]*)>', h))
    cols, group = {}, ""  # 차체 탭(SWB/LWB 등)마다 열 번호가 1부터 다시 시작하므로 (차체, 열)로 묶는다
    for k, m in enumerate(marks):
        chunk = h[m.end(): marks[k + 1].start() if k + 1 < len(marks) else m.end() + 60000]
        cls = m.group(1)
        g = (re.search(r'data-specpack-id="(A_[A-Za-z0-9_]+?)--', m.group(3)) or re.search(r'\b(A_[A-Za-z0-9_]+?)--A_', cls)
             or re.search(r'accordion-control-panel-(A_[A-Za-z0-9_]+)-\d+"', chunk[:600]))
        group = g.group(1) if g else group
        c = cols.setdefault((group, int(m.group(2))), {"sid": "", "name": "", "img": "", "key": [], "cats": {}})
        items = [text(x) for x in re.findall(r'<p class="DerivativeViewer__spec-description[^"]*"[^>]*>(.*?)</p>', chunk, re.S)]
        items = [x for x in items if x]
        if "spec-image-container" in cls:
            sid = re.search(r'data-specpack-id="([^"]+)"', m.group(3))
            c["sid"] = sid.group(1) if sid else ""
            img = re.search(r'<img[^>]+src="([^"]+)"', chunk)
            c["img"] = img.group(1) if img else ""
        elif "model-and-price" in cls:
            n = re.search(r'spec-full-derivative-name[^>]*>(.*?)</h2>', chunk, re.S)
            c["name"] = text(n.group(1)) if n else ""
        elif "key-features-wrapper" in cls:
            c["key"] = list(dict.fromkeys(items))
        elif "spec-sections-row" in cls:
            hd = re.search(r'<h3[^>]*>(.*?)</h3>', chunk, re.S)
            if hd and items:
                lst = c["cats"].setdefault(text(hd.group(1)), [])
                lst.extend(x for x in items if x not in lst)
    return [c for _, c in sorted(cols.items()) if c["name"]]


def norm(s):
    s = " ".join(s.upper().replace("(", " ").replace(")", " ").split())
    for p in PREFIX:
        if s.startswith(p):
            return s[len(p):]
    return s


def match(trim, cards):
    """가격표 트림 이름 → 같은 트림 카드(없으면 None)"""
    t = norm(trim)
    body = None
    if re.search(r"\b[SL]WB\b", t):
        body = "LWB_7" if "7 SEAT" in t else ("LWB" if "LWB" in t else "SWB")
        t = " ".join(w for w in re.sub(r"7 SEAT", "", t).split() if w not in ("SWB", "LWB"))
    for c in cards:
        n, cb = norm(c["name"]), re.match(r"A_(.+?)--", c["sid"])
        if body and (not cb or cb.group(1) != body):
            continue
        if n == t:
            return c
        if t.startswith("TROPHY") and n.startswith("TROPHY") and t.split()[-1] in n.split():
            return c
    return None


def engine_desc(e):
    if e.startswith("D"):
        return ENGINE["D"]
    if e.endswith("e"):
        return ENGINE["PHEV"]
    return ENGINE.get(e, ENGINE["P"])


def fuel(e):
    return "디젤" if e.startswith("D") else ("플러그인 하이브리드" if e.endswith("e") else "가솔린")


def main():
    url, pdate = chart_url()
    data = chart(curl_get(url, binary=True, cache=False))
    out = DATA / "landrover"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.json"):
        old.unlink()
    for mname, (key, pages) in MODELS.items():
        if mname not in data or not data[mname]["rows"]:
            print("가격표에 없음", mname)
            continue
        cards = {b: spec_page(p) for b, p in pages.items()}
        variants, missing, img = {}, [], ""
        for body, eng, trim, price in data[mname]["rows"]:
            page = "OCTA" if trim.upper().startswith("OCTA") else body
            card = match(trim, cards.get(page) or cards.get("") or [])
            cats = [{"cat": "파워트레인", "items": [{"n": f"{eng} {engine_desc(eng)}"}]}]
            if card:
                if card["key"]:
                    cats.append({"cat": "주요 사양", "items": [{"n": x} for x in card["key"]]})
                cats += [{"cat": k, "items": [{"n": x} for x in v]} for k, v in card["cats"].items()
                         if k != "충전" or eng.endswith("e")]  # 같은 카드라도 충전 항목은 PHEV에만
                img = img or card["img"]
            else:
                missing.append(trim)
            name = " ".join(x for x in (body, eng, trim) if x)
            vname = (body if mname == "Defender" and page != "OCTA" else "OCTA" if page == "OCTA" else fuel(eng))
            variants.setdefault(vname, []).append({"name": name, "price": price, "cats": cats, "adds": [], "opts": []})
        if not img:
            for cs in cards.values():
                img = img or next((c["img"] for c in cs if c["img"]), "")
        notes = [f"랜드로버 코리아 공식 가격표({pdate})의 권장 소비자 가격(부가세·블랙박스·하이패스·ONE CARE 포함)과 "
                 f"차종별 '모델 및 제원' 페이지의 트림별 사양입니다. 연식: {data[mname]['year'] or '-'}년형."]
        if missing:
            notes.append("사양이 비어 있는 트림(" + ", ".join(missing) + ")은 공식 '모델 및 제원' 페이지에 같은 이름의 트림 카드가 없어 가격만 실었습니다.")
        if mname == "Range Rover":
            notes.append("LWB 모델에는 전동식 사이드 스텝이 기본 장착되며 가격에 포함되어 있습니다.")
        vs = [{"name": k, "code": key, "trims": variants[k]} for k in sorted(variants, key=ORDER.index)]
        d = {"id": f"landrover-{key}", "brand": "landrover", "name": mname, "segment": "SUV", "image": "",
             "imageSource": img, "lowPrice": min(t["price"] for v in vs for t in v["trims"]), "priceDate": pdate,
             "sources": [url] + [BASE + p + SPEC for p in pages.values()], "structure": "price-list",
             "variants": vs, "notes": notes}
        save(out / f"{key}.json", d)
        print(d["id"], [(v["name"], [(t["name"], t["price"], len(t["cats"])) for t in v["trims"]]) for v in vs])


if __name__ == "__main__":
    main()
