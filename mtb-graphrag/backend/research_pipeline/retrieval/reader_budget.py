"""Pack complete source units; deferred text is never a scientific abstention."""


def pack_reader_units(unit_ids: tuple[str, ...], units: dict, maximum_chars: int | None) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if maximum_chars is None:
        return unit_ids, ()
    if type(maximum_chars) is not int or maximum_chars < 1:
        raise ValueError('Reader character budget must be positive')
    selected, deferred, used = [], [], 0
    for uid in unit_ids:
        size = len(str(units[uid].get('text') or ''))
        if used + size <= maximum_chars:
            selected.append(uid)
            used += size
        else:
            deferred.append(uid)
    return tuple(selected), tuple(deferred)
