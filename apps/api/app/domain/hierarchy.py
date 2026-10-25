from collections.abc import Mapping, Sequence
from typing import Any

from app.domain.models import HierarchyNode, QualityFlag, QualitySummary


def reconstruct_hierarchy(records: Sequence[Mapping[str, Any]]) -> list[HierarchyNode]:
    """Build a finite tree while keeping duplicate, orphan, and cycle evidence visible."""
    nodes: list[HierarchyNode] = []
    by_id: dict[str, list[HierarchyNode]] = {}
    for index, record in enumerate(records):
        node_id = str(record.get("id") or record.get("node_id") or "").strip()
        if not node_id:
            continue
        node = HierarchyNode(
            id=node_id,
            record_id=f"{node_id}#{index}",
            name=str(record.get("name") or record.get("label") or node_id),
            node_type=str(record.get("node_type") or record.get("type") or "unknown"),
            parent_id=str(record["parent_id"]) if record.get("parent_id") else None,
            meter_count=_safe_count(record.get("meter_count")),
        )
        nodes.append(node)
        by_id.setdefault(node_id, []).append(node)

    for node_id, duplicates in by_id.items():
        if len(duplicates) > 1:
            for node in duplicates:
                node.quality = QualitySummary(
                    flags=[QualityFlag.DUPLICATE], issue_count=1, notes=[f"duplicate hierarchy id: {node_id}"]
                )

    roots: list[HierarchyNode] = []
    for node in nodes:
        if node.parent_id is None:
            roots.append(node)
            continue
        parent = by_id.get(node.parent_id, [None])[0]
        if parent is None:
            node.quality = _add_quality(node.quality, QualityFlag.ORPHAN, "parent id was not present")
            roots.append(node)
            continue
        if _would_cycle(node, parent, by_id):
            node.quality = _add_quality(node.quality, QualityFlag.CYCLE, "parent relationship forms a cycle")
            roots.append(node)
            continue
        parent.children.append(node)
    return roots


def _safe_count(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _add_quality(quality: QualitySummary, flag: QualityFlag, note: str) -> QualitySummary:
    return QualitySummary(
        flags=list(dict.fromkeys([*quality.flags, flag])),
        issue_count=quality.issue_count + 1,
        notes=[*quality.notes, note],
    )


def _would_cycle(node: HierarchyNode, parent: HierarchyNode, by_id: dict[str, list[HierarchyNode]]) -> bool:
    visited: set[str] = set()
    current: HierarchyNode | None = parent
    while current is not None:
        if current.id == node.id or current.id in visited:
            return True
        visited.add(current.id)
        current = by_id.get(current.parent_id or "", [None])[0]
    return False
