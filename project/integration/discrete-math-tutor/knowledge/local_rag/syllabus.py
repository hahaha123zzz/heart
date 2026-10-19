"""DeepTutor 有序课程单元；covered 由学习者确认，不推断掌握。"""
from dataclasses import dataclass, field, asdict


@dataclass(slots=True)
class SyllabusUnit:
    """One ordered unit of what this course is supposed to cover.

    The syllabus is what gives progress a denominator. Without it "you have
    done 6 questions" answers nothing — six out of what? A course that declares
    twelve weeks can finally say which of them are still untouched.

    ``covered`` is set by the learner, never inferred. Matching a unit's topics
    against mastered knowledge points would take a guess and render it as a
    number, and a progress bar that quietly guesses is worse than no progress
    bar. The evidence is shown next to the checkbox instead, so the learner
    decides with the numbers in front of them.
    """

    id: str
    position: int
    title: str
    topics: list[str] = field(default_factory=list)
    covered: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
