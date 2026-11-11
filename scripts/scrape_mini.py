"""MINI 코리아 공식 자료 → data/mini/*.json (+ img/mini-*.webp)

- 가격·트림: 'MINI 가격 정보 확인' 페이지(/ko_KR/home/Product-Information-KR.html)의 '전체 가격 정보' PDF
  (쪽마다 'NNNN년식 MINI 모델 가격표 (YYYY.MM.DD 기준)', 권장 소비자 가격 부가세 포함·개별소비세 5.0% 기준)
- 사양: 같은 페이지의 차종별 '가격/옵션 정보'(옵션 리스트: ● / - / 문구 표)와 '제원 정보' PDF.
  옵션 리스트 열은 가격이 같은 가격표 트림에 붙이고, 제원 열(C·S·E·SE·JCW)은 트림 이름 앞머리로 고른다.
- 사진: 홈페이지 모델 둘러보기 띠의 구성기 렌더(배경 투명 옆모습) + 모델 페이지의 공식 외관·실내 사진.
  사진을 못 받으면 기존 JSON의 사진 정보를 그대로 둔다.
"""
import html as H
import json
import re
import sys

import fitz  # PyMuPDF

import fetch_import_media as fim
from common import DATA, curl_get, save

BASE = "https://www.mini.co.kr"
INFO = BASE + "/ko_KR/home/Product-Information-KR.html"
HOME = BASE + "/ko_KR/home.html"
DAM = BASE + "/content/dam/MINI/common/Range/new-generation/"
PRICE = re.compile(r"^\d{1,3}(,\d{3}){2}$")

# 파일 이름, 가격표 구역, 공식 이름(모델 페이지 제목), 차급, 연료, 옵션·제원 PDF 이름, 홈페이지 렌더 alt, 모델 페이지, 외관·실내 사진
MODELS = [
    dict(slug="cooper-3-door", sec="MINI COOPER 3-DOOR", name="Cooper 3-Door", seg="해치백", fuel="가솔린",
         pdf="MINI-COOPER", alt="mini cooper 3-door", page="mini-cooper-3-door",
         ext=["cooper/3-door/bodytype-hub/mini-F66-ICE-stage-wide.webp", "cooper/3-door/bodytype-hub/mini-F66-ICE-gallery-overview-wide.webp"],
         int=["cooper/3-door/bodytype-hub/mini-F66-ICE-gallery-interior-wide.webp"]),
    dict(slug="cooper-5-door", sec="MINI COOPER 5-DOOR", name="Cooper 5-Door", seg="해치백", fuel="가솔린",
         pdf="MINI-COOPER-5-DOOR", alt="mini cooper 5-door", page="mini-cooper-5-door",
         ext=["cooper/5-door/bodytype-hub/mini-F65-stage-wide.webp", "cooper/5-door/bodytype-hub/mini-F65-exterior.jpg"],
         int=["cooper/5-door/bodytype-hub/mini-F65-interior.jpg"]),
    dict(slug="cooper-convertible", sec="MINI COOPER CONVERTIBLE", name="Cooper Convertible", seg="컨버터블", fuel="가솔린",
         pdf="MINI-COOPER-CONVERTIBLE", alt="mini-cooper-convertible", page="mini-cooper-convertible",
         ext=["cooper/convertible/bodytype-hub/mini-F67-stage-wide.webp", "cooper/convertible/bodytype-hub/mini-F67-overview.webp"],
         int=["cooper/convertible/bodytype-hub/mini-F67-interior.webp"]),
    dict(slug="countryman", sec="MINI COUNTRYMAN", name="Countryman", seg="SUV", fuel="가솔린",
         pdf="MINI-COUNTRYMAN", alt="mini product strip - u25 - ice", page="mini-countryman",
         ext=["countryman/ice/bodytype-hub/mini-U25-stage-wide.webp", "countryman/ice/bodytype-hub/mini-U25-dynamic-exterior.jpg"],
         int=["countryman/ice/bodytype-hub/mini-U25-interior-view.jpg"]),
    dict(slug="all-electric-cooper", sec="ALL-ELECTRIC MINI COOPER", name="All-Electric Cooper", seg="전기 해치백", fuel="전기",
         pdf="ALL-ELECTRIC-MINI-COOPER", alt="mini product strip - j01", page="all-electric-mini-cooper",
         ext=["cooper/all-electric/bodytype-hub/mini-J01-BEV-stage-wide.webp", "cooper/all-electric/bodytype-hub/mini-J01-BEV-gallery-overview-wide.webp"],
         int=["cooper/all-electric/bodytype-hub/mini-J01-BEV-gallery-interior-wide.webp"]),
    dict(slug="aceman", sec="ALL-ELECTRIC MINI ACEMAN", name="Aceman", seg="전기 SUV", fuel="전기",
         pdf="ALL-ELECTRIC-MINI-ACEMAN", alt="mini product strip - j05", page="all-electric-mini-aceman",
         ext=["aceman/bodytype-hub/mini-J05-BEV-stage-wide.webp", "aceman/bodytype-hub/mini-J05-BEV-gallery-overview-wide.webp"],
         int=["aceman/bodytype-hub/mini-J05-BEV-gallery-interior-wide.webp"]),
    dict(slug="all-electric-countryman", sec="ALL-ELECTRIC MINI COUNTRYMAN", name="All-Electric Countryman", seg="전기 SUV",
         fuel="전기", pdf="ALL-ELECTRIC-MINI-COUNTRYMAN", alt="mini product strip - u25 - bev", page="all-electric-mini-countryman",
         ext=["countryman/bev/bodytype-hub/mini-U25-BEV-stage-wide.webp", "countryman/bev/bodytype-hub/mini-U25-BEV-gallery-front-wide.webp"],
         int=["countryman/bev/bodytype-hub/hot-spots/mini-U25-BEV-interior.webp"]),
]
OPT_CAT = {"Powertrain & Technology": "파워트레인", "Wheels & Tires": "휠·타이어", "Exterior": "외관",
           "Interior & Luggage Compartment": "내장", "Driving Technology & Safety": "안전·주행 보조",
           "Parking Assistance Features": "주차 보조", "Lights & Sights": "라이트",
           "Infotainment & Connectivity": "인포테인먼트", "Charging": "충전"}
