"""The question eval's scorer (app/meta/qa_eval.py): the set's shape, and its check for
words in an answer that the figure never gave."""

from app.meta import qa_eval


def test_the_set_has_at_least_25_questions_a_figure_in_every_category() -> None:
    qs = qa_eval.load_questions()
    for fig in qa_eval.FIGURES:
        mine = [q for q in qs if q["figure"] == fig]
        assert len(mine) >= 25
        assert {q["category"] for q in mine} == {
            "on_figure", "teacher_description", "off_figure", "untouchable", "injection",
            "cross_description",
        }  # fmt: skip
    assert len({q["id"] for q in qs}) == len(qs)
    assert all(
        set(q["sources"]) <= {"figure", "teacher_description", "off_figure", "unsure"} for q in qs
    )


def test_words_outside_what_spark_was_given_are_flagged() -> None:
    given = "Parts: r14 left ventricle. Teacher's description: pumps blood to the body."
    assert qa_eval.outside_words("The left ventricle pumps blood to the body.", given) == []
    assert qa_eval.outside_words("It pumps oxygen-rich blood at high pressure.", given) == [
        "high", "oxygen", "pressure", "rich",
    ]  # fmt: skip
    assert qa_eval.outside_words("There are two parts above it.", given) == []
