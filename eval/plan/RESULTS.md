# Tactile-aware part plan, from the live recordings

S2 settings: nest inside 0.95, shared IoU 0.8. Written by app/meta/plan_eval.py.

## heart

- Subject: heart. Grade band: none.
- Listed 19: areas 15, lines 4, groups 0, not located 0.
- Touchable areas: 14 of 15. Touchable parts in regions.json: 14.
- Needs you: 1. septum (spill: holds points of right ventricle after a retry)
- Lines: tricuspid valve between right atrium and right ventricle; chordae tendineae in right ventricle; semilunar valves between left ventricle and aorta; mitral valve between left atrium and left ventricle.
- Nested by geometry: none.
- Merge proposals: 1. brachiocephalic artery, left common carotid artery, left subclavian artery, aorta as 'aortic arch' (Spark marked them as one unbroken shape)
- Silhouette: SAM 1 instance(s), 803939 px; in regions.json: True, 3 raised contour piece(s).
- Rules report: 1 violation(s). Replayed calls: 21.

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
- Touchable areas: 12 of 13. Touchable parts in regions.json: 14.
- Needs you: 1. floral axis (no_mask: SAM's mask holds none of the part's points)
- Lines: none.
- Nested by geometry: microsporangium in connective.
- Merge proposals: 4. petal, filament as 'petal and filament' (their outlines overlap almost entirely); connective, anther as 'connective and anther' (their outlines overlap almost entirely); ovules, stigma, style, ovary as 'pistil column' (Spark marked them as one unbroken shape); nectary, floral axis, pedicel as 'flower base' (Spark marked them as one unbroken shape)
- Silhouette: SAM 2 instance(s), 148899 px; in regions.json: True, 1 raised contour piece(s).
- Rules report: 31 violation(s). Replayed calls: 18.

16 parts, no mask 1, needs teacher 1, regressions 3 of 3 references, specks 0, under a point symbol 2, on text 0, on leader lines 0, fragmented 4, overlapping pairs 1 before resolution and 1 after. Points 25: on text 0, on lines 0, on ink 0.

| Reference part | Listed now as | Matched by | v2f IoU | IoU now | Verdict |
|---|---|---|---|---|---|
| ovary | ovary | name | 0.245 | 0.0 | still regressed |
| connective | connective | name | 0.0 | 0.068 | still regressed |
| pollen sac | microsporangium | mask IoU 0.367 | 0.476 | 0.367 | still regressed |
| anther | anther | name | 0.0 | 0.198 | still regressed |
| filament stalk | filament | word | 0.0 | 0.0 | still regressed |

## japan_regions

- Subject: Japan. Grade band: none.
- Listed 9: areas 9, lines 0, groups 0, not located 0.
- Touchable areas: 9 of 9. Touchable parts in regions.json: 9.
- Needs you: 0. 
- Lines: none.
- Nested by geometry: none.
- Merge proposals: 0. 
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
- Touchable areas: 10 of 10. Touchable parts in regions.json: 10.
- Needs you: 0. 
- Lines: central sulcus between precentral gyrus and postcentral gyrus; lateral sulcus between frontal lobe and temporal lobe.
- Nested by geometry: none.
- Merge proposals: 2. postcentral gyrus, parietal lobe as 'postcentral gyrus and parietal lobe' (their outlines overlap almost entirely); pons, medulla, cerebellum, spinal cord as 'brainstem' (Spark marked them as one unbroken shape)
- Silhouette: SAM 1 instance(s), 1042167 px; in regions.json: True, 0 raised contour piece(s).
- Rules report: 0 violation(s). Replayed calls: 13.

## brain_lobes

- Subject: brain. Grade band: 6_8.
- Listed 6: areas 6, lines 0, groups 0, not located 0.
- Touchable areas: 5 of 6. Touchable parts in regions.json: 5.
- Needs you: 1. olfactory bulb (no_points: every point was dropped by the guard)
- Lines: none.
- Nested by geometry: none.
- Merge proposals: 0. 
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