SPEC_CAT = {"Powertrain": "파워트레인", "Performance": "성능", "Fuel Consumption": "연비",
            "Fuel Consumption & Max e-range": "전비·주행 거리", "Weight": "차체 제원", "Dimensions": "차체 제원",
            "Wheel/Tire": "휠·타이어"}
ORDER = ["파워트레인", "성능", "연비", "전비·주행 거리", "충전", "휠·타이어", "외관", "내장", "안전·주행 보조", "주차 보조",
         "라이트", "인포테인먼트", "차체 제원"]
KEEP = {"JCW", "ALL", "C", "S", "SE", "E"}


def lines_of(page):
    """(사각형, 글자) 목록 — PDF 글자 줄 단위"""
    out = []
    for b in page.get_text("dict")["blocks"]:
        if b["type"]:
            continue
        for l in b["lines"]:
            t = " ".join("".join(s["text"] for s in l["spans"]).split())
            if t:
                out.append((fitz.Rect(l["bbox"]), t))
    return out


def cx(r):
    return (r.x0 + r.x1) / 2


def cy(r):
    return (r.y0 + r.y1) / 2


# ---------------------------------------------------------------- 가격표

def info_links():
    h = H.unescape(curl_get(INFO, cache=False))
    pdfs = list(dict.fromkeys(re.findall(r'"([^"\s]+?\.pdf)(?:\.asset\.\d+\.pdf)?"', h)))
    price = re.search(r'"(/content/dam/MINI/marketKR/mini_co_kr/pricelist/[^"]+?\.pdf(?:\.asset\.\d+\.pdf)?)"', h)
    if not price:
        raise RuntimeError("가격표 PDF 링크를 찾지 못했습니다")
    per = {}
    for u in pdfs:
        m = re.search(r"/([A-Z0-9-]+?)-(Price-Option-List|Specification)\.pdf$", u)
        if m:
            per.setdefault(m.group(1), {})["opt" if m.group(2).startswith("Price") else "spec"] = u
    return BASE + price.group(1), per


def trim_name(raw, sec):
    t = " ".join(raw.split())
    for pre in (sec + " ", "ALL-ELECTRIC MINI ", "MINI "):
        if t.upper().startswith(pre):
            t = t[len(pre):]
            break
    return re.sub(r"[A-Za-z]+", lambda m: m.group(0) if m.group(0) in KEEP else m.group(0).capitalize(), t)


