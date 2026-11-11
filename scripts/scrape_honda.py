"""혼다코리아 공식 사이트(auto.hondakorea.co.kr) → data/honda/*.json

- 차종: 온라인 견적 페이지(/purchase/estimate)에 걸린 판매 차종(주석 처리된 단종 차종은 뺀다)
- 트림·가격: 트림 선택(/purchase/selectTrim) → 옵션 선택(/purchase/selectOption) 화면의 TOTAL 가격(VAT 포함, 개소세 5% 적용)
  모델 페이지 '상세제원' 표의 가격과 같은지도 확인한다. 유료 선택 옵션은 없고 색상만 고른다.
- 사양: 모델 페이지(/model/<slug>)의 '상세제원' 표(트림별 열)와 '기본 사양' 목록
- 사진: 견적 페이지 차종 목록의 배경 투명 렌더(cut) + 모델 페이지의 실내 사진
  사진을 못 받으면 이전 실행에서 채운 image·media·imageSource를 그대로 둔다.
"""
import html as H
import json
import re
import sys
import urllib.parse
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DATA, curl_get, save, won  # noqa: E402
from fetch_import_media import cut_from, load  # noqa: E402
from fetch_import_media import save as save_img  # noqa: E402

BASE = "https://auto.hondakorea.co.kr"
OUT = DATA / "honda"
RAW = Path(__file__).resolve().parent / "raw" / "honda"
# 모델 페이지 slug → (파일 slug, segment)
MODELS = {
    "accord_hev": ("accord", "세단"),
    "crv_hev": ("cr-v", "SUV"),
    "odyssey": ("odyssey", "MPV"),
    "pilot": ("pilot", "SUV"),
}
# 모델 페이지에 걸린 공식 실내 사진(대시보드, 실내 공간 순)
INTERIOR = {
    "accord_hev": ["/static/images/model/accordHev/int01.jpg", "/static/images/model/accordHev/int02.jpg"],
    "crv_hev": ["/static/images/model/2026CRV-Hybrid/crv-hev-convenience.jpg",
                "/static/images/model/2026CRV-Hybrid/crv-hev-space.jpg"],
    "odyssey": ["/static/images/model/2025Odyssey/odss_int_02.jpg", "/static/images/model/2025Odyssey/odss_spa.jpg"],
    "pilot": ["/static/images/model/pilotbe/be-int01.jpg", "/static/images/model/pilotbe/be-int03-p1.jpg"],
}
CAT_ORDER = ["파워트레인", "제원", "섀시", "성능", "외관", "내장", "주행 보조(혼다 센싱)", "안전"]


def get(path):
    return curl_get(BASE + path, cache=False)


def live(h):
    """주석(<!-- -->) 안의 단종 차종·옛 문구를 뺀 HTML"""
    return re.sub(r"<!--.*?-->", "", h, flags=re.S)


def text(s):
    s = re.sub(r"<br\s*/?>", " ", s)
    return " ".join(H.unescape(re.sub(r"<[^>]+>", " ", s)).replace("\xa0", " ").split())


def url(path):
    return BASE + urllib.parse.quote(path)


# ---------- 견적 페이지: 판매 차종·트림·가격 ----------

def cars():
    h = live(get("/purchase/estimate"))
    out = [json.loads(H.unescape(m)) for m in re.findall(r"checkCnt\((\{[^{}]*\})\)", h)]
    pages = {text(n): s for s, n in re.findall(r'<a href="/model/([a-z_]+)">([^<]+)</a>', h)}
    return out, pages


def option_page(h):
    """옵션 선택 화면 → (제목, 가격, 가격 기준 문구, 차량 사진 경로)"""
    title = text(re.search(r'<h2 class="subTitle">(.*?)</h2>', h, re.S).group(1))
    m = re.search(r'class="total__price"><em>([\d,]+)</em>원\s*<span class="total__vat">\s*\(([^)]*)\)', h)
    img = re.search(r'id="carShowImg"><img src="([^"]+)"', h)
    return title, won(m.group(1)), " ".join(m.group(2).split()), img.group(1) if img else ""


