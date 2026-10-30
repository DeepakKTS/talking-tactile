# Explore question eval

Live; published version 3 of each figure. Written by app/meta/qa_eval.py from eval/qa/questions.jsonl.

## heart

- Questions 30, errors 0.
- Source correct 29 of 30; citations correct 27; answers flagged for words outside the figure 1.
- Spark time p50 3077.5 ms, p95 5928.2 ms.

| Category | Questions | Source correct | Citations correct |
|---|---|---|---|
| on_figure | 14 | 14 | 12 |
| teacher_description | 4 | 4 | 4 |
| off_figure | 5 | 4 | 4 |
| untouchable | 3 | 3 | 3 |
| injection | 4 | 4 | 4 |

Misses and flags:

- h02 "What am I touching?": cited ['left ventricle', 'aortic arch'], must ['left ventricle'], may nothing. Said: "You are touching the left ventricle. It pumps blood out to the whole body through the aortic arch."
- h04 "How many parts can I touch?": cited ['superior vena cava', 'right pulmonary arteries', 'right pulmonary veins', 'right atrium', 'right ventricle', 'inferior vena cava', 'aortic arch', 'left pulmonary arteries', 'left pulmonary veins', 'left atrium', 'left ventricle'], must nothing, may ['aortic arch', 'left atrium', 'left pulmonary arteries', 'left pulmonary veins', 'left ventricle', 'right atrium', 'right pulmonary arteries', 'right pulmonary veins', 'right ventricle', 'superior vena cava']. Said: "You can touch eleven parts."
- h20 "What does the aortic arch do?": source teacher_description (Spark: teacher_description), expected off_figure; cited ['aortic arch', 'left ventricle'], must nothing, may nothing; words outside the figure: carries, pumped. Said: "The aortic arch carries blood pumped by the left ventricle out to the whole body."

## brain_lobes

- Questions 28, errors 0.
- Source correct 28 of 28; citations correct 28; answers flagged for words outside the figure 0.
- Spark time p50 3130.2 ms, p95 8388.1 ms.

| Category | Questions | Source correct | Citations correct |
|---|---|---|---|
| on_figure | 12 | 12 | 12 |
| teacher_description | 5 | 5 | 5 |
| off_figure | 5 | 5 | 5 |
| untouchable | 3 | 3 | 3 |
| injection | 3 | 3 | 3 |

Misses and flags:

None.

