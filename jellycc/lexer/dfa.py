from collections import defaultdict
from typing import Optional, List, Callable, Set, FrozenSet, Dict, Tuple, Union

import sys

from jellycc.lexer.nfa import NFAState, NFARule
from jellycc.project.grammar import Terminal
from jellycc.utils.source import SrcLoc


class Keyword:
	def __init__(self, rule: NFARule) -> None:
		self.rule: NFARule = rule
		self.strings: List[str] = []


class DFAState:
	def __init__(self) -> None:
		self.trans: List[Optional[DFAState]] = [None] * 256
		self.accepts: Optional[NFARule] = None
		self.repr: Optional[DFAState] = None
		self.paths: Optional[int] = 0

	def visit(self, visitor: Callable[['DFAState'], None]) -> None:
		visited: Set[DFAState] = set()

		def _visit(state: Optional[DFAState]) -> None:
			if state is None:
				return
			if state in visited:
				return
			visited.add(state)
			visitor(state)
			for target_state in state.trans:
				_visit(target_state)

		_visit(self)


class SCC:
	def __init__(self) -> None:
		self.states: List[NFAState] = []
		self.closure: Optional[FrozenSet[SCC]] = None

	def add(self, state: NFAState) -> None:
		self.states.append(state)

	def build_closure(self, builder: 'Builder') -> None:
		closure: Set[SCC] = set()
		closure.add(self)

		other_closures: Set[FrozenSet[SCC]] = set()

		for state in self.states:
			for target_state in state.etrans:
				target_node = builder.states[target_state]
				if target_node.scc == self:
					continue
				assert target_node.scc is not None
				assert target_node.scc.closure is not None
				other_closures.add(target_node.scc.closure)

		for other_closure in other_closures:
			closure.update(other_closure)

		self.closure = frozenset(closure)


class GraphNode:
	def __init__(self, state: NFAState) -> None:
		self.state: NFAState = state
		self.scc: Optional[SCC] = None
		self.scc_index: Optional[int] = None
		self.scc_lowlink: Optional[int] = None
		self.scc_onstack: bool = False
		self.closure: Set[SCC] = set()


