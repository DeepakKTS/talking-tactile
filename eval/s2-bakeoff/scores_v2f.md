# S2 scores, v2f

## flower

16 parts, no mask 7, needs teacher 7, regressions 5 of 5 references, specks 0, under a point symbol 4, on text 0, on leader lines 0, fragmented 0, overlapping pairs 9 before resolution and 0 after. Points 36: on text 0, on lines 0, on ink 0.

| # | Part | v1 A grade | Kind | Conf | mm2 | Pieces | Text | Line | Ref IoU | Flags |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | ovules | fail | area | 0.93 | 0.0 | 0 |  |  |  | needs teacher: spill, holds points of ovary, style; after a retry; overlapped before resolution style, ovary |
| 2 | pistil group | fail | group |  | 583.6 | 2 | 0% | 0% |  |  |
| 3 | stigma | fail | area | 0.59 | 0.0 | 0 |  |  |  | needs teacher: spill, holds points of style; after a retry; overlapped before resolution style |
| 4 | style | fail | thin | 0.43 | 0.0 | 0 |  |  |  | needs teacher: spill, holds points of ovary, ovules, stigma; after a retry; overlapped before resolution ovules, stigma, ovary |
| 5 | ovary | conditional | area | 0.84 | 583.6 | 2 | 0% | 0% | 0.245 (B) | regression: IoU 0.245 with the passing Arm B mask; overlapped before resolution ovules, style |
| 6 | petal | fail | area | 0.77 | 0.0 | 0 |  |  |  | needs teacher: spill, holds points of filament stalk; after a retry; overlapped before resolution floral axis, filament stalk |
| 7 | sepal | conditional | area | 0.51 | 21.9 | 1 | 0% | 2% |  | under a point symbol's area |
| 8 | perianth group | fail | group |  | 21.9 | 1 | 0% | 2% |  | under a point symbol's area |
| 9 | nectary | fail | area | 0.55 | 14.6 | 1 | 0% | 0% |  | under a point symbol's area |
| 10 | floral axis | fail | area | 0.64 | 31.4 | 1 | 0% | 0% |  | under a point symbol's area; overlapped before resolution petal, filament stalk |
| 11 | pedicel | conditional | area | 0.74 | 134.2 | 1 | 0% | 0% |  |  |
| 12 | connective | fail | area | 0.55 | 0.0 | 0 |  |  | 0.0 (B) | needs teacher: no mask; regression: IoU 0.0 with the passing Arm B mask |
| 13 | pollen sac | fail | area | 0.44 | 52.1 | 1 | 0% | 1% | 0.476 (B) | regression: IoU 0.476 with the passing Arm B mask; overlapped before resolution anther |
| 14 | anther | fail | area | 0.82 | 0.0 | 0 |  |  | 0.0 (B) | needs teacher: spill, holds points of filament stalk; after a retry; regression: IoU 0.0 with the passing Arm B mask; overlapped before resolution pollen sac, filament stalk |
| 15 | filament stalk | pass | thin | 0.52 | 0.0 | 0 |  |  | 0.0 (A) | needs teacher: spill, holds points of sepal; after a retry; regression: IoU 0.0 with the passing Arm A mask; overlapped before resolution petal, floral axis, anther |
| 16 | stamen group | fail | group |  | 52.1 | 1 | 0% | 1% |  |  |

## heart

19 parts, no mask 6, needs teacher 6, regressions 1 of 4 references, specks 0, under a point symbol 1, on text 0, on leader lines 0, fragmented 1, overlapping pairs 6 before resolution and 0 after. Points 33: on text 0, on lines 0, on ink 0.

