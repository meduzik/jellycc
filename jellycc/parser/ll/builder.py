import time
from collections import defaultdict
from functools import cmp_to_key
from typing import List, Union, Dict, Optional, Tuple, Callable, TypeVar, Set, Generator, cast, Iterable, Any

import sys

from jellycc.parser.grammar import ParserGrammar, SymbolTerminal, Action, SymbolNonTerminal
from jellycc.utils.scc import topological_sort


class LLState:
	def __init__(self, name: str):
		self.name = name
		self.productions: List[LLProduction] = []
		self.nullable: Optional[Tuple[Action]] = None
		self.first: Set[SymbolTerminal] = set()
		self.follow: Set[SymbolTerminal] = set()
		self.order: int = -1

	def add_production(self, production: 'LLProduction') -> None:
		for my_production in self.productions:
			if len(my_production.items) != len(production.items):
				continue
			for idx in range(len(my_production.items)):
				if my_production.items[idx] != production.items[idx]:
					break
			else:
				return
		self.productions.append(production)

	def __str__(self) -> str:
		return self.name + '(' + str(len(self.productions)) + ')'


class LLProduction:
	def __init__(self, state: LLState):
		self.state: LLState = state
		self.items: List[LLItem] = []
		self.nonnulls: int = 0

	def extract_reachable(self) -> Tuple[Optional[LLState], int]:
		for idx, item in enumerate(self.items):
			if isinstance(item, LLState):
				return item, idx
			elif isinstance(item, Action):
				pass
			else:
				return None, idx
		return None, len(self.items)

	def extract_action_prefix(self) -> Tuple[Action]:
		idx = 0
		n = len(self.items)
		while idx < n:
			if not isinstance(self.items[idx], Action):
				break
			idx += 1
		return tuple(cast(Iterable[Action], self.items[:idx]))

	def __str__(self) -> str:
		return ' '.join(map(str, self.items))


LLItem = Union[LLState, SymbolTerminal, Action]


T = TypeVar('T')


def remove_if(list: List[T], fn: Callable[[T], bool]) -> None:
	i = 0
	j = 0
	n = len(list)
	while i < n:
		if not fn(list[i]):
			list[j] = list[i]
			j += 1
		i += 1
	if j != i:
		del list[j:n]


def compare_lists(l1: List[T], l2: List[T]) -> bool:
	if len(l1) != len(l2):
		return False
	for idx in range(len(l1)):
		if l1[idx] is not l2[idx]:
			return False
	return True