class Builder:
	def __init__(self, err: Terminal, rules: List[NFARule], keyword_threshold: int) -> None:
		self.states: Dict[NFAState, GraphNode] = dict()
		self.powerset: Dict[FrozenSet[SCC], DFAState] = dict()
		self.worklist: List[Tuple[FrozenSet[SCC], DFAState]] = []
		self.accepts: Dict[DFAState, List[NFARule]] = dict()
		self.rules: List[NFARule] = rules
		self.keyword_threshold: int = keyword_threshold
		self.keywords: Dict[NFARule, Keyword] = dict()
		self.final_rule: NFARule = NFARule(-1, SrcLoc("", 0, 0), err)

	def build(self, state: NFAState) -> DFAState:
		def pre_visit(state: NFAState) -> None:
			self.states[state] = GraphNode(state)

		state.visit(pre_visit)

		self.find_scc()

		scc = self.states[state].scc
		assert scc is not None
		closure = scc.closure
		assert closure is not None
		dfa_state = self.get_dfa_for_subset(closure)
		self.process()
		self.find_keywords(dfa_state)
		self.resolve_accepts_from_keywords(dfa_state)

		return dfa_state

	def find_keywords(self, initial_state: DFAState) -> None:
		initial_state.accepts = None
		in_edges: Dict[DFAState, List[Tuple[int, DFAState]]] = defaultdict(lambda: [])
		all_states: Set[DFAState] = set()

		def count_paths(initial_state: DFAState) -> None:
			initial_state.paths = 1

			ins: Dict[DFAState, int] = defaultdict(lambda: 0)
			worklist: List[DFAState] = []

			def count_ins(state: DFAState) -> None:
				for idx, target_state in enumerate(state.trans):
					if target_state is not None:
						ins[target_state] += 1
						in_edges[target_state].append((idx, state))
				all_states.add(state)

			initial_state.visit(count_ins)

			if initial_state not in ins:
				worklist.append(initial_state)

			i = 0
			while i < len(worklist):
				state = worklist[i]
				for target_state in state.trans:
					if target_state is not None:
						ins[target_state] -= 1
						if ins[target_state] == 0:
							worklist.append(target_state)
						assert target_state.paths is not None
						assert state.paths is not None
						target_state.paths += state.paths
				i += 1

			for state, count in ins.items():
				if count > 0:
					state.paths = None

		count_paths(initial_state)

		count_per_rule: Dict[NFARule, Optional[int]] = dict()

		def visit_state(state: DFAState) -> None:
			accept = state.accepts
			if not accept:
				return
			count = count_per_rule.get(accept, 0)
			if count is None:
				return
			if state.paths is None:
				count_per_rule[accept] = None
			else:
				count_per_rule[accept] = count + state.paths

		initial_state.visit(visit_state)

		for rule, count in count_per_rule.items():
			if count is not None and count <= self.keyword_threshold:
				keyword = Keyword(rule)
				self.keywords[rule] = keyword

		def find_paths(state: DFAState, keyword: Keyword) -> None:
			path: List[int] = []

			def visit(state: DFAState) -> None:
				if state not in in_edges:
					keyword.strings.append(''.join(map(chr, reversed(path))))
				else:
					for char, from_state in in_edges[state]:
						path.append(char)
						visit(from_state)
						path.pop()

			visit(state)

		for state in all_states:
			if state.accepts is not None:
				keyword = self.keywords.get(state.accepts, None)
				if keyword is not None:
					find_paths(state, keyword)

		for rule in self.rules:
			if count_per_rule.get(rule, 0) == 0:
				print(f"Lexer rule at {rule.loc} is useless", file=sys.stderr)

	def process(self) -> None:
		i: int = 0
		while i < len(self.worklist):
			subset, dfa_state = self.worklist[i]
			self.process_dfa_state(subset, dfa_state)
			i += 1

	def process_dfa_state(self, subset: FrozenSet[SCC], dfa_state: DFAState) -> None:
		transitions: List[Set[SCC]] = [set() for i in range(256)]
		accepts: Set[NFARule] = set()

		for scc in subset:
			for nfa_state in scc.states:
				if nfa_state.rule:
					accepts.add(nfa_state.rule)
				for chars, target_state in nfa_state.trans:
					for char in chars:
						target_node = self.states[target_state]
						assert target_node.scc is not None
						assert target_node.scc.closure is not None
						transitions[char].update(target_node.scc.closure)

		frozen_transitions: List[FrozenSet[SCC]] = list(map(lambda itr: frozenset(itr), transitions))
		for idx, subset in enumerate(frozen_transitions):
			if len(subset) == 0:
				dfa_state.trans[idx] = None
			else:
				dfa_state.trans[idx] = self.get_dfa_for_subset(subset)

		if len(accepts) > 0:
			accepts_list = list(accepts)
			accepts_list.sort(key=lambda rule: rule.order)
			self.accepts[dfa_state] = accepts_list
			dfa_state.accepts = accepts_list[0]

	def get_dfa_for_subset(self, subset: FrozenSet[SCC]) -> DFAState:
		if subset not in self.powerset:
			dfa_state = DFAState()
			self.worklist.append((subset, dfa_state))
			self.powerset[subset] = dfa_state
		return self.powerset[subset]

	def find_scc(self) -> None:
		index: int = 0
		stack: List[GraphNode] = []

		def strongconnect(v: GraphNode) -> None:
			nonlocal index
			v.scc_index = index
			v.scc_lowlink = index
			index += 1
			stack.append(v)
			v.scc_onstack = True

			for target in v.state.etrans:
				w = self.states[target]
				if w.scc_index is None:
					strongconnect(w)
					v.scc_lowlink = min(v.scc_lowlink, w.scc_lowlink)
				elif w.scc_onstack:
					v.scc_lowlink = min(v.scc_lowlink, w.scc_index)

			if v.scc_lowlink == v.scc_index:
				scc = SCC()

				while True:
					w = stack.pop()
					w.scc_onstack = False
					scc.add(w.state)
					w.scc = scc
					if w == v:
						break

				scc.build_closure(self)

		for state in self.states.values():
			if state.scc_index is None:
				strongconnect(state)

	def get_transitive_closure(self, state: NFAState) -> FrozenSet[SCC]:
		state_node = self.states[state]
		assert state_node is not None
		scc = state_node.scc
		assert scc is not None
		assert scc.closure is not None
		return scc.closure

	def resolve_accepts_from_keywords(self, initial_state: DFAState) -> None:
		def find_nonkeyword_accept(state: DFAState) -> Optional[NFARule]:
			accepts: Optional[NFARule] = None

			def visit(state: DFAState) -> None:
				nonlocal accepts
				if accepts is not None:
					return
				if state.accepts is not None and state.accepts not in self.keywords:
					accepts = state.accepts

			state.visit(visit)
			return accepts

		def visit(state: DFAState) -> None:
			if state.accepts in self.keywords:
				state.accepts = find_nonkeyword_accept(state)
				if state.accepts is None:
					state.accepts = self.final_rule

		initial_state.visit(visit)



