"""현대자동차 공식 가격표(hyundai.com) → data/hyundai/*.json

가격표 HTML 조각(트림별 기본품목·선택품목)과 선택품목 상세 API(패키지 구성품)를 읽는다.
"""
import re
import sys
from concurrent.futures import ThreadPoolExecutor

from bs4 import BeautifulSoup

from common import DATA, clean, fetch, fetch_json, save, short, won

BASE = "https://www.hyundai.com"
API = BASE + "/kr/ko/gw/product/v1/product"

# (id, 표시명, 차급, [대표차 코드], 각 코드의 기본 연료 이름)
CASPER = [  # 캐스퍼는 별도 사이트(casper.hyundai.com)에서 판매
    ("casper", "캐스퍼", "https://casper.hyundai.com/vehicles/price", "가솔린", "AX08"),
    ("casper-electric", "캐스퍼 일렉트릭", "https://casper.hyundai.com/vehicles/electric/price", "전기", "AX07"),
]

MODELS = [
    ("avante", "아반떼", "준중형 세단", [("FN01", "가솔린"), ("FN02", "하이브리드")]),
    ("avante-n", "아반떼 N", "고성능", [("CN26", "가솔린 2.0T")]),
    ("sonata", "쏘나타 디 엣지", "중형 세단", [("DN26", "가솔린"), ("DN27", "하이브리드")]),
    ("grandeur", "그랜저", "준대형 세단", [("GN11", "가솔린"), ("GN12", "하이브리드")]),
    ("venue", "베뉴", "소형 SUV", [("QX07", "가솔린")]),
    ("kona", "코나", "소형 SUV", [("SX19", "가솔린"), ("SX20", "하이브리드")]),
    ("kona-electric", "코나 일렉트릭", "소형 SUV", [("SX17", "전기")]),
    ("tucson", "투싼", "준중형 SUV", [("GX01", "가솔린"), ("GX02", "하이브리드")]),
    ("santafe", "싼타페", "중형 SUV", [("MX07", "가솔린"), ("MX08", "하이브리드")]),
    ("palisade", "팰리세이드", "대형 SUV", [("FX03", "가솔린"), ("FX04", "하이브리드")]),
    ("ioniq5", "아이오닉 5", "준중형 SUV", [("NE09", "전기")]),
    ("ioniq5-n", "아이오닉 5 N", "고성능", [("NE08", "전기")]),
    ("ioniq6", "아이오닉 6", "중형 세단", [("CE03", "전기")]),
    ("ioniq6-n", "아이오닉 6 N", "고성능", [("CE05", "전기")]),
    ("ioniq9", "아이오닉 9", "대형 SUV", [("ME02", "전기")]),
    ("nexo", "넥쏘", "중형 SUV", [("HE02", "수소")]),
    ("staria", "스타리아", "MPV·승합", [("US30", "디젤"), ("US33", "하이브리드")]),
    ("staria-lounge", "스타리아 라운지", "MPV·승합", [("US31", "디젤"), ("US34", "하이브리드")]),
    ("staria-limousine", "스타리아 리무진", "MPV·승합", [("US46", "하이브리드")]),
    ("staria-kinder", "스타리아 킨더", "MPV·승합", [("US36", "디젤"), ("US45", "하이브리드")]),
    ("staria-electric", "스타리아 일렉트릭", "MPV·승합",
     [("US39", "스타리아"), ("US40", "라운지"), ("US41", "리무진")]),
    ("st1", "ST1", "상용·트럭", [("TS12", "전기")]),
    ("porter2", "포터 II", "상용·트럭", [("M578", "디젤")]),
    ("porter2-electric", "포터 II 일렉트릭", "상용·트럭", [("M579", "전기")]),
]


