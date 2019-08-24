from typing import List, FrozenSet, Tuple, Callable, Set, Dict, Optional

from jellycc.project.grammar import Terminal
from jellycc.utils.error import CCError
from jellycc.utils.source import SrcLoc

from typing import TYPE_CHECKING
if TYPE_CHECKING:
	from jellycc.lexer.regexp import Re


class NFARule:
	def __init__(self, order: int, loc: SrcLoc, terminal: 'Terminal') -> None:
		self.order: int = order
		self.loc: SrcLoc = loc
		self.terminal: Terminal = terminal


class NFAState:
	def __init__(self) -> None:
		self.etrans: List[NFAState] = []
		self.trans: List[Tuple[FrozenSet[int], NFAState]] = []
		self.rule: Optional[NFARule] = None

	def add_etrans(self, state: 'NFAState') -> None:
		self.etrans.append(state)

	def add_trans(self, chars: FrozenSet[int], state: 'NFAState') -> None:
		self.trans.append((chars, state))

	def visit(self, visitor: Callable[['NFAState'], None]) -> None:
		visited: Set[NFAState] = set()

		def _visit(state: 'NFAState') -> None:
			if state in visited:
				return
			visited.add(state)
			visitor(state)
			for target_state in state.etrans:
				_visit(target_state)
			for chars, target_state in state.trans:
				_visit(target_state)

		_visit(self)


class NFAFragment:
	def __init__(self, loc: SrcLoc, name: str, re: 'Re') -> None:
		self.loc: SrcLoc = loc
		self.name: str = name
		self.re: 'Re' = re
		self.nfa: Optional[Tuple[NFAState, NFAState]] = None

	def build(self, ctx: 'NFAContext') -> Tuple[NFAState, NFAState]:
		if not self.nfa:
			begin = NFAState()
			end = NFAState()
			self.nfa = (begin, end)
			self.re.build_nfa(ctx, begin, end)
		return self.nfa


class NFAContext:
	def __init__(self) -> None:
		self.fragments: Dict[str, NFAFragment] = dict()

	def add_fragment(self, loc: SrcLoc, name: str, re: 'Re') -> None:
		if name in self.fragments:
			raise CCError(loc, f"duplicate fragment '{name}', previous definition at {self.fragments[name].loc}")
		self.fragments[name] = NFAFragment(loc, name, re)

	def get_fragment(self, loc: SrcLoc, name: str) -> Tuple[NFAState, NFAState]:
		if name not in self.fragments:
			raise CCError(loc, f"fragment '{name}' not found")
		fragment = self.fragments[name]
		return fragment.build(self)


def clone(begin: NFAState, end: NFAState) -> Tuple[NFAState, NFAState]:
	remap: Dict[NFAState, NFAState] = dict()

	def get_clone(state: NFAState) -> NFAState:
		if state in remap:
			return remap[state]
		new_state = NFAState()
		remap[state] = new_state
		for target_state in state.etrans:
			new_state.etrans.append(get_clone(target_state))
		for chars, target_state in state.trans:
			new_state.trans.append((chars, get_clone(target_state)))
		return new_state

	return get_clone(begin), get_clone(end)

