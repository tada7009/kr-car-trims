"""기아 공식 가격표(kia.com 자가용 가격 페이지) → data/kia/*.json

가격 페이지는 서버에서 렌더링되며, 트림마다 '전체품목 보기' 영역에 전체 기본품목·추가품목·선택품목이 들어 있다.
패키지 구성품은 kwpapi.kia.com 상세 API로 읽는다.
"""
import re
import sys
from concurrent.futures import ThreadPoolExecutor

from bs4 import BeautifulSoup

from common import DATA, clean, fetch, fetch_json, save, short, won

BASE = "https://www.kia.com"
API = "https://kwpapi.kia.com/kr/ko/api/v1/goods/spec/parts"
HDR = {"Referer": BASE + "/", "Origin": BASE}

# (id, 표시명, 차급, [(가격 페이지 slug, 변형 접두어)])
MODELS = [
    ("morning", "모닝", "경차", [("morning", "")]),
    ("ray", "레이", "경차", [("ray", "")]),
    ("ray-ev", "레이 EV", "경차", [("ray-ev", "")]),
    ("k5", "K5", "중형 세단", [("k5", "")]),
    ("k8", "K8", "준대형 세단", [("k8", "")]),
    ("k9", "K9", "대형 세단", [("k9", "")]),
    ("seltos", "셀토스", "소형 SUV", [("seltos", "")]),
    ("niro", "니로", "소형 SUV", [("niro", "")]),
    ("sportage", "스포티지", "준중형 SUV", [("sportage", "")]),
    ("sorento", "쏘렌토", "중형 SUV", [("sorento", "")]),
    ("carnival", "카니발", "MPV·승합", [("carnival", "")]),
    ("carnival-hi-limousine", "카니발 하이리무진", "MPV·승합", [("carnival-hi-limousine", "")]),
    ("ev3", "EV3", "소형 SUV", [("ev3", ""), ("ev3-gt", "GT")]),
    ("ev4", "EV4", "준중형 세단", [("ev4", ""), ("ev4-gt", "GT")]),
    ("ev5", "EV5", "준중형 SUV", [("ev5", ""), ("ev5-gt", "GT")]),
    ("ev6", "EV6", "준중형 SUV", [("ev6", ""), ("ev6-gt", "GT")]),
    ("ev9", "EV9", "대형 SUV", [("ev9", ""), ("ev9-gt", "GT")]),
    ("tasman", "타스만", "픽업", [("tasman", "")]),
    ("pv5-passenger", "PV5 패신저", "MPV·승합", [("pv5-passenger", "")]),
    ("pv5-cargo", "PV5 카고", "상용·트럭", [("pv5-cargo", ""), ("pv5-cargo-compact", "컴팩트")]),
    ("bongo3", "봉고 III", "상용·트럭", [("bongo3", "")]),
    ("bongo3-ev", "봉고 III EV", "상용·트럭", [("bongo3-ev", "")]),
]


def items_from(acc):
    """accordion 영역 → [{cat, items:[{n,c,new}]}]"""
    cats = []
    if not acc:
        return cats
    for li in acc.select("ul.accordion__list > li"):
        btn = li.select_one(".accordion__tit button, .accordion__tit")
        items = []
        for it in li.select(".accordion__cont li"):
            a = it.select_one("a")
            n = clean(it.get_text(" "))
            if n:
                items.append({"n": n, "c": (a.get("data-modal-id") if a else "") or "",
                              **({"new": 1} if "pointer" in (it.get("class") or []) else {})})
        if btn and items:
            cats.append({"cat": clean(btn.get_text(" ")), "items": items})
    return cats


def size(cats):
    return sum(len(c["items"]) for c in cats)


def parse_panel(panel):
    trims = []
    main_names = [clean(h.get_text()) for h in panel.select(".pricelist__pc .price_list__item-title")]
    for i, tp in enumerate(panel.select(".vicle-price__tabpannel")):
        cap = tp.select_one("table.car_option caption")
        name = main_names[i] if i < len(main_names) else ""
        if not name and cap:
            name = re.sub(r"^판매가격으로 구성된 | 가격정보$", "", clean(cap.get_text()))
        prices = {}
        for tr in tp.select("table.car_option tr"):
            th, td = tr.select_one("th"), tr.select_one("td")
            if th and td:
                prices[clean(th.get_text())] = won(td.get_text())
        price = prices.get("세제혜택 후 판매가격") or prices.get("판매가격") or next(iter(prices.values()), None)
        before = prices.get("세제혜택 전 판매가격")
        accs = tp.select(".accordion__wrap")
        full = tp.select_one(".accordion__wrap.i-basic")
        adds = tp.select_one(".accordion__wrap.i-off")
        if not full and accs:
            full = max(accs, key=lambda a: len(a.select(".accordion__cont li")))
        cats = items_from(full)
        add_cats = items_from(adds) if adds and adds is not full else []
        opts = []
        for t in tp.select("table"):
            if "car_option" in (t.get("class") or []):
                continue
            cap_t = clean(t.caption.get_text()) if t.caption else ""
            group = cap_t.split(":")[0].strip() or "선택품목"
            group = "옵션" if group.startswith("선택품목") else group
            for tr in t.select("tr"):
                th, td = tr.select_one("th"), tr.select_one("td")
                if not th or not td:
                    continue
                a = th.select_one("a[data-modal-id]")
                n = clean(th.get_text(" "))
                note = ""
                m = re.match(r"^(.*?)\s*\((.*(?:선택|불가|적용|시).*)\)$", n)
                if m:
                    n, note = m.group(1), m.group(2)
                opts.append({"n": n, "c": (a.get("data-modal-id") if a else "") or "",
                             "p": won(td.get_text()), "g": group, "note": note})
        img = tp.select_one(".vicle-price__images img")
        t = {"name": name, "en": "", "price": price, "cats": cats, "adds": add_cats, "opts": opts}
        if before and before != price:
            t["priceBefore"] = before
        if img and img.get("src"):
            t["img"] = BASE + img["src"]
        trims.append(t)
    return trims


