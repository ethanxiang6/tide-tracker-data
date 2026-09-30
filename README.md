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
| `banners` | `{{Convene}}` + `{{Convene/Pool}}` on the Featured Resonator / Featured Weapon Convene pages, plus announced banners from `upcoming.json` | yes |
| `releaseHistory` | derived from banner start dates | yes |
| `events` | `{{Event}}` infoboxes on dated pages in `Category:Events` | yes |
| `shop`, `patchNotes`, `devNotes`, `maintenance` | — | **empty on purpose** |

The wiki has no structured source for the last four. They stay empty rather than
being filled with invented entries — the app renders an empty state for them, which
is honest where placeholder data would not be.

## Announced banners the wiki hasn't caught up with

The wiki only gets banner pages a few days before (or after) a version goes live, so a
freshly announced line-up would otherwise be missing from the app. Add it to
`upcoming.json` instead: each entry is a normal banner (`type`, `featured`, `version`,
`phase`, `start`, `end`, `status`, `dateNote`). Reruns can leave out `element`,
`weaponType` and `rarity`; they are copied from the item's earlier banners.

Every run merges these in, and drops each one by itself once the wiki has a banner for
the same item in the same version, so the file never needs cleaning up. Editing it on
`main` triggers a rebuild. To apply it locally without calling the wiki:

```bash
python wiki_to_schedule.py --out schedule.json --merge-only
```

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

## codes.json

Redeem codes shown on the app's Redeem codes screen. Edited by hand: add new codes at the top when a
livestream announces them, with `expires` as an ISO date (a plain date means the code works through
that day) or `"expired": true` once a code is known to be dead. The app checks this file on launch
and every 12 hours, and notifies when an active code appears that it hadn't seen.
