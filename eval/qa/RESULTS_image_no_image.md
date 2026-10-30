# Explore question eval (no figure image: ask_answer_text.v1)

Live; published version 4 of each figure. Written by app/meta/qa_eval.py from eval/qa/questions.jsonl.

## heart

- Questions 6, errors 0.
- Source correct 3 of 6; citations correct 3; answers flagged for words outside the figure 0.
- Spark time p50 4190.8 ms, p95 5513.6 ms.

| Category | Questions | Source correct | Citations correct |
|---|---|---|---|
| image | 6 | 3 | 3 |

Misses and flags:

- h62 "What shape is the aortic arch?": source off_figure (Spark: off_figure), expected figure; cited nothing, must ['aortic arch'], may nothing. Said: "This figure does not show that. Ask your teacher."
- h63 "Which part is the biggest?": source off_figure (Spark: off_figure), expected figure; cited nothing, must ['right ventricle'], may ['aortic arch', 'left ventricle']. Said: "This figure does not show that. Ask your teacher."
- h67 "Is the left atrium bigger than the right atrium?": source off_figure (Spark: off_figure), expected figure; cited nothing, must ['left atrium', 'right atrium'], may nothing. Said: "This figure does not show that. Ask your teacher."

## brain_lobes

- Questions 6, errors 0.
- Source correct 3 of 6; citations correct 3; answers flagged for words outside the figure 0.
- Spark time p50 4071.7 ms, p95 4856.6 ms.

| Category | Questions | Source correct | Citations correct |
|---|---|---|---|
| image | 6 | 3 | 3 |

Misses and flags:

- b68 "What shape is the temporal lobe?": source off_figure (Spark: off_figure), expected figure; cited nothing, must ['temporal lobe'], may nothing. Said: "This figure does not show that. Ask your teacher."
- b69 "Which lobe is the biggest?": source off_figure (Spark: off_figure), expected figure; cited nothing, must ['frontal lobe'], may ['parietal lobe']. Said: "This figure does not show that. Ask your teacher."
- b73 "Which is bigger, the frontal lobe or the occipital lobe?": source off_figure (Spark: off_figure), expected figure; cited nothing, must ['frontal lobe', 'occipital lobe'], may nothing. Said: "This figure does not show that. Ask your teacher."