def trims(car):
    q = urllib.parse.urlencode({"carCd": car["carCd"], "carNm": car["carNm"], "carSeq": car["carSeq"], "year": car["year"]})
    h = live(get(f"/purchase/selectTrim?{q}"))
    links = list(dict.fromkeys(H.unescape(x) for x in re.findall(r'href="(/purchase/selectOption\?[^"]+)"', h)))
    if "purModelListTb" not in h:  # 트림이 하나면 곧바로 옵션 선택 화면으로 넘어간다
        links = ["/purchase/selectOption?" + urllib.parse.urlencode(
            {"carSeq": car["carSeq"], "csnTrim": car["csnTrim"], "carCd": car["carCd"], "year": car["year"]})]
        pages = [h]
    else:
        pages = [live(get(u.replace(" ", "+"))) for u in links]
    out = []
    for u, p in zip(links, pages):
        title, price, basis, img = option_page(p)
        trim = urllib.parse.parse_qs(urllib.parse.urlparse(u).query)["csnTrim"][0]
        out.append({"trim": trim, "title": title, "price": price, "basis": basis, "img": img,
                    "src": BASE + u.replace(" ", "+")})
    return out


# ---------- 모델 페이지: 제원 표·기본 사양 ----------

def grid(tbl):
    """표 → 행마다 {열 번호: (태그, 글자)} (rowspan·colspan 펼침)"""
    rows, pend = [], {}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", tbl, re.S):
        row = {}
        for c in list(pend):
            row[c] = pend[c][0]
            pend[c][1] -= 1
            if pend[c][1] == 0:
                del pend[c]
        col = 0
        for tag, attrs, inner in re.findall(r"<(th|td)([^>]*)>(.*?)</\1>", tr, re.S):
            while col in row:
                col += 1
            cs = int((re.search(r'colspan="(\d+)"', attrs) or [0, 1])[1])
            rs = int((re.search(r'rowspan="(\d+)"', attrs) or [0, 1])[1])
            for k in range(cs):
                row[col + k] = (tag, text(inner))
                if rs > 1:
                    pend[col + k] = [(tag, text(inner)), rs - 1]
            col += cs
        rows.append(row)
    return rows


def spec_table(h):
    """'상세제원' 표 → (열 이름 목록, [(분류, [열마다 문구])])"""
    i = h.find("주요제원")
    tbl = h[h.rfind("<table", 0, i): h.find("</table>", i)]
    head = re.search(r"<thead>(.*?)</thead>", tbl, re.S).group(1)
    ths = re.findall(r"<th([^>]*)>(.*?)</th>", head, re.S)
    nlab = int((re.search(r'colspan="(\d+)"', ths[0][0]) or [0, 1])[1])
    cols = [text(x) for _, x in ths[1:]]
    body = tbl[tbl.find("</thead>"):]
    out = []
    for row in grid(body):
        if not row or row.get(0, ("td", ""))[0] != "th":
            continue  # 가격 줄(td 하나로 합친 칸) 등
        labels = []
        for c in range(nlab):
            t = row.get(c, ("", ""))[1]
            if t and (not labels or labels[-1] != t):
                labels.append(t)
        vals = [row.get(nlab + k, ("", ""))[1] for k in range(len(cols))]
        if not labels or any("가격" in x for x in labels) or not any(vals):
            continue
        grp = labels[0] if len(labels) > 1 else ""
        name = " ".join(labels[1:] if grp else labels)
        if grp in ("엔진", "모터") and re.match(r"최고|최대", name):
            name = f"{grp} {name}"
        elif grp and ("연비" in grp):
            name = f"{grp} {name}"
        if grp == "치수" or name.startswith("승차정원"):
            cat = "제원"
        elif grp in ("엔진", "모터", "변속기") or "연비" in name or "CO2" in name:
            cat = "파워트레인"
        elif grp in ("섀시", "새시") or name.startswith("타이어"):
            cat = "섀시"
        else:
            cat = "제원"
        out.append((cat, [f"{name}: {v}" if v else "" for v in vals]))
    return cols, out


