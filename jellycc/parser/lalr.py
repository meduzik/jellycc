from collections import defaultdict
from typing import NamedTuple, Iterable, FrozenSet, Set, List, Optional, Dict, Tuple, TypeVar, Union, Any
from itertools import chain

import sys

from jellycc.parser.grammar import Production, SymbolNonTerminal, SymbolTerminal, Symbol, ParserGrammar
from jellycc.parser.lr1 import Reduce, AcceptType, RejectType, LR1State, Shift, Accept
from jellycc.project.grammar import Terminal
from jellycc.utils.helpers import head
from jellycc.utils.source import SrcLoc


class LRActionShift(NamedTuple):
	target: 'LR0Set'

	def __str__(self) -> str:
		return f"shift {self.target.idx}"


class LRActionAccept:
	def __init__(self) -> None:
		pass

	def __str__(self) -> str:
		return "accept"


LRAction = Union[Reduce, LRActionShift, AcceptType]


class LR0Item(NamedTuple):
	nt: SymbolNonTerminal
	prod: Production
	offset: int

	def is_kernel(self) -> bool:
		if self.offset > 0 or self.nt.exported:
			return True
		return False


class LR1Item(NamedTuple):
	nt: SymbolNonTerminal
	prod: Production
	offset: int
	la: SymbolTerminal


class LR0Set:
	__slots__ = (
		'idx', 'kernel', 'nonkernel', 'goto',
		'lookahead', 'propagates', 'action_list',
		'goto_list', 'shift', 'actions', 'witness',
		'gen'
	)

	def __init__(self, idx: int, kernel: FrozenSet[LR0Item], nonkernel: FrozenSet[LR0Item]):
		self.idx: int = idx
		self.kernel: FrozenSet[LR0Item] = kernel
		self.nonkernel: FrozenSet[LR0Item] = nonkernel
		self.goto: Dict[Symbol, LR0Set] = dict()
		self.lookahead: Dict[LR0Item, Set[SymbolTerminal]] = defaultdict(lambda: set())
		self.propagates: Dict[LR0Item, Set[Tuple[LR0Set, LR0Item]]] = defaultdict(lambda: set())
		self.shift = LRActionShift(self)
		self.actions: Dict[SymbolTerminal, Set[LRAction]] = dict()
		self.gen: LR1State = LR1State()

	def __hash__(self) -> int:
		return hash(self.kernel)

	def __eq__(self, other: Any) -> bool:
		if not isinstance(other, LR0Set):
			return NotImplemented
		return other.kernel == self.kernel


T = TypeVar('T')


def extend_set(set: Set[T], values: Iterable[T]) -> bool:
	updated = False
	for value in values:
		if value not in set:
			set.add(value)
			updated = True
	return updated


class LRTable:
	def __init__(self) -> None:
		self.entries: Dict[SymbolNonTerminal, LR1State] = dict()
		self.states: List[LR1State] = []


