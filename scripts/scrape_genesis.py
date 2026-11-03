"""제네시스 공식 견적(BTO) 데이터 → data/genesis/*.json

제네시스는 트림 대신 '기본 가격 + 엔진·구동·패키지 선택' 구조라서,
엔진×구동 조합을 트림처럼 보여 주고 휠·패키지·선택품목·유료 컬러를 선택품목으로 정리한다.
"""
import re
import sys
from datetime import date

from common import DATA, clean, fetch, fetch_json, save, short, won

BASE = "https://www.genesis.com"
API = BASE + "/wsvc/kr/api/v2/structure/data?key=btomodel&lngloc=ko-KR&model="

# (id, 표시명, 차급, [(BTO 모델 코드, 변형 이름, BTO 경로)])
MODELS = [  # (BTO 코드, 변형 이름, BTO 경로, 가격표 PDF 이름 앞부분)
    ("g70", "G70", "중형 세단", [("JU5B", "G70", "luxury-sedan-genesis/g70", "genesis-g70"),
                                ("JU5U", "슈팅 브레이크", "luxury-sedan-genesis/g70-shooting-brake", "genesis-g70-sb")]),
    ("g80", "G80", "준대형 세단", [("JJ7B", "G80", "luxury-sedan-genesis/g80", "genesis-g80"),
                                  ("JJ7U", "G80 블랙", "luxury-sedan-genesis/g80-black", "genesis-g80-black")]),
    ("electrified-g80", "G80 전동화", "준대형 세단",
     [("JI5B", "전기", "luxury-sedan-genesis/electrified-g80", "genesis-g80-ev")]),
    ("g90", "G90", "대형 세단", [("JP3B", "G90", "luxury-sedan-genesis/g90", "genesis-g90"),
                               ("JP6W", "G90 블랙", "luxury-sedan-genesis/g90-black", "genesis-g90-black"),
                               ("JP4L", "롱 휠베이스", "luxury-sedan-genesis/g90-long-wheel-base", "genesis-g90-long-wheel-base"),
                               ("JP69", "롱 휠베이스 블랙", "luxury-sedan-genesis/g90-long-wheel-base-black",
                                "genesis-g90-long-wheel-base-black")]),
    ("gv60", "GV60", "준중형 SUV", [("JW6B", "GV60", "luxury-suv-genesis/gv60", "genesis-gv60"),
                                   ("JWMB", "GV60 마그마", "luxury-suv-genesis/gv60-magma", "genesis-gv60-magma")]),
    ("gv70", "GV70", "중형 SUV", [("JK9B", "GV70", "luxury-suv-genesis/gv70", "genesis-gv70")]),
    ("electrified-gv70", "GV70 전동화", "중형 SUV",
     [("JV5B", "전기", "luxury-suv-genesis/electrified-gv70", "genesis-gv70-ev")]),
    ("gv80", "GV80", "대형 SUV", [("JXNB", "GV80", "luxury-suv-genesis/gv80", "genesis-gv80"),
                                 ("JXN1", "GV80 블랙", "luxury-suv-genesis/gv80-black", "genesis-gv80-black"),
                                 ("JH1B", "하이브리드", "luxury-suv-genesis/gv80-hybrid", "genesis-gv80-hybrid"),
                                 ("JH11", "하이브리드 블랙", "luxury-suv-genesis/gv80-hybrid-black", "genesis-gv80-hybrid-black")]),
    ("gv80-coupe", "GV80 쿠페", "대형 SUV", [("JXZB", "GV80 쿠페", "luxury-suv-genesis/gv80-coupe", "genesis-gv80-coupe"),
                                          ("JXZY", "GV80 쿠페 블랙", "luxury-suv-genesis/gv80-coupe-black",
                                           "genesis-gv80-coupe-black")]),
]

DL = BASE + "/kr/ko/support/download-center/genesis-models.html"
CATS = ("파워트레인 및 성능", "외관", "내장", "안전", "편의", "시트", "인포테인먼트")


