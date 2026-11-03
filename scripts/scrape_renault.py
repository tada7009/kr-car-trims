"""르노코리아 공식 가격표 PDF(cdn.renault.co.kr) → data/renault/*.json

가격표는 트림마다 '판매가격 / 공급가액 / (친환경차) 세제 혜택 후 가격', '・분류 : 품목' 목록,
'▶ 아래 트림 기본 품목 및' 참조, '▶ 선택 품목 … 가격' 순서로 되어 있다.
"""
import hashlib
import io
import re
import sys
import urllib.request
from datetime import date

import pymupdf

from common import CACHE, DATA, fetch, save, won
from scrape_kgm import merge, split_items

CDN = "https://cdn.renault.co.kr/upload/asset/price/price_{key}_{ym}.pdf"
SITE = "https://www.renault.co.kr/ko/model/{key}_overview.jsp"

MODELS = [  # (id, 표시명, 차급, 가격표 키)
    ("arkana", "아르카나", "소형 SUV", "Arkana"),
    ("grand-koleos", "그랑 콜레오스", "중형 SUV", "koleos"),
    ("filante", "필랑트", "대형 SUV", "filante"),
]
PRICE = re.compile(r"^\d{1,3}(,\d{3})+$")
SUPPLY = re.compile(r"^\d{1,3}(,\d{3})+\s*\(\d{1,3}(,\d{3})+\)$")
CAT_NAMES = {"파워트레인": "파워트레인", "첨단 주행 보조": "첨단 주행 보조", "안전": "안전", "외관": "외관", "내장": "내장",
             "편의": "편의", "멀티미디어": "멀티미디어", "공조시스템": "공조"}


def months_back(n=6):
    d = date.today()
    y, m = d.year, d.month
    for _ in range(n):
        yield f"{y}{m:02d}"
        m -= 1
        if not m:
            y, m = y - 1, 12


def get_pdf(key):
    for ym in months_back():
        url = CDN.format(key=key, ym=ym)
        path = CACHE / f"renault-{key}-{ym}.pdf"
        if not path.exists():
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = r.read()
                if not data.startswith(b"%PDF"):
                    continue
                path.write_bytes(data)
            except Exception:
                continue
        return url, path.read_bytes()
    return None, None


def is_trim_start(L, i):
    return (i + 3 < len(L) and PRICE.match(L[i + 2]) and SUPPLY.match(L[i + 3])
            and re.search(r"[가-힣]", L[i + 1]) and not L[i].startswith(("▶", "・", "※")))


def parse_page(text):
    # 가격표의 ▶ 기호 뒤에 제어문자(\x07)가 섞여 나온다
    L = [re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f]", " ", l)).strip() for l in text.split("\n")]
    L = [l for l in L if l]
    # 한 페이지에 변형이 둘 이상일 수 있다(아르카나: 1.6 GTe + 하이브리드). '트림별 판매가격' 바로 윗줄이 변형 제목
    segs, notes, cur, title = [], [], None, ""
    mode, opt = None, None

    def finish_opt():
        nonlocal opt
        if opt is not None:
            opt["text"] = re.sub(r"\s+", " ", opt["text"]).replace("▶", "").strip()
            opt["parts"] = [p.strip() for p in opt["text"].split(" + ") if p.strip()]
        opt = None

    i = 0
    while i < len(L):
        l = L[i]
        if i + 1 < len(L) and L[i + 1].startswith("트림별 판매가격"):
            finish_opt()
            title, cur = l, None
            segs.append((title, []))
            i += 2
            continue
        if is_trim_start(L, i) and segs:
            finish_opt()
            cur = {"en": L[i], "name": L[i + 1].strip("() "), "price": won(L[i + 2]), "priceAfter": None,
                   "ref": None, "_cats": [], "_remove": [], "_opts": []}
            segs[-1][1].append(cur)
            i, mode = i + 4, None
            continue
        if cur is None:
            i += 1
            continue
        if re.search(r"세제 ?혜택 ?후 ?판매 ?가격", l) and i + 1 < len(L) and PRICE.match(L[i + 1]):
            cur["priceAfter"] = won(L[i + 1])
            i += 2
            continue
        if l.startswith(("※", "•")):
            finish_opt()
            notes.append(re.sub(r"^[※•]\s*", "", l))
            mode = None
        elif l.startswith("▶") and "미적용" in l:
            finish_opt()
            mode = "remove"
        elif l.startswith("▶") and "기본 품목" in l:
            finish_opt()
            cur["ref"] = re.sub(r"^▶\s*|\s*기본 품목.*$", "", l).strip()
            mode = None
        elif l.startswith("▶"):
            finish_opt()
            opt = {"text": l, "p": None}
            cur["_opts"].append(opt)
            mode = "opt"
        elif l.startswith("・"):
            finish_opt()
            m = re.match(r"^・\s*([^:]+?)\s*:\s*(.*)$", l)
            if m:
                (cur["_remove"] if mode == "remove" else cur["_cats"]).append([m.group(1).strip(), m.group(2)])
                mode = "remove" if mode == "remove" else "cat"
        elif PRICE.match(l):
            # 가격은 옵션 바로 뒤에 오지만, 옵션 여러 개 뒤에 몰려 나오기도 한다 → 가격 없는 첫 옵션에 차례로 붙인다
            target = opt if (mode == "opt" and opt is not None and opt["p"] is None) else None
            finish_opt()
            if target is None:  # 몰려 나온 가격 — 순서가 틀릴 수 있어 아래 좌표 대조로 다시 확인한다
                target = next((o for o in cur["_opts"] if o["p"] is None), None)
                if target is not None:
                    target["late"] = True
            if target is not None:
                target["p"] = won(l)
                if i + 1 < len(L) and re.match(r"^→\s*\d{1,3}(,\d{3})+$", L[i + 1]):  # 할인가
                    target["p"] = won(L[i + 1])
                    i += 1
            mode = None
        elif mode in ("cat", "remove"):
            bucket = cur["_remove"] if mode == "remove" else cur["_cats"]
            if bucket:
                bucket[-1][1] += " " + l
        elif mode == "opt" and opt is not None:
            opt["text"] += " " + l
        i += 1
    finish_opt()
    return segs, notes


