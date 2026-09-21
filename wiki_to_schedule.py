#!/usr/bin/env python3
"""
Build schedule.json from the Wuthering Waves Wiki (Fandom) MediaWiki API.

  python wiki_to_schedule.py --out schedule.json

Extracts FACTS ONLY (dates, names, element, weapon type, rarity, image file names)
from template parameters -- never prose. Wiki text is CC BY-SA 3.0; the generated file credits
the wiki in its `notice` field.

Sections filled: versions, banners (with wiki artwork), releaseHistory, shop
(outfits), events, and patchNotes -- one note per version whose entries are written
from the banner data rather than copied from the wiki.
Left empty on purpose: devNotes and maintenance. The wiki has no structured source
for those, and an empty tab is honest where invented entries would not be.

Wiki times are Asia server time (UTC+8), as the wiki's own compensation notes state.
They are emitted with an explicit +08:00 offset so the app reads exact instants.
"""
import argparse, json, os, re, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone, timedelta

API = "https://wutheringwaves.fandom.com/api.php"
UA = "tide-tracker-schedule-builder/1.0 (+https://github.com/ethanxiang6/WuWa-Tracker)"
BATCH = 50

ELEMENTS = {"aero", "glacio", "fusion", "electro", "havoc", "spectro"}
WEAPONS = {"sword", "broadblade", "pistols", "gauntlets", "rectifier"}


def api(**params):
    params.setdefault("format", "json")
    params.setdefault("formatversion", "2")
    url = API + "?" + urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            if attempt == 3:
                raise
            time.sleep(1.5 * (attempt + 1))


def category(name):
    """Every page title in a category, following continuation."""
    out, cont = [], {}
    while True:
        d = api(action="query", list="categorymembers", cmtitle="Category:" + name,
                cmlimit="500", **cont)
        out += [m["title"] for m in d.get("query", {}).get("categorymembers", [])]
        if "continue" not in d:
            return out
        cont = d["continue"]


def allpages(prefix):
    out, cont = [], {}
    while True:
        d = api(action="query", list="allpages", apprefix=prefix, aplimit="500", **cont)
        out += [p["title"] for p in d.get("query", {}).get("allpages", [])]
        if "continue" not in d:
            return out
        cont = d["continue"]


def wikitext(titles):
    """{title: wikitext} for many titles, batched."""
    out = {}
    for i in range(0, len(titles), BATCH):
        chunk = titles[i:i + BATCH]
        d = api(action="query", prop="revisions", rvprop="content", rvslots="main",
                titles="|".join(chunk))
        for page in d.get("query", {}).get("pages", []):
            revs = page.get("revisions")
            if revs:
                out[page["title"]] = revs[0]["slots"]["main"]["content"]
    return out


def file_urls(names, width=640):
    """{file name: CDN url} for wiki File: pages, asking the CDN for a card-sized copy."""
    names = sorted({n for n in names if n})
    out = {}
    for i in range(0, len(names), BATCH):
        chunk = names[i:i + BATCH]
        d = api(action="query", prop="imageinfo", iiprop="url",
                titles="|".join("File:" + n for n in chunk))
        for page in d.get("query", {}).get("pages", []):
            info = page.get("imageinfo")
            if not info:
                continue
            title = page["title"].split(":", 1)[1]
            base, sep, query = info[0]["url"].partition("?")
            if base.endswith("/revision/latest"):
                base += "/scale-to-width-down/%d" % width
            # Match on both spellings: the API normalises underscores to spaces.
            out[title] = out[title.replace(" ", "_")] = base + sep + query
    return out


# ---------------------------------------------------------------- wikitext parsing

def strip_comments(s):
    return re.sub(r"<!--.*?-->", "", s, flags=re.S)


def find_template(text, name):
    """Body of the first {{name ...}} call, brace-balanced. None if absent."""
    m = re.search(r"\{\{\s*" + re.escape(name) + r"\s*[|}]", text)
    if not m:
        return None
    i, depth = m.start(), 0
    while i < len(text):
        if text.startswith("{{", i):
            depth += 1
            i += 2
        elif text.startswith("}}", i):
            depth -= 1
            i += 2
            if depth == 0:
                return text[m.start() + 2:i - 2]
        else:
            i += 1
    return None


def params(body):
    """Top-level |key = value pairs, ignoring nested templates and links."""
    if body is None:
        return {}
    out, depth, cur, parts = {}, 0, [], []
    for idx, ch in enumerate(body):
        two = body[idx:idx + 2]
        if two in ("{{", "[["):
            depth += 1
        elif two in ("}}", "]]"):
            depth -= 1
        if ch == "|" and depth <= 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    for p in parts[1:]:                       # parts[0] is the template name
        if "=" not in p:
            continue
        k, v = p.split("=", 1)
        out[k.strip().lower()] = strip_comments(v).strip()
    return out


