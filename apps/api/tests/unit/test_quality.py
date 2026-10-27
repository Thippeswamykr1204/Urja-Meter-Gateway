from app.domain.models import QualityFlag, QualitySummary
from app.domain.quality import quality_report, summarize_quality


def test_quality_summary_deduplicates_flags_and_limits_notes() -> None:
    result = summarize_quality(
        [
            QualitySummary(flags=[QualityFlag.MISSING], issue_count=1, notes=["missing"]),
            QualitySummary(flags=[QualityFlag.MISSING, QualityFlag.INVALID], issue_count=2, notes=["invalid"]),
        ]
    )
    assert result.flags == [QualityFlag.MISSING, QualityFlag.INVALID]
    assert result.issue_count == 3
    assert result.notes == ["missing", "invalid"]


def test_quality_report_counts_flags_and_recent_notes() -> None:
    issue_count, by_flag, notes = quality_report(
        [QualitySummary(flags=[QualityFlag.ORPHAN], issue_count=1, notes=["orphaned"]), QualitySummary()],
        2,
    )
    assert issue_count == 1
    assert by_flag == {"orphan": 1}
    assert notes == ["orphaned"]
