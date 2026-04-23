"""קיבוץ נושאי שיעורים דומים (לדוגמה: 'אלגברה לינארית' ≈ 'אלגברא לינארית')."""
from __future__ import annotations

from collections import defaultdict

from rapidfuzz import fuzz


def group_similar_topics(
    topics: list[str], threshold: int = 70
) -> dict[str, list[str]]:
    """מקבץ נושאים דומים.

    מחזיר dict: {representative_topic: [topic1, topic2, ...]}.
    כל נושא שייך לקבוצה אחת בלבד.
    """
    topics = [t for t in topics if t and str(t).strip()]
    if not topics:
        return {}

    # סדר לפי תדירות: נושא נפוץ יותר הופך להיות "נציג"
    freq: dict[str, int] = defaultdict(int)
    for t in topics:
        freq[t.strip()] += 1
    sorted_topics = sorted(freq.keys(), key=lambda t: (-freq[t], t))

    groups: dict[str, list[str]] = {}
    assigned: set[str] = set()

    for topic in sorted_topics:
        if topic in assigned:
            continue
        groups[topic] = [topic]
        assigned.add(topic)
        for other in sorted_topics:
            if other in assigned:
                continue
            similarity = fuzz.token_set_ratio(topic, other)
            if similarity >= threshold:
                groups[topic].append(other)
                assigned.add(other)

    return groups


def build_topic_map(
    topics: list[str], threshold: int = 70
) -> dict[str, str]:
    """מחזיר dict שממפה כל נושא מקורי לנושא הנציג של הקבוצה שלו."""
    groups = group_similar_topics(topics, threshold=threshold)
    mapping: dict[str, str] = {}
    for representative, variants in groups.items():
        for v in variants:
            mapping[v] = representative
    return mapping
