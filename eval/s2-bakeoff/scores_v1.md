# S2 scores, v1

## flower

16 parts, no mask 0, needs teacher 0, regressions 4 of 5 references, specks 4, under a point symbol 10, on text 3, on leader lines 3, fragmented 5, overlapping pairs 6 before resolution and 6 after. Points 16: on text 3, on lines 1, on ink 0. Graded fail at confidence 0.7 or higher: 2.

| # | Part | v1 A grade | Kind | Conf | mm2 | Pieces | Text | Line | Ref IoU | Flags |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | ovules | fail |  | 0.54 | 2.1 | 1 | 0% | 0% |  | under a point symbol's area |
| 2 | pistil group | fail |  | 0.56 | 4.6 | 1 | 100% | 0% |  | under a point symbol's area; 100% on text; point [423, 192] on text |
| 3 | stigma | fail |  | 0.71 | 2.0 | 0 | 0% | 0% |  | speck |
| 4 | style | fail |  | 0.36 | 2.1 | 1 | 0% | 13% |  | under a point symbol's area; 13% on leader lines; overlaps ovary |
| 5 | ovary | conditional |  | 0.43 | 236.4 | 3 | 0% | 0% | 0.594 (B) | regression: IoU 0.594 with the passing Arm B mask; 3 fragments; overlaps style |
| 6 | petal | fail |  | 0.70 | 6.0 | 1 | 0% | 82% |  | under a point symbol's area; 82% on leader lines; point [817, 636] on line |
| 7 | sepal | conditional |  | 0.35 | 24.2 | 2 | 0% | 7% |  | under a point symbol's area; 2 fragments; overlaps nectary |
| 8 | perianth group | fail |  | 0.70 | 804.2 | 3 | 34% | 0% |  | 34% on text; 3 fragments; point [438, 941] on text |
| 9 | nectary | fail |  | 0.21 | 8.8 | 1 | 0% | 43% |  | under a point symbol's area; 43% on leader lines; overlaps sepal |
| 10 | floral axis | fail |  | 0.25 | 1.2 | 0 | 0% | 0% |  | speck; overlaps pedicel |
| 11 | pedicel | conditional |  | 0.44 | 161.0 | 2 | 0% | 0% |  | 2 fragments; overlaps floral axis |
| 12 | connective | fail |  | 0.25 | 1.6 | 0 | 0% | 8% | 0.154 (B) | regression: IoU 0.154 with the passing Arm B mask; speck; overlaps pollen sac |
| 13 | pollen sac | fail |  | 0.68 | 291.6 | 2 | 0% | 1% | 0.223 (B) | regression: IoU 0.223 with the passing Arm B mask; 2 fragments; overlaps connective, anther, filament stalk |
| 14 | anther | fail |  | 0.50 | 1.8 | 0 | 0% | 0% | 0.009 (B) | regression: IoU 0.009 with the passing Arm B mask; speck; overlaps pollen sac |
| 15 | filament stalk | pass |  | 0.72 | 66.2 | 1 | 3% | 0% | 1.0 (A) | overlaps pollen sac |
| 16 | stamen group | fail |  | 0.78 | 55.2 | 1 | 100% | 0% |  | 100% on text; point [1638, 1057] on text |

## heart

19 parts, no mask 0, needs teacher 0, regressions 0 of 4 references, specks 0, under a point symbol 4, on text 0, on leader lines 2, fragmented 7, overlapping pairs 14 before resolution and 14 after. Points 19: on text 0, on lines 0, on ink 1. Graded fail at confidence 0.7 or higher: 1.