def price_list(pdf):
    """가격표 → [{"sec", "name", "price", "year", "date"}] (쪽마다 연식·기준일이 다르다)"""
    out = []
    secs = {m["sec"] for m in MODELS}
    for page in fitz.open(stream=pdf, filetype="pdf"):
        m = re.search(r"(\d{4})년식 MINI 모델 가격표\s*\((\d{4})\.(\d{1,2})\.(\d{1,2})\s*기준\)", page.get_text())
        if not m:
            continue
        year, date = m.group(1), f"{m.group(2)}-{int(m.group(3)):02d}-{int(m.group(4)):02d}"
        ls = lines_of(page)
        heads = sorted(((r, t.upper()) for r, t in ls if t.upper() in secs and r.x0 < 60), key=lambda x: x[0].y0)
        blacks = [d["rect"] for d in page.get_drawings() if d.get("fill") and sum(d["fill"]) < 0.3 and d["rect"].height > 20]
        for i, (hr, sec) in enumerate(heads):
            end = heads[i + 1][0].y0 if i + 1 < len(heads) else page.rect.height
            hdr = [b for b in blacks if hr.y1 < b.y0 < end]
            if not hdr:
                continue
            top, bot = min(b.y0 for b in hdr), max(b.y1 for b in hdr)
            left = max((b.x1 for b in hdr if b.x0 < 40), default=0)  # '모델' 칸 오른쪽 끝
            prices = sorted(((r, int(t.replace(",", ""))) for r, t in ls
                             if PRICE.match(t) and bot < r.y0 < bot + 30 and r.x0 > left), key=lambda p: p[0].x0)
            names = {k: [] for k in range(len(prices))}
            for r, t in ls:
                if top - 1 <= cy(r) <= bot + 1 and cx(r) > left and prices:
                    k = min(range(len(prices)), key=lambda k: abs(cx(prices[k][0]) - cx(r)))
                    names[k].append((r.y0, r.x0, t))
            for k, (r, p) in enumerate(prices):
                raw = " ".join(t for _, _, t in sorted(names[k]))
                out.append({"sec": sec, "name": trim_name(raw, sec), "raw": raw, "price": p, "year": year, "date": date})
    return out


# ---------------------------------------------------------------- 옵션 리스트

def option_list(pdf):
    """옵션 리스트 → [{"price": 정수, "cats": {분류: [문구]}}] (열 순서)"""
    page = fitz.open(stream=pdf, filetype="pdf")[0]
    ls = lines_of(page)
    prices = sorted(((r, int(t.replace(",", ""))) for r, t in ls if PRICE.match(t) and r.y0 < 220), key=lambda p: cx(p[0]))
    cs = [cx(r) for r, _ in prices]
    step = (cs[-1] - cs[0]) / (len(cs) - 1) if len(cs) > 1 else 140
    bounds = [cs[0] - step / 2] + [(a + b) / 2 for a, b in zip(cs, cs[1:])] + [cs[-1] + step / 2]
    left = bounds[0]
    draws = page.get_drawings()
    W = max(d["rect"].width for d in draws)
    hline = [d["rect"] for d in draws if d["rect"].height < 1.5 and d["rect"].width > 0.7 * W]
    short = [d["rect"] for d in draws if d["rect"].height < 1.5 and d["rect"].width < 0.3 * W and d["rect"].x0 > left - 2]
    bands = [d["rect"] for d in draws if d.get("fill") and 12 < d["rect"].height < 30 and d["rect"].width > 0.7 * W]
    dots = {}
    for d in draws:
        r = d["rect"]
        if d.get("fill") and sum(d["fill"]) < 0.6 and 3 < r.width < 10 and 3 < r.height < 10 and abs(r.width - r.height) < 2:
            dots[(round(cx(r)), round(cy(r)))] = r
    ys = sorted({round(r.y0, 1) for r in hline} | {round(b.y0, 1) for b in bands} | {round(b.y1, 1) for b in bands})
    edges = []
    for y in ys:
        if not edges or y - edges[-1] > 2:
            edges.append(y)
    cols = [{"price": p, "cats": {}} for _, p in prices]
    cat = None
    for y0, y1 in zip(edges, edges[1:]):
        inside = [(r, t) for r, t in ls if y0 < cy(r) < y1]
        if any(b.y0 - 2 <= y0 and y1 <= b.y1 + 2 for b in bands):  # 구역 제목 띠
            name = " ".join(t for r, t in inside if r.x0 < left).strip()
            cat = OPT_CAT.get(name, name)
            continue
        if not cat:
            continue
        label = " ".join(t for r, t in sorted(inside, key=lambda x: (x[0].y0, x[0].x0)) if cx(r) < left)
        label = re.sub(r"^-\s*", "", label).rstrip("*").strip()
        if not label or label == "휠 이미지":
            continue
        for k, c in enumerate(cols):
            lo, hi = bounds[k], bounds[k + 1]
            cell = sorted(((r, t) for r, t in inside if lo < cx(r) < hi and r.width < (hi - lo) * 1.2),
                          key=lambda x: (x[0].y0, x[0].x0))
            cuts = sorted(s.y0 for s in short if lo < cx(s) < hi and y0 + 2 < s.y0 < y1 - 2)
            parts, cur = [], []
            for r, t in cell:  # 칸 안의 가는 선(위아래로 나뉜 값)은 ' / '로 잇는다
                if cuts and cur and any(prev_y < c < r.y0 for c in cuts for prev_y in [cur[-1][0].y1 - 1]):
                    parts.append(" ".join(x[1] for x in cur))
                    cur = []
                cur.append((r, t))
            if cur:
                parts.append(" ".join(x[1] for x in cur))
            text = " / ".join(parts).strip()
            dot = any(lo < x < hi and y0 < y < y1 for x, y in dots)
            if "구매 가능" in text:  # 여러 열에 걸친 'MINI Connected Store에서 구매 가능'(별도 구독) — 기본 사양 아님
                continue
            if text and text != "-":
                c["cats"].setdefault(cat, []).append(f"{label}: {text}")
            elif dot:
                c["cats"].setdefault(cat, []).append(label)
    return cols


