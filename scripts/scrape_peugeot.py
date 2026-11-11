"""푸조 코리아 공식 홈페이지(www.epeugeot.co.kr) → data/peugeot/*.json (+ img/peugeot-*.webp)

- 트림·가격: '이 달의 프로모션' 페이지(base.epeugeot.co.kr/Sales/promotion)의 차종별 트림 선택 상자와 '차량가격'
  (선택 상자 n번째 항목 = n번째 tab-contents). 같은 트림이 연식만 달리 같은 가격이면 하나로 묶는다.
- 사양: 차종 페이지(/new-cars/<차종>hybrid.html)의 'ALLURE 트림'·'GT 트림' 적용 사양.
  GT는 'ALLURE 사양 외 GT에 추가된 사양'이라 ALLURE 사양을 합친다(제원은 트림별 값 그대로).
  PERFORMANCE 단락의 엔진·변속기 제원은 모든 트림에, 연비·CO2는 페이지 기준 모델(GT)에만 넣는다.
- 사진: 차종 페이지 색상 보기의 배경 투명 렌더(cut). 5008은 투명 렌더에 'NEW' 표시가 붙어 있어 스튜디오 사진(photo)을 쓴다.
가격 날짜가 페이지에 없어서 priceDate는 수집일로 둔다.
"""
import html as H
import json
import re
import sys

from common import DATA, curl_get, save
from fetch_import_media import cut_from, load, photo_set
from fetch_import_media import save as save_img

WWW = "https://www.epeugeot.co.kr"
PROMO = "https://base.epeugeot.co.kr/Sales/promotion"
DAM = WWW + "/content/dam/peugeot/south_korea/"
PRICE_DATE = "2026-11-11"
MODELS = [
    {"slug": "308", "page": "308hybrid", "promo": "308Hybrid", "segment": "해치백",
     "cut": "frnt308r.png", "photos": [], "int": ["mobby1.jpg", "mobby4.jpg"]},
    {"slug": "408", "page": "408hybrid", "promo": "408Hybrid", "segment": "쿠페형 SUV",
     "cut": "frnt4084.png", "photos": [], "int": ["intfinal408hb1pc.jpg", "seats408hb.jpg"]},
    {"slug": "3008", "page": "3008hybrid", "promo": "3008Hybrid", "segment": "SUV",
     "cut": "3008_HYBRIDbluef.png", "photos": [], "int": ["PEUGEOT_3008_HYBRID_2412PJ_511_FR_pc.jpg", "surger3008.jpg"]},
    {"slug": "5008", "page": "5008hybrid", "promo": "5008", "segment": "SUV",
     "cut": None, "photos": ["ingaroblueseries1.png", "ingaroblueseries3.png"], "int": ["int_5008m.jpg", "5008int3.jpg"]},
]
PERF = re.compile(r"^(?:•\s*)?(엔진\s*형식|배기량|엔진 최고 출력|모터 최고 출력|엔진 최대 토크|모터 최대 토크|사용 연료|구동 방식|변속기|복합연비|복합CO2 배출량)\s*(\([^)]*\))?\s*:\s*(.+)$")
FUEL = ("복합연비", "복합CO2 배출량")


def text(s):
    s = re.sub(r"<br\s*/?>", " ", s or "")
    s = H.unescape(re.sub(r"<[^>]+>", "", s)).replace("\xa0", " ").replace("​", "")
    return " ".join(s.split())


def promo():
    """프로모션 페이지 → {섹션 id: ([(트림 이름, 가격, 연식, 출고월)], 페이지 문구)}"""
    h = re.sub(r"<!--.*?-->", "", curl_get(PROMO, cache=False), flags=re.S)
    out = {}
    for m in re.finditer(r'<section class="re-prom[^"]*"[^>]*\bid="([^"]+)"[^>]*>', h):
        sec = h[m.end():h.find("</section>", m.end())]
        opts = [text(o) for o in re.findall(r"<option[^>]*>(.*?)</option>", sec, re.S)]
        tabs = re.split(r'<div class="tab-contents', sec)[1:]
        rows = []
        for i, o in enumerate(opts):
            if i >= len(tabs):
                break
            p = re.search(r'차량\s*가격\s*</span>\s*:\s*<span class="val">\s*([\d,]+)\s*만\s*원', tabs[i])
            if not p:
                continue
            my = re.match(r"^\((\d{2})MY\)\s*", o)
            month = re.search(r"(\d{1,2})월 출고 혜택", tabs[i])
            rows.append((re.sub(r"^\(\d{2}MY\)\s*", "", o), int(p.group(1).replace(",", "")) * 10000,
                         my.group(1) if my else None, month.group(1) if month else None))
        out[m.group(1)] = rows
    return out