def menu_info():
    """GNB 메뉴에서 대표차 코드별 이미지·URL 이름·최저가를 얻는다."""
    j = fetch_json(API.replace("/product/v1/product", "/common/v1/common")
                   + "/gnb/menus/M?siteType=H&imageSectionCode=01&includeModelYn=Y")
    out = {}

    def walk(o):
        if isinstance(o, dict):
            if o.get("carCode") and o.get("carName"):
                out.setdefault(o["carCode"], o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(j)
    return out


def read_ul(ul):
    cats = []
    for li in ul.find_all("li", recursive=False):
        head = li.select_one(".list-title, .name")
        if not head:
            continue
        items = []
        for sp in li.select(".content .spec_opts"):
            name = clean(sp.get_text())
            if name:
                items.append({"n": name, "c": sp.get("data-car-spc-cd") or ""})
        if items:
            cats.append({"cat": clean(head.get_text()), "items": items})
    return cats


def item_lists(box):
    """기본품목 영역 → (전체 품목, 하위 트림 대비 추가 품목).
    상위 트림에는 '전체 품목'과 '추가 품목' 목록이 함께 있으므로 품목 수가 많은 쪽을 전체로 본다."""
    if not box:
        return [], []
    lists = [read_ul(u) for u in box.select("ul.table-list-contents")]
    lists = [c for c in lists if c]
    if not lists:
        return [], []
    size = lambda cs: sum(len(c["items"]) for c in cs)
    lists.sort(key=size, reverse=True)
    return lists[0], (lists[1] if len(lists) > 1 else [])


def parse_casper(html):
    """casper.hyundai.com 가격표(서버 렌더링 표) → [(표 제목, 트림 목록)]"""
    soup = BeautifulSoup(html, "lxml")
    out = []
    for table in soup.select("table"):
        rows = table.select("tbody > tr[data-trim]")
        if not rows:
            continue
        cap = clean(table.select_one("caption").get_text()) if table.select_one("caption") else ""
        trims = []
        for tr in rows:
            th = tr.select_one("th")
            tds = tr.find_all("td", recursive=False)
            # <h2><p>이름</p><strong>가격</strong></h2> — lxml이 h2 안의 p를 밖으로 빼므로 th 기준으로 찾는다
            ps = [p for p in th.select("p") if "t-gray" not in (p.get("class") or [])] if th else []
            name = clean(ps[0].get_text()) if ps else tr["data-trim"]
            price = won(th.select_one("strong").get_text()) if th and th.select_one("strong") else None
            desc = clean(th.select_one("p.t-gray").get_text()) if th and th.select_one("p.t-gray") else ""
            cats, adds = item_lists(tds[0] if tds else None)
            opts = []
            if len(tds) > 1:
                for oli in tds[1].select("ul[data-opts=select] > li"):
                    nm = oli.select_one(".item-name")
                    sp = nm.select_one(".spec_opts") if nm else None
                    if not nm:
                        continue
                    n = clean(sp.get_text()) if sp else clean(nm.get_text())
                    note = clean(clean(nm.get_text(" ")).replace(n, "", 1)).strip("() ")
                    pr = oli.select_one(".item-price")
                    opts.append({"n": n, "c": "", "p": won(pr.get_text()) if pr else None,
                                 "g": "옵션", "note": note})
            trims.append({"name": name, "en": "", "price": price, "desc": desc,
                          "cats": cats, "adds": adds, "opts": opts})
        out.append((cap.replace(" 트림별 가격표", ""), trims))
    return out


def scrape_casper(mid, name, url, fuel, menu_code, menu):
    html = fetch(url)
    variants, low = [], None
    for cap, trims in parse_casper(html):
        vname = fuel + (" · VAN" if "VAN" in cap else "")
        variants.append({"name": vname, "code": menu_code, "trims": trims, "notes": []})
        for t in trims:
            if t["price"] and (low is None or t["price"] < low):
                low = t["price"]
    m = menu.get(menu_code, {})
    date = re.search(r"\d{4}년 \d{1,2}월 \d{1,2}일 기준", html)
    return {
        "id": "hyundai-" + mid, "brand": "hyundai", "name": name, "segment": "경차",
        "image": BASE + m["carImgPath"] if m.get("carImgPath") else "", "lowPrice": low,
        "priceDate": date.group(0) if date else "", "sources": [url],
        "variants": variants, "packages": {},
    }


def parse_fragment(html):
    soup = BeautifulSoup(html, "lxml")
    date = clean(soup.select_one("#priceDay").get_text()) if soup.select_one("#priceDay") else ""
    trims = []
    for blk in soup.select("div.price-trim-list"):
        title = blk.select_one(".table-price-title")
        if not title:
            continue
        en = clean(title.select_one(".en").get_text()) if title.select_one(".en") else ""
        kr = clean(title.select_one(".kr").get_text()).strip("()") if title.select_one(".kr") else ""
        price = won(title.select_one(".price").get_text()) if title.select_one(".price") else None
        cats, adds = item_lists(blk.select_one(".basic-item"))
        opts = []
        sel = blk.select_one(".select-item")
        if sel:
            for li in sel.select("ul.table-list-contents > li"):
                group = clean(li.select_one(".list-title").get_text()) if li.select_one(".list-title") else "옵션"
                for oli in li.select(".conts li"):
                    nm = oli.select_one(".item-name")
                    if not nm:
                        continue
                    sp = nm.select_one(".spec_opts")
                    name = clean(sp.get_text()) if sp else clean(nm.get_text())
                    full = clean(nm.get_text(" "))
                    note = clean(full.replace(name, "", 1)) if name else ""
                    pr = oli.select_one(".item-price")
                    opts.append({
                        "n": name, "c": (sp.get("data-car-spc-cd") if sp else "") or "",
                        "p": won(pr.get_text()) if pr else None, "g": group, "note": note,
                    })
        trims.append({"name": kr or en, "en": en if kr else "", "price": price,
                      "cats": cats, "adds": adds, "opts": opts})
    notes = []
    etc = soup.select_one(".etc-table")
    if etc:
        for t in etc.select("li li, p, td"):
            s = clean(t.get_text(" "))
            if 8 < len(s) < 400 and s not in notes:
                notes.append(s)
    return date, trims, notes[:40]


def option_detail(code, repn):
    try:
        j = fetch_json(f"{API}/price/spec/info?carSpcCd={code}&repnCarCode={repn}")
    except Exception:
        return None
    d = j.get("data") or {}
    head = d.get("carOptionDetailchoice") or {}
    subs = d.get("carOptionPackageDetail") or []
    return {
        "desc": short(head.get("spcExplSbl"), 300),
        "items": [{"n": clean(s.get("pcltSpcNm")), "d": short(s.get("spcExplSbl"), 220)}
                  for s in subs if s.get("pcltSpcNm")],
    }


def variant_name(fuel, sub):
    """연료 이름 + 가격표 탭 이름 → 짧은 파워트레인 이름 ('디젤 · 투어러 11인승' 등)."""
    if not sub:
        return fuel
    sub = sub.replace("일렉트릭", "")
    sub = re.sub(r"\d+\s*\((\d+)인승\)", r"\1인승", sub)
    sub = re.sub(r"\s+", " ", sub).strip()
    if any(k in sub for k in ("가솔린", "LPG", "디젤", "하이브리드")):
        return sub
    words = fuel.replace("·", " ").split()
    while sub.split() and sub.split()[0] in words:  # '라운지 · 라운지 7인승' 같은 중복 제거
        sub = sub.split(" ", 1)[1] if " " in sub else ""
    return f"{fuel} · {sub}" if sub else fuel


def scrape_model(mid, name, segment, codes, menu):
    variants, packages, images, srcs, dates = [], {}, [], [], []
    low = None
    for code, fuel in codes:
        m = menu.get(code, {})
        dp = fetch_json(f"{API}/car-detailpage/{code}/H?repnCarCode={code}&siteSnCode=H")
        info = (dp.get("data") or [{}])[0]
        slug = info.get("rcUrlScnNm") or m.get("carEngName") or ""
        skip = ("장애인", "특장차", "택시", "영업용", "법인택시", "개인택시", "렌터카", "운전교습용")
        frags = [u for u in info.get("usfList") or []
                 if u.get("menuTypeCode") == "03" and (u.get("usf1Nm") or "") not in skip
                 and "교습" not in (u.get("usf2Nm") or "")]
        if m.get("carImgPath"):
            images.append(BASE + m["carImgPath"])
        srcs.append(f"{BASE}/kr/ko/e/vehicles/{slug}/price")
        for u in frags:
            html = fetch(f"{BASE}{u['urlAdr']}/{u['fileNm']}")
            date, trims, notes = parse_fragment(html)
            if not trims:
                continue
            dates.append(date)
            vname = variant_name(fuel, u.get("usf2Nm"))
            variants.append({"name": vname, "code": code, "trims": trims, "notes": notes})
            for t in trims:
                if t["price"] and (low is None or t["price"] < low):
                    low = t["price"]
                for o in t["opts"]:
                    if o["c"] and o["c"] not in packages:
                        packages[o["c"]] = (o["c"], code)
    # 선택품목 상세(패키지 구성품) 병렬 수집
    with ThreadPoolExecutor(8) as ex:
        res = dict(zip(packages, ex.map(lambda a: option_detail(*a), packages.values())))
    pk = {c: r for c, r in res.items() if r and (r["items"] or r["desc"])}
    return {
        "id": "hyundai-" + mid, "brand": "hyundai", "name": name, "segment": segment,
        "image": images[0] if images else "", "lowPrice": low,
        "priceDate": max(dates) if dates else "", "sources": sorted(set(srcs)),
        "variants": variants, "packages": pk,
    }


def main(only=None):
    menu = menu_info()
    index = []
    jobs = [(c[0], lambda c=c: scrape_casper(*c, menu)) for c in CASPER]
    jobs += [(m[0], lambda m=m: scrape_model(*m, menu)) for m in MODELS]
    for mid, job in jobs:
        if only and mid not in only:
            continue
        try:
            d = job()
        except Exception as e:
            print("FAIL", mid, e)
            continue
        if not d["variants"]:
            print("EMPTY", mid)
            continue
        save(DATA / "hyundai" / f"{mid}.json", d)
        ntr = sum(len(v["trims"]) for v in d["variants"])
        print(f"OK {mid}: {len(d['variants'])} variants, {ntr} trims, {len(d['packages'])} options, {d['priceDate']}")
        index.append(mid)
    return index


if __name__ == "__main__":
    main(set(sys.argv[1:]) or None)