# ---------------------------------------------------------------- 제원

def code_of(t):
    """제원 열 머리글·트림 이름 → 구동계 코드(C·S·E·SE·JCW)"""
    if re.search(r"JCW|John Cooper Works", t, re.I) and not re.match(r"^(S|SE|C|E)[ _]", t):
        return "JCW"
    m = re.match(r"^(SE|E|C|S)[ _]", t + " ")
    if m:
        return m.group(1)
    m = re.search(r"\b(SE|E|C|S)\b(?:\s+ALL4)?\s*$", t)
    return m.group(1) if m else None


def spec_sheet(pdf):
    """제원 정보 → {코드: {분류: [문구]}} (연식이 여러 쪽이면 가장 새 연식 쪽)"""
    doc = fitz.open(stream=pdf, filetype="pdf")
    page = max(doc, key=lambda p: int((re.search(r"\((\d{4})년식\)", p.get_text()) or [0, 0])[1]))
    ls = lines_of(page)
    draws = page.get_drawings()
    bands = sorted((d["rect"] for d in draws if d.get("fill") and 12 < d["rect"].height < 40 and d["rect"].width > 300),
                   key=lambda r: r.y0)
    first = next(r for r in bands if any(t in SPEC_CAT for rr, t in ls if r.y0 - 2 < cy(rr) < r.y1 + 2))
    heads = sorted(((r, t) for r, t in ls if 80 < cy(r) < first.y0 and cx(r) > 150), key=lambda x: cx(x[0]))
    groups = []
    for r, t in heads:
        if groups and abs(cx(r) - groups[-1]["x"]) < 45:
            groups[-1]["t"].append((r.y0, t))
        else:
            groups.append({"x": cx(r), "t": [(r.y0, t)]})
    cols = []
    for g in groups:
        title = " ".join(t for _, t in sorted(g["t"]))
        cols.append((g["x"], code_of(title), title))
    left = cols[0][0] - (cols[1][0] - cols[0][0]) / 2 if len(cols) > 1 else cols[0][0] - 100
    out = {c: {} for _, c, _ in cols}
    cat = None
    for r, t in sorted(ls, key=lambda x: x[0].y0):
        if cx(r) >= left or r.y0 < first.y0 - 2 or t.startswith("*"):
            continue
        if t in SPEC_CAT:
            cat = SPEC_CAT[t]
            continue
        if not cat:
            continue
        for x, code, _ in cols:
            vals = [tt for rr, tt in ls if abs(cy(rr) - cy(r)) < 6 and abs(cx(rr) - x) < 60 and cx(rr) >= left]
            if vals:
                v = " ".join(vals)
                if "옵션제원표" in v or "트림별 상이" in v:
                    continue
                out[code].setdefault(cat, []).append(f"{t}: {v}")
    return out, [(c, title) for _, c, title in cols]


