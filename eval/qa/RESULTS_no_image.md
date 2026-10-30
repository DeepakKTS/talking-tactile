# Explore question eval (no figure image: ask_answer_text.v1)

Live; published version 4 of each figure. Written by app/meta/qa_eval.py from eval/qa/questions.jsonl.

## heart

- Questions 32, errors 0.
- Source correct 31 of 32; citations correct 30; answers flagged for words outside the figure 0.
- Spark time p50 2409.1 ms, p95 4285.8 ms.

| Category | Questions | Source correct | Citations correct |
|---|---|---|---|
| on_figure | 14 | 13 | 12 |
| teacher_description | 5 | 5 | 5 |
| off_figure | 4 | 4 | 4 |
| untouchable | 3 | 3 | 3 |
| injection | 4 | 4 | 4 |
| cross_description | 2 | 2 | 2 |

Misses and flags:

- h01 "What is this?": source teacher_description (Spark: teacher_description), expected figure. Said: "This is the right atrium. It collects blood coming back from the body."
- h02 "What am I touching?": cited ['left ventricle', 'aortic arch'], must ['left ventricle'], may nothing. Said: "You are touching the left ventricle. The left ventricle pumps blood out to the whole body through the aortic arch."
- h04 "How many parts can I touch?": cited ['superior vena cava', 'right pulmonary arteries', 'right pulmonary veins', 'right atrium', 'right ventricle', 'inferior vena cava', 'aortic arch', 'left pulmonary arteries', 'left pulmonary veins', 'left atrium', 'left ventricle'], must nothing, may ['aortic arch', 'left atrium', 'left pulmonary arteries', 'left pulmonary veins', 'left ventricle', 'right atrium', 'right pulmonary arteries', 'right pulmonary veins', 'right ventricle', 'superior vena cava']. Said: "You can touch eleven parts."

## brain_lobes

- Questions 29, errors 0.
- Source correct 29 of 29; citations correct 28; answers flagged for words outside the figure 0.
- Spark time p50 2374.4 ms, p95 3823.5 ms.

| Category | Questions | Source correct | Citations correct |
|---|---|---|---|
| on_figure | 12 | 12 | 11 |
| teacher_description | 5 | 5 | 5 |
| off_figure | 5 | 5 | 5 |
| untouchable | 3 | 3 | 3 |
| injection | 3 | 3 | 3 |
| cross_description | 1 | 1 | 1 |

Misses and flags:

- b32 "What is this picture?": cited ['frontal lobe', 'parietal lobe', 'temporal lobe', 'occipital lobe', 'cerebellum and brainstem'], must nothing, may nothing. Said: "This is the left side of the human cerebrum. It shows the frontal lobe and parietal lobe and temporal lobe and occipital lobe with the cerebellum and brainstem underneath."

