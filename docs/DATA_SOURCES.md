# Data sources and attribution

## Real-world craft-photo acceptance candidates

Original downloads for all four exact candidates failed with DNS resolution errors.
Their source pages/license terms were reviewed; **no photograph pixels were obtained
or visually inspected**, and no candidate was selected. No unrelated image replaced
a failed source. Usability, manual outline, scaling, fitting and SVG acceptance are
all **untested**, not failed geometry tests or assumed successes.

| Candidate / photographer | Terms reviewed |
| --- | --- |
| [Ripped brown papers — Cup of Couple](https://www.pexels.com/photo/ripped-brown-papers-6632858/) | [Pexels License](https://www.pexels.com/license/), app use permitted subject to restrictions |
| [Fabric pile — Le Tia](https://unsplash.com/photos/pile-of-red-white-and-purple-fabric-scraps-nf_KjvkE7vo) | [Unsplash License](https://unsplash.com/license), attribution retained |
| [Fabric scraps — Elinkorn](https://commons.wikimedia.org/wiki/File:Fabric_scraps.jpg) | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/), attribution and share-alike for adaptations |
| [Boxes with shredded clothes — Alexander Zvir](https://www.pexels.com/photo/boxes-with-shredded-clothes-11496283/) | Pexels License; no claim of suitability from its title |

[Availability sheet](craft-photo-contact-sheet.svg) and
[candidate records](../examples/craft_photos/candidates.json) distinguish catalog
metadata from actual inspection. `tools/prepare_craft_photos.py --download` makes
one GET per missing source without retries; it preserves original bytes outside
public/, never silently overwrites user files, and does not select images or
produce outlines. On successful retrieval, inspect a visible flat region, upload
normally, trace manually and supply a real measurement. No candidate segmentation,
physical dimension, fabricated layout, SAM call or image-grounded Muse call exists.

## Internal regression provenance

CTVG and all 12 synthetic scenes are now **internal regression fixtures only**.
The public gallery is empty pending suitable, inspected craft photographs. No new source
photograph was selected from the three requested replacement datasets: none was
found in the project, ~/Downloads or the existing hackathon data directory, and
sandbox DNS prevented downloading archives. Web catalog metadata was reviewed;
actual replacement images/annotations/archive contents **were not inspected**.
Descriptions are not treated as proof of flatness, quality, provenance or usable
annotations. No new mask, photograph or physical measurement was invented.
The industrial-background CTVG examples are retained for regression only.
Craft photographs use manual outlining, without imported masks or hidden contours.

| Candidate | Official catalog and license statement | Actual inspection / decision |
| --- | --- | --- |
| Re-annotated and Segmented TrashNet, Rohit, Tabassum, Raihan (2026) | [Mendeley v1](https://data.mendeley.com/datasets/f6y37w8hxb/1), DOI 10.17632/f6y37w8hxb.1; catalog CC BY 4.0 | No local archive/download access. Catalog describes YOLO polygons; payload, source-image rights and actual flat paper/cardboard quality unverified. No import. |
| DWSD, Asfak ali, Suvojit Acharjee, MD Manarul Sk, SALMAN ALHARTHI, Sheli Sinha Chaudhuri, Adnan Akhunzada (2024) | [Mendeley v1](https://data.mendeley.com/datasets/gr99ny6b8p/1), DOI 10.17632/gr99ny6b8p.1; catalog CC BY 4.0 | Catalog lists DSWD.zip, 241 MB; describes color annotations. Archive and image/mask pairing unavailable. Outdoor/dense waste suitability not established. No import. |
| CLICK Trash, Manjit Baishya (2026) | [Mendeley v2](https://data.mendeley.com/datasets/htcvvz6fm2/2), DOI 10.17632/htcvvz6fm2.2; catalog CC BY 4.0 | Catalog describes outdoor litter and COCO polygons, with SAM 3-assisted/human-corrected labels; its prose still says license to be added. Embedded license and payload unverified. No import or claim of app SAM inference. |

The local download attempt returned `nodename nor servname provided, or not known`;
web-tool file-list/archive access was also unavailable. Metadata review is not
archive review. To resume selection, obtain the official archive on a host with
network access, inspect its file tree, embedded licenses, original photographs and
matched masks/polygons, then keep at most 4–6 suitable flat materials. Never derive
fake segmentation from boxes. Missing annotations require honest manual tracing.
Retain original coordinates and record every transform/derivative and source hash.

## CTVG: verified retained assets

**Daniel Costa, João Cruz, Gualter Barros and Nelson Rodrigues (2024), CTVG,
Mendeley Data V1, [DOI 10.17632/m5wds8287s.1](https://doi.org/10.17632/m5wds8287s.1).**
[Official dataset](https://data.mendeley.com/datasets/m5wds8287s/1).
License: **[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)**.
No author endorsement is implied. Original app/importer code is distinct from
these licensed third-party photographs/annotations.

An existing external CTVG.zip was inspected during import: 111,276,150 bytes,
31,436 entries; real/black contains 888 image/JSON pairs under all_448.
Observed local archive SHA-256 (not a publisher signature):
`c41f9cde258360ba725621159da7b109472578c402e0db665e4935719dfda76e`.
It remains outside the repository; no full archive is redistributed.
Only the real subset was imported, never the synthetic full/single/binary subsets.

Source stems below are relative to `CTVG/all_448/real/black/`; each has matching
`.jpeg` and `.json` files. All full photographs are 448×448, one source polygon each.

| Material | Fixture key | Exact source stem | Vertices / area px² |
| --- | --- | --- | --- |
| Blouse sleeve | ctvg-01 | blouse/jersey_plain_purple/0000 | 206 / 34882 |
| Shirt panel | ctvg-02 | shirt/taffeta_polyester_green/0000 | 219 / 46932 |
| Dress piece | ctvg-03 | dress/poplin_cotton_mix/0028 | 142 / 19662 |
| Shorts piece | ctvg-04 | shorts/poplin_cotton_mix/0008 | 192 / 24971 |

The retained pieces have distinct silhouettes, valid source contours and successful
layout checks; their staging is not presented as an aesthetic improvement.
Original JPEG/JSON bytes and pixel coordinates are unchanged. The manifest records
source member names, hashes, labels and modifications in annotation_provenance.
Annotations use image.{width,height,n_polygons,polygons}, with each segmentation an
explicit pixel contour. All four polygons are valid and positive-area. None has
holes/disconnected components; none are invented. Import rejects invalid/nested
unsupported contours instead of silently repairing them. Disjoint valid contours
can form MultiPolygon; overlapping incompatible annotations are rejected.

Modifications: close rings for GeoJSON without changing vertices; derive binary
black/white SVG masks; crop to annotation bounds plus padding and resize/re-encode
**gallery thumbnails only** to <=224 px WebP (8,982 bytes combined). Full-photo
coordinates never refer to cropped thumbnails. The documentation preview draws
supplied contours on cropped/resized photos. SVG exports are attributed derivatives
including authors, DOI, CC BY 4.0, source and modification/scale notices.
See [public attribution](../public/ctvg/ATTRIBUTION.md),
[photo/contour preview](ctvg-real-preview.jpg) and [verified fits](REAL_DATASET_FITS.json).

No physical scale is supplied by CTVG. Pixel bounding boxes and grasp points are
not millimeter markers. The user must measure a width/reference for real cutting,
or explicitly choose illustrative 0.06 mm/px for demonstration. All four internal regression photos
fit square-tabs, triangle-markers and corner-pieces at that assumption with 0.5 mm
clearance/grid (12/12); these are **not measured garment dimensions**.
Dataset contours are not SAM predictions; manual edits and provider predictions
retain separate labels. No new AI segmentation was performed here.

Reproduce from the external source archive without extracting everything:

```sh
backend/.venv/bin/python tools/import_ctvg.py /path/to/CTVG.zip
AI_ENABLED=false backend/.venv/bin/python tools/verify_real_dataset.py
```

Only the selected files are written; original archive/user source files are not
modified. Reimport and regeneration preserve the public/fixture separation.

## Synthetic regression data and earlier local inspection

All 12 original MakeFromThis synthetic polygon/SVG pairs are retained in
backend/app/scenes.json and public/scenes, with exact holes/disconnected geometry,
source labels and scale. They are original procedural hackathon fixtures, not
photographs or AI masks. They are absent from public listing and bundled gallery
fallback. Direct fixture APIs remain for tests/reproducibility, not gallery choices.
Generate with `python3.12 tools/generate_scenes.py`; verify with
`backend/.venv/bin/python tools/verify_demo_scenes.py`. Five material families fit
all three templates at 0.5 mm; the narrow frame's eroded region is empty and export
is refused. [Synthetic fit evidence](DEMO_SCENE_FITS.json).

The initial project/Downloads inspection found no Nesting/Strip Packing SVG archive,
FabriD photographs or Nestbolt benchmark assets. An unrelated stripe-backup name
match was not opened. No unclear-rights fabric texture was redistributed. Synthetic
textures are original procedural marks, with deterministic explicit polygons.
No photographic realism, benchmark improvement or industrial cutting accuracy is
claimed. Third-party software includes React/Vite/FastAPI/Shapely/GEOS; model weights
are not distributed. See [submission limitations](HACKATHON_SUBMISSION.md).