| # | Part | v1 A grade | Kind | Conf | mm2 | Pieces | Text | Line | Ref IoU | Flags |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | brachiocephalic artery | fail |  | 0.82 | 3.4 | 1 | 0% | 0% |  | under a point symbol's area; overlaps aorta |
| 2 | superior vena cava | conditional |  | 0.76 | 279.1 | 1 | 0% | 0% |  | overlaps right pulmonary arteries |
| 3 | right pulmonary arteries | pass |  | 0.68 | 44.1 | 1 | 0% | 4% | 1.0 (A) | overlaps superior vena cava |
| 4 | right pulmonary veins |  |  | 0.67 | 52.9 | 1 | 0% | 2% |  | point [681, 723] on ink |
| 5 | right atrium | pass |  | 0.68 | 315.0 | 1 | 0% | 0% | 1.0 (A) | overlaps chordae tendineae |
| 6 | tricuspid valve | fail |  | 0.09 | 333.1 | 8 | 0% | 0% |  | 8 fragments; overlaps chordae tendineae, right ventricle |
| 7 | chordae tendineae | fail |  | 0.37 | 902.7 | 3 | 0% | 0% |  | 3 fragments; overlaps right atrium, tricuspid valve, right ventricle |
| 8 | right ventricle | conditional |  | 0.49 | 957.4 | 4 | 0% | 0% |  | 4 fragments; overlaps tricuspid valve, chordae tendineae |
| 9 | inferior vena cava |  |  | 0.18 | 14.5 | 1 | 0% | 59% |  | under a point symbol's area; 59% on leader lines |
| 10 | left common carotid artery | pass |  | 0.69 | 71.2 | 1 | 0% | 0% | 1.0 (A) | overlaps left subclavian artery, aorta |
| 11 | left subclavian artery | fail |  | 0.40 | 680.7 | 3 | 0% | 0% |  | 3 fragments; overlaps left common carotid artery, aorta |
| 12 | aorta |  |  | 0.94 | 884.9 | 1 | 0% | 0% |  | overlaps brachiocephalic artery, left common carotid artery, left subclavian artery |
| 13 | left pulmonary arteries | pass |  | 0.44 | 323.9 | 1 | 0% | 0% | 1.0 (A) |  |
| 14 | left pulmonary veins |  |  | 0.88 | 20.8 | 1 | 0% | 2% |  | under a point symbol's area; overlaps mitral valve |
| 15 | left atrium |  |  | 0.73 | 102.9 | 1 | 0% | 0% |  | overlaps mitral valve, left ventricle |
| 16 | semilunar valves | fail |  | 0.05 | 14.6 | 1 | 0% | 21% |  | under a point symbol's area; 21% on leader lines; overlaps septum |
| 17 | mitral valve | fail |  | 0.43 | 763.6 | 5 | 0% | 1% |  | 5 fragments; overlaps left pulmonary veins, left atrium, left ventricle |
| 18 | left ventricle | conditional |  | 0.22 | 686.5 | 5 | 0% | 0% |  | 5 fragments; overlaps left atrium, mitral valve |
| 19 | septum | fail |  | 0.44 | 994.2 | 27 | 0% | 0% |  | 27 fragments; overlaps semilunar valves |

## japan_regions

9 parts, no mask 0, needs teacher 0, regressions 0 of 7 references, specks 0, under a point symbol 1, on text 0, on leader lines 0, fragmented 2, overlapping pairs 0 before resolution and 0 after. Points 9: on text 0, on lines 0, on ink 0. Graded fail at confidence 0.7 or higher: 1.

| # | Part | v1 A grade | Kind | Conf | mm2 | Pieces | Text | Line | Ref IoU | Flags |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Hokkaido region | pass |  | 0.96 | 626.9 | 1 | 0% | 0% | 1.0 (A) |  |
| 2 | Tohoku region | fail |  | 0.71 | 126.5 | 2 | 0% | 0% |  | 2 fragments |
| 3 | Kanto region | pass |  | 0.85 | 240.2 | 1 | 0% | 0% | 1.0 (A) |  |
| 4 | Chubu region | pass |  | 0.51 | 471.0 | 1 | 0% | 0% | 1.0 (A) |  |
| 5 | Kansai region | conditional |  | 0.52 | 253.9 | 2 | 3% | 0% | 0.829 (B) | 2 fragments |
| 6 | Chugoku region | pass |  | 0.81 | 235.7 | 1 | 0% | 0% | 1.0 (A) |  |
| 7 | Shikoku region | pass |  | 0.94 | 147.0 | 1 | 0% | 0% | 1.0 (A) |  |
| 8 | Kyushu region | pass |  | 0.87 | 294.7 | 1 | 0% | 0% | 1.0 (A) |  |
| 9 | Okinawa inset region | conditional |  | 0.86 | 16.5 | 1 | 0% | 0% |  | under a point symbol's area |
