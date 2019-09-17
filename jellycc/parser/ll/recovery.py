from collections import defaultdict
from typing import Optional, List, Dict, Iterable, Tuple, Generator

from jellycc.parser.grammar import SymbolTerminal
from jellycc.parser.ll.lhtable import LHTable, LHState, Transition, MegaAction, SkipNode
from jellycc.utils.scc import topological_sort


def state_to_edges(state: LHState) -> Generator[LHState, None, None]:
	yield from state.target_states


class LHRecovery:
	def __init__(self, table: LHTable):
		self.table: LHTable = table

	def compute(self) -> None:
		self.fill_edges()
		self.compute_skip_costs()

	def fill_edges(self) -> None:
		for state in self.table.states:
			if state.etransition:
				for target in state.etransition[2]:
					state.target_states.add(target)
			for _, _, targets in state.transitions.values():
				for target in targets:
					state.target_states.add(target)

	def compute_skip_costs(self) -> None:
		for scc in topological_sort(self.table.states, state_to_edges):
			self.compute_scc_skip(scc)

	def compute_scc_skip(self, states: List[LHState]) -> None:
		def compute_skip(
			state: LHState,
			term: Optional[SymbolTerminal],
			action: MegaAction,
			skips: Tuple[LHState, ...]
		) -> bool:
			cost = 0
			acc: List[SkipNode] = []
			if term is not None:
				cost += 1
				acc.append(term)
			acc.append(action)
			for target in skips:
				if target.sync_skip is None:
					return False
				cost += target.sync_skip[0]
				acc.extend(target.sync_skip[1])
			if (state.sync_skip is None) or (state.sync_skip[0] > cost):
				state.sync_skip = (cost, tuple(acc))
				return True
			return False

		def compute_advance(
			state: LHState,
			term: Optional[SymbolTerminal],
			action: MegaAction,
			skips: Tuple[LHState, ...]
		) -> bool:
			cost = 0
			acc: List[SkipNode] = []
			if term is not None:
				cost += 1
				acc.append(term)
			acc.append(action)
			flag = False
			for idx, target in enumerate(skips):
				for term, (target_cost, target_seq, rest_states) in target.sync.items():
					if (term not in state.sync) or (state.sync[term][0] > target_cost + cost):
						state.sync[term] = (cost + target_cost, (*acc, *target_seq), (*rest_states, *skips[idx+1:]))
						flag = True
				cost += target.sync_skip[0]
				acc.extend(target.sync_skip[1])
			return flag

		flag = True
		while flag:
			flag = False
			for state in states:
				for term, (shift, action, targets) in state.transitions.items():
					if compute_skip(state, term if shift else None, action, targets):
						flag = True
				if state.etransition:
					_, action, targets = state.etransition
					if compute_skip(state, None, action, targets):
						flag = True

		for state in states:
			for term in state.transitions.keys():
				state.sync[term] = (0, (), (state,))

		flag = True
		while flag:
			flag = False
			for state in states:
				for term, (shift, action, targets) in state.transitions.items():
					if compute_advance(state, term if shift else None, action, targets):
						flag = True
				if state.etransition:
					_, action, targets = state.etransition
					if compute_advance(state, None, action, targets):
						flag = True
