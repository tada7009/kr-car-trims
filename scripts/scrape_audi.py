"""아우디코리아 모델 페이지의 공식 디지털 카탈로그 PDF → data/audi/*.json

카탈로그 뒤쪽 'Detail Information' 표가 국내 판매 트림별 가격·사양표다.
표는 [구분 | 항목 | 트림1 | 트림2 …]이고 칸 값은 ●(기본) / -(없음) / 글자(기본, 사양 값)다.
머리글(트림 이름)과 가로선을 좌표로 찾아 칸을 나눈다.
"""
import re
from urllib.parse import quote

import fitz  # PyMuPDF

from common import DATA, curl_get, save

LIST = "https://www.audi.co.kr/ko/models/?bycarlinegroup=a6"
SEG = {"a3": "세단", "a5": "세단", "a6": "세단", "a8": "세단", "q3": "SUV", "q4": "전기 SUV", "q5": "SUV", "q7": "SUV",
       "q8": "SUV", "e-tron-gt": "전기 4도어 쿠페", "a-6-e-tron": "전기 세단"}


def catalog_url(page):
    html = curl_get("https://www.audi.co.kr" + page)
    m = re.search(r'(https://cdn\.audikoreaevent\.co\.kr/lms/aca/ecatalog/download/[^"&]+?\.pdf)', html)
    if not m:
        return None, html
    u = m.group(1)
    return "https://" + quote(u[8:], safe="/:()%"), html


def hlines(page):
    ys = []
    w = page.rect.width
    for dr in page.get_drawings():
        for it in dr["items"]:
            if it[0] == "l" and abs(it[1].y - it[2].y) < .6 and abs(it[2].x - it[1].x) > w * .45:
                ys.append(it[1].y)
            elif it[0] == "re" and it[1].height < 2 and it[1].width > w * .45:
                ys.append(it[1].y0)
    ys.sort()
    out = []
    for y in ys:
        if not out or y - out[-1] > 2:
            out.append(y)
    return out


def table(page):
    """한 쪽의 표 → (트림 이름 목록, [(구분, 항목, [칸 값…])])"""
    words = page.get_text("words")
    model = next((w for w in words if w[4] == "Model"), None)
    if not model:
        return None
    head = [w for w in words if model[1] - 25 < w[1] < model[3] + 25 and w[0] > model[2] + 80 and w[4] not in ("●", "-", "○")]
    if not head:
        return None
    top = max(w[3] for w in head) + 2
    head.sort(key=lambda w: w[0])
    cols = []
    for w in head:  # 머리글 글자를 x 간격으로 묶어 열을 만든다
        if cols and w[0] - cols[-1]["x1"] < 18:
            cols[-1]["w"].append(w)
            cols[-1]["x1"] = max(cols[-1]["x1"], w[2])
        else:
            cols.append({"x0": w[0], "x1": w[2], "w": [w]})
    for c in cols:
        c["cx"] = (c["x0"] + c["x1"]) / 2
        c["name"] = " ".join(x[4] for x in sorted(c["w"], key=lambda x: (round(x[1]), x[0])))
        c["name"] = re.sub(r"\bqu\.", "quattro", re.sub(r"\s+", " ", c["name"])).strip()
        # Q5·A6 e-tron처럼 가격이 머리글(트림 이름 아래)에 붙어 있는 표도 있다
        m = re.search(r"([\d,]{9,})\s*원", c["name"])
        c["price"] = int(m.group(1).replace(",", "")) if m else None
        c["name"] = re.sub(r"\s*[\d,]{9,}\s*원.*$", "", c["name"]).strip()
    if len(cols) < 1:
        return None
    left = min(c["x0"] for c in cols) - 12
    rows, cat = [], ""
    # 행 경계: 표에 가로선이 그림으로 들어 있어 쓸 수 없으므로, 항목 칸 글자의 줄 위치로 행을 나눈다
    # 표 아래 각주(※, *, ¹로 시작)부터는 표가 아니다
    foot = min([w[1] for w in words if w[1] > top and re.match(r"^(※|\*|¹|²)", w[4]) and w[0] < left] or [1e9])
    body = [w for w in words if top < w[1] < foot - 1]
    item_ys = sorted({round((w[1] + w[3]) / 2) for w in body if model[0] + 45 <= w[0] and w[2] < left})
    anchors = []
    for y in item_ys:
        if anchors and y - anchors[-1][-1] < 14:
            anchors[-1].append(y)
        else:
            anchors.append([y])
    mids = [sum(a) / len(a) for a in anchors]
    bounds = [top] + [(a + b) / 2 for a, b in zip(mids, mids[1:])] + [(mids[-1] + 20) if mids else top]
    # 구분(Exterior 등)은 여러 행을 합친 칸의 세로 가운데에 있으므로, 행마다 가장 가까운 구분 이름을 쓴다
    groups = []  # 여러 줄로 쓴 구분 이름(Infotain-/ment)은 한 덩어리로 묶는다
    for w in sorted([w for w in body if w[2] < model[0] + 45], key=lambda w: (w[1], w[0])):
        if groups and w[1] - groups[-1][-1][3] < 14:
            groups[-1].append(w)
        else:
            groups.append([w])
    labels = [(sum((w[1] + w[3]) / 2 for w in g) / len(g),
               re.sub(r"-\s+", "", " ".join(w[4] for w in g)).replace("¹", "").strip()) for g in groups]
    for i in range(1, len(labels)):  # 'Comfort' / '& Safety'처럼 멀리 떨어진 두 줄짜리 이름
        if labels[i][1].startswith("&"):
            full = f"{labels[i - 1][1]} {labels[i][1]}"
            labels[i - 1], labels[i] = (labels[i - 1][0], full), (labels[i][0], full)
    for y0, y1 in zip(bounds, bounds[1:]):
        ws = [w for w in words if y0 < (w[1] + w[3]) / 2 < y1]
        if not ws:
            continue
        if labels:
            cat = min(labels, key=lambda l: abs(l[0] - (y0 + y1) / 2))[1]
        item = " ".join(w[4] for w in sorted([w for w in ws if model[0] + 45 <= w[0] and w[2] < left], key=lambda w: (round(w[1]), w[0])))
        if not item:
            continue
        cells = []
        for c in cols:
            cw = [w for w in ws if w[0] >= left and min(cols, key=lambda k: abs(k["cx"] - (w[0] + w[2]) / 2)) is c]
            cells.append(" ".join(w[4] for w in sorted(cw, key=lambda w: (round(w[1]), w[0]))))
        rows.append((cat, item.strip(), cells))
    return [c["name"] for c in cols], rows, [c["price"] for c in cols]