class LLBuilder:
	def __init__(self, grammar: ParserGrammar):
		self.grammar: ParserGrammar = grammar
		self.states: List[LLState] = []
		self.entries: Dict[SymbolNonTerminal, LLState] = dict()
		self.singleton_sets: Dict[SymbolTerminal, Set[SymbolTerminal]] = dict()
		self.empty_set: Set[SymbolTerminal] = set()
		self.ranks: Dict[LLState, int] = dict()

	def build(self) -> None:
		self.construct_initial_states()
		self.eliminate_nullables()
		self.eliminate_left_recursion()

		for i in range(1):
			self.eliminate_nullables()
			self.left_factor()
			self.eliminate_nullables()
			self.filter_states()
			self.eliminate_units()
			self.eliminate_singletons()
			self.merge_states()
			self.filter_states()

		self.eliminate_nullables()
		self.left_factor()
		self.eliminate_nullables()
		self.eliminate_units()
		self.merge_states()
		self.filter_states()

		self.eliminate_nullables()
		self.left_factor()
		self.compute_first_sets()

		self.filter_states()
		self.print_stats()

	def print_stats(self) -> None:
		print(f"LL states: {len(self.states)}")

	def dump_states(self, do_contents=True) -> None:
		print("---")
		for state in sorted(self.states, key=lambda state: state.name):
			print(f"State {state.name}")
			if do_contents:
				for production in state.productions:
					print(f"  {production}")
				if state.first:
					print(f"  FIRST: {', '.join(map(str, state.first))}")
				if state.follow:
					print(f"  FOLLOW: {', '.join(map(str, state.follow))}")
		print(f"TOTAL STATES: {len(self.states)}")
		print("===")

	def construct_initial_states(self) -> None:
		nt_to_state: Dict[SymbolNonTerminal, LLState] = dict()
		nt_list: List[Tuple[SymbolNonTerminal, LLState]] = []

		for nt in self.grammar.nonterminals:
			state = LLState(nt.to_inline_str())
			self.states.append(state)
			nt_list.append((nt, state))
			nt_to_state[nt] = state

		for nt in self.grammar.keep:
			self.entries[nt] = nt_to_state[nt]

		for nt, state in nt_list:
			for prod in nt.prods:
				production = LLProduction(state)
				for symbol in prod.symbols:
					if isinstance(symbol, SymbolTerminal):
						production.items.append(symbol)
					elif isinstance(symbol, SymbolNonTerminal):
						production.items.append(nt_to_state[symbol])
				if prod.action:
					production.items.append(prod.action)
				state.add_production(production)

	def find_nullables(self) -> None:
		state_to_productions: Dict[LLState, List[LLProduction]] = defaultdict(lambda: [])
		worklist: List[LLState] = []

		for state in self.states:
			state.nullable = None
			for production in state.productions:
				production.nonnulls = 0
				for item in production.items:
					if not isinstance(item, Action):
						production.nonnulls += 1

		def discover_nullable(production: LLProduction) -> None:
			if production.state.nullable is None:
				nullable = []
				for item in production.items:
					if isinstance(item, LLState):
						assert (item.nullable is not None)
						nullable.extend(item.nullable)
					elif isinstance(item, Action):
						nullable.append(item)
				production.state.nullable = tuple(nullable)
				worklist.append(production.state)

		for state in self.states:
			for production in state.productions:
				for item in production.items:
					if isinstance(item, LLState):
						state_to_productions[item].append(production)
				if production.nonnulls == 0:
					discover_nullable(production)

		i = 0
		while i < len(worklist):
			state = worklist[i]
			for production in state_to_productions[state]:
				production.nonnulls -= 1
				if production.nonnulls == 0:
					discover_nullable(production)
			i += 1

		for state in self.states:
			if state.nullable is not None:
				for production in state.productions:
					if production.nonnulls == 0:
						nullable_candidate: List[Action] = []
						for item in production.items:
							if isinstance(item, Action):
								nullable_candidate.append(item)
							elif isinstance(item, LLState):
								nullable_candidate.extend(item.nullable)
						if state.nullable != tuple(nullable_candidate):
							print(
								f"Different nullable sequence was inferred for {state.name}:\n  {state.nullable}\n  {tuple(nullable_candidate)}",
								file=sys.stderr
							)
							raise RuntimeError("refactoring failed")

	def eliminate_nullables(self) -> None:
		self.find_nullables()
		self.factor_in_nullables()

	def factor_in_nullables(self) -> None:
		states_to_kill: Set[LLState] = set()
		for state in self.states:
			for production in state.productions:
				for idx, item in enumerate(production.items):
					if isinstance(item, LLState) and (item.nullable is not None):
						new_production = LLProduction(state)
						new_production.items.extend(production.items[:idx])
						new_production.items.extend(item.nullable)
						new_production.items.extend(production.items[idx+1:])
						state.add_production(new_production)
			remove_if(
				state.productions,
				lambda production:
					all(map(lambda item: isinstance(item, Action), production.items))
			)
			if len(state.productions) == 0:
				states_to_kill.add(state)
		self.remove_states(states_to_kill)
		for state in self.states:
			state.nullable = None

	def remove_states(self, states: Set[LLState]) -> None:
		for state in self.states:
			remove_if(state.productions, lambda production: any(map(lambda item: item in states, production.items)))
		remove_if(self.states, lambda s: s in states)

	def eliminate_left_recursion(self) -> None:
		self.semisort()
		self.prevent_left_recursion()
		self.eliminate_nullables()

	def semisort(self) -> None:
		reachables: Dict[LLState, Set[LLState]] = defaultdict(set)
		ordered: List[LLState] = []

		for state in self.states:
			for production in state.productions:
				reachable, _ = production.extract_reachable()
				if reachable is not None:
					reachables[state].add(reachable)

		def edges_of(state: LLState) -> Generator[LLState, None, None]:
			yield from reachables[state]

		for scc in topological_sort(self.states, edges_of):
			ordered.extend(scc)

		ordered.reverse()

		for idx, state in enumerate(ordered):
			state.order = idx

		self.states = ordered

	def prevent_left_recursion(self) -> None:
		for state in self.states:
			if state.order < 0:
				continue
			extra_productions: List[LLProduction] = []
			remove_productions: Set[LLProduction] = set()
			for production in state.productions:
				reachable, idx = production.extract_reachable()
				if (reachable is not None) and (reachable.order < state.order):
					remove_productions.add(production)
					for their_production in reachable.productions:
						new_production = LLProduction(state)
						new_production.items.extend(production.items[:idx])
						new_production.items.extend(their_production.items)
						new_production.items.extend(production.items[idx+1:])
						extra_productions.append(new_production)
			if len(remove_productions) > 0 or len(extra_productions) > 0:
				remove_if(state.productions, lambda s: s in remove_productions)
				state.productions.extend(extra_productions)
			self.eliminate_direct_left_recursion(state)

	def eliminate_direct_left_recursion(self, state: LLState) -> None:
		has_recursion = False

		for production in state.productions:
			reachable, idx = production.extract_reachable()
			if reachable is state:
				has_recursion = True
				break

		if not has_recursion:
			return

		lhs: List[List[LLItem]] = []
		rhs: List[List[LLItem]] = []

		for production in state.productions:
			reachable, idx = production.extract_reachable()
			if reachable is not state:
				lhs.append(production.items)
				continue
			else:
				if idx != 0:
					print(
						f"Left recursion elimination failed: state {state.name} has self-recurring prefix {' '.join(map(str, production.items[:idx+1]))}",
						file=sys.stderr
					)
					raise RuntimeError("refactoring failed")
				rhs.append(production.items[idx+1:])

		state_rhs = LLState(state.name + "'rhs")
		state_rhs.nullable = []
		for items in rhs:
			production = LLProduction(state_rhs)

			has_nonnull = False
			for item in items:
				if isinstance(item, SymbolTerminal):
					has_nonnull = True
					break
				elif isinstance(item, LLState) and (item.nullable is None):
					has_nonnull = True
					break

			if not has_nonnull:
				print(
					f"Left recursion elimination failed: state {state.name} has self-recurring suffix {' '.join(map(str, items))}",
					file=sys.stderr
				)
				raise RuntimeError("refactoring failed")

			production.items.extend(items)
			production.items.append(state_rhs)
			state_rhs.add_production(production)
		state_rhs.add_production(LLProduction(state_rhs))
		self.states.append(state_rhs)

		state.productions = []
		for items in lhs:
			production = LLProduction(state_rhs)
			production.items.extend(items)
			production.items.append(state_rhs)
			state.add_production(production)

	def find_first_follow_conflicts(self) -> None:
		self.compute_first_sets()
		self.compute_follow_sets()

	def compute_first_sets(self) -> None:
		edges: Dict[LLState, List[LLState]] = defaultdict(lambda: [])

		def inject_first(state: LLState, token: SymbolTerminal) -> None:
			if token not in state.first:
				state.first.add(token)
				for target in edges[state]:
					inject_first(target, token)

		for state in self.states:
			for production in state.productions:
				for item in production.items:
					if isinstance(item, LLState):
						edges[item].append(state)
						if item.nullable is None:
							break
					elif isinstance(item, SymbolTerminal):
						break

		for state in self.states:
			for production in state.productions:
				for item in production.items:
					if isinstance(item, SymbolTerminal):
						inject_first(state, item)
						break
					elif isinstance(item, LLState) and item.nullable is None:
						break

	def compute_follow_sets(self) -> None:
		edges: Dict[LLState, List[LLState]] = defaultdict(lambda: [])

		prevs: List[LLState] = []

		for state in self.states:
			for production in state.productions:
				prevs.clear()
				for item in production.items:
					if isinstance(item, SymbolTerminal):
						for prev in prevs:
							prev.follow.add(item)
						prevs.clear()
					elif isinstance(item, LLState):
						for prev in prevs:
							prev.follow.update(item.first)
						if item.nullable is None:
							prevs.clear()
						prevs.append(item)
					else:
						pass
				for prev in prevs:
					edges[state].append(prev)

		def propagate(state: LLState):
			if state not in edges:
				return
			for target in edges[state]:
				n = len(target.follow)
				target.follow.update(state.follow)
				if n != len(target.follow):
					propagate(target)

		for state in self.states:
			propagate(state)

	def left_factor(self) -> None:
		self.compute_first_sets()
		self.eliminate_common_prefix()

	def get_production_first_set(self, production: LLProduction) -> Set[SymbolTerminal]:
		for item in production.items:
			if isinstance(item, SymbolTerminal):
				if item not in self.singleton_sets:
					self.singleton_sets[item] = {item}
				return self.singleton_sets[item]
			elif isinstance(item, LLState):
				return item.first
		return self.empty_set

	def left_factor_state(self, expanded_rules: Dict[LLState, int], state: LLState):
		new_productions = []
		self.reprocess_bucket(expanded_rules, state, state.productions, new_productions)
		uniques: Dict[Tuple[LLItem, ...], LLState] = dict()
		for production in new_productions:
			key = tuple(production.items)
			if key not in uniques:
				uniques[key] = production
		state.productions = list(uniques.values())

	def reduce_ranks(self, expanded_rules: Dict[LLState, int], state: LLState, rank: int, list: List[LLProduction]) -> bool:
		new_productions: List[LLProduction] = []
		new_expansions: Set[LLState] = set()
		for production in list:
			if self.get_production_rank(production) == rank:
				for idx, item in enumerate(production.items):
					if isinstance(item, LLState):
						new_expansions.add(item)
						if (item in expanded_rules) and (expanded_rules[item] >= 1):
							return False
						for item_production in item.productions:
							new_production = LLProduction(state)
							new_production.items.extend(production.items[:idx])
							new_production.items.extend(item_production.items)
							new_production.items.extend(production.items[idx+1:])
							new_productions.append(new_production)
						break
			else:
				new_productions.append(production)
		list.clear()
		list.extend(new_productions)
		for expansion in new_expansions:
			expanded_rules[expansion] += 1
		return True

	def reprocess_bucket(self, expanded_rules: Dict[LLState, int], state: LLState, list: List[LLProduction], output: List[LLProduction]) -> None:
		buckets: List[Tuple[Set[SymbolTerminal], List[LLProduction]]] = []
		for production in list:
			my_set = self.get_production_first_set(production)
			for idx, bucket in enumerate(buckets):
				if not bucket[0].isdisjoint(my_set):
					if len(bucket[1]) == 1:
						buckets[idx] = (bucket[0].union(my_set), bucket[1])
					else:
						bucket[0].update(my_set)
					bucket[1].append(production)
					break
			else:
				buckets.append((my_set, [production]))

		for bucket in buckets:
			if len(bucket[1]) > 1:
				self.left_factor_bucket(expanded_rules, state, bucket[1], output)
			else:
				output.append(bucket[1][0])

	def insert_unique_state(self, state: LLState) -> LLState:
		for other in self.states:
			if other is state:
				return state
			if len(other.productions) != len(state.productions):
				continue
			for idx in range(len(other.productions)):
				if not compare_lists(other.productions[idx].items, state.productions[idx].items):
					break
			else:
				return other
		self.states.append(state)
		return state

	def left_factor_bucket(self, expanded_rules: Dict[LLState, int], state: LLState, bucket: List[LLProduction], output: List[LLProduction]) -> None:
		common_sequence: List[LLItem] = bucket[0].items[:]
		for production in bucket[1:]:
			n = min(len(common_sequence), len(production.items))
			idx = 0
			while idx < n:
				if common_sequence[idx] != production.items[idx]:
					break
				idx += 1
			if idx != len(common_sequence):
				del common_sequence[idx:]

		if len(common_sequence) == 0:
			max_rank = max(map(self.get_production_rank, bucket))
			if not self.reduce_ranks(expanded_rules, state, max_rank, bucket):
				productions = '\n'.join(map(lambda x: '  ' + str(x), bucket))
				states = ' '.join(map(str, expanded_rules))
				print(
					f"Left factoring failed: state {state.name} invokes recursive expansion:\n{states}\n\n{productions}"
				)
				self.dump_states()
				raise RuntimeError("refactoring failed")
			else:
				self.reprocess_bucket(expanded_rules, state, bucket, output)
				return

		rhs_state = LLState(state.name + '[' + ' '.join(map(str, common_sequence)) + ']')
		for production in bucket:
			rhs_production = LLProduction(rhs_state)
			rhs_production.items.extend(production.items[len(common_sequence):])
			rhs_state.add_production(rhs_production)
			rhs_state.follow = state.follow
			rhs_state.first.update(self.get_production_first_set(rhs_production))
		old_state = rhs_state
		rhs_state = self.insert_unique_state(rhs_state)
		if rhs_state == old_state:
			rules_copy = defaultdict(lambda: 0)
			for k, v in expanded_rules.items():
				rules_copy[k] = v
			self.left_factor_state(rules_copy, rhs_state)

		factored_production = LLProduction(state)
		factored_production.items.extend(common_sequence)
		factored_production.items.append(rhs_state)
		output.append(factored_production)

	def eliminate_common_prefix(self) -> None:
		self.compute_ranks()
		for state in self.states[::]:
			self.left_factor_state(defaultdict(lambda: 0), state)

	def get_production_rank(self, production: LLProduction) -> int:
		for item in production.items:
			if isinstance(item, SymbolTerminal):
				return 0
			elif isinstance(item, LLState):
				return self.ranks[item]
		return 0

	def compute_ranks(self) -> None:
		self.semisort()
		for state in reversed(self.states):
			rank = 1
			for production in state.productions:
				rank = max(rank, self.get_production_rank(production) + 1)
			self.ranks[state] = rank

	def eliminate_units(self) -> None:
		derivable: Dict[LLState, LLState] = dict()

		def is_singleton(production) -> bool:
			return len(production.items) == 1 and isinstance(production.items[0], LLState)

		self.semisort()
		for state in self.states:
			if len(state.productions) != 1:
				continue
			for production in state.productions:
				if len(production.items) == 1 and isinstance(production.items[0], LLState):
					derivable[state] = production.items[0]

		for state in reversed(self.states):
			for production in state.productions:
				for idx, item in enumerate(production.items):
					if isinstance(item, LLState):
						if item in derivable:
							production.items[idx] = derivable[item]

	def eliminate_singletons(self) -> None:
		derivable: Dict[LLState, Set[LLState]] = defaultdict(lambda: set())

		def is_singleton(production) -> bool:
			return len(production.items) == 1 and isinstance(production.items[0], LLState)

		self.semisort()
		for state in self.states:
			for production in state.productions:
				if len(production.items) == 1 and isinstance(production.items[0], LLState):
					derivable[state].add(production.items[0])

		for state in reversed(self.states):
			remove_if(state.productions, is_singleton)
			for target in derivable[state]:
				for production in target.productions:
					production_copy = LLProduction(state)
					production_copy.items.extend(production.items)
					state.add_production(production_copy)

	def merge_states(self) -> None:
		shapes: Dict[LLState, int] = dict()

		def compare(l1, l2) -> int:
			if len(l1) > len(l2):
				return -1
			if len(l1) < len(l2):
				return 1
			for idx in range(len(l1)):
				i1 = l1[idx]
				i2 = l2[idx]
				if isinstance(i1, int) and isinstance(i2, int):
					if i1 - i2 != 0:
						return i1 - i2
				elif isinstance(i1, int):
					return -1
				elif isinstance(i2, int):
					return 1
				else:
					if id(i1) != id(i2):
						return id(i1) - id(i2)
			return 0

		def construct_state_key(state: LLState) -> Any:
			key_list = []
			for production in state.productions:
				key_sublist = []
				for item in production.items:
					if isinstance(item, LLState):
						key_sublist.append(shapes[item])
					else:
						key_sublist.append(item)
				key_list.append(tuple(key_sublist))
			return tuple(sorted(key_list, key=cmp_to_key(compare)))

		for state in self.states:
			shapes[state] = 0

		old_len = 0
		while True:
			key_to_shape: Dict[Any, int] = dict()
			keys: Dict[LLState, Any] = dict()
			for state in self.states:
				key = construct_state_key(state)
				if key not in key_to_shape:
					key_to_shape[key] = len(key_to_shape)
				keys[state] = key
			for state in self.states:
				shapes[state] = key_to_shape[keys[state]]
			if old_len == len(key_to_shape):
				break
			old_len = len(key_to_shape)

		shape_repr: Dict[int, LLState] = dict()
		new_states: List[LLState] = []
		for state, shape in shapes.items():
			if shape not in shape_repr:
				shape_repr[shape] = state
				new_states.append(state)

		for state in self.states:
			for production in state.productions:
				for idx, item in enumerate(production.items):
					if isinstance(item, LLState):
						production.items[idx] = shape_repr[shapes[item]]

	def filter_states(self) -> None:
		visited: Set[LLState] = set()

		def visit(state: LLState):
			if state in visited:
				return
			visited.add(state)
			for production in state.productions:
				for item in production.items:
					if isinstance(item, LLState):
						visit(item)

		for state in self.entries.values():
			visit(state)

		filtered_states = list(visited)
		self.states = filtered_states
