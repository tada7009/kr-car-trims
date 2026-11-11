"""포드 국내 공식 홈페이지 → data/ford/*.json (사진 포함)

- 홈페이지: ford.co.kr에 들어가면 공식 수입원 에프엘오토코리아의 flak.co.kr/ford로 연결된다.
- 가격·트림: 차종 페이지(/ford/vehicle/<차종>)의 '소비자 가격'. 페이지를 스크립트가 그려서 curl로는 빈 껍데기만 오므로,
  내장 브라우저에서 렌더링한 본문 텍스트를 raw/ford/pages.json에 저장해 두고 읽는다(브로슈어 주소도 거기서 찾는다).
- 사양: 브로슈어 다운로드 페이지에 걸린 공식 브로슈어 PDF(mediaflak.co.kr)의 제원·사양표.
  ●/– 표는 글자 좌표로 열을 맞춰 읽고, 제원표는 '이름 값' 쌍으로 읽는다. 문구는 브로슈어 그대로 쓴다.
- 사진: 차종 페이지에 쓰인 공식 이미지(mediaflak.co.kr). 배경 투명 색상 렌더가 있으면 cut, 없으면 사진 여러 장.
  사진 단계가 실패하면 이전 JSON의 사진 정보를 그대로 둔다.

scrape_lincoln.py가 이 파일의 표 읽기·조립 함수를 같이 쓴다.
"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import fitz

import fetch_import_media as M
from common import DATA, curl_get, save, won

RAW = Path(__file__).resolve().parent / "raw"
SITE = "https://flak.co.kr"
MEDIA = "https://mediaflak.co.kr/img/models/"

HOME = {"ford": "ford.co.kr에서 연결되는 공식 수입원 에프엘오토코리아 flak.co.kr/ford",
        "lincoln": "공식 수입원 에프엘오토코리아 flak.co.kr/lincoln"}
MARKS = {"●": True, "○": True, "–": False, "-": False, "—": False}
SECTIONS = {"MECHANICAL": "파워트레인", "EXTERIOR": "외관", "INTERIOR/COMFORT": "내장·편의", "INTERIOR": "내장·편의",
            "SAFETY/SECURITY": "안전", "SAFETY&SECURITY": "안전", "TECHNOLOGY": "주행 보조",
            "DRIVER-ASSISTTECHNOLOGY": "주행 보조", "PACKAGES": "패키지"}
# 하위 항목을 묶기만 하는 제목(따로 사양으로 넣지 않는다)
GROUP_ONLY = {"시트", "1열 시트", "2열 시트", "3열 시트", "에어백", "에어백 및 안전벨트", "Wheel & Tire", "Wheels/Tires",
              "헤드램프", "오디오 및 디스플레이", "변속기", "엔진"}
SKIP_LABELS = {"모델", "트림", "바디 스타일", "구분"}
DIMS = re.compile(r"전장|전폭|전고|휠베이스|탑승인원|연료탱크|공차중량")


# ---------------------------------------------------------------- PDF 표 읽기
def foot_y(page, x0, x1):
    """이 x 범위에 걸친 각주('※…', '본 카탈로그…')가 시작하는 높이. 쪽 아래 머리말·쪽 번호 줄도 잘라낸다."""
    y = page.rect.height - 40
    for r in _rows(page.get_text("words")):
        for a, b, t in phrases(r["w"], 15):
            if is_footer(t) and a < x1 and b > x0:
                y = min(y, r["c"] - 1)
    return y


def _rows(ws):
    ws = sorted(ws, key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    out = []
    for w in ws:
        c = (w[1] + w[3]) / 2
        if out and abs(out[-1]["c"] - c) < 3.5:
            out[-1]["w"].append(w)
        else:
            out.append({"c": c, "w": [w]})
    for r in out:
        r["w"].sort(key=lambda w: w[0])
    return out


def rows(page, x0=0, x1=1e4, cut=True):
    """x 범위 안의 단어를 세로 가운데 기준으로 줄로 묶는다(한글·영문 글꼴의 위치 차이를 흡수). 각주 아래는 버린다."""
    ws = [w for w in page.get_text("words") if x0 <= (w[0] + w[2]) / 2 < x1]
    if cut:
        y = foot_y(page, x0, x1)
        ws = [w for w in ws if (w[1] + w[3]) / 2 < y]
    out = _rows(ws)
    for r in out:
        seen, ws2 = set(), []
        for w in r["w"]:
            k = (round(w[0]), w[4])
            if k not in seen:  # 같은 글자가 두 번 찍힌 PDF가 있다
                seen.add(k)
                ws2.append(w)
        r["w"] = ws2
        r["t"] = " ".join(w[4] for w in ws2)
    return out


def is_footer(t):
    return t.startswith("※") or t.startswith("본 카탈로그")


def find_header(ws, names):
    """줄에 열 이름들이 차례로 있으면 각 이름의 가운데 x 목록"""
    toks = [w[4] for w in ws]
    centers, i = [], 0
    for name in names:
        parts = name.split()
        while i <= len(toks) - len(parts) and toks[i:i + len(parts)] != parts:
            i += 1
        if i > len(toks) - len(parts):
            return None
        centers.append((ws[i][0] + ws[i + len(parts) - 1][2]) / 2)
        i += len(parts)
    return centers


def phrases(ws, gap=12):
    out = []
    for w in ws:
        if out and w[0] - out[-1][1] <= gap:
            out[-1][1] = w[2]
            out[-1][2].append(w[4])
        else:
            out.append([w[0], w[2], [w[4]]])
    return [(a, b, " ".join(t)) for a, b, t in out]


def nearest(cs, x):
    return min(range(len(cs)), key=lambda i: abs(cs[i] - x))


def matrix(page, x0, x1, names, keys, state):
    """●/– 사양표나 열마다 값이 있는 제원표 → 줄 목록 [{x, label, vals{열 키: True/False/값}, sec}]
    names: 머리줄의 열 이름, keys: 머리줄이 나올 때마다 쓸 열 키 목록(마지막 것을 계속 쓴다),
    state['sec']: 표 사이에 이어지는 분류(MECHANICAL → 파워트레인 …)"""
    out, centers, ks, zone, occ = [], None, None, 0, 0
    reg = (id(page), x0)  # 표 칸이 바뀌면 들여쓰기 관계를 잇지 않는다
    for r in rows(page, x0, x1):
        if is_footer(r["t"]):
            break
        sec = SECTIONS.get(re.sub(r"\s+", "", r["t"]))  # 대문자 제목만(익스플로러 'Exterior'는 제원 묶음 이름)
        if sec:
            state["sec"] = sec
            continue
        c = find_header(r["w"], names)
        if c:
            centers, ks = c, keys[min(occ, len(keys) - 1)]
            occ += 1
            half = min((b - a for a, b in zip(c, c[1:])), default=80) / 2
            zone = min(c) - half
            continue
        if centers is None:
            continue
        lab = [w for w in r["w"] if (w[0] + w[2]) / 2 < zone]
        cell = [w for w in r["w"] if (w[0] + w[2]) / 2 >= zone]
        label = " ".join(w[4] for w in lab)
        if label in SKIP_LABELS:
            continue
        vals = {}
        for w in cell:
            if w[4] in MARKS:
                vals[ks[nearest(centers, (w[0] + w[2]) / 2)]] = MARKS[w[4]]
        for a, b, t in phrases([w for w in cell if w[4] not in MARKS]):
            idx = [i for i, cx in enumerate(centers) if a - 8 <= cx <= b + 8] or [nearest(centers, (a + b) / 2)]
            for i in idx:
                old = vals.get(ks[i])
                vals[ks[i]] = f"{old} {t}" if isinstance(old, str) else t
        out.append({"c": r["c"], "x": lab[0][0] if lab else None, "label": label, "vals": vals,
                    "sec": state.get("sec"), "reg": reg})
    return merge_lines(out)


def merge_lines(out):
    """여러 줄에 걸친 이름(●는 가운데 줄에만 있다)과 두 줄로 나뉜 값(예: '3.0L' / 'EcoBoost® V6')을 합친다."""
    res = []
    for r in out:
        prev = res[-1] if res else None
        if prev and not r["label"] and r["vals"]:
            if not prev["vals"] and prev["label"] and r["c"] - prev["c"] <= 7:
                prev["vals"], prev["c2"] = r["vals"], r["c"]  # 이름 첫 줄 + ● 줄
                continue
            if prev["vals"] and r["c"] - prev["c"] <= 9 and all(isinstance(v, str) for v in r["vals"].values()):
                for k, v in r["vals"].items():  # 값의 둘째 줄
                    old = prev["vals"].get(k)
                    prev["vals"][k] = f"{old} {v}" if isinstance(old, str) else v
                continue
        if prev and r["label"] and not r["vals"] and prev["vals"] and prev["x"] is not None and r["x"] is not None \
                and abs(r["x"] - prev["x"]) < 3 and r["c"] - prev.get("c2", prev["c"]) <= 7:
            prev["label"] += " " + r["label"]  # ● 줄 아래에 붙은 이름 둘째 줄
            continue
        res.append(r)
    return res


def trim_items(lines, keys, cat_of=None, warn=""):
    """표 줄 목록 → {열 키: [(분류, 문구)]}. 들여쓴 하위 항목이 있는 제목 줄은 하위 항목이 들어간 트림에만 넣는다."""
    n = len(lines)
    parent = {}
    for i, r in enumerate(lines):
        if r["x"] is None:
            continue
        j = i + 1
        while j < n and lines[j]["x"] is not None and lines[j]["x"] > r["x"] + 4 and lines[j]["sec"] == r["sec"]                 and lines[j]["reg"] == r["reg"]:
            parent[j] = i  # 바깥 제목이 먼저 적히고 안쪽 제목이 덮어써서 가장 가까운 제목이 남는다
            j += 1
    kids = {}
    for j, i in parent.items():
        kids.setdefault(i, []).append(j)

    def text(i):
        r = lines[i]
        if r["label"].startswith("-") and i in parent:
            return f"{lines[parent[i]]['label']} {r['label']}"
        return r["label"]

    got = {k: set() for k in keys}
    out = {k: {} for k in keys}
    for i, r in enumerate(lines):
        for k in keys:
            v = r["vals"].get(k)
            if v is True and r["label"]:
                out[k][i] = text(i)
            elif isinstance(v, str):
                out[k][i] = f"{r['label']} {v}".strip()
            elif not r["vals"] and i not in kids and r["label"]:
                if len(keys) == 1:  # 열이 하나뿐인 표에 실린 항목은 그 트림 사양이다
                    out[k][i] = text(i)
                elif k == keys[0] and warn:
                    print(f"  [{warn}] 표시 없는 줄 건너뜀: {r['label']}")
    for i in sorted(kids, reverse=True):  # 하위 항목이 들어간 트림에만 제목을 넣는다
        lab = lines[i]["label"]
        if lines[i]["vals"] or lab in GROUP_ONLY or any(lines[j]["label"].startswith("-") for j in kids[i]):
            continue
        for k in keys:
            if any(j in out[k] for j in kids[i]):
                out[k][i] = lab
    res = {}
    for k in keys:
        res[k] = [((lines[i]["sec"] or (cat_of or spec_cat)(lines[i]["label"])), out[k][i]) for i in sorted(out[k])]
    return res


def segments(ws, gap=15):
    return phrases(ws, gap)


def sheet(page, x0=0, x1=1e4):
    """한 트림용 제원표 → [(묶음 제목, 이름, 값)]. 이름이 ''이면 문장 그대로(정부 공인 연비), 'WHEEL'이면 휠"""
    out, block, wheel, wc = [], "", None, 0
    for r in rows(page, x0, x1):
        if is_footer(r["t"]):
            break
        segs = segments(r["w"])
        t = " ".join(s[2] for s in segs)
        if re.fullmatch(r"WHEELS?", t):
            wheel = []
            continue
        if wheel is not None:
            if not wheel or r["c"] - wc <= 12:
                wheel.append(t)
                wc = r["c"]
                continue
            out.append(("", "WHEEL", " ".join(wheel)))
            wheel = None
        if len(segs) == 1:
            if ":" in t and re.match(r"(차종명|복합연비|구동방식|등급|복합 CO2)", t):
                for part in re.split(r" (?=(?:등급|복합 CO2 배출량) ?:)", t):
                    out.append((block, "", part))
                continue
            if t.startswith("(") and out and out[-1][1] == "":
                out[-1] = (out[-1][0], "", out[-1][2] + " " + t)
                continue
            block = t
            continue
        for k in range(0, len(segs) - 1, 2):
            lab, val = segs[k][2], segs[k + 1][2]
            if re.search(r"\d", val) and not re.match(r"(Exterior|Capacities|구분)", lab):
                out.append((block, lab, val))
    if wheel:
        out.append(("", "WHEEL", " ".join(wheel)))
    return out


def spec_cat(label):
    return "제원" if DIMS.search(label) else "파워트레인"


def sheet_items(entries):
    """sheet() 결과 → [(분류, 문구)]"""
    res = []
    for _, lab, val in entries:
        if lab == "WHEEL":
            res.append(("외관", val))
        elif not lab:
            res.append(("파워트레인", val))
        else:
            res.append((spec_cat(lab), f"{lab} {val}"))
    return res


def column_texts(page, x0, x1, names):
    """머리줄(열 이름)의 시작 x로 아래 줄들을 열마다 모은다(익스플로러 휠 칸)"""
    rs = rows(page, x0, x1, cut=False)
    for n, r in enumerate(rs):
        if find_header(r["w"], names):
            starts = [w[0] for w in r["w"] if w[4] in names]
            if len(starts) != len(names):
                return {}
            cols, last = {nm: [] for nm in names}, r["c"]
            for r2 in rs[n + 1:]:
                if r2["c"] - last > 15 or is_footer(r2["t"]):
                    break
                last = r2["c"]
                for w in r2["w"]:
                    i = max((k for k, s in enumerate(starts) if s <= w[0] + 2), default=0)
                    cols[names[i]].append(w[4])
            return {k: " ".join(v) for k, v in cols.items()}
    return {}


def to_cats(pairs):
    """[(분류, 문구)] → cats(분류 순서는 처음 나온 순서, 같은 문구는 한 번만)"""
    cats = {}
    for c, t in pairs:
        t = re.sub(r"\s+", " ", t).strip()
        if t and t not in cats.setdefault(c, []):
            cats[c].append(t)
    return [{"cat": c, "items": [{"n": t} for t in v]} for c, v in cats.items() if v]


def brochure(url):
    return fitz.open(stream=curl_get(url, binary=True), filetype="pdf")


def brochure_year(doc):
    for p in doc[:2]:
        m = re.search(r"\b(20\d\d)\b", p.get_text())
        if m:
            return m.group(1)
    return ""


# ---------------------------------------------------------------- 홈페이지(가격·브로슈어 주소)
def load_pages(brand):
    d = json.loads((RAW / brand / "pages.json").read_text(encoding="utf-8"))
    t = datetime.fromisoformat(d["capturedAt"].replace("Z", "+00:00")).astimezone(timezone(timedelta(hours=9)))
    return d["pages"], t.strftime("%Y-%m-%d")


def prices(text, names):
    """차종 페이지 본문 → (맨 위 '소비자 가격 … 원 부터', {트림 이름: 가격})"""
    t = re.sub(r"\s+", " ", text)
    head = re.search(r"소비자 가격 ([\d,]+) 원 부터", t)
    out = {}
    for n in names:
        m = re.search(re.escape(n) + r" 소비자 가격 ?: ?([\d,]+) 원", t)
        out[n] = won(m.group(1)) if m else None
    listed = len(re.findall(r"소비자 가격 ?: ?[\d,]+ 원", t))
    if listed > len([n for n in names if out[n]]):
        print(f"  페이지에 가격 줄이 {listed}개인데 설정한 트림은 {len(names)}개 — 새 트림이 있는지 확인")
    return (won(head.group(1)) if head else None), out


def brochure_url(pages, brand, model):
    for txt, href in pages.get(f"/{brand}/shopping/brochure", {}).get("links", []):
        if txt.upper().startswith(model.upper()) and href.lower().endswith(".pdf"):
            return href
    return None


# ---------------------------------------------------------------- 사진
def media(d, ph):
    r = None
    if ph.get("cut"):
        r = M.cut_from(d, MEDIA + ph["cut"])
    if not r and ph.get("photos"):
        r = M.photo_set(d, [MEDIA + u for u in ph["photos"]])
    if not r:
        return None
    r["media"]["int"] = [M.save(M.load(MEDIA + u), f"{d['id']}-i{i}.webp", False, 1600)
                         for i, u in enumerate(ph.get("int", []), 1)]
    return r


# ---------------------------------------------------------------- 조립
def build(brand, slug, cfg, pages, pdate, brand_ko, no_photo=False):
    """cfg: name, segment, page(차종 페이지 경로), brochure(브로슈어 다운로드 이름), trims[(변형, 페이지 트림 이름, 표시 이름)],
    spec(doc) → {표시 이름: [(분류, 문구)]}, photos, notes(추가 안내)"""
    page = pages[cfg["page"]]
    names = [t[1] for t in cfg["trims"] if t[1]]
    head, by_name = prices(page["text"], names)
    burl = brochure_url(pages, brand, cfg["brochure"])
    doc = brochure(burl) if burl else None
    specs = cfg["spec"](doc) if doc else {}
    year = brochure_year(doc) if doc else ""
    variants, empty = {}, []
    for vname, pname, tname in cfg["trims"]:
        price = by_name.get(pname) if pname else head
        if not price:
            print(f"  {slug}: '{pname or tname}' 가격을 찾지 못함 — 넣지 않음")
            continue
        cats = to_cats(specs.get(tname, []))
        if not cats:
            empty.append(tname)
        variants.setdefault(vname, []).append({"name": tname, "price": price, "cats": cats, "adds": [], "opts": []})
    vs = [{"name": k, "code": slug, "trims": sorted(v, key=lambda t: t["price"])} for k, v in variants.items()]
    low = min(t["price"] for v in vs for t in v["trims"])
    if head and head != low:
        print(f"  {slug}: 맨 위 시작 가격 {head:,}과 최저 트림가 {low:,}가 다름")
    notes = [f"{brand_ko} 국내 공식 홈페이지({HOME[brand]}) 차종 페이지의 "
             f"소비자 가격(부가세 포함, 개별소비세 인하 반영, '원부터' 시작 가격)과 공식 브로슈어"
             f"{f'({year}년형)' if year else ''}의 제원·사양입니다."]
    notes += cfg.get("notes", [])
    if empty:
        notes.append("사양이 비어 있는 트림(" + ", ".join(empty) + ")은 공식 브로슈어에서 사양을 찾지 못해 가격만 실었습니다.")
    d = {"id": f"{brand}-{slug}", "brand": brand, "name": cfg["name"], "segment": cfg["segment"], "image": "",
         "imageSource": "", "lowPrice": low, "priceDate": pdate,
         "sources": [SITE + cfg["page"]] + ([burl] if burl else []), "structure": "web",
         "variants": vs, "media": {"hero": "", "heroType": "photo", "ext": [], "int": []}, "notes": notes}
    path = DATA / brand / f"{slug}.json"
    old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    r = None
    if not no_photo:
        try:
            r = media(d, cfg["photos"])
        except Exception as e:
            print(f"  {slug}: 사진 오류 {e}")
    if r:
        d["image"], d["media"], d["imageSource"] = r["image"], r["media"], r["src"]
    elif old.get("image"):  # 사진을 못 받아도 이전 사진 정보는 지킨다
        d["image"], d["media"], d["imageSource"] = old["image"], old.get("media", d["media"]), old.get("imageSource", "")
    save(path, d)
    print(d["id"], d["segment"], [(v["name"], [(t["name"], t["price"], sum(len(c["items"]) for c in t["cats"]))
                                               for t in v["trims"]]) for v in vs],
          d["media"]["heroType"] if d["image"] else "사진 없음", f"실내 {len(d['media']['int'])}장")
    return d


# ---------------------------------------------------------------- 포드 차종
def explorer_spec(doc):
    p = doc[8]  # 제원·엔진·연비 표(트림 3열) + 휠
    keys = ["Tremor", "ST-Line", "Platinum"]
    res = trim_items(matrix(p, 560, 1e4, ["Tremor", "ST- Line", "Platinum"], [keys], {}), keys, warn="explorer")
    wheels = column_texts(p, 0, 560, keys)
    for k in keys:
        res[k] = res[k] + ([("외관", wheels[k])] if wheels.get(k) else [])
    return res


def expedition_spec(doc):
    return {"Platinum": sheet_items(sheet(doc[8], 580))}


def bronco_spec(doc):
    st = {}
    lines = []
    for a, b in ((0, 290), (290, 553), (553, 1e4)):  # 한 쪽에 표가 세 칸
        lines += matrix(doc[37], a, b, ["Outer Banks"], [["Outer Banks"]], st)
    items = trim_items(lines, ["Outer Banks"], warn="bronco")["Outer Banks"]
    return {"Outer Banks": sheet_items(sheet(doc[36], 570)) + items}


MUSTANG = ["Ecoboost Premium Coupe", "Ecoboost Premium Convertible", "GT Premium Coupe Standard",
           "GT Premium Convertible Standard"]


def mustang_spec(doc):
    eb, gt = MUSTANG[:2], MUSTANG[2:]
    res = {k: [] for k in MUSTANG}
    for block, lab, val in sheet(doc[14], 420):  # 제원·엔진(엔진은 묶음 제목으로 나눈다)
        targets = eb if "2.3L" in block else gt if "5.0L" in block else MUSTANG
        for k in targets:
            res[k] += sheet_items([(block, lab, val)])
    fuel = trim_items(matrix(doc[15], 420, 1e4, ["Coupe", "Convertible"], [eb, gt], {}), MUSTANG, warn="mustang 연비")
    st, lines = {}, []
    for pn in (16, 17):
        for a, b in ((0, 420), (420, 1e4)):
            lines += matrix(doc[pn], a, b, ["Coupe", "Convertible", "Coupe", "Convertible"], [MUSTANG], st)
    feats = trim_items(lines, MUSTANG, warn="mustang")
    for k in MUSTANG:
        res[k] += fuel[k] + feats[k]
    return res


FORD = {
    "explorer": {
        "name": "Explorer", "segment": "SUV", "page": "/ford/vehicle/explorer", "brochure": "EXPLORER",
        "trims": [("가솔린", "ST-Line", "ST-Line"), ("가솔린", "Platinum", "Platinum"), ("가솔린", "Tremor", "Tremor")],
        "spec": explorer_spec,
        "photos": {"cut": "explorer/exp_st_vapor_blue.png",
                   "int": ["explorer/2026/gallery21.jpg", "explorer/2026/gallery22.jpg"]},
    },
    "expedition": {
        "name": "Expedition", "segment": "SUV", "page": "/ford/vehicle/expedition", "brochure": "EXPEDITION",
        "trims": [("가솔린", None, "Platinum")],
        "spec": expedition_spec,
        "photos": {"cut": "expedition/2026/img--ex2.png",
                   "int": ["expedition/2026/img--in1.jpg", "expedition/2026/img--in2.jpg"]},
        "notes": ["공식 브로슈어의 편의·안전 사양은 사진으로만 실려 있어, 글자로 확인되는 제원·엔진·연비·휠만 넣었습니다."],
    },
    "bronco": {
        "name": "Bronco", "segment": "SUV", "page": "/ford/vehicle/bronco", "brochure": "BRONCO",
        "trims": [("가솔린", None, "Outer Banks")],
        "spec": bronco_spec,
        "photos": {"photos": ["bronco/gallery_1_1.avif", "bronco/brc_banner01.jpg", "bronco/gallery_1_5.avif"],
                   "int": ["bronco/gallery_2_3.avif", "bronco/gallery_2_7.jpg"]},
    },
    "mustang": {
        "name": "Mustang", "segment": "쿠페", "page": "/ford/vehicle/mustang", "brochure": "MUSTANG",
        "trims": [("쿠페", MUSTANG[0], MUSTANG[0]), ("쿠페", MUSTANG[2], MUSTANG[2]),
                  ("컨버터블", MUSTANG[1], MUSTANG[1]), ("컨버터블", MUSTANG[3], MUSTANG[3])],
        "spec": mustang_spec,
        "photos": {"photos": ["mustang/gallery_1_2.avif", "mustang/gallery_1_1.avif", "mustang/visual-01.jpg"],
                   "int": ["mustang/gallery_2_5.webp", "mustang/gallery_2_1.avif"]},
    },
}


def main(only=None, no_photo=False):
    pages, pdate = load_pages("ford")
    for slug, cfg in FORD.items():
        if only and slug not in only:
            continue
        build("ford", slug, cfg, pages, pdate, "포드", no_photo)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    main(set(args) or None, "--no-photo" in sys.argv)
