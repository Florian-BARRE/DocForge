---
name: bbox-normalized-overlay
description: IR bbox is normalized [0,1] — overlay code that scales by page points/zoom is wrong (boxes collapse to corner)
metadata:
  type: project
---

# IR bbox is normalized [0,1], not page points

`common_libs/domain/ir/models/provenance.py` — `Provenance.bbox` is documented and
stored as a **normalized (x0,y0,x1,y1) in [0,1]** tuple. Confirmed by
`s1_parse/renderer.py:122-124` which multiplies `bbox * page_w/page_h` to recover
points for figure crops. The pages router (`pages/router.py:_block_info`) passes
`list(b.bbox)` straight through — still normalized — into `BlockInfo.bbox`.

**Why:** any frontend overlay (e.g. `PageBlockOverlay`) that draws bbox boxes over a
page screenshot must treat coords as fractions: `left = bbox[0]*100%`, `width =
(bbox[2]-bbox[0])*100%`. NO division by image natural width, NO 2× zoom correction.
The server renders the screenshot at 2× zoom, but normalization already makes the
ratio irrelevant — the displayed `<img>` spans the full page, so fractions map 1:1.

**How to apply:** flag as a correctness BUG any overlay that divides bbox by
`naturalWidth`, `naturalWidth/2`, page points, or a zoom factor. Symptom: every box
collapses to sub-pixel size in the top-left corner. The screenshot URL must carry
auth via `getPageScreenshotUrl` (`?token=` query param — `<img>` can't send the
Authorization header).
