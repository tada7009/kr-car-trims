"""BMW 코리아 월별 가격표 PDF → data/bmw/*.json

BMW 코리아 홈페이지에 걸린 'BMW 가격표' PDF(시리즈별 표: 연료 | 트림 | 시작 가격)를 좌표로 읽는다.
국내 공식 자료로 공개된 것은 트림과 가격뿐이라(구성기는 유럽 사양 기준이라는 안내가 붙어 있다),
사양은 트림 이름에서 확실히 알 수 있는 것(연료, xDrive, M 스포츠 패키지 등)만 적는다.
"""
import io
import re

import fitz  # PyMuPDF

from common import DATA, curl_get, save

HOME = "https://www.bmw.co.kr/ko/index.html"
FUELS = ("가솔린", "디젤", "플러그인 하이브리드", "순수 전기", "마일드 하이브리드", "하이브리드")
PRICE = re.compile(r"^\d{1,3}(,\d{3}){2}$")
BODY = {"세단": "sedan", "투어링": "touring", "쿠페": "coupe", "그란 쿠페": "gran-coupe", "액티브 투어러": "active-tourer",
        "컨버터블": "convertible", "로드스터": "roadster", "해치백": "hatch", "SUV": "suv"}
SEGMENT = {"세단": "세단", "투어링": "왜건", "쿠페": "쿠페", "그란 쿠페": "4도어 쿠페", "액티브 투어러": "MPV",
           "컨버터블": "컨버터블", "로드스터": "로드스터", "해치백": "해치백", "SUV": "SUV"}


def pdf_url():
    html = curl_get(HOME, cache=False)
    m = re.search(r'(/content/dam/bmw/marketKR/bmw_co_kr/Pricelist/pricelist_[^"\']+?\.pdf)', html)
    if not m:
        raise RuntimeError("가격표 PDF 링크를 찾지 못했습니다")
    return "https://www.bmw.co.kr" + m.group(1)


def rows(page):
    """같은 줄(y)·같은 단(왼쪽/오른쪽)의 단어 묶음을 (y, 단, [(x0, 글자)])로 돌려준다."""
    lines = {}
    for x0, y0, x1, y1, w, b, l, n in page.get_text("words"):
        lines.setdefault((b, l), []).append((x0, y0, x1, w))
    out = []
    for ws in lines.values():
        ws.sort()
        out.append((round(ws[0][1], 1), ws[0][0], ws[-1][2], " ".join(w[3] for w in ws)))
    return sorted(out, key=lambda r: (r[0], r[1]))


def parse(pdf):
    doc = fitz.open(stream=pdf, filetype="pdf")
    page = doc[0]
    text = page.get_text()
    when = re.search(r"(\d{4})년\s*(\d{1,2})월\s*기준", text)
    date = f"{when.group(1)}-{int(when.group(2)):02d}-01" if when else None
    mid = page.rect.width / 2
    section, sub, fuel = None, {0: None, 1: None}, {0: None, 1: None}
    pend = {}  # (단, y) → {'trim': .., 'price': ..}
    items = []
    for y, x0, x1, t in rows(page):
        col = 0 if x0 < mid - 2 else 1
        if t.startswith("BMW ") and x0 < 60 and "가격표" not in t:
            section = t[4:].strip()
            sub = {0: None, 1: None}
            fuel = {0: None, 1: None}
            continue
        if t.startswith("시작 가격") or t.startswith("*") or "기준" in t:
            continue
        rel = x0 - (0 if col == 0 else mid)
        key = (col, round(y))
        if PRICE.match(t):
            pend.setdefault(key, {})["price"] = int(t.replace(",", ""))
        elif rel < 70 and t in FUELS:
            fuel[col] = t
        elif rel < 70:
            sub[col] = t  # 차체(세단·쿠페…) 또는 X 레인지의 모델 이름
            fuel[col] = None
        else:
            # 오른쪽 단은 차체 제목 없이 왼쪽 단(세단)에 이어서 PHEV만 싣기도 한다
            pend.setdefault(key, {}).update(trim=t, section=section, sub=sub[col] or sub[1 - col], fuel=fuel[col])
        e = pend.get(key)
        if e and "trim" in e and "price" in e:
            items.append(pend.pop(key))
    return date, items


