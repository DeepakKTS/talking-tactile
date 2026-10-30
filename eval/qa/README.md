# Explore question eval

`questions.jsonl` holds the questions; `app/meta/qa_eval.py` runs them through the same code as
`POST /api/ask` and writes `RESULTS.md` and `scores.json`. Each question names its figure, the
part under the finger and the parts touched before, the sources it accepts, the parts the answer
must cite and the parts it may cite.

## Rules for expectations

- `figure`: the answer comes from the published figure: its parts, their positions (computed in
  code), lines, groups, the title and summary, or the image.
- `teacher_description`: the answer comes from a teacher's description of a part.
- `off_figure`: the figure and the descriptions do not give the answer, including any question
  that tries to change the rules. Explore deflects it to the teacher in fixed words.
- `unsure`: what is asked or what the answer is cannot be told.
- An inference from teacher descriptions is grounded: it is `teacher_description`, and it must
  cite every part whose description it used. "What does the aortic arch do?" answered from the
  left ventricle's description ("pumps blood out to the whole body through the aortic arch")
  is grounded, and must cite the left ventricle; it may cite the aortic arch, the part it is
  about. The `cross_description` questions check that this holds.
- Citations: every part in `cite_must` is cited, and nothing outside `cite_must` and
  `cite_may`.
