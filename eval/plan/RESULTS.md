# Tactile-aware part plan, from the live recordings

S2 settings: nest inside 0.95, shared IoU 0.8. Written by app/meta/plan_eval.py.

## heart

- Subject: heart. Grade band: none.
- Listed 19: areas 15, lines 4, groups 0, not located 0.
- Touchable areas: 14 of 15. Touchable parts in regions.json: 0.
- Needs you: 1. septum (spill: holds points of right ventricle after a retry)
- Lines: tricuspid valve between right atrium and right ventricle; chordae tendineae in right ventricle; semilunar valves between left ventricle and aorta; mitral valve between left atrium and left ventricle.
- Nested by geometry: none.
- Merge proposals: 1. brachiocephalic artery, left common carotid artery, left subclavian artery, aorta as 'aortic arch' (Spark marked them as one unbroken shape)
- Left out of a merge Spark marked: none.
- Silhouette: SAM 1 instance(s), 803939 px; in regions.json: True, 3 raised contour piece(s).
- Rules report: 0 violation(s). Replayed calls: 21.

15 parts, no mask 1, needs teacher 1, regressions 0 of 4 references, specks 0, under a point symbol 0, on text 0, on leader lines 0, fragmented 2, overlapping pairs 0 before resolution and 0 after. Points 25: on text 0, on lines 0, on ink 0.

| Reference part | Listed now as | Matched by | v2f IoU | IoU now | Verdict |
|---|---|---|---|---|---|
| right pulmonary arteries | right pulmonary arteries | name | 0.952 | 0.947 | held |
| right atrium | right atrium | name | 0.985 | 0.969 | held |
| left common carotid artery | left common carotid artery | name | 0.0 | 0.927 | improved |
| left pulmonary arteries | left pulmonary arteries | name | 0.972 | 0.976 | held |

## flower

- Subject: mature flower. Grade band: none.
- Listed 16: areas 13, lines 0, groups 3, not located 0.
- Touchable areas: 7 of 13. Touchable parts in regions.json: 0.
- Needs you: 6. ovules (same_outline: same outline as ovary; a drawn line or color edge lies between them); style (spill: holds points of ovary, ovules after a retry); ovary (spill: holds points of style after a retry); floral axis (no_mask: SAM's mask holds none of the part's points); connective (same_outline: same outline as anther; a drawn line or color edge lies between them); filament (same_outline: same outline as petal; a drawn line or color edge lies between them)
- Lines: none.
- Nested by geometry: microsporangium in anther.
- Merge proposals: 1. floral axis, pedicel as 'flower base' (Spark marked them as one unbroken shape)
- Left out of a merge Spark marked: nectary (not merged with floral axis: a drawn line or color edge lies between them).
- Silhouette: SAM 2 instance(s), 148899 px; in regions.json: True, 1 raised contour piece(s).
- Rules report: 2 violation(s). Replayed calls: 20.

16 parts, no mask 9, needs teacher 6, regressions 3 of 3 references, specks 0, under a point symbol 2, on text 0, on leader lines 0, fragmented 1, overlapping pairs 1 before resolution and 1 after. Points 25: on text 0, on lines 0, on ink 0.

| Reference part | Listed now as | Matched by | v2f IoU | IoU now | Verdict |
|---|---|---|---|---|---|
| ovary | ovary | name | 0.245 | 0.0 | still regressed |
| connective | connective | name | 0.0 | 0.0 | still regressed |
| pollen sac | microsporangium | mask IoU 0.367 | 0.476 | 0.367 | still regressed |
| anther | anther | name | 0.0 | 0.421 | still regressed |
| filament stalk | filament | word | 0.0 | 0.0 | still regressed |

## japan_regions

- Subject: Japan. Grade band: none.
- Listed 9: areas 9, lines 0, groups 0, not located 0.
- Touchable areas: 9 of 9. Touchable parts in regions.json: 0.
- Needs you: 0.
- Lines: none.
- Nested by geometry: none.
- Merge proposals: 0.
- Left out of a merge Spark marked: none.
- Silhouette: SAM 0 instance(s), 0 px; in regions.json: False, 0 raised contour piece(s).
- Rules report: 0 violation(s). Replayed calls: 12.

