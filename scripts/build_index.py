"""data/<brand>/*.json → data/index.json(차종 목록), data/search.json(사양 검색어)"""
import json
from datetime import date

from common import DATA, save

BRANDS = ["hyundai", "kia", "genesis", "kgm", "renault", "chevrolet"]


def main():
    models, search = [], {}
    for b in BRANDS:
        for f in sorted((DATA / b).glob("*.json")) if (DATA / b).exists() else []:
            d = json.loads(f.read_text(encoding="utf-8"))
            prices = [t["price"] for v in d["variants"] for t in v["trims"] if t.get("price")]
            if not prices:
                continue
            models.append({
                "id": d["id"], "brand": b, "name": d["name"], "segment": d["segment"],
                "image": d.get("image", ""), "low": min(prices), "high": max(prices),
                "fuels": list(dict.fromkeys(v["name"] for v in d["variants"])),
                "trims": sum(len(v["trims"]) for v in d["variants"]),
                "date": d.get("priceDate", ""), "file": f"{b}/{f.name}",
            })
            names = set()
            for v in d["variants"]:
                for t in v["trims"]:
                    for c in t["cats"]:
                        names.update(i["n"] for i in c["items"])
                    names.update(o["n"] for o in t["opts"])
            for p in d.get("packages", {}).values():
                names.update(i["n"] for i in p.get("items", []))
            search[d["id"]] = "|".join(sorted(names)).lower()
    save(DATA / "index.json", {"updated": date.today().isoformat(), "models": models})
    save(DATA / "search.json", search)
    print(f"{len(models)} models")


if __name__ == "__main__":
    main()
