import itertools
from typing import Optional, NoReturn, FrozenSet

from jellycc.utils.error import CCError
from jellycc.utils.source import SourceInput, SourceInputState, SrcLoc


Whitespaces = frozenset(" \t\r\n")
InlineWhitespaces = frozenset(" \t")
Linebreaks = frozenset("\r\n")
Quotes = frozenset("'\"")
ControlCharacters = frozenset(itertools.chain(range(0, 32), (127, )))
Punctuation = frozenset("!#$%&'\"()*+,-./:;<=>?[\\]^_`{}|~")
SelfEscapes = frozenset(itertools.chain(Punctuation))
Escapes = {
	'n': '\n',
	'r': '\r',
	't': '\t',
	'0': '\0'
}
Hex = {
	'0': 0,
	'1': 1,
	'2': 2,
	'3': 3,
	'4': 4,
	'5': 5,
	'6': 6,
	'7': 7,
	'8': 8,
	'9': 9,
	'a': 10,
	'b': 11,
	'c': 12,
	'd': 13,
	'e': 14,
	'f': 15,
	'A': 10,
	'B': 11,
	'C': 12,
	'D': 13,
	'E': 14,
	'F': 15,
}
NZDigits = frozenset("123456789")
Digits = frozenset("0123456789")
IdStartChars = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_")
IdChars = frozenset(itertools.chain(IdStartChars, Digits))


class ParserBase:
	def __init__(self, input: SourceInput) -> None:
		self.input: SourceInput = input

	def peek(self) -> Optional[str]:
		return self.input.peek()

	def advance(self) -> Optional[str]:
		return self.input.advance()

	def save(self) -> SourceInputState:
		return self.input.save()

	def restore(self, state: SourceInputState) -> None:
		self.input.restore(state)

	def loc(self) -> SrcLoc:
		return self.input.loc()

	def report(self, message: str, loc: Optional[SrcLoc] = None) -> NoReturn:
		if loc is None:
			loc = self.loc()
		raise CCError(loc, message)

	def expect(self, ch: str) -> None:
		if self.peek() != ch:
			self.report(f"expected '{ch}'")
		self.advance()

	def lookahead(self, token: str) -> bool:
		savepoint = self.input.save()
		pos = 0
		while True:
			if len(token) <= pos:
				return True
			ch = self.peek()
			if ch == token[pos]:
				self.advance()
				pos += 1
			else:
				break
		self.input.restore(savepoint)
		return False

	def skip_line(self) -> None:
		while True:
			ch = self.peek()
			if ch is None:
				break
			if ch in Linebreaks:
				self.skip_nl()
				break
			self.advance()

	def skip_empty_line(self) -> None:
		while True:
			ch = self.peek()
			if ch is None:
				break
			elif ch in Linebreaks:
				self.skip_nl()
				break
			elif ch in InlineWhitespaces:
				self.advance()
			elif ch == '#':
				return self.skip_line()
			else:
				self.report("expected empty line")

	def skip_ws(self) -> None:
		while True:
			ch = self.peek()
			if ch is None:
				break
			if ch == '#':
				self.advance()
				self.skip_line()
			elif ch in Whitespaces:
				self.advance()
			else:
				break

	def skip_inline_ws(self) -> None:
		while True:
			ch = self.peek()
			if ch is None:
				break
			if ch in InlineWhitespaces:
				self.advance()
			else:
				break

	def skip_nl(self) -> None:
		if self.peek() == '\r':
			self.advance()
		if self.peek() == '\n':
			self.advance()

	def parse_int(self) -> int:
		ch = self.peek()
		sign = 1
		acc = 0

		if ch == '-':
			sign = -1
			self.advance()
			ch = self.peek()

		if ch == '0':
			self.advance()
			return 0

		if ch not in NZDigits:
			self.report("expected integer")

		while True:
			ch = self.peek()
			if ch in Digits:
				acc = acc * 10 + (ord(ch) - ord('0'))
				self.advance()
			else:
				break

		return acc * sign

	def parse_hexdig(self) -> int:
		ch = self.peek()
		if ch not in Hex:
			self.report("expected hex digit")
		self.advance()
		return Hex[ch]

	def _pase_hexcode(self, digits: int) -> str:
		acc = 0
		for i in range(digits):
			acc = acc * 16 + self.parse_hexdig()
		return chr(acc)

	def parse_esc(self) -> str:
		ch = self.peek()
		if ch in SelfEscapes:
			self.advance()
			return ch
		if ch in Escapes:
			self.advance()
			return Escapes[ch]
		if ch == 'x':
			self.advance()
			return self._pase_hexcode(2)
		elif ch == 'u':
			self.advance()
			return self._pase_hexcode(4)
		elif ch == 'U':
			self.advance()
			return self._pase_hexcode(8)
		else:
			self.report("invalid escape sequence")

	def parse_string(self) -> str:
		ch = self.peek()
		if (ch is None) or (ch not in Quotes):
			self.report("expected string")
		open_ch = ch
		self.advance()
		s = []
		while True:
			ch = self.peek()
			if (ch is None) or (ch == open_ch):
				break
			elif ch == '\\':
				self.advance()
				s.append(self.parse_esc())
			elif ch in ControlCharacters:
				self.report("unexpected character inside string literal")
			else:
				s.append(ch)
				self.advance()
		self.expect(open_ch)
		return ''.join(s)

	def parse_id(self) -> str:
		ch = self.peek()
		s = []
		if ch not in IdStartChars:
			self.report("expected identifier")
		self.advance()
		s.append(ch)
		while True:
			ch = self.peek()
			if ch in IdChars:
				s.append(ch)
				self.advance()
			else:
				break
		return ''.join(s)

	def collect(self, chars: FrozenSet[str]) -> str:
		s = []
		while True:
			ch = self.peek()
			if ch in chars:
				s.append(ch)
				self.advance()
			else:
				break
		return ''.join(s)
