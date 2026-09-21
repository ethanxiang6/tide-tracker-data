# tide-tracker-data

Schedule data for the Tide Tracker Android app, rebuilt daily from the
[Wuthering Waves Wiki](https://wutheringwaves.fandom.com).

**Live URL the app reads:**

```
https://raw.githubusercontent.com/ethanxiang6/tide-tracker-data/main/schedule.json
```

## What's in it

| Section | Source | Filled |
|---|---|---|
| `versions` | `{{Version}}` infoboxes on `Version/*` pages | yes |
| `banners` | `{{Convene}}` + `{{Convene/Pool}}` on the Featured Resonator / Featured Weapon Convene pages | yes |
| `releaseHistory` | derived from banner start dates | yes |
| `events` | `{{Event}}` infoboxes on dated pages in `Category:Events` | yes |
| `shop`, `patchNotes`, `devNotes`, `maintenance` | — | **empty on purpose** |

The wiki has no structured source for the last four. They stay empty rather than
being filled with invented entries — the app renders an empty state for them, which
is honest where placeholder data would not be.

## How it updates

`.github/workflows/refresh.yml` runs `wiki_to_schedule.py` on a daily cron and commits
`schedule.json` only when something other than the timestamp changed. You can also
trigger it by hand from the Actions tab.

To run it locally:

```bash
python wiki_to_schedule.py --out schedule.json
```

No dependencies beyond the Python 3.8+ standard library.

## Times

Wiki times are Asia server time (UTC+8), which the wiki's own compensation notes
confirm. They are emitted with an explicit `+08:00` offset so the app reads exact
instants rather than guessing. Values the wiki only gives to the day stay date-only,
and the app marks those as approximate.

## Attribution and accuracy

Dates, names, elements, weapon types and rarities are extracted as **facts** from wiki
template parameters — no prose is copied. Wiki content is licensed
[CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/); this derived dataset
is offered under the same terms.

This is community-maintained, unofficial data. It lags the game: a new version's banner
pages only appear here once someone has written them on the wiki. Not affiliated with
or endorsed by Kuro Games.