def clean(v):
    """Drop wiki link syntax and bold markers from a value."""
    if not v:
        return ""
    v = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", v)
    v = re.sub(r"\[\[([^\]]+)\]\]", r"\1", v)
    return v.replace("'''", "").strip()


def moment(v):
    """'2026-09-10 10:00' -> ISO with +08:00. '2026-09-10' -> plain date. Else None."""
    v = clean(v)
    if not v:
        return None
    m = re.match(r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}):(\d{2})", v)
    if m:
        return "%sT%s:%s:00+08:00" % (m.group(1), m.group(2), m.group(3))
    m = re.match(r"^(\d{4}-\d{2}-\d{2})$", v)
    return m.group(1) if m else None


def day(iso):
    """Calendar day (server time) of an emitted moment string."""
    return iso[:10] if iso else None


def semis(v):
    return [clean(x) for x in (v or "").split(";") if clean(x)]


def slug(*parts):
    s = "-".join(str(p) for p in parts if p).lower()
    return re.sub(r"[^a-z0-9.]+", "-", s).strip("-")


def ensure_unique_ids(rows, label):
    """The app de-duplicates by id when it builds its snapshot, so a collision silently
    drops a row. Suffix any duplicates and say so rather than losing them."""
    seen, clashes = {}, 0
    for r in rows:
        base = r["id"]
        if base in seen:
            seen[base] += 1
            r["id"] = "%s-%d" % (base, seen[base])
            clashes += 1
        else:
            seen[base] = 1
    if clashes:
        print("  note: %d duplicate %s id(s) suffixed" % (clashes, label), file=sys.stderr)
    return rows


# ---------------------------------------------------------------- builders

def build_versions(pages):
    """(versions, {number: official announcement url})."""
    out, links = [], {}
    for title, text in sorted(pages.items()):
        p = params(find_template(strip_comments(text), "Version"))
        num = clean(p.get("version")) or title.split("/", 1)[-1]
        if not re.match(r"^\d+\.\d+$", num):
            continue
        # The infobox holds several announcement links; the lowest-numbered is the
        # version's own news post.
        for key in ("link", "link2", "link3", "link4", "link5", "link6"):
            url = clean(p.get(key))
            if url.startswith("http"):
                links[num] = url
                break
        start, end = moment(p.get("date")), moment(p.get("date_end"))
        out.append({
            "number": num,
            "name": clean(p.get("title")),
            "startDate": start,
            "endDate": end,
            "phases": [],
            "status": "CONFIRMED" if start else "PREDICTED",
            "dateNote": None if end else "End date not yet announced",
        })
    out.sort(key=lambda v: [int(x) for x in v["number"].split(".")])
    return out, links


def version_windows(versions):
    """[(number, start_day, end_day)] with gaps closed.

    Older version pages often leave `date_end` blank, which would otherwise make the
    first such version match every later date. Fall back to the day before the next
    version starts; only the newest version stays open-ended.
    """
    dated = [v for v in versions if v["startDate"]]
    out = []
    for i, v in enumerate(dated):
        end = day(v["endDate"])
        if not end and i + 1 < len(dated):
            nxt = datetime.strptime(day(dated[i + 1]["startDate"]), "%Y-%m-%d")
            end = (nxt - timedelta(days=1)).strftime("%Y-%m-%d")
        out.append((v["number"], day(v["startDate"]), end))
    return out


def version_for(start_iso, windows):
    """Which version's window contains this banner start, and which half of it."""
    if not start_iso:
        return None, None
    d = day(start_iso)
    for number, vs, ve in reversed(windows):      # newest first
        if d >= vs and (ve is None or d <= ve):
            return number, (1 if d == vs else 2)
    return None, None


def banner_images(char_pages, weap_pages):
    """{page title: image url} from each Convene page's `image` parameter."""
    wanted = {}
    for pages in (char_pages, weap_pages):
        for title, text in pages.items():
            img = clean(params(find_template(strip_comments(text), "Convene")).get("image"))
            if img:
                wanted[title] = img
    urls = file_urls(set(wanted.values()))
    return {title: urls[img] for title, img in wanted.items() if img in urls}


