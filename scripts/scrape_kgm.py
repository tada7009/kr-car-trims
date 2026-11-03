"""KG모빌리티 공식 간편견적 API → data/kgm/*.json

트림·구동별 가격, 트림별 기본품목(상위 트림은 '하위 트림 기본 품목 외' 추가분), 선택 품목·가격과
패키지 구성, 커스터마이징 품목, 유료 외장 컬러를 읽는다.
"""
import re
import sys
from datetime import date

from common import DATA, clean, fetch_json, save, short

API = "https://web.kg-mobility.com/app/estimate"
HDR = {"Referer": "https://www.kg-mobility.com/", "Origin": "https://www.kg-mobility.com"}

# (id, 표시명, 차급, [(견적 카테고리 번호, 연료 표시)])
MODELS = [
    ("tivoli", "티볼리", "소형 SUV", [("200000200010006", "")]),
    ("actyon", "액티언", "중형 SUV", [("200000200010003", ""), ("200000200010014", "하이브리드")]),
    ("torres", "토레스", "중형 SUV", [("200000200010008", ""), ("200000200010013", "하이브리드")]),
    ("torres-evx", "토레스 EVX", "중형 SUV", [("200000200010001", "")]),
    ("rexton", "렉스턴 뉴 아레나", "대형 SUV", [("200000200010005", "")]),
    ("musso", "무쏘", "픽업", [("200000200010009", "")]),
    ("musso-ev", "무쏘 EV", "픽업", [("200000200010012", "")]),
]

CATS = [("pwElcTxt", "파워트레인"), ("extrrSpecTxt", "외관"), ("builtSpecTxt", "내장"), ("cnvnSpecTxt", "편의"),
        ("sftSpecTxt", "안전"), ("multiMediaTxt", "멀티미디어"), ("cstmzngSpecTxt", "커스터마이징")]
# 같은 이름으로 끝나는 두 품목은 상위 트림에서 교체된 것으로 본다(17→18인치 휠, 7→8에어백 등)
REPLACE_TAILS = ["휠", "타이어", "에어백", "가죽시트", "룸미러", "클러스터", "내비게이션", "스피커", "헤드램프",
                 "크루즈 컨트롤", "파워 윈도우", "패키지", "스티어링 휠", "전동시트", "시트"]


def api(path, **q):
    qs = "&".join(f"{k}={v}" for k, v in q.items())
    j = fetch_json(f"{API}/{path}.do?{qs}", HDR)
    return j.get("body") or []


def split_items(s):
    out, depth, cur = [], 0, ""
    for ch in s or "":
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth <= 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return [re.sub(r"\s+", " ", x).strip(" .") for x in out if len(x.strip()) > 1]


def core(n):
    """괄호·대괄호 설명을 뗀 품목 이름 (중첩 괄호가 있어 첫 여는 괄호부터 끝까지 버린다)"""
    return re.sub(r"\s+", " ", re.split(r"[\[(]", n)[0]).strip()


def replaces(old, new):
    a, b = core(old), core(new)
    if re.search(r"\d+\s*에어백", a) and re.search(r"\d+\s*에어백", b):
        return True
    if re.search(r"\d+\s*인치.*(휠|타이어)", a) and re.search(r"\d+\s*인치.*(휠|타이어)", b):
        return True
    for t in REPLACE_TAILS:
        if a.endswith(t) and b.endswith(t):
            if t == "시트":  # 시트는 재질(가죽시트)끼리만 교체
                return bool(re.search(r"가죽 ?시트$", a) and re.search(r"가죽 ?시트$", b))
            if t == "패키지":
                return "멀티미디어" in (old + new) or ("내비게이션" in b or "미러링" in a)
            return True
    return False


SEPARATE = "별도로 구성"  # "티볼리 V5는 V1의 품목과 별도로 구성됩니다" — 누적이 아닌 별도 계열 트림


def cats_of(row):
    out = []
    for key, name in CATS:
        txt = row.get(key) or ""
        txt = re.sub(r"<b>※.*?</b>", "", txt)
        items = split_items(clean(txt))
        if items:
            out.append({"cat": name, "items": [{"n": n, "c": ""} for n in items]})
    return out


def merge(base, add):
    new = [{"cat": c["cat"], "items": list(c["items"])} for c in base]
    for c in add:
        bucket = next((x for x in new if x["cat"] == c["cat"]), None)
        if bucket is None:
            bucket = {"cat": c["cat"], "items": []}
            new.append(bucket)
        for it in c["items"]:
            if any(x["n"] == it["n"] for x in bucket["items"]):
                continue
            bucket["items"] = [x for x in bucket["items"] if not replaces(x["n"], it["n"])]
            bucket["items"].append(it)
    return new


def accumulate(rows):
    """첫 트림은 전체 품목, 이후 트림은 바로 아래 트림 대비 추가분 → 트림마다 (전체, 추가분).
    '별도로 구성' 표기가 있는 트림은 별도 계열의 첫 트림(전체 목록)이거나 그 계열 위에 누적된다."""
    out, full, series, by_name = [], [], None, {}
    for i, r in enumerate(rows):
        add = cats_of(r)
        name = r.get("trimName") or ""
        sep = any(SEPARATE in (r.get(k) or "") for k, _ in CATS)
        # 'M7 그랜드 스타일'처럼 앞 트림 이름에 붙은 에디션은 그 트림에서 갈라지고, 다음 트림 누적에는 끼지 않는다
        parent = next((n for n in reversed(list(by_name)) if name.startswith(n + " ")), None)
        if i == 0:
            cur = add
            out.append((cur, []))
        elif parent:
            cur = merge(by_name[parent], add)
            out.append((cur, add))
        elif sep and series is None:
            cur = series = add
            out.append((cur, []))
        else:
            cur = merge(series if sep else full, add)
            if sep:
                series = cur
            out.append((cur, add))
        by_name[name] = cur
        if not parent:
            full = cur
    return out


