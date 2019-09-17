from typing import Tuple, Iterable, Union, Dict, List, Set, Optional

from jellycc.parser.grammar import ParserGrammar, Action, SymbolTerminal, SymbolNonTerminal
from jellycc.parser.ll.builder import LLBuilder, LLState


class ShiftType:
	def __init__(self) -> None:
		pass

	def __str__(self) -> str:
		return "S"


Shift = ShiftType()


MegaActionNode = Union[Action, ShiftType]


class MegaAction:
	def __init__(self, actions: Iterable[MegaActionNode]):
		self.actions: Tuple[MegaActionNode, ...] = tuple(actions)

	def __str__(self) -> str:
		return ' '.join(map(str, self.actions))


Transition = Tuple[bool, MegaAction, Tuple['LHState', ...]]
SkipNode = Union[SymbolTerminal, MegaAction]


class LHState:
	def __init__(self, list: List['LHState']):
		self.order: int = len(list)
		list.append(self)
		self.transitions: Dict[SymbolTerminal, Transition] = dict()
		self.etransition: Optional[Transition] = None
		self.target_states: Set[LHState] = set()
		self.sync_skip: Optional[Tuple[int, Tuple[SkipNode, ...]]] = None
		self.sync: Dict[SymbolTerminal, Tuple[int, Tuple[SkipNode, ...], Tuple[LHState, ...]]] = dict()

	def __str__(self) -> str:
		return str(self.order)


class LHTable:
	def __init__(
		self,
		entries: Dict[SymbolNonTerminal, LHState],
		states: List[LHState],
		null_action: MegaAction
	):
		self.entries: Dict[SymbolNonTerminal, LHState] = entries
		self.states: List[LHState] = states
		self.null_action: MegaAction = null_action