def page_specs(h):
    """차종 페이지 → ({트림 머리글: {분류: [항목]}}, 성능 항목 [(라벨, 문구)], 기준 문구)"""
    trims = {}
    heads = [(m.start(), text(m.group(1)).split()[0].upper())
             for m in re.finditer(r'<span class="font-\d+">([A-Za-z]+ 트림)</span>', h)]
    for k, (pos, name) in enumerate(heads):
        if name in trims:  # 같은 내용이 모바일용으로 한 번 더 나온다
            continue
        end = heads[k + 1][0] if k + 1 < len(heads) else pos + 40000
        seg = h[pos:end]
        cut = seg.find("시승 신청")
        seg = seg[:cut] if cut > 0 else seg
        cats, cat = {}, None
        for m in re.finditer(r"<p>(.*?)</p>|<li>(.*?)</li>", seg, re.S):
            if m.group(1) is not None:
                t = text(m.group(1))
                if t and "<b>" in m.group(1) and not t.startswith("["):
                    cat = t
            elif cat:
                t = text(m.group(2))
                if t and t not in cats.setdefault(cat, []):
                    cats[cat].append(t)
        trims[name] = cats
    body = re.sub(r"<script.*?</script>|<style.*?</style>", "", h, flags=re.S)
    body = re.sub(r"<[^>]+>", " ", re.sub(r"<(br|/p|/li|/div)[^>]*>", "\n", body))
    lines = [" ".join(H.unescape(l).replace("​", "").split()) for l in body.split("\n")]
    perf, seen = [], set()
    for l in lines:
        m = PERF.match(l)
        if m and m.group(1) not in seen:
            seen.add(m.group(1))
            perf.append((m.group(1), re.sub(r"^•\s*", "", l)))
    basis = next((l for l in lines if l.startswith("※ 상기 데이터는")), "")
    return trims, perf, basis


def photos(d, m, old):
    """공식 사진 → image·media·imageSource. 실패하면 이전 값을 그대로 둔다."""
    try:
        r = cut_from(d, DAM + m["cut"]) if m["cut"] else None
        if not r:
            r = photo_set(d, [DAM + p for p in m["photos"]])
        r["media"]["int"] = [save_img(load(DAM + p), f"{d['id']}-i{n}.webp", False, 1600) for n, p in enumerate(m["int"], 1)]
        return r
    except Exception as e:
        print("  사진 실패", d["id"], e)
        if old.get("image"):
            return {"image": old["image"], "media": old.get("media"), "src": old.get("imageSource", "")}
        return None


