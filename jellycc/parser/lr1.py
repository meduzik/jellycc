from typing import NamedTuple, Dict, Union, Tuple

from jellycc.parser.grammar import SymbolTerminal, SymbolNonTerminal, Production


class LR1State:
	__slots__ = ("actions", "gotos")

	def __init__(self) -> None:
		self.actions: Dict[SymbolTerminal, Action] = dict()
		self.gotos: Dict[SymbolNonTerminal, LR1State] = dict()


_reduce_cache: Dict[Tuple[SymbolNonTerminal, Production], 'Reduce'] = dict()


class Reduce(NamedTuple):
	nt: SymbolNonTerminal
	prod: Production

	@staticmethod
	def get(nt: SymbolNonTerminal, prod: Production) -> 'Reduce':
		key = (nt, prod)
		if key not in _reduce_cache:
			_reduce_cache[key] = Reduce(nt, prod)
		return _reduce_cache[key]

	def __str__(self) -> str:
		return f"reduce {self.nt.to_inline_str()} -> {self.prod}"


class Shift(NamedTuple):
	state: LR1State


class AcceptType:
	def __init__(self) -> None:
		pass


class RejectType:
	def __init__(self) -> None:
		pass


Accept = AcceptType()
Reject = RejectType()
Action = Union[Shift, Reduce, AcceptType, RejectType]
