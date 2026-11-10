"""메르세데스-벤츠 코리아 일반 소비자 판매 가격표 PDF → data/mercedes/*.json

가격표 페이지(/passengercars/models/price-list.html)에 걸린 PDF 한 장짜리 긴 표를 좌표로 읽는다.
표는 [차종(연식) | 트림 | 가격]이고, 차종 칸은 가로 전체 선(x 50~950)으로 나뉜다.
같은 차종이 연식별로 따로 실려 있어 연식을 변형(variant)으로 둔다.
"""
import re

import fitz  # PyMuPDF

from common import DATA, curl_get, save

PAGE = "https://www.mercedes-benz.co.kr/passengercars/models/price-list.html"
BODIES = {"Hatchback": "해치백", "Sedan": "세단", "SUV": "SUV", "Coupé": "쿠페", "Coupe": "쿠페",
          "Cabriolet": "카브리올레", "Roadster": "로드스터", "Cabriolet & Roadster": "카브리올레", "Van": "밴", "MPV": "MPV"}
BRANDS = ("Mercedes-Benz", "Mercedes-AMG", "Mercedes-Maybach")
PRICE = re.compile(r"^\d{1,3}(,\d{3}){1,2}$")


def pdf_url():
    html = curl_get(PAGE, cache=False)
    m = re.search(r'(/content/dam/[^"\']+?Price-List[^"\']*?\.pdf)', html, re.I)
    if not m:
        raise RuntimeError("가격표 PDF 링크를 찾지 못했습니다")
    return "https://www.mercedes-benz.co.kr" + m.group(1)


def lines(page):
    out = {}
    for x0, y0, x1, y1, w, b, l, n in page.get_text("words"):
        out.setdefault((b, l), []).append((x0, y0, x1, y1, w))
    res = []
    for ws in out.values():
        ws.sort()
        res.append({"x0": ws[0][0], "x1": ws[-1][2], "y": (ws[0][1] + ws[0][3]) / 2,
                    "t": " ".join(w[4] for w in ws).strip()})
    return sorted(res, key=lambda r: (r["y"], r["x0"]))


def separators(page):
    ys = []
    for dr in page.get_drawings():
        for it in dr["items"]:
            if it[0] == "l" and abs(it[1].y - it[2].y) < .5 and min(it[1].x, it[2].x) < 60 and max(it[1].x, it[2].x) > 900:
                ys.append(it[1].y)
            elif it[0] == "re" and it[1].height < 3 and it[1].x0 < 60 and it[1].x1 > 900:
                ys.append(it[1].y0)
    ys.sort()
    merged = []
    for y in ys:
        if not merged or y - merged[-1] > 3:
            merged.append(y)
    return merged


def parse(pdf):
    doc = fitz.open(stream=pdf, filetype="pdf")
    page = doc[0]
    date = re.search(r"(\d{4})\.(\d{2})\.(\d{2})", page.get_text())
    date = f"{date.group(1)}-{date.group(2)}-{date.group(3)}" if date else None
    ls = lines(page)
    seps = separators(page) + [page.rect.height]
    brand, body, out = "Mercedes-Benz", None, []
    y_prev = 0
    for y_sep in seps:
        block = [r for r in ls if y_prev <= r["y"] < y_sep]
        y_prev = y_sep
        left = [r for r in block if r["x0"] < 195]
        right = [r for r in block if r["x0"] >= 195]
        for r in left:
            if r["t"] in BRANDS:
                brand = r["t"]
        heads = [r["t"] for r in left if r["t"] not in BRANDS]
        trims = [r for r in right if not PRICE.match(r["t"].replace(" ", "")) and r["x0"] < 600]
        prices = [r for r in right if PRICE.match(r["t"].replace(" ", ""))]
        if not trims:
            for h in heads:
                if h in BODIES:
                    body = BODIES[h]
            continue
        label = " ".join(h for h in heads if not h.startswith("("))
        year = next((re.sub(r"[()\s]", "", h) for h in heads if "년식" in h), "")
        for t in trims:
            p = min(prices, key=lambda r: abs(r["y"] - t["y"]), default=None)
            if not p or abs(p["y"] - t["y"]) > 8:
                continue
            out.append({"brand": brand, "body": body, "cls": re.sub(r"\s+", " ", label).strip(), "year": year,
                        "trim": re.sub(r"\s+", " ", re.sub(r"^[\x00-\x1f]\s*", "Mercedes-Maybach ", t["t"])).strip(), "price": int(re.sub(r"\D", "", p["t"]))})
    return date, out