def build_banners(char_pages, weap_pages, windows, attrs, images):
    banners = []
    for pages, btype, key in ((char_pages, "CHARACTER", "resonator_5_f"),
                              (weap_pages, "WEAPON", "weapon_5_f")):
        for title, text in pages.items():
            text = strip_comments(text)
            info = params(find_template(text, "Convene"))
            pool = params(find_template(text, "Convene/Pool"))
            start, end = moment(info.get("time_start")), moment(info.get("time_end"))
            featured = semis(pool.get(key))
            if not start or not featured:
                continue
            name = title.split("/", 1)[0]
            ver, phase = version_for(start, windows)
            a = attrs.get(featured[0], {})
            banners.append({
                "id": slug(name, day(start)),
                "type": btype,
                "name": name,
                "featured": featured[0],
                "element": a.get("element"),
                "weaponType": a.get("weaponType"),
                "rarity": a.get("rarity", 5),
                "start": start,
                "end": end,
                "version": ver,
                "phase": phase,
                "isRerun": False,          # filled in below
                "status": "CONFIRMED",
                "dateNote": "Times are Asia server time (UTC+8)",
                "imageUrl": images.get(title),
                "note": None,
            })
    banners.sort(key=lambda b: (b["start"], b["name"]))
    seen = set()
    for b in banners:                       # first appearance is a debut, the rest are reruns
        k = (b["type"], b["featured"])
        b["isRerun"] = k in seen
        seen.add(k)
    return ensure_unique_ids(banners, "banner")


def build_release_history(banners):
    hist = {}
    for b in banners:
        hist.setdefault((b["featured"], b["type"]), set()).add(day(b["start"]))
    return [{"item": item, "kind": kind, "dates": sorted(dates)}
            for (item, kind), dates in sorted(hist.items())]


def build_events(pages, windows):
    out = []
    for title, text in sorted(pages.items()):
        p = params(find_template(strip_comments(text), "Event"))
        start, end = moment(p.get("time_start")), moment(p.get("time_end"))
        if not start:
            continue
        name = title.split("/", 1)[0]
        ver, _ = version_for(start, windows)
        out.append({
            "id": slug(name, day(start)),
            "name": name,
            "start": start,
            "end": end,
            "rewardsSummary": "",
            "version": ver,
            "status": "CONFIRMED",
            "isSample": False,
        })
    return ensure_unique_ids(out, "event")


def build_shop(pages):
    """Outfits, from {{Outfit Infobox}}. The wiki lists no prices, so those stay null."""
    names = {}
    for title, text in pages.items():
        p = params(find_template(strip_comments(text), "Outfit Infobox"))
        img = clean(p.get("image"))
        if img:
            names[title] = img
    urls = file_urls(set(names.values()), width=480)

    out = []
    for title, text in sorted(pages.items()):
        p = params(find_template(strip_comments(text), "Outfit Infobox"))
        if not p:
            continue
        name = clean(p.get("name")) or title
        released = moment(p.get("releasedate"))
        # "Unlocked upon obtaining Resonator" and similar are permanent; the rest are
        # store or event outfits that come and go.
        obtain = clean(p.get("obtain")).lower()
        permanent = "resonator" in obtain or clean(p.get("type")).lower() == "original"
        out.append({
            "id": slug(name, clean(p.get("character"))),
            "name": name,
            "category": "OUTFIT",
            "character": clean(p.get("character")) or None,
            "price": None,
            "currency": None,
            "availability": "PERMANENT" if permanent else "LIMITED",
            "start": released,
            "end": None,
            "status": "CONFIRMED",
            "imageUrl": urls.get(names.get(title, "")),
            "isSample": False,
        })
    return ensure_unique_ids(out, "shop")


def build_patch_notes(versions, banners, links):
    """One note per released version, with its banner line-up as entries.

    Entries are written from the banner data, not copied from the wiki: each says which
    resonator or weapon the banner featured and whether it was a debut or a rerun.
    """
    by_version = {}
    for b in banners:
        if b["version"]:
            by_version.setdefault(b["version"], []).append(b)

    out = []
    for v in versions:
        num = v["number"]
        rows = sorted(by_version.get(num, []), key=lambda b: (b["start"], b["type"]))
        if not v["startDate"] or not rows:
            continue
        debuts = [b["featured"] for b in rows if not b["isRerun"] and b["type"] == "CHARACTER"]
        entries = [{
            "category": "NEW_CONTENT",
            "text": "%s: %s %s, phase %s (%s)" % (
                b["name"], b["featured"],
                "rerun" if b["isRerun"] else "debut",
                b["phase"] or 1, day(b["start"])),
            "affectedItems": [b["featured"]],
            "platform": "ALL",
            "impact": "NONE",
        } for b in rows]
        out.append({
            "id": slug("version", num),
            "versionNumber": num,
            "title": "Version %s%s" % (num, " - " + v["name"] if v["name"] else ""),
            "releaseDate": v["startDate"],
            "type": "VERSION",
            "summary": "%d banners across %d phases%s." % (
                len(rows), len({b["phase"] for b in rows}),
                ". New resonators: " + ", ".join(debuts) if debuts else ""),
            "sourceUrl": links.get(num),
            "status": "CONFIRMED",
            "lastUpdated": v["startDate"],
            "isSample": False,
            "entries": entries,
        })
    out.sort(key=lambda n: [int(x) for x in n["versionNumber"].split(".")], reverse=True)
    return ensure_unique_ids(out, "patch note")


