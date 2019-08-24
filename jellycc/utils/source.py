from typing import NamedTuple, Optional


class SrcLoc(NamedTuple('SrcLoc', (('file', str), ('line', int), ('col', int)))):
	__slots__ = ()

	def __str__(self) -> str:
		return f"{self.file}({self.line + 1}, {self.col + 1})"


SourceInputState = NamedTuple('SourceInputState', (('pos', int), ('line', int), ('col', int), ('rn', bool)))


class SourceInput:
	__slots__ = ('path', '_contents', '_pos', '_line', '_col', '_rn')

	def __init__(self, path: str, contents: str) -> None:
		self.path: str = path
		self._contents: str = contents
		self._pos: int = 0
		self._line: int = 0
		self._col: int = 0
		self._rn: bool = False

	def save(self) -> SourceInputState:
		return SourceInputState(self._pos, self._line, self._col, self._rn)

	def restore(self, state: SourceInputState) -> None:
		self._pos = state.pos
		self._line = state.line
		self._col = state.col
		self._rn = state.rn

	def loc(self) -> SrcLoc:
		return SrcLoc(self.path, self._line, self._col)

	def peek(self) -> Optional[str]:
		if self._pos >= len(self._contents):
			return None
		return self._contents[self._pos]

	def advance(self) -> Optional[str]:
		if self._pos >= len(self._contents):
			return None
		ch = self._contents[self._pos]
		if ch == '\n':
			if not self._rn:
				self._line += 1
				self._col = 0
			self._rn = False
		elif ch == '\r':
			self._rn = True
			self._line += 1
			self._col = 0
		else:
			self._rn = False
			self._col += 1
		self._pos += 1
		return ch


def source_file(path: str) -> SourceInput:
	with open(path, 'r') as fp:
		contents = fp.read()
	return SourceInput(path, contents)