def model_name(e):
    """차종 칸 이름 + 트림 이름 → 모델 이름. AMG·마이바흐는 트림 이름 앞머리로 가린다."""
    cls, trim = e["cls"].replace("Coupe", "Coupé"), e["trim"]
    if cls == "CLE" or (cls.startswith("CLE") and "Coup" not in cls and "Cabrio" not in cls):
        cls = "CLE Cabriolet" if "Cabriolet" in trim else "CLE Coupé"
    if trim.startswith("Mercedes-AMG") and not cls.startswith("AMG"):
        cls = "AMG " + cls
    if trim.startswith("Mercedes-Maybach") and not cls.startswith("Maybach"):
        cls = "Maybach " + cls
    return cls


def body_of(name):
    n = re.sub(r"^(AMG|Maybach) ", "", name)
    if re.search(r"Cabriolet", n):
        return "카브리올레"
    if n.startswith("SL"):
        return "로드스터"
    if re.match(r"(GLC|GLE) Coup", n):
        return "쿠페형 SUV"
    if re.match(r"(GL[A-Z]|G-Class|EQA|EQB|EQ[ES] SUV)", n):
        return "SUV"
    if re.search(r"Coup|GT", n):
        return "4도어 쿠페" if "4-Door" in n or "4도어" in n else "쿠페"
    if n.startswith("A-Class"):
        return "해치백"
    return "세단"


def features(trim):
    cats, line, drive = [], [], []
    if "4MATIC" in trim:
        drive.append({"n": "사륜구동 4MATIC"})
    for w, n in (("AMG Line", "AMG Line"), ("AVANTGARDE", "AVANTGARDE"), ("EXCLUSIVE", "EXCLUSIVE"),
                 ("Special Edition", "Special Edition"), ("Long", "롱 휠베이스"), ("Night", "나이트 에디션")):
        if w in trim:
            line.append({"n": n})
    m = re.search(r"\b(\d{2,3})\s?(d|e)?\b", trim)
    fuel = "디젤" if re.search(r"\b\d{3} d\b", trim) else "플러그인 하이브리드" if re.search(r"\b\d{3} e\b", trim) else None
    if re.match(r"(EQ|CLA 250\+|.*electric)", trim, re.I) or trim.startswith("EQ"):
        fuel = "전기"
    if fuel:
        cats.append({"cat": "파워트레인", "items": [{"n": fuel}]})
    if drive:
        cats.append({"cat": "구동", "items": drive})
    if line:
        cats.append({"cat": "라인·패키지", "items": line})
    return cats


def main():
    url = pdf_url()
    date, items = parse(curl_get(url, binary=True))
    models = {}
    for e in items:
        models.setdefault(model_name(e), []).append(e)
    out = DATA / "mercedes"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.json"):
        old.unlink()
    for name, es in models.items():
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower().replace("é", "e")).strip("-")
        variants = {}
        for e in sorted(es, key=lambda e: e["year"], reverse=True):  # 최신 연식 먼저
            v = variants.setdefault(e["year"] or "기본", {"name": e["year"] or "기본", "code": slug, "trims": []})
            v["trims"].append({"name": re.sub(r"^Mercedes-(AMG|Maybach) ", r"\1 ", e["trim"]), "price": e["price"], "cats": features(e["trim"]), "adds": [], "opts": []})
        seg = body_of(name)
        if re.sub(r"^(AMG|Maybach) ", "", name).startswith("EQ") or "EQ Technology" in name:
            seg = f"전기 {seg}"
        d = {"id": f"mercedes-{slug}", "brand": "mercedes", "name": name, "segment": seg, "image": "",
             "lowPrice": min(e["price"] for e in es), "priceDate": date, "sources": [url], "structure": "price-list",
             "variants": list(variants.values()),
             "notes": ["메르세데스-벤츠 코리아 일반 소비자 판매 가격표(권장소비자가격) 기준입니다. 연식별 가격이 따로 공시되어 연식을 나눠 보여 줍니다."]}
        save(out / f"{slug}.json", d)
        print(d["id"], seg, sum(len(v["trims"]) for v in variants.values()), [v["name"] for v in variants.values()])


if __name__ == "__main__":
    main()