def panel_notes(panel):
    out = []
    for li in panel.select(".price-notice__list li"):
        if li.find_parent(class_="vicle-price__tabpannel") or li.find_parent(class_="accordion__cont"):
            continue
        s = clean(li.get_text(" "))
        if 8 < len(s) < 400 and s not in out:
            out.append(s)
    return out[:40]


def parse_page(html):
    soup = BeautifulSoup(html, "lxml")
    date = ""
    m = re.search(r"\d{4}년 \d{1,2}월 \d{1,2}일 기준", soup.get_text(" "))
    if m:
        date = m.group(0)
    names = [clean(t.get_text(" ")) for t in soup.select("li.cmp-tabs__tab, li.aem-tabs__tab")]
    panels = soup.select(".cmp-tabs__tabpanel")
    out = []
    for i, p in enumerate(panels):
        if not p.select(".vicle-price__tabpannel"):
            continue
        trims = parse_panel(p)
        if trims:
            out.append((names[i] if i < len(names) else f"구성 {i+1}", trims, panel_notes(p)))
    if not out:  # 탭이 없는 단일 가격표
        trims = parse_panel(soup)
        if trims:
            out.append(("", trims, panel_notes(soup)))
    hero = soup.select_one(".vicle-price__images img")
    return date, out, (BASE + hero["src"]) if hero and hero.get("src") else ""


def option_detail(code):
    for cls in ("20", "10"):
        try:
            j = fetch_json(f"{API}/{code}?classification={cls}", HDR)
        except Exception:
            continue
        b = j.get("body") or {}
        subs = b.get("subSpecModel") or []
        if subs or b.get("specDetail") not in (None, "", "detail"):
            return {"desc": short(b.get("specDetail") if b.get("specDetail") != "detail" else "", 300),
                    "items": [{"n": clean(s.get("specName")), "d": short(s.get("specDetail"), 220)}
                              for s in subs if s.get("specName")]}
    return None


def scrape_model(mid, name, segment, pages):
    variants, codes, srcs, dates, img = [], set(), [], [], ""
    for slug, prefix in pages:
        html = None
        for url in (f"{BASE}/kr/vehicles/{slug}/price/private", f"{BASE}/kr/vehicles/{slug}/price"):
            try:
                html = fetch(url, retries=1)
                break
            except Exception:
                continue
        if html is None:
            print("  skip", slug)
            continue
        date, groups, hero = parse_page(html)
        if not groups:
            continue
        srcs.append(url)
        dates.append(date)
        img = img or hero
        for gname, trims, notes in groups:
            vname = " · ".join(x for x in (prefix, gname) if x) or name
            variants.append({"name": vname, "code": slug, "trims": trims, "notes": notes})
            for t in trims:
                for o in t["opts"]:
                    if o["c"]:
                        codes.add(o["c"])
    with ThreadPoolExecutor(8) as ex:
        res = dict(zip(codes, ex.map(option_detail, codes)))
    pk = {c: r for c, r in res.items() if r and (r["items"] or r["desc"])}
    prices = [t["price"] for v in variants for t in v["trims"] if t["price"]]
    return {
        "id": "kia-" + mid, "brand": "kia", "name": name, "segment": segment,
        "image": img, "lowPrice": min(prices) if prices else None,
        "priceDate": max(dates) if dates else "", "sources": srcs,
        "variants": variants, "packages": pk,
    }


def main(only=None):
    for mid, name, seg, pages in MODELS:
        if only and mid not in only:
            continue
        try:
            d = scrape_model(mid, name, seg, pages)
        except Exception as e:
            print("FAIL", mid, repr(e))
            continue
        if not d["variants"]:
            print("EMPTY", mid)
            continue
        save(DATA / "kia" / f"{mid}.json", d)
        ntr = sum(len(v["trims"]) for v in d["variants"])
        print(f"OK {mid}: {len(d['variants'])} variants, {ntr} trims, {len(d['packages'])} options, {d['priceDate']}")


if __name__ == "__main__":
    main(set(sys.argv[1:]) or None)