def scrape_lineup(m, packages):
    code, ctype = m["modelCd"], m.get("carType") or "M"
    trims = api("getCarModelTrimList", carType=ctype, modelCd=code)
    trims = [t for t in trims if t.get("carSuplAmt") and not re.search(r"투톤|TAXI|택시", t.get("className") or "")]
    # 트림 이름마다 조회해야 그 트림까지의 행이 온다 → trimSeq로 합친다
    rows = {}
    for tn in dict.fromkeys(t["trimName"] for t in trims):
        for b in api("getCarModelTrimBasicItemsList", carType=ctype, modelCd=code, trimName=tn):
            rows.setdefault(b.get("trimSeq") or 0, b)
    basic = [rows[k] for k in sorted(rows)]
    order = [b["trimName"] for b in basic]
    acc = dict(zip(order, accumulate(sorted(basic, key=lambda b: b.get("trimSeq") or 0))))
    groups = {}
    for t in trims:
        oil = {"경유": "디젤"}.get(t.get("oilName") or "", t.get("oilName") or "")
        key = (oil, t.get("driveCd") or "")
        groups.setdefault(key, []).append(t)
    variants = []
    for (oil, drive), ts in groups.items():
        ts.sort(key=lambda t: (order.index(t["trimName"]) if t["trimName"] in order else 99, t["carSuplAmt"]))
        out = []
        for t in ts:
            ext = api("getCarExteriorList", modelCd=code, trimName=t["trimName"])
            ext_cd = ext[0]["exteriorCd"] if ext else ""
            opts = []
            for o in api("getCarOptionList", modelCd=code, carCd=t["carCd"], carType=ctype, exteriorCd=ext_cd):
                oc = f"KGM-{code}-{o['optionCd']}"
                if oc not in packages:
                    det = api("getCarOptionDetailList", modelCd=code, optionCd=o["optionCd"])
                    items = []
                    for d in det:
                        items += split_items(clean(d.get("optionDtlDesc")))
                    packages[oc] = {"desc": "", "items": [{"n": n, "d": ""} for n in dict.fromkeys(items)]}
                opts.append({"n": clean(o.get("optionName")), "c": oc, "p": o.get("optionAmt"), "g": "옵션", "note": ""})
            for c in api("getCarCustomList", modelCd=code, carCd=t["carCd"], carType=ctype):
                if c.get("baseGubun") == "Y":
                    continue
                opts.append({"n": clean(c.get("customOptName")), "c": "", "p": c.get("customOptAmt"), "g": "커스터마이징", "note": ""})
            seen = set()
            for e in ext:
                if e.get("exteriorAmt") and e["exteriorName"] not in seen:
                    seen.add(e["exteriorName"])
                    opts.append({"n": clean(e["exteriorName"]), "c": "", "p": e["exteriorAmt"], "g": "유료 컬러", "note": "외장"})
            full, add = acc.get(t["trimName"], ([], []))
            out.append({"name": t.get("homepageTrimNm") or t["trimName"], "en": "", "price": t["carSuplAmt"],
                        "cats": full, "adds": add, "opts": opts})
        variants.append({"name": " · ".join(x for x in (oil, drive) if x), "code": code, "trims": out, "notes": []})
    return variants


def scrape_model(mid, name, segment, cats, packages):
    variants, img, srcs = [], "", []
    for cat_no, fuel in cats:
        lineups = api("getCarModelList", carType="", modelCd="", categoryNo=cat_no)
        for m in lineups:
            vs = scrape_lineup(m, packages)
            label = m["modelName"].replace(name, "").strip().strip("()")
            for v in vs:
                bits = [b for b in (label if label != fuel else "", v["name"]) if b]
                v["name"] = " · ".join(bits) or name
            variants += vs
            img = img or m.get("modelImgAddr") or ""
        srcs.append(f"https://www.kg-mobility.com/od/estimate/line-up/{cat_no}")
    return variants, img, srcs


def main(only=None):
    stamp = "{0.year}년 {0.month}월 {0.day}일 KGM 간편견적 조회".format(date.today())
    for mid, name, seg, cats in MODELS:
        if only and mid not in only:
            continue
        packages = {}
        try:
            variants, img, srcs = scrape_model(mid, name, seg, cats, packages)
        except Exception as e:
            print("FAIL", mid, repr(e))
            continue
        variants = [v for v in variants if v["trims"]]
        if not variants:
            print("EMPTY", mid)
            continue
        prices = [t["price"] for v in variants for t in v["trims"]]
        d = {"id": "kgm-" + mid, "brand": "kgm", "name": name, "segment": seg, "image": img,
             "lowPrice": min(prices), "priceDate": stamp, "sources": srcs, "variants": variants,
             "packages": {k: v for k, v in packages.items() if v["items"]}}
        save(DATA / "kgm" / f"{mid}.json", d)
        print(f"OK {mid}: " + " / ".join(f"{v['name']}({len(v['trims'])})" for v in variants) + f", {len(d['packages'])} pkgs")


if __name__ == "__main__":
    main(set(sys.argv[1:]) or None)