class LHTableBuilder:
	def __init__(self, grammar: ParserGrammar):
		self.grammar = grammar
		self.entries: Dict[SymbolNonTerminal, LHState] = dict()
		self.state_map: Dict[LLState, LHState] = dict()
		self.states: List[LHState] = []
		self.megaactions: Dict[Tuple[MegaActionNode], MegaAction] = dict()
		self.terminal_map: Dict[SymbolTerminal, LHState] = dict()
		self.long_transition_map: Dict[Tuple[LHState], LHState] = dict()
		self.action_map: Dict[Action, LHState] = dict()

	def build(self) -> LHTable:
		ll_builder = LLBuilder(self.grammar)
		ll_builder.build()

		for nt, ll_state in ll_builder.entries.items():
			self.entries[nt] = self.convert_state(ll_state)

		self.optimize_states()
		self.split_long_states()

		return LHTable(
			self.entries,
			self.states,
			self.get_megaaction(())
		)

	def dump_states(self):
		for state in self.states:
			print(f"State {state.order}")
			for term, (shift, action, targets) in state.transitions.items():
				print(f"  {term} -> {shift}; {action}; {' '.join(map(str, targets))}")
			if state.etransition:
				shift, action, targets = state.etransition
				print(f"  <$>  -> {shift}; {action}; {' '.join(map(str, targets))}")

	def get_megaaction(self, seq: Iterable[MegaActionNode]) -> MegaAction:
		key = tuple(seq)
		if key not in self.megaactions:
			self.megaactions[key] = MegaAction(key)
		return self.megaactions[key]

	def convert_action(self, action: Action) -> LHState:
		if action not in self.action_map:
			lh = LHState(self.states)
			lh.etransition = (False, self.get_megaaction((action,)), ())
			self.action_map[action] = lh
		return self.action_map[action]

	def convert_terminal(self, terminal: SymbolTerminal) -> LHState:
		if terminal not in self.terminal_map:
			lh = LHState(self.states)
			lh.transitions[terminal] = (True, self.get_megaaction((Shift,)), ())
			self.terminal_map[terminal] = lh
		return self.terminal_map[terminal]

	def convert_state(self, ll: LLState) -> LHState:
		if ll in self.state_map:
			return self.state_map[ll]
		lh = LHState(self.states)
		self.state_map[ll] = lh
		for production in ll.productions:
			action_collection: List[MegaActionNode] = []
			terminals: Set[SymbolTerminal] = set()
			targets: List[LHState] = []
			shift: bool = False
			items = production.items
			n = len(items)
			idx = 0
			while idx < n:
				item = items[idx]
				if isinstance(item, Action):
					action_collection.append(item)
				elif isinstance(item, SymbolTerminal):
					terminals.add(item)
					action_collection.append(Shift)
					idx += 1
					while idx < n and isinstance(items[idx], Action):
						action_collection.append(items[idx])
						idx += 1
					shift = True
					break
				elif isinstance(item, LLState):
					terminals.update(item.first)
					break
				idx += 1
			while idx < n:
				item = items[idx]
				if isinstance(item, Action):
					targets.append(self.convert_action(item))
				elif isinstance(item, SymbolTerminal):
					targets.append(self.convert_terminal(item))
				elif isinstance(item, LLState):
					targets.append(self.convert_state(item))
				idx += 1
			transition = (shift, self.get_megaaction(action_collection), tuple(targets))
			if len(terminals) == 0:
				lh.etransition = transition
			else:
				for terminal in terminals:
					lh.transitions[terminal] = transition
		return lh

	def optimize_states(self) -> None:
		self.inline_states()
		self.filter_states()

	def convert_long_transition(self, states: Tuple[LHState]) -> LHState:
		if states not in self.long_transition_map:
			lh = LHState(self.states)
			lh.etransition = self.create_long_transition(False, self.get_megaaction(()), states)
			self.long_transition_map[states] = lh
		return self.long_transition_map[states]

	def create_long_transition(self, shift: bool, action: MegaAction, states: Tuple[LHState]) -> Transition:
		if len(states) <= 4:
			return (shift, action, states)
		return (shift, action, (*states[:3], self.convert_long_transition(states[3:])))

	def split_long_transition(self, transition: Optional[Transition]) -> Optional[Transition]:
		if transition is None:
			return transition
		shift, actions, states = transition
		if len(states) <= 4:
			return transition
		return self.create_long_transition(shift, actions, states)

	def split_long_states(self) -> None:
		for state in self.states:
			for term, trans in state.transitions.items():
				state.transitions[term] = self.split_long_transition(trans)
			state.etransition = self.split_long_transition(state.etransition)

	def inline_states(self) -> None:
		for state in self.states:
			for term, (shift, action, targets) in state.transitions.items():
				if (not shift):
					stack: List[LHState] = list(reversed(targets))
					actions: List[Action] = list(action.actions)
					while len(stack) > 0:
						their_state = stack.pop()
						if term in their_state.transitions:
							(tshift, taction, ttargets) = their_state.transitions[term]
						else:
							(tshift, taction, ttargets) = their_state.etransition
						actions.extend(taction.actions)
						stack.extend(reversed(ttargets))
						shift = tshift
						if shift:
							break
					state.transitions[term] = (shift, self.get_megaaction(actions), tuple(reversed(stack)))

	def filter_states(self) -> None:
		new_list: List[LHState] = []
		visited: Set[LHState] = set()

		def visit(state: LHState):
			if state in visited:
				return
			state.order = len(visited)
			visited.add(state)
			new_list.append(state)
			for _, (_, _, targets) in state.transitions.items():
				for target in targets:
					visit(target)
			if state.etransition is not None:
				(_, _, targets) = state.etransition
				for target in targets:
					visit(target)

		for state in self.entries.values():
			visit(state)

		self.states = new_list

	def simulate(self, nt: SymbolNonTerminal, s: str) -> None:
		input: List[SymbolTerminal] = []
		for word in s.split(' '):
			input.append(self.grammar.find_terminal(word))
		input.append(self.grammar.eof)

		stack: List[LHState] = [self.entries[nt]]
		output: List[MegaAction] = []

		pos = 0
		while True:
			if len(stack) == 0:
				break
			state = stack.pop()
			tok = input[pos]
			if tok in state.transitions:
				transition = state.transitions[tok]
			else:
				transition = state.etransition
			if transition is None:
				raise RuntimeError(f"simulated parse error around {pos}")
			(shift, action, target) = transition
			if shift:
				pos += 1
			if action.actions:
				output.append(action)
			for state in reversed(target):
				stack.append(state)

		print(f"Parse complete at {pos}. Actions taken:\n{' '.join(map(str, output))}")