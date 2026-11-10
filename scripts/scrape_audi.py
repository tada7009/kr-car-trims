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
       "q8": "SUV", "e-tron-gt": "전기 4도어 쿠페", "a-6-e-tron": "전기 세단", "q4-e-tron": "전기 SUV"}


# 카탈로그 표의 영문 구분 → 화면 표기(줄바꿈·각주로 깨진 'Infotain- ment', 'Assistant System¹'도 같은 키가 된다)
CAT = {"exterior": "외관", "interior": "내장", "comfort": "편의", "technology&safety": "안전·기술",
       "assistantsystem": "주행 보조", "infotainment": "인포테인먼트", "infootainment": "인포테인먼트",
       "driving": "파워트레인"}


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


def table_cols(page):
    """칸마다 밑줄이 따로 그어진 표(e-tron GT 카탈로그 등): 밑줄 선분의 x 범위로 칸을, y로 행을 나눈다.
    [구분 | 항목 | 트림1 | 트림2 …] 모양이 아니면 None을 돌려줘 table()로 넘긴다."""
    from collections import Counter
    segs = []
    for dr in page.get_drawings():
        for it in dr["items"]:
            if it[0] == "l" and abs(it[1].y - it[2].y) < .6:
                segs.append((min(it[1].x, it[2].x), max(it[1].x, it[2].x), it[1].y))
            elif it[0] == "re" and it[1].height < 2:
                segs.append((it[1].x0, it[1].x1, it[1].y0))
    words = page.get_text("words")
    head = [w for w in words if w[4] == "Model"]
    if not head or not segs:
        return None
    hy, hx = head[0][1], head[0][0]
    above = [s[2] for s in segs if s[2] < hy - 1]
    top = max(above) if above else hy - 40
    under = [s[2] for s in segs if s[2] > head[0][3]]
    if not under:
        return None
    hb = min(under)  # 머리글(트림 이름, 여러 줄일 수 있음) 아래 첫 선
    below = [s for s in segs if s[2] > hb - 1]
    rng = Counter((round(s[0]), round(s[1])) for s in below if s[1] - s[0] > 40)
    cols, parts = [], {}
    for w in words:
        cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
        if not (top < cy < hb) or w[4] == "Model" or w[0] < hx + 20:
            continue
        cand = [(n, r) for r, n in rng.items() if r[0] < cx < r[1]]
        if not cand:
            continue
        r = max(cand)[1]
        parts.setdefault(r, []).append(w)
    cols = sorted(parts)
    if not cols or any(a[1] > b[0] + 6 for a, b in zip(cols, cols[1:])):
        return None
    def join(ws):  # 위에서 아래 줄 순서로(한글·영문 글꼴 높이가 달라 y가 1~2pt 어긋나도 같은 줄로 본다)
        lines = []
        for w in sorted(ws, key=lambda w: w[1]):
            if lines and abs(w[1] - lines[-1][0][1]) < 3:
                lines[-1].append(w)
            else:
                lines.append([w])
        return " ".join(x[4] for ln in lines for x in sorted(ln, key=lambda w: w[0]))

    names = [join(parts[c]) for c in cols]
    left = cols[0][0]
    item_segs = [s for s in below if left - 15 <= s[1] <= left + 2 and s[1] - s[0] > 60]
    if len(item_segs) < 3:
        return None
    item_left = Counter(round(s[0]) for s in item_segs).most_common(1)[0][0]
    ys = []
    for y in sorted(s[2] for s in item_segs):
        if not ys or y - ys[-1] > 2:
            ys.append(y)
    cat_ys = []
    for y in sorted(s[2] for s in below if s[1] <= item_left + 6 and s[0] < item_left - 20):
        if not cat_ys or y - cat_ys[-1] > 2:
            cat_ys.append(y)
    cat_ys = [hb] + cat_ys

    def inside(w, x0, x1, y0, y1):
        cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
        return x0 <= cx < x1 and y0 < cy < y1


    cats = []
    for a, b in zip(cat_ys, cat_ys[1:]):
        cats.append((a, b, join([w for w in words if inside(w, 0, item_left - 3, a, b) and w[0] > hx - 30])))
    rows = []
    for a, b in zip([hb] + ys, ys):
        item = join([w for w in words if inside(w, item_left - 3, left, a, b)])
        cells = [join([w for w in words if inside(w, x0, x1, a, b)]) for x0, x1 in cols]
        if not item and not any(cells):
            continue
        mid = (a + b) / 2
        cat = next((c for a2, b2, c in cats if a2 <= mid < b2), "")
        rows.append((cat, item, cells))
    if len(rows) < 3:
        return None
    return names, rows, [None] * len(names)


def parse(pdf):
    doc = fitz.open(stream=pdf, filetype="pdf")
    trims, order = {}, []
    for page in doc:
        text = page.get_text()
        if "Detail" not in text or "Model" not in text or "●" not in text:  # 제원(Tech data) 쪽은 건너뛴다
            continue
        t = table_cols(page) or table(page)
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
                cat = CAT.get(re.sub(r"[^a-z&]", "", (cat or "").lower()), cat or "사양")
                v = re.sub(r"^[ㄱ-ㅎ]+(?=●)", "", v)  # 원문 오타 'ㅍ●' 같은 것
                if len(v) > 1 and v[0] == "●":  # '●(폴딩, 열선 …)' → '항목 (폴딩, 열선 …)'
                    v, item = "●", f"{item} {v[1:].strip()}"
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
    pages = sorted(set(re.findall(r'/ko/models/[a-z0-9-]+/[a-z0-9_-]+/', html)))  # q3_2026처럼 밑줄 있는 주소도
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
            for t in trims:
                t["name"] = re.sub(r"^Audi\s+", "", t["name"])  # 'Audi Q4 45 e-tron' → 'Q4 45 e-tron'

        except Exception as e:
            print(page, "error", e)
            continue
        if not trims:
            print(page, "가격표 없음")
            continue
        # 모델 이름은 카탈로그 단위(차종 가족)로: A5(S5 포함), Q5(SUV·스포트백), A8(S8 포함)
        name = {"a-6-e-tron": "A6 e-tron", "e-tron-gt": "e-tron GT", "q4-e-tron": "Q4 e-tron"}.get(fam) or (
            "RS 3" if slug.startswith("rs-3") else "RS Q8" if slug.startswith("rs-q8") else fam.upper())
        groups = {}
        for t in sorted(trims, key=lambda t: t["price"]):
            vname = "전기" if fam == "e-tron-gt" else "스포트백" if re.search(r"\bSB\b|Sportback", t["name"]) else "S 모델" if re.match(r"S\d|S e-tron", t["name"]) else "기본"
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
