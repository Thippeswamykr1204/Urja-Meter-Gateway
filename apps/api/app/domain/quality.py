from collections import Counter
from collections.abc import Iterable

from app.domain.models import QualityFlag, QualitySummary


def summarize_quality(qualities: Iterable[QualitySummary]) -> QualitySummary:
    flags: list[QualityFlag] = []
    notes: list[str] = []
    issue_count = 0
    for quality in qualities:
        issue_count += quality.issue_count
        for flag in quality.flags:
            if flag not in flags:
                flags.append(flag)
        notes.extend(quality.notes)
    return QualitySummary(flags=flags, issue_count=issue_count, notes=notes[:20])


def quality_report(qualities: Iterable[QualitySummary], total_records: int) -> tuple[int, dict[str, int], list[str]]:
    counts: Counter[str] = Counter()
    notes: list[str] = []
    issue_count = 0
    for quality in qualities:
        issue_count += quality.issue_count
        counts.update(flag.value for flag in quality.flags)
        notes.extend(quality.notes)
    return issue_count, dict(counts), notes[:20]
