"""校注覆盖盲区引擎（annotation coverage blind spots）。

基于项目**已保存**的转写片段与校注，按说话人统计发言被校注覆盖的情况，
全部按半开区间 ``[start, end)`` 计算：

1. **发言区间**：忽略空说话人（空串 / 纯空白）与零长度 / 非法片段
   （``end <= start``、时间非数字）；同一说话人**重叠或首尾相接**的片段
   先合并为互不相连的区间，合并后的总时长即该说话人的实际发言时长。
   多人同时发言的时段分别计入各自说话人，互不影响；
2. **覆盖区间**：只有与说话人**同名**（去首尾空白后精确相等）的校注才能
   覆盖其发言；同一说话人的校注同样先合并（重叠校注不重复计时），再
   裁剪到发言区间之内——校注超出发言的部分不计入覆盖时长；
3. **盲区**：发言区间中未被任何同名校注覆盖的部分，按时间顺序列出。

整个过程只读项目文档，不写回任何数据。
"""
from __future__ import annotations

import math
from typing import Any

EPS = 1e-9


def _r3(value: float) -> float:
    return round(float(value) + 0.0, 3)


def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out or math.isinf(out):  # NaN / ±inf
        return None
    return out


def _speaker_of(raw: dict) -> str:
    name = raw.get("speaker")
    return name.strip() if isinstance(name, str) else ""


def _merge_ranges(ranges: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Merge overlapping / touching half-open ranges; output is sorted."""
    if not ranges:
        return []
    ranges = sorted(ranges)
    merged = [list(ranges[0])]
    for start, end in ranges[1:]:
        if start <= merged[-1][1] + EPS:
            if end > merged[-1][1]:
                merged[-1][1] = end
        else:
            merged.append([start, end])
    return [(s, e) for s, e in merged]


def _clip_to(ranges: list[tuple[float, float]],
             bounds: list[tuple[float, float]]
             ) -> list[tuple[float, float]]:
    """Intersect two sorted, disjoint range lists (two-pointer sweep)."""
    out: list[tuple[float, float]] = []
    i = j = 0
    while i < len(ranges) and j < len(bounds):
        a0, a1 = ranges[i]
        b0, b1 = bounds[j]
        lo, hi = max(a0, b0), min(a1, b1)
        if hi - lo > EPS:
            out.append((lo, hi))
        if a1 <= b1:
            i += 1
        else:
            j += 1
    return out


def _subtract(interval: tuple[float, float],
              covered: list[tuple[float, float]]
              ) -> list[tuple[float, float]]:
    """Parts of ``interval`` not covered by the (merged) ``covered`` ranges."""
    start, end = interval
    pieces: list[tuple[float, float]] = []
    cursor = start
    for cs, ce in covered:
        if ce <= cursor + EPS:
            continue
        if cs >= end - EPS:
            break
        if cs > cursor + EPS:
            pieces.append((cursor, min(cs, end)))
        cursor = max(cursor, ce)
        if cursor >= end - EPS:
            break
    if cursor < end - EPS:
        pieces.append((cursor, end))
    return [(s, e) for s, e in pieces if e - s > EPS]


def _valid_intervals(items: Any) -> dict[str, list[tuple[float, float]]]:
    """Group well-formed ``(start, end)`` intervals by trimmed speaker name.

    Items without a speaker name, with non-numeric bounds or with
    ``end <= start`` are skipped.  Dict key order keeps first appearance.
    """
    out: dict[str, list[tuple[float, float]]] = {}
    for raw in items or []:
        if not isinstance(raw, dict):
            continue
        name = _speaker_of(raw)
        if not name:
            continue
        start, end = _num(raw.get("start")), _num(raw.get("end"))
        if start is None or end is None or end <= start:
            continue
        out.setdefault(name, []).append((start, end))
    return out


def compute_coverage(document: dict, speaker: str | None = None) -> dict:
    """Per-speaker speech / coverage durations and blind-spot intervals.

    ``speaker`` (optional, exact name after trimming) restricts the report
    to one speaker; an unknown name yields an empty ``speakers`` list.
    Speakers appear in first-appearance order of their speech segments;
    annotation-only names (no speech) are not listed.
    """
    doc = document or {}
    speech_raw = _valid_intervals(doc.get("segments", []))
    ann_raw = _valid_intervals(doc.get("annotations", []))

    wanted = speaker.strip() if isinstance(speaker, str) else ""
    wanted = wanted or None

    speakers_out: list[dict] = []
    total_speech = total_covered = total_blind = 0.0
    blind_count = 0
    for name, seg_ranges in speech_raw.items():
        if wanted is not None and name != wanted:
            continue
        speech = _merge_ranges(seg_ranges)
        # only same-name annotations cover; merged first so overlapping
        # annotations never count twice, then clipped into the speech
        covered = _clip_to(_merge_ranges(ann_raw.get(name, [])), speech)
        blind: list[tuple[float, float]] = []
        for iv in speech:
            blind.extend(_subtract(iv, covered))

        speech_seconds = sum(e - s for s, e in speech)
        covered_seconds = sum(e - s for s, e in covered)
        blind_seconds = sum(e - s for s, e in blind)
        speakers_out.append({
            "speaker": name,
            "segmentCount": len(seg_ranges),
            "annotationCount": len(ann_raw.get(name, [])),
            "speechSeconds": _r3(speech_seconds),
            "coveredSeconds": _r3(covered_seconds),
            "uncoveredSeconds": _r3(blind_seconds),
            "coverageRate": (round(covered_seconds / speech_seconds, 4)
                             if speech_seconds > EPS else 0.0),
            "speechIntervals": [
                {"start": _r3(s), "end": _r3(e)} for s, e in speech],
            "coveredIntervals": [
                {"start": _r3(s), "end": _r3(e)} for s, e in covered],
            "blindSpots": [
                {"start": _r3(s), "end": _r3(e), "duration": _r3(e - s)}
                for s, e in blind],
        })
        total_speech += speech_seconds
        total_covered += covered_seconds
        total_blind += blind_seconds
        blind_count += len(blind)

    return {
        "speakers": speakers_out,
        "summary": {
            "speakerCount": len(speakers_out),
            "speechSeconds": _r3(total_speech),
            "coveredSeconds": _r3(total_covered),
            "uncoveredSeconds": _r3(total_blind),
            "coverageRate": (round(total_covered / total_speech, 4)
                             if total_speech > EPS else 0.0),
            "blindSpotCount": blind_count,
        },
    }
