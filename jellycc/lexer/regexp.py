from abc import abstractmethod
from typing import Iterable

from jellycc.lexer.nfa import NFAState, NFAContext, clone
from jellycc.utils.source import SrcLoc


class Re:
	def __init__(self) -> None:
		pass

	@abstractmethod
	def build_nfa(self, ctx: NFAContext, begin: NFAState, end: NFAState) -> None:
		pass


class ReEmpty(Re):
	def __init__(self) -> None:
		super().__init__()

	def build_nfa(self, ctx: NFAContext, begin: NFAState, end: NFAState) -> None:
		begin.add_etrans(end)


class ReChar(Re):
	def __init__(self, chars: Iterable[int]) -> None:
		super().__init__()
		self.chars = frozenset(chars)

	def build_nfa(self, ctx: NFAContext, begin: NFAState, end: NFAState) -> None:
		begin.add_trans(self.chars, end)


class ReConcat(Re):
	def __init__(self, lhs: Re, rhs: Re) -> None:
		super().__init__()
		self.lhs = lhs
		self.rhs = rhs

	def build_nfa(self, ctx: NFAContext, begin: NFAState, end: NFAState) -> None:
		mid = NFAState()
		self.lhs.build_nfa(ctx, begin, mid)
		self.rhs.build_nfa(ctx, mid, end)


class ReChoice(Re):
	def __init__(self, lhs: Re, rhs: Re) -> None:
		super().__init__()
		self.lhs = lhs
		self.rhs = rhs

	def build_nfa(self, ctx: NFAContext, begin: NFAState, end: NFAState) -> None:
		left_begin = NFAState()
		left_end = NFAState()
		right_begin = NFAState()
		right_end = NFAState()

		begin.add_etrans(left_begin)
		begin.add_etrans(right_begin)
		left_end.add_etrans(end)
		right_end.add_etrans(end)

		self.lhs.build_nfa(ctx, left_begin, left_end)
		self.rhs.build_nfa(ctx, right_begin, right_end)


class ReStar(Re):
	def __init__(self, re: Re) -> None:
		super().__init__()
		self.re = re

	def build_nfa(self, ctx: NFAContext, begin: NFAState, end: NFAState) -> None:
		mid_begin = NFAState()
		mid_end = NFAState()

		begin.add_etrans(mid_begin)
		begin.add_etrans(end)
		mid_end.add_etrans(mid_begin)
		mid_end.add_etrans(end)

		self.re.build_nfa(ctx, mid_begin, mid_end)


class ReRef(Re):
	def __init__(self, loc: SrcLoc, name: str) -> None:
		super().__init__()
		self.loc = loc
		self.name = name

	def build_nfa(self, ctx: NFAContext, begin: NFAState, end: NFAState) -> None:
		fragment_begin, fragment_end = clone(*ctx.get_fragment(self.loc, self.name))
		begin.add_etrans(fragment_begin)
		fragment_end.add_etrans(end)