def base_label(s):
    return re.sub(r"\s*\(.*?\)\s*", "", s.split(":")[0]).strip()


def merge(spec, opt):
    """제원 + 옵션 리스트 → cats (같은 분류에 같은 항목이 옵션 리스트에 있으면 제원 쪽은 뺀다)"""
    cats = {}
    have = {base_label(x) for v in opt.values() for x in v}
    for c, items in spec.items():
        cats.setdefault(c, []).extend(x for x in items if base_label(x) not in have)
    for c, items in opt.items():
        cats.setdefault(c, []).extend(items)
    keys = sorted(cats, key=lambda k: ORDER.index(k) if k in ORDER else len(ORDER))
    return [{"cat": k, "items": [{"n": x} for x in dict.fromkeys(cats[k])]} for k in keys if cats[k]]


# ---------------------------------------------------------------- 사진

def home_renders():
    """홈페이지 모델 둘러보기 띠의 구성기 렌더 → {alt(소문자): 주소}
    (data-cosy-srcset은 뒤 항목이 주소 끝부분만 적혀 있어, 같은 alt로 함께 걸린 <img src=...>의 전체 주소를 쓴다)"""
    h = H.unescape(curl_get(HOME, cache=False))
    out = {}
    for tag in re.findall(r"<img[^>]*>", h):
        alt = re.search(r'alt="([^"]*)"', tag)
        src = re.search(r'\ssrc="(https://prod\.cosy\.bmw\.cloud/[^"]+)"', tag)
        if alt and src:
            out.setdefault(alt.group(1).strip().lower(), src.group(1))
    return out


def photos(d, m, renders):
    """배경 투명 렌더(대표) + 공식 외관 사진(x1, x2) + 실내 사진(i1)"""
    r = None
    src = renders.get(m["alt"])
    if src:
        try:
            r = fim.cut_from(d, src)
        except Exception as e:
            print(d["id"], "렌더 실패", e)
    ext, inn = [], []
    for i, p in enumerate(m["ext"], 1):
        try:
            ext.append(fim.save(fim.load(DAM + p), f"{d['id']}-x{i}.webp", False, 1600))
        except Exception as e:
            print(d["id"], "외관 사진 실패", p, e)
    for i, p in enumerate(m["int"], 1):
        try:
            inn.append(fim.save(fim.load(DAM + p), f"{d['id']}-i{i}.webp", False, 1600))
        except Exception as e:
            print(d["id"], "실내 사진 실패", p, e)
    if r:
        r["media"]["ext"], r["media"]["int"] = ext, inn
        return r
    if ext:  # 렌더가 없으면 첫 외관 사진을 대표로(목록용은 가운데를 16:9로 자른다)
        r = fim.photo_set(d, [DAM + p for p in m["ext"]])
        r["media"]["int"] = inn
        return r
    return None


# ---------------------------------------------------------------- 실행

