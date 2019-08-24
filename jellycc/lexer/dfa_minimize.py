from typing import List, Set, Tuple, Dict, Callable, Optional

from jellycc.lexer.dfa import DFAState
from jellycc.lexer.nfa import NFARule


class MinimizeDFA:
	def __init__(self) -> None:
		self.states: List[DFAState] = []
		self.disjoint: Set[Tuple[DFAState, DFAState]] = set()

	def run(self, state: DFAState) -> DFAState:
		def pre_visit(state: DFAState) -> None:
			self.states.append(state)
			state.repr = None

		state.visit(pre_visit)

		equivalences: List[List[DFAState]] = [self.states]
		states_processed = 0

		def assign_repr() -> None:
			for sublist in equivalences:
				for state in sublist:
					state.repr = sublist[0]

		def refine_list(
			states: List[DFAState],
			refiner: Callable[[DFAState, DFAState], bool]
		) -> Tuple[List[List[DFAState]], bool]:
			nonlocal states_processed
			out: List[List[DFAState]] = []

			for state in states:
				for out_list in out:
					if refiner(out_list[0], state):
						out_list.append(state)
						break
				else:
					out.append([state])
				states_processed += 1

			return out, len(out) > 1

		def refine_all(refiner: Callable[[DFAState, DFAState], bool]) -> bool:
			nonlocal equivalences, states_processed
			states_processed = 0
			new_equivalences: List[List[DFAState]] = []
			any_progress = False
			for sublist in equivalences:
				if len(sublist) > 1:
					out, progress = refine_list(sublist, refiner)
					new_equivalences.extend(out)
					if progress:
						any_progress = True
				else:
					states_processed += 1
					new_equivalences.append(sublist)

			equivalences = new_equivalences
			assign_repr()
			return any_progress

		def compare_accepts(accept1: Optional[NFARule], accept2: Optional[NFARule]) -> bool:
			if accept1 == accept2:
				return True
			if (accept1 is None) != (accept2 is None):
				return False
			assert accept1 is not None
			assert accept2 is not None
			return accept1.terminal == accept2.terminal

		def refiner_accept(state1: DFAState, state2: DFAState) -> bool:
			return compare_accepts(state1.accepts, state2.accepts)

		def is_same_class(state1: Optional[DFAState], state2: Optional[DFAState]) -> bool:
			if state1 == state2:
				return True
			if (state1 is None) != (state2 is None):
				return False
			assert state1 is not None
			assert state2 is not None
			if state1.repr is state2.repr:
				return True
			return False

		def refiner_trans(state1: DFAState, state2: DFAState) -> bool:
			for i in range(256):
				if not is_same_class(state1.trans[i], state2.trans[i]):
					return False
			return True

		assign_repr()
		refine_all(refiner_accept)
		while refine_all(refiner_trans):
			pass

		new_states: Dict[DFAState, DFAState] = dict()
		new_states_num: int = 0

		def remap_state(state: Optional[DFAState]) -> Optional[DFAState]:
			nonlocal new_states_num
			if state is None:
				return None
			state = state.repr
			assert state is not None
			if state in new_states:
				return new_states[state]
			new_state: DFAState = DFAState()
			new_states_num += 1
			new_state.accepts = state.accepts
			new_states[state] = new_state
			for i in range(256):
				new_state.trans[i] = remap_state(state.trans[i])
			return new_state

		out_state = remap_state(state)
		assert out_state is not None

		return out_state


def minimize(state: DFAState) -> DFAState:
	m = MinimizeDFA()
	return m.run(state)
