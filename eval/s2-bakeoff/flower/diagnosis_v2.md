# Flower, Arm A v2: why the filament grew and where the references went

Replay only, Oct 29: the recorded v2 calls (`fixtures/recorded/armav2_flower_*.json`)
through `app/meta/s2_armav2.py`, with each instance's raw SAM mask captured before
post-processing. Areas are mm² on a letter page (0.0806 mm per px). No live calls.

## The filament mask, 2007.6 mm²

Spark gave the filament stalk 3 instances. SAM answered each object as follows.

| Instance | Points sent (px) | In SAM's mask | Confidence | Raw mask | Kept after pieces | What SAM returned |
|---|---|---|---|---|---|---|
| 1, right enlarged stamen view | (1525, 828), (1515, 922) | both | 0.895 | 2008.7 mm², box x 985 to 2047, y 359 to 1149 | 1949.1 mm² | The pink stamen bubble around the filament, with the labels and outlines in it, and only specks of the filament itself |
| 2, main drawing right filament | (1097, 626) | no | 0.183 | 2.9 mm² | 0 | A sliver away from the point; dropped by the piece rule |
| 3, main drawing left filament | (866, 591) | yes | 0.570 | 1934.5 mm², box x 399 to 1857, y 125 to 1122 | 1911.5 mm² | Nearly the whole flower in the main drawing: petals, pistil, sepals, pedicel |

No point was moved or dropped by the guard, and v1 gave no negative points for the filament.
Kept before resolution: 3860.6 mm². Contested pixels then went to smaller masks, 278,584 px
in all (petal 202,878, stigma 30,675, style 15,359, pedicel 15,215, sepal 5,080, pollen
sac 4,327, connective 2,978, anther 1,765, ovary 205, ovules 87, nectary 15). What is left,
2007.6 mm², is mostly instance 1's bubble.

So the size is SAM's answer to points on a strip about 10 to 20 px wide: it returned the
region around the strip (instance 1) or the whole drawing (instance 3), at confidences of
0.895 and 0.570. Spark marked the filament thin.

## The five regressed references

Each passing v1 mask (the reference) against v2, before and after contested pixels were
resolved, and which v2 part owns the reference's pixels at the end.

| Part | Reference | IoU before | IoU after | Reference pixels at the end | Cause |
|---|---|---|---|---|---|
| ovary | Arm B, 164.9 mm² | 0.224 | 0.000 | stigma 20,151, style 2,175, petal 477, filament 433, no part 2,145 | v2's ovary covered 22,751 of the 25,381 px, but the stigma's mask (209 mm²) spilled over the ovary. Stigma is smaller, so it won 20,143 of them, and style won 1,574. |
| connective | Arm B, 10.3 mm² | 0.033 | 0.042 | connective 1,408, anther 178 | v2's connective covers the reference but is 279.9 mm², 27 times larger: it spilled over the anther and the filament. |
| pollen sac | Arm B, 65.4 mm² | 0.353 | 0.353 | pollen sac 6,638, connective 3,211, no part 221 | v2's mask covers two thirds of the reference. The rest is in the connective's mask, which SAM gave it directly, not through resolution. |
| anther | Arm B, 172.3 mm² | 0.478 | 0.043 | connective 14,485, pollen sac 8,481, anther 1,244, filament 424, petal 161, no part 1,716 | v2's anther covered 24,245 px of the reference, then lost 14,485 to the connective and 8,044 to the pollen sac. Spark lists both as inside the anther, and both are smaller, so the smaller-mask rule handed them the anther's own area. |
| filament stalk | Arm A, 66.2 mm² | 0.005 | 0.003 | connective 8,147, filament 889, pollen sac 28, no part 1,115 | SAM's filament masks missed the filament (above). The connective's mask holds most of it. |

## What this says

- Two causes. SAM spills on small or thin parts: the filament, the stigma over the ovary,
  the connective over the anther and filament. Then the smaller-mask rule rewards the
  spill: a small mask that spilled wins the pixels it spilled onto.
- The rule also takes a parent's area for its children when the children's masks are too
  big (anther to connective and pollen sac).
- The spill retry in the next step targets the first cause. On this run, 8 flower masks
  hold a prompt point of another part that is not their child (Spark's parent field):
  ovules (style, ovary), stigma (ovules, style, ovary), style (ovules, ovary), ovary
  (style), petal (7 parts), connective (pollen sac, anther), pollen sac (connective,
  anther), filament stalk (10 parts). On the heart, 2: mitral valve (left ventricle,
  septum) and septum (4 parts). On Japan, none. The retry does not change the
  smaller-mask rule.
