"""지커 코리아 공식 자료 → data/zeekr/7x.json

- 가격·선택 품목: 공식 구성기(conf.zeekrlife.com/ko-kr). 화면 안에서 API(POST)로 받아 오므로
  내장 브라우저로 구성기 상태를 꺼내 raw/zeekr/configurator.json에 저장해 두고 그것을 읽는다.
  지커 코리아 보도자료(7X 고객 인도 개시)의 트림별 가격과 맞춰 본다.
- 사양: 7X 모델 페이지에 걸린 공식 브로슈어 PDF 2쪽 사양표. 글자가 벡터 그림이라 추출되지 않아
  표를 옮겨 적은 raw/zeekr/brochure_spec.json을 읽는다(모델 페이지의 브로슈어 주소가 바뀌면 알린다).
- 사진: 구성기 첫 화면의 배경 투명 렌더와 실내 사진(raw/zeekr/images.json). 받지 못하면 이전 사진 정보를 둔다.
"""
import json
import re
from pathlib import Path

from common import DATA, clean, curl_get, save
from fetch_import_media import cut_from, load, save as save_img

RAW = Path(__file__).resolve().parent / "raw" / "zeekr"
CONF = "https://conf.zeekrlife.com/ko-kr/"
PAGE = "https://www.zeekrlife.com/ko-kr/models/zeekr-7x"
NEWS = "https://www.zeekrlife.com/ko-kr/posts/7x-1-sk"
PRICE_DATE = "2026-11-11"  # 구성기 가격에 날짜가 없다
CAT_ORDER = ["제원·성능", "주행 성능·섀시", "외장", "내장", "시트", "인포테인먼트", "안전", "주행 보조", "보증·서비스"]


def check_live(brochure, prices):
    """공식 페이지가 바뀌었는지 확인: 브로슈어 주소, 보도자료의 트림별 가격"""
    try:
        h = curl_get(PAGE, cache=False)
        pdfs = set(re.findall(r'https://www\.datocms-assets\.com/[^"\']+?\.pdf', h))
        if pdfs and brochure not in pdfs:
            print("  ! 모델 페이지의 브로슈어가 바뀜:", pdfs, "→ raw/zeekr/brochure_spec.json을 새 브로슈어로 다시 옮겨 적어야 함")
    except Exception as e:
        print("  모델 페이지 확인 실패", e)
    try:
        s = clean(curl_get(NEWS, cache=False))
        news = [int(x.replace(",", "")) * 10000 for x in re.findall(r"▲\s*([\d,]+)\s*만\s*원", s)]
        if news and set(news) != set(prices):  # 본문에 같은 가격 줄이 두 번 나온다
            print("  ! 보도자료 가격과 구성기 가격이 다름:", news, prices)
    except Exception as e:
        print("  보도자료 확인 실패", e)


def photos(d, old):
    keep = {k: old[k] for k in ("image", "media", "imageSource") if old.get(k)}
    imgs = json.loads((RAW / "images.json").read_text(encoding="utf-8"))
    r = None
    for u in imgs["exterior"][:1]:
        try:
            r = cut_from(d, u)
        except Exception as e:
            print("  사진 실패", u, e)
    if not r:
        return keep
    ints = []
    for u in imgs["interior"][:2]:
        try:
            ints.append(save_img(load(u), f"{d['id']}-i{len(ints) + 1}.webp", False, 1600))
        except Exception as e:
            print("  실내 사진 실패", u, e)
    r["media"]["int"] = ints or (old.get("media") or {}).get("int", [])
    return {"image": r["image"], "media": r["media"], "imageSource": r["src"]}


