from typing import Iterable, TypeVar, Generator, List

T = TypeVar('T')


def head(itr: Iterable[T]) -> T:
	for item in itr:
		return item
	raise RuntimeError("sequence has no items")


def chunked(itr: Iterable[T], max_len: int) -> Generator[List[T], None, None]:
	it = iter(itr)
	while True:
		i = 0
		list = []
		try:
			while i < max_len:
				list.append(next(it))
				i += 1
			yield list
		except StopIteration:
			if len(list) > 0:
				yield list
			return