def pdf_keys():
    """다운로드 센터 → {pdf 파일명: file_key}"""
    h = fetch(DL)
    return dict((m.group(2), m.group(1)) for m in re.finditer(r"viewPdf\('(\w+)','([^']+\.pdf)'", h))


def latest_pricelist(keys, stem):
    names = sorted(n for n in keys if re.fullmatch(rf"{re.escape(stem)}-pricelist-kor-\d{{6}}\.pdf", n))
    return names[-1] if names else None


def pdf_text(file_key):
    import io
    import urllib.request
    from pypdf import PdfReader
    from common import CACHE
    path = CACHE / f"genesis-{file_key}.pdf"
    if not path.exists():
        req = urllib.request.Request(BASE + "/wsvc/kr/api/v2/download-center/pdfview",
                                     data=f"file_key={file_key}".encode(), headers={"User-Agent": "Mozilla/5.0", "Referer": DL})
        with urllib.request.urlopen(req, timeout=60) as r:
            path.write_bytes(r.read())
    reader = PdfReader(io.BytesIO(path.read_bytes()))
    return [p.extract_text() or "" for p in reader.pages]


def split_items(s):
    out, depth, cur = [], 0, ""
    for ch in s:
        depth += ch in "(（[" and 1 or 0
        depth -= ch in ")）]" and 1 or 0
        if ch == "," and depth <= 0:
            out.append(cur); cur = ""
        else:
            cur += ch
    out.append(cur)
    return [re.sub(r"\s+", " ", x).strip(" .") for x in out if len(x.strip()) > 1]


def base_items(pages):
    """가격표 '주요 사양' 영역 → [{cat, items}] (모든 엔진·구동 조합 공통 기본 사양)"""
    page = next((p for p in pages if "주요 사양" in p), "")
    if not page:
        return []
    seg = page[page.find("주요 사양") + 5:]
    end = min([i for i in (seg.find("필수 선택"), seg.find("선택 품목")) if i > 0] or [len(seg)])
    lines = seg[:end].split("\n")
    cats, cur, prev = [], None, ","
    for ln in lines:
        s = ln.strip()
        head = next((c for c in CATS if s.startswith(c) and not prev.rstrip().endswith(",")), None)
        if head:
            cur = {"cat": head, "text": s[len(head):]}
            cats.append(cur)
        elif cur is not None:
            cur["text"] += " " + s
        prev = s or prev
    return [{"cat": c["cat"], "items": [{"n": n, "c": ""} for n in split_items(c["text"])]}
            for c in cats if split_items(c["text"])]


DIMS = {"powertrains": "powertrainName", "drivetrains": "drivetrainName",
        "passengers": "passengerName", "wheels": "wheelName"}


def names(j):
    out = {}
    for dim, key in DIMS.items():
        out[dim] = {o["specCode"]: clean(o.get(key)) for o in j.get(dim) or []}
    return out


def avail(item, pt, dt, nm):
    """(엔진 pt, 구동 dt) 트림에서 선택 가능하면 (가격, 조건 메모), 불가하면 None."""
    base = won(item.get("price")) or 0
    flt = item.get("filter") or []
    if not flt:
        return base, ""
    hits = []
    for f in flt:
        conds = {k: v for c in f.get("condition") or [] for k, v in c.items()}
        if conds.get("powertrains", pt) != pt or conds.get("drivetrains", dt) != dt:
            continue
        price = won(f.get("price"))
        price = base if price in (None, -1) else price
        other = [nm[k].get(v, v) for k, v in conds.items() if k not in ("powertrains", "drivetrains") and k in nm]
        hits.append((price, " / ".join(other)))
    if not hits:
        return None
    prices = sorted({h[0] for h in hits})
    memo = ", ".join(sorted({h[1] for h in hits if h[1]}))
    return prices[0], (f"{memo} 선택 시" if memo else "")