def parse(pdf):
    doc = fitz.open(stream=pdf, filetype="pdf")
    trims, order = {}, []
    for page in doc:
        text = page.get_text()
        if "Detail" not in text or "Model" not in text or "●" not in text:  # 제원(Tech data) 쪽은 건너뛴다
            continue
        t = table(page)
        if not t:
            continue
        names, rows, prices = t
        for i, n in enumerate(names):
            if n not in trims:
                trims[n] = {"name": n, "price": None, "cats": {}}
                order.append(n)
            tr = trims[n]
            if prices[i] and not tr["price"]:
                tr["price"] = prices[i]
            for cat, item, cells in rows:
                v = cells[i].strip() if i < len(cells) else ""
                if "가격" in item and re.search(r"\d{2},\d{3},\d{3}", v):
                    tr["price"] = int(re.sub(r"\D", "", re.search(r"[\d,]{9,}", v).group(0)))
                    continue
                if not v or v in ("-", "–", "—", "x", "X"):
                    continue
                cat = cat or "사양"
                name = item if v in ("●", "■", "S", "s") else f"{item}: {v}" if v not in ("○",) else None
                if name is None:
                    continue
                tr["cats"].setdefault(cat, [])
                if not any(x["n"] == name for x in tr["cats"][cat]):
                    tr["cats"][cat].append({"n": name})
    out = []
    for n in order:
        t = trims[n]
        out.append({"name": n, "price": t["price"], "cats": [{"cat": c, "items": its} for c, its in t["cats"].items()],
                    "adds": [], "opts": []})
    return out


def main():
    html = curl_get(LIST)
    pages = sorted(set(re.findall(r'/ko/models/[a-z0-9-]+/[a-z0-9-]+/', html)))
    out = DATA / "audi"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.json"):
        old.unlink()
    seen = set()
    for page in pages:
        fam, slug = page.split("/")[3:5]
        url, mhtml = catalog_url(page)
        if not url:
            print(page, "카탈로그 없음")
            continue
        if url in seen:  # A5·S5, Q5 SUV·스포트백처럼 한 카탈로그를 여러 페이지가 같이 쓴다
            continue
        seen.add(url)
        try:
            trims = [t for t in parse(curl_get(url, binary=True)) if t["price"]]
        except Exception as e:
            print(page, "error", e)
            continue
        if not trims:
            print(page, "가격표 없음")
            continue
        # 모델 이름은 카탈로그 단위(차종 가족)로: A5(S5 포함), Q5(SUV·스포트백), A8(S8 포함)
        name = {"a-6-e-tron": "A6 e-tron", "e-tron-gt": "e-tron GT"}.get(fam) or (
            "RS 3" if slug.startswith("rs-3") else "RS Q8" if slug.startswith("rs-q8") else fam.upper())
        groups = {}
        for t in sorted(trims, key=lambda t: t["price"]):
            vname = "스포트백" if re.search(r"\bSB\b|Sportback", t["name"]) else "S 모델" if re.match(r"S\d|S e-tron", t["name"]) else "기본"
            groups.setdefault(vname, []).append(t)
        variants = [{"name": k, "code": slug, "trims": v} for k, v in groups.items()]
        d = {"id": "audi-" + re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-"), "brand": "audi", "name": name,
             "segment": SEG.get(fam, "세단"), "image": "", "lowPrice": min(t["price"] for t in trims), "priceDate": None,
             "sources": ["https://www.audi.co.kr" + page, url], "structure": "catalog", "variants": variants,
             "notes": ["아우디코리아 공식 디지털 카탈로그의 가격·사양표(권장소비자가격) 기준입니다."]}
        save(out / f"{d['id'][5:]}.json", d)
        print(d["id"], name, [(t["name"], t["price"], sum(len(c["items"]) for c in t["cats"])) for t in d["variants"][0]["trims"]])


if __name__ == "__main__":
    main()
