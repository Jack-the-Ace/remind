"""Build aggregate-only runtime data. Requires openpyxl; never used by the web server."""
import argparse
import hashlib
import json
import math
from tempfile import NamedTemporaryFile
from collections import Counter, defaultdict
from datetime import date
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import openpyxl
from openpyxl.utils.datetime import from_excel

ROOT = Path(__file__).resolve().parents[1]
TITLE = {"activities": "[MA] B1_A. 서울 여행 중 경험한 활동",
         "visits": "[MA] E1. 서울 여행 중 방문 장소_서울 전체 (복수응답)"}
# Only exact variable and label correspondences. Combined neighbourhoods are omitted.
METRICS = {"activities": {
    "shopping": (1, "쇼핑"), "food": (2, "음식/미식"), "history": (3, "고궁/역사 유적지 및 박물관 방문"),
    "art": (14, "문화예술체험(전시관/미술관 방문)"), "performance": (15, "공연관람(연극/영화/뮤지컬 등)"),
    "night": (18, "도시 경관 감상(빌딩/야경/현대 건축물)"), "nature": (19, "자연 경관 감상(강/등산/트레킹 등)")},
    "visits": {"gyeongbok": (1, "경복궁"), "gwangjang": (2, "광장시장"), "sejong": (16, "세종문화회관"),
               "nationalmuseum": (41, "국립중앙박물관"), "olympic": (48, "올림픽공원"),
               "seokchon": (47, "석촌호수"), "botanic": (50, "서울식물원")}}
COUNTRIES = {"일본":"JP", "중국":"CN", "대만":"TW", "홍콩":"HK"}
SOURCE = "https://www.sto.or.kr/survey/16119_/16119"


def require(condition, description):
    if not condition:
        raise ValueError("Source validation failed: " + description)


def read_book(ref):
    return openpyxl.load_workbook(ref, read_only=True, data_only=True)


def integrated_counts(folder):
    candidates = defaultdict(list)
    for path in sorted(folder.rglob("*.xlsx")):
        if path.name.startswith("~$"):
            continue
        book = read_book(path)
        for sheet in ("통합DATA", "Index2"):
            if sheet in book.sheetnames:
                candidates[sheet].append(path)
        book.close()
    require(all(len(candidates[sheet]) == 1 for sheet in ("통합DATA", "Index2")), "one integrated data/table workbook")
    table = candidates["Index2"][0]
    wb = read_book(candidates["통합DATA"][0])
    rows = wb["통합DATA"].iter_rows(values_only=True)
    header = next(rows)
    year_index = header.index("YEAR")
    require(next(rows)[year_index] == "YEAR", "integrated variable-label row")
    counts = Counter()
    partial_ids = set()
    partial_signatures = set()
    id_index = header.index("ID")
    flags = [header.index(f"B1_{n}") for n in (1, 2, 3)]
    for row in rows:
        if row[year_index] is None:
            continue
        year = str(int(row[year_index]))
        counts[year] += 1
        if year == "2025":
            uid = str(row[id_index])
            partial_ids.add(uid)
            partial_signatures.add((uid, tuple(row[i] is not None for i in flags)))
    wb.close()
    wb = read_book(table)
    published = {str(r[1]).rstrip("년"): r[4] for r in wb["Sheet1"].iter_rows(min_row=4, max_row=7, values_only=True)}
    wb.close()
    require(counts == published, "integrated YEAR counts versus published table")
    return {"rowsByYear": dict(sorted(counts.items())), "weightColumnWT": "WT" in header,
            "combinedWithFinal": False}, partial_ids, partial_signatures


def tables(wb):
    sections = {}
    rows = wb["Sheet1"].values
    for row in rows:
        for domain, title in TITLE.items():
            if row[0] == title:
                headers = next(rows)
                units = next(rows)
                total = next(rows)
                require(total[0].replace(" ", "") == "전체" and units[2:4] == ("가중 사례수", "비가중 사례수"), title)
                targets = {"all":total}
                group = None
                for subgroup in rows:
                    if subgroup[0] not in (None, ""):
                        group = subgroup[0]
                    if group == "국적(1)" and subgroup[1] in COUNTRIES:
                        targets[COUNTRIES[subgroup[1]]] = subgroup
                    if len(targets) == len(COUNTRIES) + 1:
                        break
                require(len(targets) == 5, "four published country rows")
                sections[domain] = (headers, targets)
    require(sections.keys() == TITLE.keys(), "published tables")
    return sections