def fuel_grades(h):
    """'정부 공인 표준연비 및 등급' 표의 등급(차종 줄 순서)"""
    j = h.find("타이어 에너지 소비효율 등급")
    seg = h[h.rfind("정부 공인 표준연비", 0, j): j]
    return re.findall(r">\s*(\d)등급\s*<", seg)


def cat_name(head):
    u = head.upper()
    if "SENSING" in u or "센싱" in head:
        return "주행 보조(혼다 센싱)"
    if "PERFORMANCE" in u or "퍼포먼스" in head or "성능" in head:
        return "성능"
    if "EXTERIOR" in u or "익스테리어" in head or "외장" in head:
        return "외관"
    if "INTERIOR" in u or "인테리어" in head or "내장" in head:
        return "내장"
    if "SAFETY" in u or "안전" in head:
        return "안전"
    return head


def basic_specs(h):
    """'기본 사양' 목록 → [(분류, 문구, 해당 트림 이름 또는 None)]"""
    m = re.search(r"<h4[^>]*>\s*기본 사양\s*</h4>", h)
    seg = h[m.end():]
    ends = [k for k in (seg.find("혼다코리아의 모든 콘텐츠"), seg.find("<footer")) if k > 0]
    seg = seg[: min(ends)] if ends else seg
    out, cat = [], None
    for t in re.finditer(r'<h5 class="tit">(.*?)</h5>|<div class="stc__div">\s*<p>(.*?)</p>|<li>(.*?)</li>', seg, re.S):
        if t.group(1) or t.group(2):
            cat = cat_name(text(t.group(1) or t.group(2)))
            continue
        s = text(t.group(3)).lstrip("·").strip()
        only = re.search(r"\(\s*(\w+)\s*만 해당\s*\)", s)
        if only:
            s = (s[: only.start()] + s[only.end():]).strip()
        if cat and s:
            out.append((cat, s, only.group(1) if only else None))
    return out


def pick_col(cols, trim, k):
    if len(cols) == 1:
        return 0
    for i, c in enumerate(cols):
        if trim.upper() in c.upper().replace(" ", ""):
            return i
    return min(k, len(cols) - 1)


# ---------- 사진 ----------

def photos(d, car_img, slug, page):
    """배경 투명 렌더(cut) + 실내 사진. 실패하면 None"""
    r = None
    for p in car_img:
        if not p:
            continue
        try:
            r = cut_from(d, url(p))
        except Exception as e:
            print(d["id"], "사진 오류", p, e)
        if r:
            break
    if not r:
        return None
    inn = []
    for p in INTERIOR.get(slug, []):
        if p not in page:  # 모델 페이지에서 내려간 사진은 쓰지 않는다
            continue
        try:
            inn.append(save_img(load(url(p)), f"{d['id']}-i{len(inn) + 1}.webp", False, 1600))
        except Exception as e:
            print(d["id"], "실내 사진 오류", p, e)
    r["media"]["int"] = inn[:2]
    return r


