# Explore question eval

Live; published version 4 of each figure. Written by app/meta/qa_eval.py from eval/qa/questions.jsonl.

## heart

- Questions 38, errors 0.
- Source correct 36 of 38; citations correct 35; answers flagged for words outside the figure 3.
- Spark time p50 3543.6 ms, p95 5634.5 ms.

| Category | Questions | Source correct | Citations correct |
|---|---|---|---|
| on_figure | 14 | 13 | 13 |
| teacher_description | 5 | 5 | 5 |
| off_figure | 4 | 4 | 4 |
| untouchable | 3 | 3 | 3 |
| injection | 4 | 4 | 4 |
| cross_description | 2 | 2 | 2 |
| image | 6 | 5 | 4 |

Misses and flags:

- h01 "What is this?": source teacher_description (Spark: teacher_description), expected figure. Said: "This is the right atrium. The right atrium collects blood coming back from the body."
- h02 "What am I touching?": cited ['left ventricle', 'aortic arch'], must ['left ventricle'], may nothing. Said: "You are touching the left ventricle. It pumps blood out to the whole body through the aortic arch."
- h62 "What shape is the aortic arch?": words outside the figure: bends, curved, like, round, thick, tube, u, upside. Said: "The aortic arch is a thick curved tube at the top. It bends round like an upside down U."
- h63 "Which part is the biggest?": source off_figure (Spark: off_figure), expected figure; cited nothing, must ['right ventricle'], may ['aortic arch', 'left ventricle']. Said: "This figure does not show that. Ask your teacher."
- h64 "What is at the top of the heart?": cited ['superior vena cava', 'right pulmonary arteries', 'right pulmonary veins', 'aortic arch', 'left pulmonary arteries', 'left pulmonary veins'], must ['aortic arch'], may ['left pulmonary arteries', 'right pulmonary arteries', 'superior vena cava']. Said: "The superior vena cava and aortic arch and right pulmonary arteries and right pulmonary veins and left pulmonary arteries and left pulmonary veins are at the top."
- h65 "What is at the bottom of the figure?": words outside the figure: holds. Said: "The bottom holds the right ventricle and the left ventricle with the inferior vena cava below them."
- h67 "Is the left atrium bigger than the right atrium?": words outside the figure: feels, larger. Said: "No. The right atrium feels larger than the left atrium."

## brain_lobes

- Questions 35, errors 0.
- Source correct 35 of 35; citations correct 34; answers flagged for words outside the figure 5.
- Spark time p50 3239.1 ms, p95 5697.8 ms.

| Category | Questions | Source correct | Citations correct |
|---|---|---|---|
| on_figure | 12 | 12 | 12 |
| teacher_description | 5 | 5 | 5 |
| off_figure | 5 | 5 | 5 |
| untouchable | 3 | 3 | 3 |
| injection | 3 | 3 | 3 |
| cross_description | 1 | 1 | 1 |
| image | 6 | 6 | 5 |

Misses and flags:

- b44 "What does the occipital lobe do?": words outside the figure: information. Said: "The occipital lobe makes sense of information from your eyes."
- b45 "What does this part do?": words outside the figure: take. Said: "The occipital lobe makes sense of what your eyes take in."
- b46 "Which part helps me see?": words outside the figure: take. Said: "The occipital lobe makes sense of what your eyes take in."
- b68 "What shape is the temporal lobe?": words outside the figure: end, long, round. Said: "The temporal lobe is long with a round end."
- b69 "Which lobe is the biggest?": words outside the figure: covers. Said: "The frontal lobe is the biggest lobe. It covers the front part of the brain."
- b70 "What is at the top of the brain?": cited ['frontal lobe', 'parietal lobe', 'temporal lobe'], must nothing, may ['frontal lobe', 'parietal lobe']. Said: "The frontal lobe and the parietal lobe are at the top of the brain. The temporal lobe is below them."