def attributes(names):
    """{name: {element, weaponType, rarity}} from Resonator/Weapon infoboxes."""
    out = {}
    for title, text in wikitext(sorted(names)).items():
        text = strip_comments(text)
        p = (params(find_template(text, "Resonator Infobox"))
             or params(find_template(text, "Weapon Infobox")))
        if not p:
            continue
        a = {}
        el = clean(p.get("attribute")).lower()
        wp = clean(p.get("weapon") or p.get("type")).lower()
        if el in ELEMENTS:
            a["element"] = el.upper()
        if wp in WEAPONS:
            a["weaponType"] = wp.upper()
        r = clean(p.get("rarity"))
        if r.isdigit():
            a["rarity"] = int(r)
        if a:
            out[title] = a
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--skip-events", action="store_true")
    args = ap.parse_args()

    def log(m):
        print(m, file=sys.stderr)

    log("fetching version pages...")
    versions, links = build_versions(wikitext([t for t in allpages("Version/")
                                               if re.match(r"^Version/\d+\.\d+$", t)]))
    log("  %d versions, %d with an official link" % (len(versions), len(links)))

    log("fetching convene pages...")
    char_pages = wikitext(category("Featured Resonator Convenes"))
    weap_pages = wikitext(category("Featured Weapon Convenes"))
    log("  %d character, %d weapon" % (len(char_pages), len(weap_pages)))

    # Featured names first, so we only fetch the infoboxes we actually need.
    names = set()
    for pages, key in ((char_pages, "resonator_5_f"), (weap_pages, "weapon_5_f")):
        for text in pages.values():
            names |= set(semis(params(find_template(strip_comments(text), "Convene/Pool")).get(key)))
    log("fetching %d resonator/weapon infoboxes..." % len(names))
    attrs = attributes(names)

    log("resolving banner artwork...")
    images = banner_images(char_pages, weap_pages)
    log("  %d of %d banners have art" % (len(images), len(char_pages) + len(weap_pages)))

    windows = version_windows(versions)
    banners = build_banners(char_pages, weap_pages, windows, attrs, images)
    history = build_release_history(banners)
    notes = build_patch_notes(versions, banners, links)
    log("  %d banners, %d tracked items, %d version notes" % (len(banners), len(history), len(notes)))

    log("fetching outfit pages...")
    shop = build_shop(wikitext(category("Outfits")))
    log("  %d outfits" % len(shop))

    events = []
    if not args.skip_events:
        log("fetching event pages...")
        events = build_events(wikitext(category("Events")), windows)
        log("  %d dated events" % len(events))

    doc = {
        "schemaVersion": 1,
        "lastUpdated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "notice": ("Dates, names and artwork from the Wuthering Waves Wiki "
                   "(wutheringwaves.fandom.com), CC BY-SA 3.0. Community-maintained and "
                   "unofficial; times are Asia server time (UTC+8). Version notes list each "
                   "patch's banner line-up. Outfit prices are not published by the wiki. Dev "
                   "notes and maintenance have no structured source and are left empty."),
        "versions": versions,
        "banners": banners,
        "releaseHistory": history,
        "shop": shop,
        "events": events,
        "patchNotes": notes,
        "devNotes": [],
        "maintenance": [],
    }
    # `lastUpdated` moves on every run, so compare everything else and leave the file
    # alone when nothing real changed. A scheduled rebuild can then just check `git diff`.
    if os.path.exists(args.out):
        try:
            with open(args.out, encoding="utf-8") as f:
                old = json.load(f)
            if {k: v for k, v in old.items() if k != "lastUpdated"} == \
               {k: v for k, v in doc.items() if k != "lastUpdated"}:
                log("unchanged, left %s as it was" % args.out)
                return
        except (OSError, ValueError):
            pass                              # unreadable or not JSON: just overwrite

    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(doc, f, indent=2, ensure_ascii=False)
        f.write("\n")
    log("wrote %s" % args.out)


if __name__ == "__main__":
    main()