def main():
    conf = json.loads((RAW / "configurator.json").read_text(encoding="utf-8"))
    spec = json.loads((RAW / "brochure_spec.json").read_text(encoding="utf-8"))
    series = conf["salesConfiguration"]["carSeries"][0]
    models = sorted(series["carModels"], key=lambda m: m["modelPrice"])
    check_live(spec["source"], [m["modelPrice"] for m in models])
    care = []  # 모든 트림 기본: 커넥티드 서비스·보증
    for g in series.get("nonVehicleProductGroups") or []:
        for p in g.get("products") or []:
            if p.get("pricingType") == "INCLUDED":
                care.append(p["name"].strip())
    packages, trims = {}, []
    for m in models:
        col = spec["columns"].index(m["modelName"])
        cats = {}
        for row in spec["rows"]:
            v = row["v"][col]
            if v == "●":
                cats.setdefault(row["cat"], []).append(row["n"])
            elif v not in ("○", "—", "-", ""):
                cats.setdefault(row["cat"], []).append(f"{row['n']}: {v}")
        opts, paid = [], set()
        for o in m["vehicleConfigurator"]["options"]:
            for x in o["values"]:
                name = " ".join(x["name"].split())
                if not x.get("price"):  # 0원 = 기본 포함
                    if o["type"] == "hub":
                        cats.setdefault("외장", []).append(name)
                    continue
                paid.add(name)
                if o["type"] in ("Ex_decoration", "Interior"):
                    opts.append({"n": name, "c": x["code"], "p": x["price"], "g": "유료 컬러",
                                 "note": "외장" if o["type"] == "Ex_decoration" else "내장"})
                    continue
                opt = {"n": name, "c": x["code"], "p": x["price"], "g": "선택 옵션"}
                if name == "프리미엄 컴포트 패키지":
                    items = [r["n"] for r in spec["rows"] if r.get("group") == "컴포트 패키지"]
                    packages[x["code"]] = {"desc": name, "items": [{"n": i, "d": "-"} for i in items]}
                opts.append(opt)
        # 브로슈어에서 ○(옵션)인데 구성기에 같은 이름의 유료 품목이 없으면 알린다
        for row in spec["rows"]:
            if row["v"][col] == "○" and row["n"] not in paid and not (row.get("group") and "프리미엄 컴포트 패키지" in paid):
                print(f"  ! {m['modelName']}: 브로슈어 옵션 '{row['n']}'이 구성기 유료 품목에 없음")
        if care:
            cats["보증·서비스"] = care
        cs = [{"cat": c, "items": [{"n": i} for i in dict.fromkeys(cats[c])]}
              for c in sorted(cats, key=lambda c: CAT_ORDER.index(c) if c in CAT_ORDER else 99)]
        trims.append({"name": m["modelName"], "price": m["modelPrice"], "cats": cs, "adds": [], "opts": opts})
    d = {"id": "zeekr-7x", "brand": "zeekr", "name": "7X", "segment": "전기 SUV", "image": "", "imageSource": "",
         "lowPrice": min(t["price"] for t in trims), "priceDate": PRICE_DATE,
         "sources": [CONF, spec["source"], PAGE, NEWS], "structure": "configurator",
         "variants": [{"name": "전기", "code": "zeekr-7x", "trims": trims}],
         "packages": packages,
         "notes": ["지커 코리아 공식 구성기의 차량 가격·선택 품목 가격과 Zeekr 7X 공식 브로슈어(2026년 6월) 사양표의 트림별 사양입니다. 연식 표기는 없습니다.",
                   "구성기 가격은 '차량 소계(GST 포함)', 즉 부가세 포함으로 표시되고 보조금 항목은 없습니다. 개별소비세 등 세제 혜택 반영 여부는 "
                   "공식 자료에 적혀 있지 않습니다. 같은 가격이 지커 코리아 보도자료(2026-10-15)에 '국내 판매 가격'으로 나옵니다.",
                   "구성기 가격에는 기간 한정 프로모션 혜택이 반영되지 않을 수 있습니다(지커 코리아 공지)."]}
    out = DATA / "zeekr"
    out.mkdir(parents=True, exist_ok=True)
    path = out / "7x.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    d.update(photos(d, old))
    if not d.get("media"):
        d["media"] = {"hero": "", "heroType": "cut", "ext": [], "int": []}
    save(path, d)
    print(d["id"], [(t["name"], t["price"], sum(len(c["items"]) for c in t["cats"]), len(t["opts"])) for t in trims],
          d["media"].get("heroType"), len(d["media"].get("int", [])))


if __name__ == "__main__":
    main()
