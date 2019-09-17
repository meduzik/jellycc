from typing import Iterable, TypeVar, Callable, Generator, List, Optional, Dict

T = TypeVar('T')


class _SCCInfo:
	def __init__(self, node: T):
		self.index: Optional[int] = None
		self.lowlink: Optional[int] = None
		self.onstack: bool = False
		self.node: T = node


def topological_sort(
	nodes: Iterable[T],
	walker: Callable[
		[T],
		Generator[T, None, None]
	]
) -> Generator[List[T], None, None]:
	index: int = 0
	stack: List[_SCCInfo] = []
	data: Dict[T, _SCCInfo] = dict()
	worklist: List[_SCCInfo] = []

	def get_info(node):
		if node not in data:
			v = _SCCInfo(node)
			worklist.append(v)
			data[node] = v
		return data[node]

	def strongconnect(v):
		nonlocal index
		v.index = index
		v.lowlink = index
		index += 1
		stack.append(v)
		v.onstack = True

		for node in walker(v.node):
			w = get_info(node)
			if w.index is None:
				yield from strongconnect(w)
				v.lowlink = min(v.lowlink, w.lowlink)
			elif w.onstack:
				v.lowlink = min(v.lowlink, w.index)

		if v.lowlink == v.index:
			scc = []

			while True:
				w = stack.pop()
				w.onstack = False
				scc.append(w.node)
				w.scc = scc
				if w == v:
					break

			yield scc

	for node in nodes:
		get_info(node)

	i = 0
	while i < len(worklist):
		v = worklist[i]
		if v.index is None:
			yield from strongconnect(v)
		i += 1
