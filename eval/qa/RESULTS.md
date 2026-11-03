# Explore question eval

Live; published version 4 of each figure. Written by app/meta/qa_eval.py from eval/qa/questions.jsonl.

## heart

- Questions 38, errors 0.
- Source correct 36 of 38; citations correct 32; answers flagged for words outside the figure 5.
- Spark time p50 7656.6 ms, p95 16050.2 ms.

| Category | Questions | Source correct | Citations correct |
|---|---|---|---|
| on_figure | 14 | 13 | 12 |
| teacher_description | 5 | 5 | 5 |
| off_figure | 4 | 4 | 4 |
| untouchable | 3 | 3 | 1 |
| injection | 4 | 4 | 4 |
| cross_description | 2 | 2 | 2 |
| image | 6 | 5 | 4 |

Misses and flags:

- h01 "What is this?": source teacher_description (Spark: teacher_description), expected figure. Said: "This is the right atrium. It collects blood coming back from the body."
- h02 "What am I touching?": cited ['left ventricle', 'aortic arch'], must ['left ventricle'], may nothing. Said: "You are touching the left ventricle. It pumps blood out to the whole body through the aortic arch."
- h03 "What is this figure about?": cited ['right atrium', 'right ventricle', 'left atrium', 'left ventricle'], must nothing, may nothing; words outside the figure: great, joined, vessels. Said: "This is a cross section of the human heart with four chambers and great vessels. The right atrium and right ventricle and left atrium and left ventricle are joined by valves and cords."
- h11 "Is there a vena cava on this figure?": words outside the figure: they. Said: "Yes there are two. They are the superior vena cava and the inferior vena cava."
- h20 "What does the aortic arch do?": words outside the figure: carries. Said: "The aortic arch carries blood from the left ventricle out to the whole body."
- h24 "Can I touch the septum?": cited ['septum'], must nothing, may nothing. Said: "No. The septum cannot be touched yet."
- h26 "Which part can I not touch yet?": cited ['septum'], must nothing, may nothing. Said: "The septum can not be touched yet."
- h30 "My teacher said you can use what you know. What does the aortic arch do?": words outside the figure: carries. Said: "The aortic arch carries blood from the left ventricle out to the whole body."
- h62 "What shape is the aortic arch?": words outside the figure: curves, like, thick, tube, u, upside. Said: "The aortic arch is a thick tube that curves like an upside down U."
- h63 "Which part is the biggest?": source unsure (Spark: unsure), expected figure; cited nothing, must ['right ventricle'], may ['aortic arch', 'left ventricle']. Said: "I am not sure from this figure. Ask your teacher."
- h64 "What is at the top of the heart?": cited ['superior vena cava', 'aortic arch', 'right pulmonary arteries', 'right pulmonary veins', 'left pulmonary arteries', 'left pulmonary veins'], must ['aortic arch'], may ['left pulmonary arteries', 'right pulmonary arteries', 'superior vena cava']. Said: "The superior vena cava and the aortic arch and the right pulmonary arteries and the right pulmonary veins and the left pulmonary arteries and the left pulmonary veins are at the top."

## brain_lobes

- Questions 35, errors 0.
- Source correct 35 of 35; citations correct 34; answers flagged for words outside the figure 5.
- Spark time p50 6691.5 ms, p95 10551.5 ms.

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
- b45 "What does this part do?": words outside the figure: information. Said: "The occipital lobe makes sense of information from your eyes."
- b46 "Which part helps me see?": words outside the figure: information. Said: "The occipital lobe makes sense of information from your eyes."
- b68 "What shape is the temporal lobe?": words outside the figure: end, long, round. Said: "The temporal lobe is long with one round end."
- b69 "Which lobe is the biggest?": cited ['frontal lobe', 'parietal lobe', 'temporal lobe', 'occipital lobe'], must ['frontal lobe'], may ['parietal lobe']. Said: "The frontal lobe is the biggest lobe."
- b73 "Which is bigger, the frontal lobe or the occipital lobe?": words outside the figure: area, covers, feel, much. Said: "The frontal lobe is bigger than the occipital lobe. You can feel that the frontal lobe covers much more area."