def summarize(archive, integrated):
    with ZipFile(archive) as z:
        books = [read_book(BytesIO(z.read(name))) for name in z.namelist() if name.lower().endswith(".xlsx")]
        coded = [w for w in books if {"데이터_변수", "데이터_변수명"} <= set(w.sheetnames)]
        summary = [w for w in books if {"Index", "Sheet1"} <= set(w.sheetnames)]
        require(len(coded) == len(summary) == 1, "one final data/table workbook")
        published = tables(summary[0])
        summary[0].close()
        data = coded[0]
    rows = data["데이터_변수"].values
    labels, header = next(rows), next(rows)
    labelled = data["데이터_변수명"].values
    require(next(labelled) == labels and next(labelled) == header, "aligned code/label sheet headers")
    require(labels[header.index("WT")] == "가중치" and labels[header.index("SQ8_1")] == "거주국가", "WT/residence")
    def variable(domain, code):
        return ("B1_1_" if domain == "activities" else "E1_") + str(code)
    columns = {}
    for domain, metrics in METRICS.items():
        for key, (code, label) in metrics.items():
            idx = header.index(variable(domain, code))
            require(labels[idx] == ("서울 여행 중 경험한 활동_" if domain == "activities" else "서울 여행 중 방문 장소_") + str(code), key)
            columns[domain, key] = (idx, code)
    counts, weights = Counter(), Counter()
    numerators, weighted = defaultdict(Counter), defaultdict(Counter)
    audit, partial_ids, partial_signatures = integrated
    observed, waves = set(), Counter()
    dates = set()
    matching_ids = matching_signatures = 0
    for row, names in zip(rows, labelled, strict=True):
        uid = row[header.index("UID")]
        require(names[header.index("UID")] == uid, "aligned interview IDs")
        require(uid is not None and uid not in observed, "unique final interview")
        observed.add(uid)
        recorded_date = str(row[header.index("DATE")]).strip()
        try:
            interviewed = date.fromisoformat(recorded_date)
        except ValueError:
            # Some interview dates are exported as text containing Excel serial days.
            interviewed = from_excel(float(recorded_date), epoch=data.epoch).date()
        require(interviewed.year == 2025, "final fieldwork year")
        dates.add(interviewed)
        matching_ids += str(uid) in partial_ids
        flags = tuple(row[header.index(f"B1_1_{n}")] is not None for n in (1, 2, 3))
        matching_signatures += (str(uid), flags) in partial_signatures
        waves[str(row[header.index("PART")])] += 1
        weight = row[header.index("WT")]
        require(isinstance(weight, (int,float)) and math.isfinite(weight) and weight > 0, "positive WT")
        scopes = ["all"]
        country = COUNTRIES.get(names[header.index("SQ8_1")])
        if country:
            scopes.append(country)
        for scope in scopes:
            counts[scope] += 1
            weights[scope] += weight
        for metric, (index, code) in columns.items():
            value = row[index]
            require(value in (None, code), f"checkbox {metric} has unexpected coding")
            if value is not None:
                for scope in scopes:
                    numerators[scope][metric] += 1
                    weighted[scope][metric] += weight
    groups = {}
    for scope in sorted(counts):
        group = {"rawN": counts[scope], "weightedDenominator": round(weights[scope], 6)}
        for domain, metrics in METRICS.items():
            group[domain] = {}
            for key, (code, label) in metrics.items():
                k = domain, key
                rate = weighted[scope][k] / weights[scope]
                names, totals = published[domain]
                row = totals[scope]
                require(row[3] == counts[scope] and math.isclose(row[2], weights[scope], rel_tol=1e-8), "published denominator")
                require(abs(100 * rate - row[names.index(label)]) < 0.00001, "published percent " + label)
                group[domain][key] = {"rawYes":numerators[scope][k], "weightedYes":round(weighted[scope][k],6), "rate":round(rate,8)}
        groups[scope] = group
    audit["overlapCheck"] = {"partialUniqueIds":len(partial_ids), "exactRawIdMatches":matching_ids,
                             "alsoMatchThreeActivityFlags":matching_signatures, "identityCrosswalkVerified":False}
    return {"id":"sto-2025-final-b1-e1-v1", "surveyYear":2025, "source":SOURCE, "publicationDate":"2026-03-03",
            "sourceSha256":hashlib.sha256(archive.read_bytes()).hexdigest(), "scopeVariable":"SQ8_1",
            "weight":"WT", "denominator":"all final interviews in the scope, official multiple-response base",
            "metrics":{d:{k:{"variable":variable(d,i),"label":l} for k,(i,l) in m.items()} for d,m in METRICS.items()},
            "integratedAudit":audit, "finalWaves":dict(sorted(waves.items())),
            "fieldwork":{"first":min(dates).isoformat(), "last":max(dates).isoformat()}, "groups":groups}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("references", type=Path)
    parser.add_argument("official_zip", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "backend/app/data/seoul_survey_2025.json")
    args = parser.parse_args()
    result = summarize(args.official_zip, integrated_counts(args.references))
    with NamedTemporaryFile(dir=args.output.parent, delete=False) as temp:
        staged = Path(temp.name)
    try:
        staged.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        staged.replace(args.output)
    finally:
        staged.unlink(missing_ok=True)
    print("Verified 5 published bases and 70 weighted percentages.", result["integratedAudit"], {k:v["rawN"] for k,v in result["groups"].items()})