def model_of(e):
    """가격표의 시리즈·차체·트림 이름 → (모델 이름, 차체)"""
    sec, sub, trim = e["section"], (e["sub"] or "").strip(), e["trim"]
    sub = re.sub(r"^뉴\s*", "", sub)
    if sec == "i 모델":
        return trim.split()[0], ("SUV" if sub == "SUV" else sub)
    if sec == "M 모델":
        m = re.match(r"(X\d M|XM|M\d)", trim)
        name = m.group(1) if m else trim.split()[0]
        return name, sub
    if sec == "X 레인지":
        return sub, "SUV"
    if sec.endswith("모델"):  # Z4 모델
        return sec.replace(" 모델", ""), sub
    # 1·2·3·4·5·7·8시리즈: 차체가 하나뿐이면 시리즈 이름만
    return f"{sec} {sub}".strip(), sub


def features(trim, fuel):
    cats = [{"cat": "파워트레인", "items": [{"n": fuel}]}]
    drive = []
    if "xDrive" in trim:
        drive.append({"n": "사륜구동 xDrive"})
    if drive:
        cats.append({"cat": "구동", "items": drive})
    pk = []
    if re.search(r"M 스포츠 프로|M 스포츠 패키지 프로|\b프로\b", trim):
        pk.append({"n": "M 스포츠 패키지 프로"})
    elif "M 스포츠" in trim:
        pk.append({"n": "M 스포츠 패키지"})
    for w, n in (("xLine", "xLine"), ("럭셔리", "럭셔리 라인"), ("디자인 퓨어 엑설런스", "디자인 퓨어 엑설런스"),
                 ("컴페티션", "M 컴페티션"), ("7인승", "7인승"), ("6인승", "6인승")):
        if w in trim:
            pk.append({"n": n})
    if pk:
        cats.append({"cat": "라인·패키지", "items": pk})
    return cats


def main():
    url = pdf_url()
    date, items = parse(curl_get(url, binary=True))
    seen, models = set(), {}
    for e in items:
        if e["trim"] in seen:  # M 모델 표는 X5 M·XM 등을 다시 싣는다
            continue
        seen.add(e["trim"])
        name, body = model_of(e)
        m = models.setdefault(name, {"bodies": [], "trims": []})
        if body and body not in m["bodies"]:
            m["bodies"].append(body)
        m["trims"].append(e)
    out = DATA / "bmw"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.json"):
        old.unlink()
    for name, m in models.items():
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower().replace("시리즈", "-series")
                      .replace("세단", "sedan").replace("투어링", "touring").replace("그란 쿠페", "gran-coupe")
                      .replace("쿠페", "coupe").replace("액티브 투어러", "active-tourer").replace("컨버터블", "convertible")
                      .replace("로드스터", "roadster").replace("해치백", "hatch")).strip("-")
        multi_body = len(m["bodies"]) > 1
        variants = {}
        for e in m["trims"]:
            vname = (f"{e['sub']} " if multi_body and e["sub"] else "") + (e["fuel"] or "")
            v = variants.setdefault(vname.strip() or "기본", {"name": vname.strip() or "기본", "code": slug, "trims": []})
            v["trims"].append({"name": e["trim"], "price": e["price"], "cats": features(e["trim"], e["fuel"] or ""),
                               "adds": [], "opts": []})
        body = m["bodies"][0] if m["bodies"] else ""
        seg = SEGMENT.get(body, body)
        if any("전기" in (e["fuel"] or "") for e in m["trims"]) and all("전기" in (e["fuel"] or "") for e in m["trims"]):
            seg = f"전기 {seg}"
        d = {"id": f"bmw-{slug}", "brand": "bmw", "name": name if name.startswith(("i", "X", "M", "Z")) else name,
             "segment": seg, "image": "", "lowPrice": min(e["price"] for e in m["trims"]), "priceDate": date,
             "sources": [url], "structure": "price-list", "variants": list(variants.values()),
             "notes": ["BMW 코리아 공식 가격표 기준 시작 가격입니다. 국내 판매 사양의 상세 품목은 공식 딜러에 확인해 주세요."]}
        save(out / f"{slug}.json", d)
        print(d["id"], d["segment"], len(m["trims"]), "트림", d["lowPrice"])


if __name__ == "__main__":
    main()
