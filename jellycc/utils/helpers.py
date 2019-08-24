from typing import Iterable, TypeVar


T = TypeVar('T')


def head(itr: Iterable[T]) -> T:
	for item in itr:
		return item
	raise RuntimeError("sequence has no items")