9 parts, no mask 0, needs teacher 0, regressions 0 of 0 references, specks 0, under a point symbol 0, on text 0, on leader lines 0, fragmented 0, overlapping pairs 0 before resolution and 0 after. Points 19: on text 0, on lines 0, on ink 0.

| Reference part | Listed now as | Matched by | v2f IoU | IoU now | Verdict |
|---|---|---|---|---|---|
| Hokkaido region | Hokkaido island area | word | 0.986 | 0.984 | held |
| Kanto region | Kanto region area | word | 0.981 | 0.974 | held |
| Chubu region | Chubu region area | word | 0.958 | 0.93 | held |
| Kansai region | Kansai region area | word | 0.612 | 0.804 | improved |
| Chugoku region | Chugoku region area | word | 0.971 | 0.965 | held |
| Shikoku region | Shikoku island area | word | 0.982 | 0.983 | held |
| Kyushu region | Kyushu island area | word | 0.986 | 0.985 | held |

## brain_upload

- Subject: human brain. Grade band: 6_8.
- Listed 12: areas 10, lines 2, groups 0, not located 0.
- Touchable areas: 8 of 10. Touchable parts in regions.json: 0.
- Needs you: 2. parietal lobe (same_outline: same outline as postcentral gyrus; a drawn line or color edge lies between them); pons (same_outline: same outline as cerebellum; a drawn line or color edge lies between them)
- Lines: central sulcus between precentral gyrus and postcentral gyrus; lateral sulcus between frontal lobe and temporal lobe.
- Nested by geometry: medulla in cerebellum, spinal cord in cerebellum.
- Merge proposals: 1. pons, medulla, spinal cord as 'brainstem' (Spark marked them as one unbroken shape)
- Left out of a merge Spark marked: none.
- Silhouette: SAM 1 instance(s), 1042167 px; in regions.json: True, 0 raised contour piece(s).
- Rules report: 1 violation(s). Replayed calls: 13.

## brain_lobes

- Subject: brain. Grade band: 6_8.
- Listed 6: areas 6, lines 0, groups 0, not located 0.
- Touchable areas: 5 of 6. Touchable parts in regions.json: 0.
- Needs you: 1. olfactory bulb (no_points: every point was dropped by the guard)
- Lines: none.
- Nested by geometry: none.
- Merge proposals: 0.
- Left out of a merge Spark marked: none.
- Silhouette: SAM 1 instance(s), 1035244 px; in regions.json: True, 1 raised contour piece(s).
- Rules report: 0 violation(s). Replayed calls: 8.

## First-mask pairs, for NEST_INSIDE

| Share inside | Pairs |
|---|---|
| 0.25 to 0.50 | 12 |
| 0.50 to 0.70 | 5 |
| 0.70 to 0.80 | 2 |
| 0.80 to 0.85 | 3 |
| 0.85 to 0.90 | 5 |
| 0.90 to 0.95 | 6 |
| 0.95 to 1.00 | 27 |