def main(only=None):
    out = DATA / "peugeot"
    out.mkdir(parents=True, exist_ok=True)
    old = {}
    for f in out.glob("*.json"):
        o = json.loads(f.read_text(encoding="utf-8"))
        old[o["id"]] = o
    prices = promo()
    done = set()
    for m in MODELS:
        mid = f"peugeot-{m['slug']}"
        if only and mid not in only:
            done.add(f"{m['slug']}.json")
            continue
        rows = prices.get(m["promo"]) or []
        if not rows:
            print(mid, "프로모션 페이지에 가격 없음 — 넣지 않음")
            continue
        page = f"{WWW}/new-cars/{m['page']}.html"
        specs, perf, basis = page_specs(curl_get(page, cache=False))
        # 같은 트림·같은 가격의 연식 묶기
        merged = {}
        for name, price, my, month in rows:
            key = (name, price)
            e = merged.setdefault(key, {"mys": [], "months": set()})
            if my:
                e["mys"].append(my)
            if month:
                e["months"].add(month)
        base = specs.get("ALLURE", {})
        trims, missing = [], []
        for (name, price), e in merged.items():
            same = [n for (n, _p) in merged if n == name]
            tname = name if len(same) == 1 or not e["mys"] else f"({'·'.join(e['mys'])}MY) {name}"
            head = name.split()[0].upper()
            own = specs.get(head)
            cats = {}
            if own is None:
                missing.append(tname)
            elif head == "ALLURE":
                cats = {k: list(v) for k, v in own.items()}
            else:  # GT = ALLURE 적용 사양 + GT 추가 사양
                for k, v in base.items():
                    if k != "제원":
                        cats[k] = list(v)
                for k, v in own.items():
                    if k == "제원":
                        cats[k] = list(v)
                    else:
                        cats.setdefault(k, [])
                        cats[k] += [x for x in v if x not in cats[k]]
                if "제원" not in cats and "제원" in base:
                    cats["제원"] = list(base["제원"])
            pw = [s for lab, s in perf if lab not in FUEL or (head in basis.upper() and own is not None)]
            out_cats = ([{"cat": "파워트레인", "items": [{"n": s} for s in pw]}] if pw and own is not None else []) + \
                       [{"cat": k, "items": [{"n": x} for x in v]} for k, v in cats.items()]
            trims.append({"name": tname, "price": price, "cats": out_cats, "adds": [], "opts": []})
        trims.sort(key=lambda t: t["price"])
        months = sorted({mo for e in merged.values() for mo in e["months"]})
        notes = [f"푸조 코리아 공식 홈페이지 '이 달의 프로모션' 페이지의 차량가격({'·'.join(months) + '월 출고 기준, ' if months else ''}"
                 "지원금 적용 전)과 차종 페이지의 트림별 적용 사양입니다. 가격표 날짜와 부가세·개별소비세 포함 여부는 "
                 "공식 페이지에 적혀 있지 않아 수집일을 기준일로 두었습니다."]
        if basis and any(lab in FUEL for lab, _ in perf):
            notes.append(f"연비·CO2 배출량은 공식 페이지에 '{basis.lstrip('※ ').strip()}'라고 되어 있어 해당 트림에만 넣었습니다.")
        mys = sorted({my for e in merged.values() for my in e["mys"]})
        if len(mys) > 1 and all(len(e["mys"]) > 1 for e in merged.values()):
            notes.append(f"{'·'.join(mys)}년식이 같은 차량가격으로 함께 판매되고 있습니다(지원금은 연식별로 다름). 사양은 공식 페이지 기준입니다.")
        sold = {re.sub(r"^\(.*?\)\s*", "", t["name"]).split()[0].upper() for t in trims}
        unsold = [k for k in specs if k not in sold]
        if unsold:
            notes.append(f"공식 차종 페이지에는 {'·'.join(unsold)} 트림 사양도 있으나 공식 페이지에 가격이 없어 싣지 않았습니다.")
        if missing:
            notes.append("사양이 비어 있는 트림(" + ", ".join(missing) + ")은 공식 차종 페이지에 같은 트림의 사양 목록이 없어 가격만 실었습니다.")
        d = {"id": mid, "brand": "peugeot", "name": m["slug"], "segment": m["segment"], "image": "", "imageSource": "",
             "lowPrice": min(t["price"] for t in trims), "priceDate": PRICE_DATE, "sources": [PROMO, page], "structure": "web",
             "variants": [{"name": "스마트 하이브리드", "code": m["page"], "trims": trims}],
             "media": {"hero": "", "heroType": "photo", "ext": [], "int": []}, "notes": notes}
        r = photos(d, m, old.get(mid, {}))
        if r:
            d["image"], d["media"], d["imageSource"] = r["image"], r["media"], r["src"]
        save(out / f"{m['slug']}.json", d)
        done.add(f"{m['slug']}.json")
        print(mid, [(t["name"], t["price"], sum(len(c["items"]) for c in t["cats"])) for t in trims],
              d["media"].get("heroType"), len(d["media"].get("int", [])))
    for f in out.glob("*.json"):  # 공식 사이트에서 빠진 차종 파일 정리
        if f.name not in done:
            f.unlink()
            print("삭제", f.name)


if __name__ == "__main__":
    main(set(sys.argv[1:]) or None)