def okey(s):
    return re.sub(r"[\W_]+", "", re.sub(r"[\x00-\x1f]", "", s).replace("▶", ""))


def geo_options(page):
    """PDF 좌표로 '▶ 옵션' 줄과 같은 높이의 가격 줄을 짝짓는다 (할인가 '→800,000'이 아래에 있으면 그 값).
    반환: 옵션 키 → [(y, 가격)], 트림 가격 문자열 → y"""
    lines = []
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            t = re.sub(r"[\x00-\x1f]", " ", "".join(s["text"] for s in ln["spans"])).strip()
            if t:
                lines.append((ln["bbox"], t))
    num = re.compile(r"^→?\d{1,3}(,\d{3})+$")
    prices = [(bb, t.replace(" ", "")) for bb, t in lines if num.match(t.replace(" ", ""))]
    opts, trim_y = {}, {}
    for bb, t in lines:
        if PRICE.match(t.replace(" ", "")):
            trim_y.setdefault(t.replace(" ", ""), bb[1])
        if not t.startswith("▶") or "기본 품목" in t or "미적용" in t:
            continue
        yc = (bb[1] + bb[3]) / 2
        cands = [(pb, pt) for pb, pt in prices if pb[0] > bb[0] and not pt.startswith("→") and abs((pb[1] + pb[3]) / 2 - yc) < 8]
        if not cands:
            continue
        pb, pt = min(cands, key=lambda c: abs((c[0][1] + c[0][3]) / 2 - yc))
        # 할인가 줄은 바로 위 가격 줄의 것: 화살표 줄에서 가장 가까운 일반 가격 줄이 pb일 때만 적용
        plain = [q for q in prices if not q[1].startswith("→")]
        owner = lambda a: min(plain, key=lambda q: abs(a[0][1] - q[0][3]) + abs(a[0][2] - q[0][2]))
        arrow = [q for q in prices if q[1].startswith("→") and abs(q[0][2] - pb[2]) < 20 and owner(q) == (pb, pt)]
        val = won(arrow[0][1]) if arrow else won(pt)
        opts.setdefault(okey(t), []).append((bb[1], val))
    return opts, trim_y


def to_cats(raw):
    out = []
    for name, txt in raw:
        items = split_items(txt)
        if items:
            out.append({"cat": CAT_NAMES.get(name, name), "items": [{"n": n, "c": ""} for n in items]})
    return out


def opt_name(parts):
    first = parts[0]
    return re.sub(r"\s+", " ", first).strip()