def details(o):
    return [{"n": clean(d.get("title")), "d": short(d.get("description"), 220)}
            for d in o.get("details") or [] if clean(d.get("title"))]


def scrape_variant(code, vname):
    j = fetch_json(API + code)
    nm = names(j)
    base = won(j.get("basePrice")) or 0
    pts = j.get("powertrains") or [{"specCode": "", "powertrainName": "", "price": "0"}]
    dts = j.get("drivetrains") or [{"specCode": "", "drivetrainName": "", "price": "0"}]
    steps = {s["title"]: i for i, s in enumerate(j.get("steps") or [])}
    pk_titles = [s["title"] for s in j.get("steps") or []]
    groups = []  # (그룹 이름, 항목 목록, 이름 키)
    if len(j.get("passengers") or []) > 1:
        groups.append(("스포츠/구성", j["passengers"], "passengerName"))
    groups.append(("휠 & 타이어", j.get("wheels") or [], "wheelName"))
    # packages / packages2 / packages3 의 실제 단계 이름은 steps 순서를 따른다
    pkg_steps = [t for t in pk_titles if "패키지" in t or "선택" in t or "액세서리" in t]
    pkg_steps = [t for t in pkg_steps if "스포츠" not in t] or ["패키지", "선택 품목", "액세서리"]
    for i, key in enumerate(("packages", "packages2", "packages3")):
        label = pkg_steps[i] if i < len(pkg_steps) else key
        groups.append((label, j.get(key) or [], "packageName"))
    packages = {}
    trims = []
    for pt in pts:
        for dt in dts:
            # 구동 항목은 엔진별로 따로 정의되어 있다(filter로 엔진 지정)
            a = avail(dt, pt["specCode"], dt["specCode"], nm) if dt.get("filter") else (won(dt.get("price")) or 0, "")
            if a is None:
                continue
            price = base + (won(pt.get("price")) or 0) + a[0]
            dname = clean(dt.get("drivetrainName", "")).split(" - ")[0]
            tname = " ".join(x for x in (clean(pt.get("powertrainName")), dname) if x)
            opts = []
            for label, items, key in groups:
                for o in items:
                    n = clean(o.get(key))
                    if not n or "미노출" in n or (label == "스포츠/구성" and not won(o.get("price"))
                                                   and not o.get("filter") and n == "기본 모델"):
                        continue
                    r = avail(o, pt["specCode"], dt["specCode"], nm)
                    if r is None:
                        continue
                    price_o, memo = r
                    if label == "스포츠/구성" and n == "기본 모델":
                        continue
                    if price_o == 0 and label == "휠 & 타이어":
                        memo = f"{memo} 기본 적용" if memo else "기본 적용"
                    pcode = f"{code}-{o.get('specCode')}"
                    det = details(o)
                    desc = clean(o.get("sdesc1") or o.get("description") or "")
                    if det or desc:
                        packages[pcode] = {"desc": short(desc, 400), "items": det}
                    ex = [x for x in o.get("exclude") or [] if isinstance(x, str)]
                    if ex:
                        exn = [clean(p.get("packageName")) for k in ("packages", "packages2", "packages3")
                               for p in j.get(k) or [] if p.get("specCode") in ex]
                        if exn:
                            memo = (memo + " · " if memo else "") + "동시 선택 불가: " + ", ".join(exn)
                    opts.append({"n": n, "c": pcode, "p": price_o, "g": label, "note": memo})
            seen = set()
            for g in j.get("exteriorColors") or []:
                for c in g.get("list") or []:
                    p = won(c.get("price")) or 0
                    n = f"{clean(c.get('colorName'))} ({clean(g.get('name'))})"
                    if p and n not in seen:
                        seen.add(n)
                        opts.append({"n": n, "c": "", "p": p, "g": "유료 컬러", "note": "외장"})
            for d in j.get("interiorDesigns") or []:
                dn = clean(d.get("designName"))
                for c in d.get("interiorColors") or []:
                    p = won(c.get("price")) or 0
                    cn = re.sub(r"\s*-\s*" + re.escape(dn) + r"$", "", clean(c.get("colorName")))
                    n = f"{dn} · {cn}"
                    if p and n not in seen:
                        seen.add(n)
                        opts.append({"n": n, "c": "", "p": p, "g": "유료 컬러", "note": "내장"})
            trims.append({"name": tname, "en": "", "price": price, "cats": [], "adds": [], "opts": opts})
    spec = []
    for pt in pts:
        bits = [f"{clean(pt.get('desc1'))} {clean(pt.get('sdesc1'))}", f"{clean(pt.get('desc2'))} {clean(pt.get('sdesc2'))}",
                f"{clean(pt.get('desc3'))} {clean(pt.get('sdesc3'))}"]
        bits = [b.strip() for b in bits if b.strip() and "None" not in b]
        if bits:
            spec.append(f"{clean(pt.get('powertrainName'))}: " + ", ".join(bits))
    colors = list(dict.fromkeys(clean(c.get("colorName")) for g in j.get("exteriorColors") or []
                                for c in g.get("list") or []))
    notes = spec + ([f"외장 컬러 {len(colors)}종: " + ", ".join(colors)] if colors else [])
    first = next((c for g in j.get("exteriorColors") or [] for c in g.get("list") or []), {})
    img = (first.get("image") or {}).get("small") or ""
    return {"name": vname, "code": code, "trims": trims, "notes": notes,
            "modelYear": j.get("title") or "", "img": BASE + img if img else ""}, packages


