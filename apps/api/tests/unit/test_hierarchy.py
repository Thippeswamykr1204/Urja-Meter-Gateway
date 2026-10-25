from app.domain.hierarchy import reconstruct_hierarchy
from app.domain.models import QualityFlag


def test_hierarchy_flags_orphans_and_cycles() -> None:
    roots = reconstruct_hierarchy(
        [
            {"id": "root", "name": "Root"},
            {"id": "child", "parent_id": "root"},
            {"id": "orphan", "parent_id": "missing"},
            {"id": "cycle-a", "parent_id": "cycle-b"},
            {"id": "cycle-b", "parent_id": "cycle-a"},
        ]
    )
    orphan = next(node for node in roots if node.id == "orphan")
    cycle = next(node for node in roots if node.id == "cycle-a")
    assert QualityFlag.ORPHAN in orphan.quality.flags
    assert QualityFlag.CYCLE in cycle.quality.flags
    assert roots[0].children[0].id == "child"