class LALRBuilder:
	def __init__(self, grammar: ParserGrammar):
		self.grammar = grammar
		self.sharp = SymbolTerminal(Terminal(SrcLoc("", 0, 0), '#', '#'))
		self.states: List[LR0Set] = []
		self.terminal_list: List[SymbolTerminal] = []
		self.nonterminal_list: List[SymbolNonTerminal] = []
		self.entry: Dict[SymbolNonTerminal, LR0Set] = dict()

	def build(self) -> LRTable:
		print("fn")
		self.find_nullables()
		self.find_first()
		self.construct_sets()
		self.determine_lookaheads()
		self.propagate_lookaheads()
		self.construct_actions()
		self.resolve_conflicts()
		self.generate_table()

		table = LRTable()
		states_set: Set[LR1State] = set()

		def visit(state: LR1State) -> None:
			if state in states_set:
				return
			states_set.add(state)
			table.states.append(state)
			for target_state in state.gotos.values():
				visit(target_state)
			for action in state.actions.values():
				if isinstance(action, Shift):
					visit(action.state)

		for nt, lr0 in self.entry.items():
			table.entries[nt] = lr0.gen
			visit(lr0.gen)

		return table

	def generate_table(self) -> None:
		for state in self.states:
			for symbol, target in state.goto.items():
				if isinstance(symbol, SymbolNonTerminal):
					state.gen.gotos[symbol] = target.gen
			for terminal, actions in state.actions.items():
				action = head(actions)
				if isinstance(action, AcceptType) or isinstance(action, Reduce):
					state.gen.actions[terminal] = action
				elif isinstance(action, LRActionShift):
					state.gen.actions[terminal] = Shift(action.target.gen)
				else:
					raise RuntimeError("internal error: invalid action produced")

	def resolve_conflicts(self) -> None:
		conflicts: Dict[LR0Set, List[Tuple[SymbolTerminal, Set[LRAction]]]] = defaultdict(lambda: [])

		for terminal in self.grammar.terminal_map.values():
			terminal.idx = len(self.terminal_list)
			self.terminal_list.append(terminal)
		for nt in self.grammar.nonterminals:
			nt.idx = len(self.nonterminal_list)
			self.nonterminal_list.append(nt)
		for state in self.states:
			for symbol, actions in state.actions.items():
				if len(actions) > 1:
					conflicts[state].append((symbol, actions))

		if len(conflicts) > 0:
			newline = '\n'
			for state, conflict in conflicts.items():
				self.print_state(state)
				by_actions: Dict[FrozenSet[LRAction], Set[SymbolTerminal]] = defaultdict(lambda: set())
				for symbol, actions in conflict:
					by_actions[frozenset(actions)].add(symbol)
				for action_set, symbols in by_actions.items():
					symbols_str = ' / '.join(map(lambda s: s.to_inline_str(), symbols))
					print(
						f"CONFLICT for {symbols_str}:{''.join(map(lambda action: newline + '  ' + str(action), action_set))}",
						file=sys.stderr
					)

	def construct_actions(self) -> None:
		def add_action(state: LR0Set, terminal: SymbolTerminal, action: LRAction) -> None:
			if terminal not in state.actions:
				state.actions[terminal] = set()
			state.actions[terminal].add(action)

		for state in self.states:
			for item in chain(state.kernel, state.nonkernel):
				if len(item.prod.symbols) > item.offset:
					next = item.prod.symbols[item.offset]
					if isinstance(next, SymbolTerminal) and next in state.goto:
						target = state.goto[next]
						add_action(state, next, target.shift)
				else:
					for lookahead in state.lookahead[item]:
						if not item.nt.exported:
							add_action(state, lookahead, Reduce.get(item.nt, item.prod))
						elif lookahead == self.grammar.eof:
							add_action(state, lookahead, Accept)

	def first(self, rule: Iterable[Symbol], la: Iterable[SymbolTerminal]) -> Set[SymbolTerminal]:
		result = set()
		for symbol in rule:
			if isinstance(symbol, SymbolTerminal):
				result.add(symbol)
				break
			elif isinstance(symbol, SymbolNonTerminal):
				result.update(symbol.first)
				if not symbol.nullable:
					break
		else:
			result.update(la)
		return result

	def find_nullables(self) -> None:
		while True:
			progress = False
			for nt in self.grammar.nonterminals:
				if not nt.nullable:
					for prod in nt.prods:
						for symbol in prod.symbols:
							if isinstance(symbol, SymbolTerminal) or (isinstance(symbol, SymbolNonTerminal) and symbol.nullable):
								break
						else:
							nt.nullable = True
							progress = True
			if not progress:
				break

	def find_first(self) -> None:
		for nt in self.grammar.nonterminals:
			for prod in nt.prods:
				for symbol in prod.symbols:
					if isinstance(symbol, SymbolTerminal):
						nt.first.add(symbol)
						break

		while True:
			progress = False
			for nt in self.grammar.nonterminals:
				for prod in nt.prods:
					for symbol in prod.symbols:
						if isinstance(symbol, SymbolTerminal):
							break
						elif isinstance(symbol, SymbolNonTerminal):
							if extend_set(nt.first, symbol.first):
								progress = True
							if not symbol.nullable:
								break
			if not progress:
				break

	def closure_lr1(self, items: Iterable[LR1Item]) -> FrozenSet[LR1Item]:
		worklist: List[LR1Item] = list(items)
		closure: Set[LR1Item] = set(items)
		i = 0
		while i < len(worklist):
			item = worklist[i]
			if len(item.prod.symbols) > item.offset:
				next = item.prod.symbols[item.offset]
				if isinstance(next, SymbolNonTerminal):
					for prod in next.prods:
						for sym in self.first(item.prod.symbols[item.offset + 1:], (item.la,)):
							newitem = LR1Item(next, prod, 0, sym)
							if newitem not in closure:
								closure.add(newitem)
								worklist.append(newitem)
			i += 1
		return frozenset(closure)

	def closure(self, items: Iterable[LR0Item]) -> Tuple[FrozenSet[LR0Item], FrozenSet[LR0Item]]:
		worklist: List[LR0Item] = list(items)
		closure: Set[LR0Item] = set(items)
		i = 0
		while i < len(worklist):
			item = worklist[i]
			if len(item.prod.symbols) > item.offset:
				next = item.prod.symbols[item.offset]
				if isinstance(next, SymbolNonTerminal):
					for prod in next.prods:
						newitem = LR0Item(next, prod, 0)
						if newitem not in closure:
							closure.add(newitem)
							worklist.append(newitem)
			i += 1
		return (
			frozenset(item for item in worklist if item.is_kernel()),
			frozenset(item for item in worklist if not item.is_kernel())
		)

	def compute_goto(self, state: LR0Set, symbol: Symbol) -> Optional[Tuple[FrozenSet[LR0Item], FrozenSet[LR0Item]]]:
		items = set()
		for item in chain(state.kernel, state.nonkernel):
			if len(item.prod.symbols) > item.offset:
				if item.prod.symbols[item.offset] == symbol:
					items.add(LR0Item(item.nt, item.prod, item.offset + 1))
		if len(items) == 0:
			return None
		return self.closure(items)

	def print_states(self) -> None:
		for state in self.states:
			self.print_state(state)

	def print_transitions(self) -> None:
		for state in self.states:
			self.print_transition(state)

	def print_transition(self, state: LR0Set) -> None:
		print(f"State {state.idx}:")
		for symbol, actions in state.actions.items():
			print(f"  {symbol.to_inline_str()} -> {' | '.join(map(str, actions))}")
		for term, target_state in state.goto.items():
			if isinstance(term, SymbolNonTerminal):
				print(f"  {term.to_inline_str()} -> {target_state.idx}")

	def print_state(self, state: LR0Set) -> None:
		print(f"State {state.idx}:", file=sys.stderr)
		for item in state.kernel:
			lhs = item.prod.symbols[:item.offset]
			rhs = item.prod.symbols[item.offset:]

			def sym_to_str(s: Symbol) -> str:
				return s.to_inline_str()

			def prod_to_str(prod: Iterable[Symbol]) -> Iterable[str]:
				return map(sym_to_str, prod)

			lookahead = ','.join(map(str, state.lookahead[item]))

			print(
				f"  {item.nt} -> {' '.join(chain(prod_to_str(lhs), '●', prod_to_str(rhs)))} | {lookahead}",
				file=sys.stderr
			)

	def determine_lookaheads(self) -> None:
		for state in self.states:
			for symbol in state.goto.keys():
				self.determine_lookahead(state, symbol)

	def determine_lookahead(self, state: LR0Set, symbol: Symbol) -> None:
		for item in state.kernel:
			closure = self.closure_lr1((LR1Item(item.nt, item.prod, item.offset, self.sharp), ))
			for closure_item in closure:
				if (
					len(closure_item.prod.symbols) > closure_item.offset
					and
					closure_item.prod.symbols[closure_item.offset] == symbol
				):
					target = state.goto[symbol]
					if closure_item.la == self.sharp:
						for target_item in chain(target.kernel, target.nonkernel):
							if (
								target_item.nt == closure_item.nt
								and
								target_item.prod == closure_item.prod
								and
								target_item.offset == closure_item.offset + 1
							):
								state.propagates[item].add((target, target_item))
								break
					else:
						for target_item in chain(target.kernel, target.nonkernel):
							if (
								target_item.nt == closure_item.nt
								and
								target_item.prod == closure_item.prod
								and
								target_item.offset == closure_item.offset + 1
							):
								target.lookahead[target_item].add(closure_item.la)
								break
			if item.nt.exported and item.offset == 0:
				assert self.grammar.eof is not None
				state.lookahead[item].add(self.grammar.eof)

	def propagate_lookaheads(self) -> None:
		while True:
			progress = False
			for state in self.states:
				for item in state.kernel:
					lookahead = state.lookahead[item]
					for target_state, target_item in state.propagates[item]:
						target_lookahead = target_state.lookahead[target_item]
						if extend_set(target_lookahead, lookahead):
							progress = True
			if not progress:
				break

		# propagate to non-kernel items
		for state in self.states:
			self.propagate_lookahead_to_nonkernels(state)

	def propagate_lookahead_to_nonkernels(self, state: LR0Set) -> None:
		worklist: List[Tuple[LR0Item, Set[SymbolTerminal]]] = list(state.lookahead.items())
		closure: Dict[LR0Item, Set[SymbolTerminal]] = state.lookahead

		def add_work(item: LR0Item, lookahead: Iterable[SymbolTerminal]) -> None:
			new_lookahead = set()
			if item not in closure:
				closure[item] = set()
			base_set = closure[item]
			for term in lookahead:
				if term not in base_set:
					base_set.add(term)
					new_lookahead.add(term)
			if len(new_lookahead) > 0:
				worklist.append((item, new_lookahead))

		for item, lookahead in state.lookahead.items():
			add_work(item, lookahead)

		i = 0
		while i < len(worklist):
			item, lookaheads = worklist[i]
			if len(item.prod.symbols) > item.offset:
				next = item.prod.symbols[item.offset]
				if isinstance(next, SymbolNonTerminal):
					for prod in next.prods:
						newitem = LR0Item(next, prod, 0)
						add_work(newitem, self.first(item.prod.symbols[item.offset + 1:], lookaheads))
			i += 1

	def construct_sets(self) -> None:
		worklist: List[LR0Set] = []
		states: Dict[FrozenSet[LR0Item], LR0Set] = dict()

		def add_state(items: Optional[Tuple[FrozenSet[LR0Item], FrozenSet[LR0Item]]]) -> Optional[LR0Set]:
			if items is None:
				return None
			if len(items[0]) == 0:
				return None
			kernel = items[0]
			if kernel not in states:
				state = LR0Set(len(self.states), *items)
				states[kernel] = state
				self.states.append(state)
				worklist.append(state)
			return states[kernel]

		for nt in self.grammar.exports.values():
			item = LR0Item(nt, nt.prods[0], 0)
			set = add_state(self.closure((item,)))
			assert set is not None
			self.entry[nt] = set

		i = 0
		while i < len(worklist):
			state = worklist[i]
			for symbol in chain(self.grammar.terminal_map.values(), self.grammar.nonterminals):
				new_state = add_state(self.compute_goto(state, symbol))
				if new_state:
					state.goto[symbol] = new_state
			i += 1