def scrape_model(mid, name, segment, variants_cfg, keys):
    variants, packages, srcs, dates = [], {}, [], []
    for code, vname, path, stem in variants_cfg:
        try:
            v, pk = scrape_variant(code, vname)
        except Exception as e:
            print("  skip", code, e)
            continue
        if not v["trims"]:
            continue
        pdf = latest_pricelist(keys, stem)
        if pdf:
            try:
                pages = pdf_text(keys[pdf])
                base = base_items(pages)
                m = re.search(r"\d{4}년 \d{1,2}월 \d{1,2}일", "\n".join(pages[:3]))
                if m:
                    dates.append(m.group(0) + " 기준")
                for t in v["trims"]:
                    t["cats"] = base
                v["notes"].insert(0, f"기본 사양 출처: 제네시스 공식 가격표 PDF ({pdf}) — 엔진·구동 조합 공통 기본 사양")
            except Exception as e:
                print("  pdf fail", pdf, e)
        variants.append(v)
        packages.update(pk)
        srcs.append(f"{BASE}/kr/ko/models/{path}/bto/")
    prices = [t["price"] for v in variants for t in v["trims"] if t["price"]]
    return {
        "id": "genesis-" + mid, "brand": "genesis", "name": name, "segment": segment,
        "image": next((v["img"] for v in variants if v.get("img")), ""),
        "lowPrice": min(prices) if prices else None,
        "priceDate": max(dates) if dates else "{0.year}년 {0.month}월 {0.day}일 견적 시스템 조회".format(date.today()),
        "sources": srcs, "variants": variants, "packages": packages, "structure": "bto",
    }


def main(only=None):
    keys = pdf_keys()
    for mid, name, seg, cfg in MODELS:
        if only and mid not in only:
            continue
        d = scrape_model(mid, name, seg, cfg, keys)
        if not d["variants"]:
            print("EMPTY", mid)
            continue
        save(DATA / "genesis" / f"{mid}.json", d)
        ntr = sum(len(v["trims"]) for v in d["variants"])
        print(f"OK {mid}: {len(d['variants'])} variants, {ntr} trims, {len(d['packages'])} options")


if __name__ == "__main__":
    main(set(sys.argv[1:]) or None)