def scrape(mid, name, seg, key):
    url, pdf = get_pdf(key)
    if not pdf:
        print("  no pdf", key)
        return None
    doc = pymupdf.open(stream=io.BytesIO(pdf), filetype="pdf")
    pages = [p.get_text() for p in doc]
    head = "\n".join(pages[:2])
    m = re.search(r"(\d{4})년\s*(\d{1,2})월", head)
    pdate = f"{m.group(1)}년 {int(m.group(2))}월 가격표 기준" if m else ""
    if not pdate:  # 표지에 날짜가 없으면 파일 이름의 연월(price_Arkana_202611.pdf)
        ym = re.search(r"_(\d{4})(\d{2})\.pdf$", url)
        pdate = f"{ym.group(1)}년 {int(ym.group(2))}월 가격표 기준" if ym else ""
    parsed = []
    for page, t in zip(doc, pages):
        if "트림별 판매가격" not in t:
            continue
        segs, notes = parse_page(t)
        geo, trim_y = geo_options(page)
        for _, trims in segs:
            for tr in trims:
                ty = trim_y.get(f"{tr['price']:,}")
                for o in tr["_opts"]:
                    # 옵션 첫 줄과 같은 높이에 찍힌 가격이 있으면 그 값이 정답 (텍스트 순서는 섞일 수 있다)
                    k = okey(o["text"])
                    hits = [h for gk, hs in geo.items() if len(gk) >= 6 and k.startswith(gk) for h in hs]
                    if hits and ty is not None:
                        o["p"] = min(hits, key=lambda h: abs(h[0] - ty))[1]
        parsed += [(title, trims, notes) for title, trims in segs]
    has_new = any("27MY" in t for t, _, _ in parsed)
    variants, packages = [], {}
    for title, trims, notes in parsed:
        if not trims or (has_new and "26MY" in title):
            continue
        vname = re.sub(r"\s*\d{2}MY\s*", " ", title.replace(name, "").replace("르노", "")).strip() or "기본"
        variants.append({"name": vname, "title": title, "trims": trims, "notes": notes[:20]})
    # '▶ (다른 변형) 트림 기본 품목 및' 참조를 풀어 전체 품목을 만든다
    done = {}

    def full_of(v, t):
        k = (v["title"], t["en"])
        if k in done:
            return done[k]
        own = to_cats(t["_cats"])
        base = []
        if t["ref"]:
            ref = t["ref"]
            # 참조 문구가 끝나는 트림 이름(영문·한글) 중 가장 긴 것 ('esprit Alpine'처럼 두 낱말도 있다)
            same = lambda x, n: n.lower() in (x["en"].lower(), x["name"].lower())
            names = sorted({n for vv in variants for x in vv["trims"] for n in (x["en"], x["name"])}, key=len, reverse=True)
            tname = next((n for n in names if ref.lower().endswith(n.lower())), ref.split()[-1])
            prefix = ref[: len(ref) - len(tname)].strip()
            has = lambda vv: any(same(x, tname) for x in vv["trims"])
            src_v = next((vv for vv in variants if prefix and prefix in vv["title"] and has(vv)), v)
            src_t = next((x for x in src_v["trims"] if same(x, tname)), None)
            if src_t is not None and src_t is not t:
                base = full_of(src_v, src_t)
        if any(c["cat"] == "파워트레인" for c in own):
            base = [c for c in base if c["cat"] != "파워트레인"]
        res = merge(base, own) if base else own
        drop = {i["n"] for c in to_cats(t["_remove"]) for i in c["items"]}  # '기본 품목 대비 미적용 품목'
        if drop:
            res = [{"cat": c["cat"], "items": [i for i in c["items"] if i["n"] not in drop]} for c in res]
        done[k] = res
        return res

    out_variants = []
    for v in variants:
        trims = []
        prev = None
        for t in v["trims"]:
            cats = full_of(v, t)
            opts = []
            for o in t["_opts"]:
                if o.get("p") is None:
                    continue
                n = opt_name(o["parts"])
                code = f"RN-{key}-{hashlib.md5(o['text'].encode()).hexdigest()[:8]}"
                if len(o["parts"]) > 1:
                    packages[code] = {"desc": "", "items": [{"n": p, "d": ""} for p in o["parts"]]}
                opts.append({"n": n + (f" 외 {len(o['parts']) - 1}종" if len(o["parts"]) > 1 else ""),
                             "c": code if len(o["parts"]) > 1 else "", "p": o["p"], "g": "옵션", "note": ""})
            price = t["priceAfter"] or t["price"]
            tr = {"name": t["name"], "en": t["en"], "price": price, "cats": cats,
                  "adds": to_cats(t["_cats"]) if t["ref"] else [], "opts": opts}
            if t["priceAfter"] and t["price"] != price:
                tr["priceBefore"] = t["price"]
            trims.append(tr)
            prev = tr
        vname = v["name"]
        if vname == "기본" and any("하이브리드" in i["n"] for t in trims for c in t["cats"] if c["cat"] == "파워트레인" for i in c["items"]):
            vname = "하이브리드 E-Tech"
        out_variants.append({"name": vname, "code": key, "trims": trims, "notes": v["notes"]})
    img = ""
    try:
        h = fetch(SITE.format(key=key.lower()))
        mm = re.search(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', h)
        img = mm.group(1) if mm else ""
    except Exception:
        pass
    out_variants.sort(key=lambda v: bool(re.search(r"Limited|Edition|에디션", v["name"])))  # 한정판은 뒤로
    prices = [t["price"] for v in out_variants for t in v["trims"]]
    return {"id": "renault-" + mid, "brand": "renault", "name": name, "segment": seg, "image": img,
            "lowPrice": min(prices) if prices else None, "priceDate": pdate, "sources": [url],
            "variants": out_variants, "packages": packages}


def main(only=None):
    for mid, name, seg, key in MODELS:
        if only and mid not in only:
            continue
        d = scrape(mid, name, seg, key)
        if not d or not d["variants"]:
            print("EMPTY", mid)
            continue
        save(DATA / "renault" / f"{mid}.json", d)
        print(f"OK {mid}: {d['priceDate']} · " + " / ".join(f"{v['name']}({len(v['trims'])})" for v in d["variants"]))


if __name__ == "__main__":
    main(set(sys.argv[1:]) or None)