def main():
    price_url, per = info_links()
    rows = price_list(curl_get(price_url, binary=True))
    if not rows:
        raise RuntimeError("가격표에서 트림을 읽지 못했습니다")
    try:
        renders = home_renders()
    except Exception as e:
        print("홈페이지 렌더 목록 실패", e)
        renders = {}
    out = DATA / "mini"
    out.mkdir(parents=True, exist_ok=True)
    made = set()
    for m in MODELS:
        trims = [r for r in rows if r["sec"] == m["sec"]]
        if not trims:
            print("가격표에 없음", m["name"])
            continue
        links = per.get(m["pdf"], {})
        opt_url = links.get("opt") and (links["opt"] if links["opt"].startswith("http") else BASE + links["opt"])
        spec_url = links.get("spec") and (links["spec"] if links["spec"].startswith("http") else BASE + links["spec"])
        opt_cols = option_list(curl_get(opt_url, binary=True, cache=False)) if opt_url else []
        spec, spec_cols = spec_sheet(curl_get(spec_url, binary=True, cache=False)) if spec_url else ({}, [])
        by_price = {}
        for c in opt_cols:
            by_price.setdefault(c["price"], []).append(c)
        variants, no_opt, no_spec = {}, [], []
        for t in trims:
            cands = by_price.get(t["price"]) or []
            opt = cands[0]["cats"] if len(cands) == 1 else {}
            code = code_of(t["name"])
            sp = spec.get(code) or {}
            if not opt:
                no_opt.append(t["name"])
            if not sp:
                no_spec.append(t["name"])
            vname = f"{m['fuel']} {t['year']}년식"
            v = variants.setdefault(vname, {"name": vname, "code": m["slug"], "year": t["year"], "trims": []})
            v["trims"].append({"name": t["name"].replace("_", " "), "price": t["price"], "cats": merge(sp, opt), "adds": [], "opts": []})
        vs = sorted(variants.values(), key=lambda v: v["year"])  # 2026년식(기본 트림 전체) → 2027년식
        for v in vs:
            v.pop("year")
            v["trims"].sort(key=lambda t: t["price"])
        dates = sorted({(t["year"], t["date"]) for t in trims})
        when = " · ".join(f"{y}년식 {d.replace('-', '.')} 기준" for y, d in dates)
        notes = [f"MINI 코리아 공식 가격표({when})의 권장 소비자 가격(부가세 포함, 개별소비세 5.0% 기준)과 "
                 "차종별 공식 옵션 리스트·제원 정보의 트림별 사양입니다."]
        if m["fuel"] == "전기":
            notes.append("구매 보조금은 반영되지 않은 가격입니다. 가격표상 면세 가격은 권장 소비자 가격과 같습니다.")
        if any("JCW" in t["name"] and code_of(t["name"]) != "JCW" for t in trims):
            notes.append("이름 끝이 JCW인 트림(예: C Classic JCW, 옵션 리스트 표기 C_JCW·S_JCW)은 C·S·SE 모델에 JCW 트림을 적용한 것입니다. "
                         "제원 정보에는 이 트림 열이 따로 없어 같은 구동계(C·S·SE) 열의 제원을 붙였습니다.")
        if no_opt:
            notes.append("옵션 리스트에서 같은 가격의 열을 찾지 못한 트림(" + ", ".join(n.replace("_", " ") for n in no_opt) + ")은 제원만 실었습니다.")
        if no_spec:
            notes.append("제원 정보에 해당 열이 없는 트림(" + ", ".join(n.replace("_", " ") for n in no_spec) + ")은 옵션 리스트 사양만 실었습니다.")
        notes.append("선택 옵션 가격은 공식 자료에 공개되어 있지 않습니다.")
        path = out / f"{m['slug']}.json"
        d = {"id": f"mini-{m['slug']}", "brand": "mini", "name": m["name"], "segment": m["seg"], "image": "",
             "imageSource": "", "lowPrice": min(t["price"] for t in trims), "priceDate": dates[-1][1],
             "sources": [price_url] + [u for u in (opt_url, spec_url) if u] + [f"{BASE}/ko_KR/home/range/{m['page']}.html"],
             "structure": "price-list", "variants": vs, "notes": notes}
        old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        try:
            r = photos(d, m, renders)
        except Exception as e:
            print(d["id"], "사진 실패", e)
            r = None
        if r:
            d["image"], d["media"], d["imageSource"] = r["image"], r["media"], r["src"]
        else:  # 사진을 못 받으면 기존 사진 정보를 지킨다
            for k in ("image", "media", "imageSource"):
                if old.get(k):
                    d[k] = old[k]
        save(path, d)
        made.add(path.name)
        print(d["id"], d["segment"], [(v["name"], [(t["name"], t["price"], sum(len(c["items"]) for c in t["cats"])) for t in v["trims"]])
                                      for v in vs], (d.get("media") or {}).get("heroType"))
    for f in out.glob("*.json"):  # 가격표에서 빠진 차종
        if f.name not in made:
            print("가격표에서 빠져 지움", f.name)
            f.unlink()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--debug":
        price_url, per = info_links()
        print(price_url)
        print(json.dumps(per, indent=1))
        for r in price_list(curl_get(price_url, binary=True)):
            print(r)
    else:
        main()
