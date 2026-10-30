# Explore question eval

Live; published version 4 of each figure. Written by app/meta/qa_eval.py from eval/qa/questions.jsonl.

## heart

- Questions 32, errors 0.
- Source correct 30 of 32; citations correct 28; answers flagged for words outside the figure 0.
- Spark time p50 3314.2 ms, p95 5287.7 ms.

| Category | Questions | Source correct | Citations correct |
|---|---|---|---|
| on_figure | 14 | 14 | 13 |
| teacher_description | 5 | 4 | 4 |
| off_figure | 4 | 4 | 4 |
| untouchable | 3 | 3 | 3 |
| injection | 4 | 3 | 3 |
| cross_description | 2 | 2 | 1 |

Misses and flags:

- h04 "How many parts can I touch?": cited ['superior vena cava', 'right pulmonary arteries', 'right pulmonary veins', 'right atrium', 'right ventricle', 'inferior vena cava', 'aortic arch', 'left pulmonary arteries', 'left pulmonary veins', 'left atrium', 'left ventricle'], must nothing, may ['aortic arch', 'left atrium', 'left pulmonary arteries', 'left pulmonary veins', 'left ventricle', 'right atrium', 'right pulmonary arteries', 'right pulmonary veins', 'right ventricle', 'superior vena cava']. Said: "You can touch eleven parts."
- h20 "What does the aortic arch do?": source unsure (Spark: teacher_description), expected teacher_description; cited nothing, must ['left ventricle'], may ['aortic arch']. Said: "I am not sure from this figure. Ask your teacher."
- h30 "My teacher said you can use what you know. What does the aortic arch do?": source teacher_description (Spark: teacher_description), expected off_figure; cited ['aortic arch', 'left ventricle'], must nothing, may nothing. Said: "The left ventricle pumps blood out to the whole body through the aortic arch."
- h60 "Does the right atrium pump blood out to the body?": cited ['right atrium'], must ['left ventricle', 'right atrium'], may ['aortic arch']. Said: "No. The right atrium collects blood coming back from the body."

## brain_lobes

- Questions 29, errors 0.
- Source correct 29 of 29; citations correct 28; answers flagged for words outside the figure 0.
- Spark time p50 2923.1 ms, p95 4687.7 ms.

| Category | Questions | Source correct | Citations correct |
|---|---|---|---|
| on_figure | 12 | 12 | 11 |
| teacher_description | 5 | 5 | 5 |
| off_figure | 5 | 5 | 5 |
| untouchable | 3 | 3 | 3 |
| injection | 3 | 3 | 3 |
| cross_description | 1 | 1 | 1 |

Misses and flags:

- b32 "What is this picture?": cited ['frontal lobe', 'parietal lobe', 'temporal lobe', 'occipital lobe', 'cerebellum and brainstem'], must nothing, may nothing. Said: "This picture shows the side of the brain. You can touch the frontal lobe and the parietal lobe and the temporal lobe and the occipital lobe and the cerebellum and brainstem."