| Figure | Part | Inside | Share | IoU | Spark |
|---|---|---|---|---|---|
| heart | left common carotid artery | aorta | 0.993 | 0.000 |  |
| heart | right ventricle | septum | 0.991 | 0.000 |  |
| heart | right atrium | septum | 0.988 | 0.000 |  |
| heart | left ventricle | septum | 0.972 | 0.000 |  |
| heart | left subclavian artery | aorta | 0.968 | 0.000 |  |
| heart | brachiocephalic artery | aorta | 0.962 | 0.000 |  |
| heart | left atrium | septum | 0.906 | 0.000 |  |
| heart | left atrium | left ventricle | 0.893 | 0.000 |  |
| heart | inferior vena cava | septum | 0.801 | 0.000 |  |
| heart | right pulmonary arteries | superior vena cava | 0.780 | 0.000 |  |
| flower | microsporangium | anther | 1.000 | 0.000 | parent |
| flower | connective | anther | 0.992 | 0.895 | parent |
| flower | ovules | ovary | 0.990 | 0.925 | parent |
| flower | stigma | petal | 0.987 | 0.000 |  |
| flower | stigma | ovary | 0.983 | 0.266 |  |
| flower | microsporangium | connective | 0.967 | 0.000 |  |
| flower | stigma | filament | 0.961 | 0.000 |  |
| flower | style | petal | 0.960 | 0.000 |  |
| flower | nectary | petal | 0.958 | 0.000 |  |
| flower | pedicel | petal | 0.957 | 0.000 |  |
| flower | filament | petal | 0.956 | 0.868 |  |
| flower | ovary | ovules | 0.934 | 0.925 |  |
| flower | style | filament | 0.919 | 0.000 |  |
| flower | pedicel | filament | 0.906 | 0.000 |  |
| flower | petal | filament | 0.904 | 0.868 |  |
| flower | anther | connective | 0.901 | 0.895 |  |
| flower | stigma | style | 0.896 | 0.661 |  |
| flower | sepal | petal | 0.882 | 0.000 |  |
| flower | style | ovary | 0.876 | 0.286 |  |
| flower | stigma | ovules | 0.839 | 0.000 |  |
| flower | style | ovules | 0.804 | 0.271 |  |
| flower | style | stigma | 0.716 | 0.661 |  |
| brain_upload | parietal lobe | postcentral gyrus | 0.995 | 0.964 |  |
| brain_upload | spinal cord | medulla | 0.993 | 0.973 |  |
| brain_upload | medulla | pons | 0.992 | 0.404 |  |
| brain_upload | spinal cord | pons | 0.991 | 0.399 |  |
| brain_upload | medulla | spinal cord | 0.980 | 0.973 |  |
| brain_upload | pons | cerebellum | 0.973 | 0.935 |  |
| brain_upload | postcentral gyrus | parietal lobe | 0.969 | 0.964 | parent |
| brain_upload | spinal cord | cerebellum | 0.963 | 0.378 |  |
| brain_upload | medulla | cerebellum | 0.962 | 0.383 |  |
| brain_upload | cerebellum | pons | 0.961 | 0.935 |  |
| brain_upload | precentral gyrus | frontal lobe | 0.893 | 0.000 | parent |

## Drawn boundaries, for EDGE_STEP and FILL_DELTA

Edge step 14, fill delta 55. Joins at: the smallest edge step, 4 to 40, at which the two share a drawn region.

| Figure | Pair | Judged for | Joins at | Fill delta | Drawn boundary |
|---|---|---|---|---|---|
| heart | aorta and brachiocephalic artery | Spark: aortic arch | 4 | 5.7 | none |
| heart | aorta and left common carotid artery | Spark: aortic arch | 5 | 43.2 | none |
| heart | aorta and left subclavian artery | Spark: aortic arch | 4 | 12.8 | none |
| heart | brachiocephalic artery and left common carotid artery | Spark: aortic arch | 5 | 48.8 | none |
| heart | brachiocephalic artery and left subclavian artery | Spark: aortic arch | 4 | 18.4 | none |
| heart | left common carotid artery and left subclavian artery | Spark: aortic arch | 5 | 30.4 | none |
| flower | anther and connective | IoU 0.895 | never | 246.8 | a drawn line or color edge lies between them |
| flower | filament and petal | IoU 0.868 | 17 | 0.0 | a drawn line or color edge lies between them |
| flower | floral axis and nectary | Spark: flower base | never | 0.0 | a drawn line or color edge lies between them |
| flower | floral axis and pedicel | Spark: flower base | 4 | 0.0 | none |
| flower | nectary and pedicel | Spark: flower base | never | 0.0 | a drawn line or color edge lies between them |
| flower | ovary and ovules | IoU 0.925 | 40 | 0.0 | a drawn line or color edge lies between them |
| flower | ovary and stigma | Spark: pistil column | never | 47.3 | a drawn line or color edge lies between them |
| flower | ovary and style | Spark: pistil column | 40 | 81.9 | a drawn line or color edge lies between them |
| flower | stigma and style | Spark: pistil column | never | 40.6 | a drawn line or color edge lies between them |
| brain_upload | cerebellum and pons | IoU 0.935 | never | 21.2 | a drawn line or color edge lies between them |
| brain_upload | medulla and pons | Spark: brainstem | 10 | 0.0 | none |
| brain_upload | medulla and spinal cord | IoU 0.973 | 4 | 0.0 | none |
| brain_upload | parietal lobe and postcentral gyrus | IoU 0.964 | 17 | 31.0 | a drawn line or color edge lies between them |
| brain_upload | pons and spinal cord | Spark: brainstem | 10 | 0.0 | none |