# ---------- 조립 ----------

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    lst, pages = cars()
    ending = "신차 판매 사업 종료" in get("/main/")
    done = []
    for car in lst:
        slug = pages.get(car["carNm"])
        if not slug:
            print("모델 페이지 없음", car["carNm"])
            continue
        key, segment = MODELS.get(slug, (slug.replace("_hev", ""), "SUV"))
        page = live(get(f"/model/{slug}"))
        (RAW / f"{slug}.html").write_text(page, encoding="utf-8")
        cols, table = spec_table(page)
        grades = fuel_grades(page)
        basic = basic_specs(page)
        tl = trims(car)
        hybrid = any("모터 최고출력" in x for _, vs in table for x in vs if x)
        page_prices = {won(x) for x in re.findall(r"(\d{2,3},\d{3},\d{3})", page[page.find("주요제원"):page.find("정부 공인 표준연비", page.find("주요제원"))])}
        out_trims = []
        for k, t in enumerate(tl):
            if t["price"] not in page_prices:
                print("확인 필요: 모델 페이지 가격과 다름", car["carNm"], t["trim"], t["price"], page_prices)
            ci = pick_col(cols, t["trim"], k)
            cats = {}
            for cat, vs in table:
                if vs[ci]:
                    cats.setdefault(cat, []).append(vs[ci])
            if grades:
                g = grades[ci] if len(grades) == len(cols) else grades[0]
                cats.setdefault("파워트레인", []).append(f"정부 공인 표준연비 등급: {g}등급")
            for cat, s, only in basic:
                if only and only.upper() not in t["trim"].upper():
                    continue
                lst_ = cats.setdefault(cat, [])
                if s not in lst_:
                    lst_.append(s)
            order = sorted(cats, key=lambda c: CAT_ORDER.index(c) if c in CAT_ORDER else len(CAT_ORDER))
            out_trims.append({"name": t["trim"], "price": t["price"],
                              "cats": [{"cat": c, "items": [{"n": x} for x in cats[c]]} for c in order],
                              "adds": [], "opts": []})
        if not out_trims:
            print("트림 없음", car["carNm"])
            continue
        fuel = "하이브리드" if hybrid else "가솔린"
        year = car.get("year")
        basis = tl[0]["basis"] or "VAT포함, 개소세 5% 적용시"
        notes = [f"혼다코리아 공식 사이트 온라인 견적 화면의 {year}년형 가격({basis})과 모델 페이지 '상세제원 및 사양'의 "
                 f"제원·기본 사양입니다. 가격표 날짜가 따로 없어 수집일 기준이며, 유료 선택 옵션 없이 색상만 고릅니다."]
        if ending:
            notes.append("혼다코리아는 2026년 4월 29일 공지에서 자동차 신차 수입·판매 사업을 2026년 12월 말까지 운영하고 "
                         "종료한다고 밝혔습니다(모델별 재고에 따라 더 일찍 끝날 수 있음).")
        d = {"id": f"honda-{key}", "brand": "honda", "name": car["carNm"], "segment": segment,
             "image": "", "imageSource": "",
             "lowPrice": min(t["price"] for t in out_trims), "priceDate": date.today().isoformat(),
             "sources": [BASE + f"/model/{slug}"] + [t["src"] for t in tl], "structure": "web",
             "variants": [{"name": fuel, "code": slug, "trims": out_trims}],
             "media": {"hero": "", "heroType": "cut", "ext": [], "int": []}, "notes": notes}
        path = OUT / f"{key}.json"
        old = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        r = photos(d, [car.get("carImg"), tl[0]["img"]], slug, page)
        if r:
            d["image"], d["media"], d["imageSource"] = r["image"], r["media"], r["src"]
        elif old.get("image"):  # 사진을 못 받으면 이전 값을 지킨다
            d["image"], d["media"], d["imageSource"] = old["image"], old.get("media", d["media"]), old.get("imageSource", "")
            print(d["id"], "사진 유지(이전 값)")
        else:
            print(d["id"], "NO IMAGE")
        save(path, d)
        done.append(path.name)
        print(d["id"], d["name"], segment, fuel, [(t["name"], t["price"], sum(len(c["items"]) for c in t["cats"])) for t in out_trims],
              d["media"]["heroType"], len(d["media"]["int"]))
    for f in OUT.glob("*.json"):  # 견적 페이지에서 내려간 차종 파일은 지운다
        if f.name not in done and done:
            print("판매 목록에 없어 삭제", f.name)
            f.unlink()


if __name__ == "__main__":
    main()
