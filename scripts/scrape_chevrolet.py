"""쉐보레(한국GM) 공식 가격표 PDF → data/chevrolet/*.json

가격표 PDF 주소는 카탈로그/가격표 페이지(e-catalog-price-list)에서 차종을 누르면 나타난다.
월마다 파일 이름이 바뀌므로 갱신할 때 아래 PRICELIST 주소를 그 페이지에서 확인해 바꾼다.
"""
import io
import re
import sys
import urllib.request

import pymupdf

from common import CACHE, DATA, save, won
from scrape_kgm import merge, split_items

BASE = "https://www.chevrolet.co.kr/content/dam/chevrolet/as/kr/ko/index/e-catalogue-price-list"
IMG = BASE + "/2025/07-july/01-images/catalog-img-{}.png?imwidth=1200"
MODELS = [  # (id, 표시명, 차급, 가격표 PDF, 이미지 이름)
    ("trax-crossover", "트랙스 크로스오버", "소형 SUV",
     BASE + "/2026/jul/trax-crossover-v3/all-line-up-pricelist-202607-trax-crossover-e-catalog.pdf", "trax-crossover"),
    ("trailblazer", "트레일블레이저", "소형 SUV",
     BASE + "/2026/jul/all-line-up-pricelist-202607-the-new-trailblazer-e-catalog.pdf", "trailblazer"),
]
PRICE = re.compile(r"^\d{1,3}(,\d{3})+$")
NAME_PRICE = re.compile(r"^(.{1,30}?)\s+(\d{1,3}(?:,\d{3})+)$")
OPT_PRICE = re.compile(r"^:\s*(\d{1,3}(?:,\d{3})+)")


def get_pdf(url):
    path = CACHE / ("chevy-" + url.rsplit("/", 1)[-1])
    if not path.exists():
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            path.write_bytes(r.read())
    return path.read_bytes()


def parse(text):
    L = [re.sub(r"\s+", " ", l).strip() for l in text.split("\n")]
    L = [l for l in L if l]
    try:
        start = next(i for i in range(len(L) - 3) if L[i] == "차종" and L[i + 1] == "판매가격")
    except StopIteration:
        return [], []
    detail, body = L[:start], L[start + 4:]
    trims, cur, names, mode, opt = [], None, [], None, None
    for l in body:
        if re.match(r"^(FWD|AWD|※|제3종|\(단위)", l):
            break
        if l.startswith("*"):  # 트림 중간의 각주('* 옐로우 포인트 인테리어 선택 가능')는 건너뛴다
            continue
        m = NAME_PRICE.match(l)
        if (m and not l.startswith(("●", ":"))) or (PRICE.match(l) and names):
            name = m.group(1) if m else " ".join(names[-2:])
            price = won(m.group(2) if m else l)
            cur = {"name": name.strip(), "price": price, "ref": None, "_cats": [], "_opts": []}
            trims.append(cur)
            names, mode, opt = [], None, None
            continue
        if cur is None or (mode is None and not l.startswith(("●", ":")) and "기본" not in l):
            if not l.startswith(("●", ":")):
                names.append(l)
            if cur is None:
                continue
        if re.search(r"기본 (사양 )?품목 및", l):
            cur["ref"] = re.sub(r"\s*기본 (사양 )?품목 및.*$", "", l).strip()
            mode = None
        elif l.startswith("●") and " : " in l:
            cat, txt = l[1:].split(" : ", 1)
            cur["_cats"].append([re.sub(r"\s*사양$", "", cat.strip()), txt])
            mode, names = "cat", []
        elif l.startswith("●"):
            opt = {"n": l[1:].strip(), "p": None}
            cur["_opts"].append(opt)
            mode, names = "opt", []
        elif OPT_PRICE.match(l) and opt is not None:
            opt["p"] = won(OPT_PRICE.match(l).group(1))
            mode, names = None, []
        elif mode == "cat":
            cur["_cats"][-1][1] += " " + l
        elif mode == "opt" and opt is not None:
            opt["n"] += " " + l
    return trims, detail


def to_cats(raw):
    return [{"cat": c, "items": [{"n": n, "c": ""} for n in split_items(t)]} for c, t in raw if split_items(t)]


def scrape(mid, name, seg, url, img):
    doc = pymupdf.open(stream=io.BytesIO(get_pdf(url)), filetype="pdf")
    text = "\n".join(p.get_text() for p in doc)
    trims, detail = parse(text)
    ym = re.search(r"(\d{4})(\d{2})", url.rsplit("/", 1)[-1])
    by_name, out, packages = {}, [], {}
    for t in trims:
        own = to_cats(t["_cats"])
        base = by_name.get(t["ref"], []) if t["ref"] else []
        full = merge(base, own) if base else own
        by_name[t["name"]] = full
        opts = []
        for o in t["_opts"]:
            if o["p"] is None:
                continue
            short = re.sub(r"^NEW\s+", "", re.sub(r"\s*\(.*?\)\s*", " ", o["n"])).strip()
            code = f"CV-{mid}-{re.sub(r'[^0-9A-Za-z가-힣]', '', short)}"
            # 가격표 앞쪽 '선택품목 상세' 표에서 같은 이름 다음 줄의 구성 품목
            for i, l in enumerate(detail):
                if short and short in l and i + 1 < len(detail) and "," in detail[i + 1]:
                    packages[code] = {"desc": "", "items": [{"n": n, "d": ""} for n in split_items(detail[i + 1])]}
                    break
            note = (re.search(r"\((.*?)\)", o["n"]) or [None, ""])[1]
            opts.append({"n": short, "c": code if code in packages else "", "p": o["p"], "g": "옵션", "note": note})
        out.append({"name": t["name"], "en": "", "price": t["price"], "cats": full,
                    "adds": own if t["ref"] else [], "opts": opts})
    notes = [re.sub(r"^[※*]\s*", "", l) for l in re.split(r"\n", text) if l.strip().startswith(("※", "* "))][:20]
    return {"id": "chevrolet-" + mid, "brand": "chevrolet", "name": name, "segment": seg,
            "image": IMG.format(img), "lowPrice": min(t["price"] for t in out) if out else None,
            "priceDate": f"{ym.group(1)}년 {int(ym.group(2))}월 가격표 기준" if ym else "",
            "sources": [url], "variants": [{"name": "가솔린", "code": mid, "trims": out, "notes": notes}],
            "packages": packages}


def main(only=None):
    for mid, name, seg, url, img in MODELS:
        if only and mid not in only:
            continue
        d = scrape(mid, name, seg, url, img)
        if not d["variants"][0]["trims"]:
            print("EMPTY", mid)
            continue
        save(DATA / "chevrolet" / f"{mid}.json", d)
        print(f"OK {mid}: " + ", ".join(f"{t['name']} {t['price']:,}" for t in d["variants"][0]["trims"]))


if __name__ == "__main__":
    main(set(sys.argv[1:]) or None)
