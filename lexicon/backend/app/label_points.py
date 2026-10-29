"""Where a photo label's pin goes (card #819, 問題回報 #945).

The vision model answers (0, 0) when it cannot place a word, and coordinates
outside 0..1000 that the tagger clamps into a corner ((1, 1), (0, 1)...).
Neither is a place in the picture: 6,767 tags at (0, 0) drew pins in the
top-left corner of 1,428 published pictures. Such a point becomes its box's
centre when there is a box; otherwise the label has no point and is flagged
pointUngrounded (the App lists it under 「整張圖」 without a pin, card #631).
"""


def _xy(point):
    if not isinstance(point, (list, tuple)) or len(point) < 2:
        return None
    try:
        return float(point[0]), float(point[1])
    except (TypeError, ValueError):
        return None


def _box(box):
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        return None
    try:
        x1, y1, x2, y2 = (float(v) for v in box)
    except (TypeError, ValueError):
        return None
    return (x1, y1, x2, y2) if x2 > x1 and y2 > y1 else None


def placeholder(point) -> bool:
    """(0, 0) or a clamped corner: the model gave no usable place."""
    xy = _xy(point)
    return xy is not None and xy[0] in (0.0, 1.0) and xy[1] in (0.0, 1.0)


def anchor(tag: dict) -> tuple[list | None, bool]:
    """(point, ungrounded) for a tag; ungrounded means "no pin"."""
    box = _box(tag.get('box'))
    point = tag.get('point')
    if placeholder(point):
        if box:
            return [round((box[0] + box[2]) / 2, 4), round((box[1] + box[3]) / 2, 4)], False
        return None, True
    if tag.get('pointUngrounded') and not box:
        return None, True
    return point, False
