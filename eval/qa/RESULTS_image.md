# Explore question eval

Live; published version 4 of each figure. Written by app/meta/qa_eval.py from eval/qa/questions.jsonl.

## heart

- Questions 6, errors 0.
- Source correct 5 of 6; citations correct 5; answers flagged for words outside the figure 2.
- Spark time p50 6434.9 ms, p95 10152.0 ms.

| Category | Questions | Source correct | Citations correct |
|---|---|---|---|
| image | 6 | 5 | 5 |

Misses and flags:

- h62 "What shape is the aortic arch?": words outside the figure: curved, like. Said: "The aortic arch is curved like an arch."
- h63 "Which part is the biggest?": source off_figure (Spark: off_figure), expected figure; cited nothing, must ['right ventricle'], may ['aortic arch', 'left ventricle']. Said: "This figure does not show that. Ask your teacher."
- h67 "Is the left atrium bigger than the right atrium?": words outside the figure: larger, looks. Said: "No. The right atrium looks larger than the left atrium in this picture."

## brain_lobes

- Questions 6, errors 0.
- Source correct 6 of 6; citations correct 6; answers flagged for words outside the figure 1.
- Spark time p50 5347.1 ms, p95 5681.0 ms.

| Category | Questions | Source correct | Citations correct |
|---|---|---|---|
| image | 6 | 6 | 6 |

Misses and flags:

- b68 "What shape is the temporal lobe?": words outside the figure: end, long, rounded. Said: "The temporal lobe is long and rounded at the end."