| # | Part | v1 A grade | Kind | Conf | mm2 | Pieces | Text | Line | Ref IoU | Flags |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | brachiocephalic artery | fail | area | 0.88 | 61.1 | 1 | 0% | 0% |  | overlapped before resolution aorta |
| 2 | superior vena cava | conditional | area | 0.86 | 244.6 | 1 | 0% | 0% |  |  |
| 3 | right pulmonary arteries | pass | area | 0.83 | 43.4 | 1 | 0% | 3% | 0.952 (A) |  |
| 4 | right pulmonary veins |  | area | 0.82 | 55.6 | 1 | 0% | 2% |  |  |
| 5 | right atrium | pass | area | 0.78 | 319.7 | 1 | 0% | 0% | 0.985 (A) |  |
| 6 | tricuspid valve | fail | area | 0.58 | 0.0 | 0 |  |  |  | needs teacher: no mask |
| 7 | chordae tendineae | fail | thin | 0.37 | 0.0 | 0 |  |  |  | needs teacher: spill, holds points of left ventricle, mitral valve, semilunar valves; after a retry; overlapped before resolution semilunar valves, mitral valve, left ventricle |
| 8 | right ventricle | conditional | area | 0.20 | 275.2 | 1 | 0% | 2% |  |  |
| 9 | inferior vena cava |  | area | 0.72 | 110.8 | 1 | 0% | 1% |  |  |
| 10 | left common carotid artery | pass | area | 0.59 | 0.0 | 0 |  |  | 0.0 (A) | needs teacher: no mask; regression: IoU 0.0 with the passing Arm A mask |
| 11 | left subclavian artery | fail | area | 0.66 | 10.0 | 1 | 0% | 9% |  | under a point symbol's area; overlapped before resolution aorta |
| 12 | aorta |  | area | 0.93 | 0.0 | 0 |  |  |  | needs teacher: spill, holds points of brachiocephalic artery; after a retry; overlapped before resolution brachiocephalic artery, left subclavian artery |
| 13 | left pulmonary arteries | pass | area | 0.90 | 327.5 | 1 | 0% | 0% | 0.972 (A) |  |
| 14 | left pulmonary veins |  | area | 0.84 | 43.5 | 2 | 0% | 1% |  | 2 fragments |
| 15 | left atrium |  | area | 0.62 | 105.1 | 1 | 0% | 0% |  |  |
| 16 | semilunar valves | fail | thin | 0.80 | 262.2 | 2 | 0% | 1% |  | overlapped before resolution chordae tendineae |
| 17 | mitral valve | fail | thin | 0.33 | 0.0 | 0 |  |  |  | needs teacher: spill, holds points of left ventricle; after a retry; overlapped before resolution chordae tendineae, left ventricle |
| 18 | left ventricle | conditional | area | 0.52 | 0.0 | 0 |  |  |  | needs teacher: spill, holds points of chordae tendineae, mitral valve; after a retry; overlapped before resolution chordae tendineae, mitral valve |
| 19 | septum | fail | area | 0.29 | 621.3 | 1 | 0% | 0% |  |  |

## japan_regions

9 parts, no mask 0, needs teacher 0, regressions 1 of 7 references, specks 0, under a point symbol 0, on text 0, on leader lines 0, fragmented 0, overlapping pairs 0 before resolution and 0 after. Points 17: on text 0, on lines 0, on ink 0.

| # | Part | v1 A grade | Kind | Conf | mm2 | Pieces | Text | Line | Ref IoU | Flags |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Hokkaido region | pass | area | 0.96 | 618.5 | 1 | 0% | 0% | 0.986 (A) |  |
| 2 | Tohoku region | fail | area | 0.88 | 512.4 | 1 | 0% | 0% |  |  |
| 3 | Kanto region | pass | area | 0.90 | 241.2 | 1 | 0% | 0% | 0.981 (A) |  |
| 4 | Chubu region | pass | area | 0.81 | 490.7 | 1 | 0% | 0% | 0.958 (A) |  |
| 5 | Kansai region | conditional | area | 0.71 | 170.9 | 1 | 4% | 0% | 0.612 (B) | regression: IoU 0.612 with the passing Arm B mask |
| 6 | Chugoku region | pass | area | 0.88 | 235.4 | 1 | 0% | 0% | 0.971 (A) |  |
| 7 | Shikoku region | pass | area | 0.93 | 147.4 | 1 | 0% | 0% | 0.982 (A) |  |
| 8 | Kyushu region | pass | area | 0.92 | 294.0 | 1 | 0% | 0% | 0.986 (A) |  |
| 9 | Okinawa inset region | conditional | area | 0.75 | 2921.2 | 1 | 6% | 0% |  |  |
