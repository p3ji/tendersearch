# CanadaBuys feeds — reference

Dataset: https://open.canada.ca/data/en/dataset/6abd20d4-7a1c-4b38-baa2-9525d0bb2fd2
Field docs: https://donnees-data.tpsgc-pwgsc.gc.ca/ba2/ac-cb/soutien-support-eng.html

| Feed | URL | Refresh (UTC-0500) |
|---|---|---|
| New | `https://canadabuys.canada.ca/opendata/pub/newTenderNotice-nouvelAvisAppelOffres.csv` | every 2h, 06:15–22:15 |
| Open | `https://canadabuys.canada.ca/opendata/pub/openTenderNotice-ouvertAvisAppelOffres.csv` | daily, 07:00–08:30 |
| FY archive | `https://canadabuys.canada.ca/opendata/pub/<FY>-TenderNotice-AvisAppelOffres.csv` | daily |
| Legacy 2009–2022 | `https://canadabuys.canada.ca/opendata/pub/2009-2022-tenderNoticeHistorical-AvisAppelOffresHistorique.csv` | static |

`openTenderNotice` is the authority on what is open and drives the daily run.

## Gotchas — measured 2026-08-03 against the live open feed (896 notices)

1. **Encoding is `utf-8-sig`.** The file has a BOM; plain `utf-8` corrupts the first column name.
2. **Multi-value fields are `*`-prefixed, newline-separated:** `"*12160000\n*12350000"`.
   Single values keep the prefix: `"*Canada"`.
3. **No estimated-value column exists.** Do not design around contract value.
4. **Code coverage is partial:** `unspsc` on 757/896 (84%), `gsin` on 39/896 (4%),
   **no code at all on 139/896 (15%)**. Keyword matching is the only way to see that 15%.

   Re-measured 2026-08-04 against 902 open notices: `unspsc` 763 (85%), `gsin` 39 (4%),
   **no code at all on 100 (11%)**. UNSPSC and GSIN coverage are stable; the no-code
   share moved 15% → 11% in a day, so treat it as a 10–15% band rather than a constant.
   Re-run the measurement before quoting a figure that matters.
5. **`noticeType` is empty on 115/896 (13%).** Low-barrier classification must not assume it.
6. **Notices are amended in place.** Identity is `referenceNumber`; `amendmentNumber` is a
   zero-padded string (`"000"`, `"001"`) — compare as int, not string.
7. **Closing dates are naive ISO datetimes** (`2026-08-19T14:00:00`) in UTC-0500.
8. **Volume is modest** — 896 open, ~3 new/day. Stage-2 cost is not a constraint at this scale.
