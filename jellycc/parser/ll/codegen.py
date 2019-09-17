from typing import List, Dict, Tuple, Optional, Callable

from jellycc.codegen.codegen import CodePrinter, parse_template

import os

from jellycc.parser.grammar import ParserGrammar, SymbolTerminal, TypeVoid, Type, Action
from jellycc.parser.ll.lhtable import LHTable, LHState, Transition, MegaAction, MegaActionNode, Shift, SkipNode
from jellycc.utils.helpers import chunked


class SharedData:
	def __init__(self):
		self.action_sync_insert_token: int = -1
		self.action_sync_skip_token: int = -1

		self.action_lec_remove: int = -1
		self.action_lec_insert: int = -1
		self.action_lec_replace: int = -1

		self.action_sentinel: int = -1

		self.action_to_index: Dict[MegaAction, int] = dict()
		self.state_to_index: Dict[LHState, int] = dict()

		self.megaactions: List[MegaAction] = []


class TableRow:
	def __init__(self, state: LHState):
		self.state: LHState = state
		self.base_offset: int = 0
		self.transition_map: Dict[Transition, int] = dict()


SyncEntry = Tuple[int, int]


class SyncRow:
	def __init__(self, table: 'SyncTable'):
		self.table: SyncTable = table
		self.term_dispatch: Dict[SymbolTerminal, SyncEntry] = dict()
		self.skip_dispatch: Tuple[int, int] = (0, 0)
		self.entries: Dict[SyncEntry, int] = dict()
		self.base: int = len(self.table.sync_entries)
		self.table.sync_base.append(self.base)

	def register_entry(self, entry: SyncEntry) -> None:
		if entry not in self.entries:
			self.entries[entry] = len(self.entries)
			self.table.sync_entries.append(entry)


class SyncTable:
	def __init__(self, shared: SharedData):
		self.shared: SharedData = shared

		self.sync_rows: List[SyncRow] = []
		self.sync_base: List[int] = []
		self.sync_entries: List[SyncEntry] = []
		self.sync_actions: List[int] = []
		self.sync_states: List[int] = []

		self.actions_ref: Dict[Tuple[SkipNode, ...], int] = dict()
		self.states_ref: Dict[Tuple[LHState, ...], int] = dict()

	def add_row(self) -> SyncRow:
		row = SyncRow(self)
		self.sync_rows.append(row)
		return row

	def add_action_sequence(self, cost: int, actions: Tuple[SkipNode, ...]) -> int:
		if actions not in self.actions_ref:
			pos = len(self.sync_actions)
			self.sync_actions.append(cost)
			self.sync_actions.append(len(actions))
			for action in actions:
				if isinstance(action, SymbolTerminal):
					self.sync_actions.append(self.shared.action_sync_insert_token)
				else:
					self.sync_actions.append(self.shared.action_to_index[action])
			for action in actions:
				if isinstance(action, SymbolTerminal):
					self.sync_actions.append(action.terminal.value)
			self.actions_ref[actions] = pos
		return self.actions_ref[actions]

	def add_state_sequence(self, states: Tuple[LHState, ...]) -> int:
		if states not in self.states_ref:
			pos = len(self.sync_states)
			self.sync_states.append(len(states))
			for state in reversed(states):
				self.sync_states.append(self.shared.state_to_index[state])
			self.states_ref[states] = pos
		return self.states_ref[states]


class CodegenLH:
	def __init__(self, grammar: ParserGrammar, table: LHTable) -> None:
		self.grammar: ParserGrammar = grammar
		self.table: LHTable = table

		self.shared_data: SharedData = SharedData()

		self.max_terminal_value: int = 0
		self.terminal_table_size: int = 0

		self.value_to_terminal: Dict[int, SymbolTerminal] = dict()
		self.eps_terminals: List[SymbolTerminal] = []
		self.all_terminals: List[Optional[SymbolTerminal]] = []

		self.states: List[TableRow] = []
		self.state_map: Dict[LHState, TableRow] = dict()

		self.table_data: List[int] = []
		self.entry_data: List[Transition] = []
		self.entry_map: Dict[Transition, int] = dict()

		self.sync_table: SyncTable = SyncTable(self.shared_data)

	def run(self) -> None:
		self.compute()

		module_dir = os.path.dirname(os.path.abspath(__file__))

		header_path = self.grammar.core_header_path
		if header_path is not None:
			with open(header_path, 'w') as fp:
				parse_template(os.path.join(module_dir, "parser_core.h")).run(
					self.grammar.shared.base_dir,
					header_path,
					fp,
					self.subst
				)

		source_path = self.grammar.core_source_path
		if source_path is not None:
			with open(source_path, 'w') as fp:
				parse_template(os.path.join(module_dir, "parser_core.cpp")).run(
					self.grammar.shared.base_dir,
					source_path,
					fp,
					self.subst
				)

	def push_val(self, printer: CodePrinter, type: Type, offset: str, func: Callable[[], None]) -> None:
		type = type.repr()
		if isinstance(type, TypeVoid):
			printer.write("(void)")
		else:
			printer.write(f"*({type}*)(data{offset}) = ")
		printer.writeln("(")
		func()
		printer.writeln(");")
		if (not isinstance(type, TypeVoid)):
			printer.writeln(f"data += Aligned<{type}>;")
		if len(offset) > 0:
			printer.writeln(f"data += {offset};")

	def print_action_expr(self, printer: CodePrinter, action: MegaActionNode) -> None:
		pass

	def print_action(self, printer: CodePrinter, action: MegaActionNode) -> None:
		printer.writeln("{")
		with printer.indented():
			if action is Shift:
				def print_shift():
					_, _, (loc, name) = self.grammar.vm_actions['shift']
					printer.include(loc, name)
				self.push_val(printer, self.grammar.terminal_type, "", print_shift)
			else:
				assert(isinstance(action, Action))

				typelist: List[str] = []
				for name, type in reversed(action.args):
					type = type.repr()
					if isinstance(type, TypeVoid):
						continue
					typelist.append(str(type))
					if name:
						printer.writeln(f"{type} ${name} = *({type}*)(data - ListOffset<{','.join(typelist)}>);")

				def print_action():
					printer.include(action.loc, action.source)

				if len(typelist) > 0:
					offset = f"-ListOffset<{','.join(typelist)}>"
				else:
					offset = ""
				self.push_val(printer, action.type, offset, print_action)
		printer.writeln("}")

	def subst(self, printer: CodePrinter, name: str) -> None:
		if name == "parser_prefix":
			printer.write(self.grammar.prefix)
		elif name == "parser_namespace":
			printer.write(self.grammar.ns)
		elif name == "token_count":
			printer.write(str(self.terminal_table_size))
		elif name == "state_count":
			printer.write(str(len(self.states)))
		elif name == "base_data":
			for chunk in chunked(self.states, 10):
				printer.write(', '.join(map(lambda row: str(row.base_offset), chunk)))
				printer.writeln(',')
		elif name == "dispatch_data":
			def get_offset_of(row: TableRow, t: Optional[SymbolTerminal]) -> int:
				if t is None:
					return 0xff
				if t in row.state.transitions:
					return row.transition_map[row.state.transitions[t]]
				if row.state.etransition is not None:
					return row.transition_map[row.state.etransition]
				return 0xff

			for row in self.states:
				printer.write('{')
				printer.write(','.join(map(lambda t: str(get_offset_of(row, t)), self.all_terminals)))
				printer.writeln('},')

			printer.write('{')
			for i in range(len(self.all_terminals)):
				printer.write('255,')
			printer.writeln('},')
		elif name == "table_data":
			for chunk in chunked(self.table_data, 16):
				printer.write(','.join(map(str, chunk)))
				printer.writeln(',')
		elif name == "entries_data":
			for chunk in chunked(self.entry_data, 6):
				for (shift, action, states) in chunk:
					printer.write('{')
					printer.write('1,' if shift else '0,')
					printer.write(str(len(states) - 1))
					printer.write(',')
					printer.write(str(self.shared_data.action_to_index[action]))
					printer.write(',')
					printer.write('{')
					for i in range(4):
						if i < len(states):
							printer.write(str(states[len(states) - i - 1].order))
							printer.write(',')
						else:
							printer.write('0,')
					printer.write('}')
					printer.write('},')
				printer.writeln('')
		elif name == "entry_states":
			for name, nt in self.grammar.exports.items():
				printer.writeln(f"{name} = {self.table.entries[nt].order},")
		elif name == "sentinel_state":
			printer.write(f'{len(self.states)}')
		elif name == "vm_extract_vm_args":
			for _, name, type in self.grammar.vm_args:
				printer.writeln(f'{type}& {name} = parser->vm_args.{name};')
		elif name == "vm_extra_params":
			for _, name, type in self.grammar.vm_args:
				printer.write(f', {type} {name}')
		elif name == "vm_struct":
			for _, name, type in self.grammar.vm_args:
				printer.writeln(f'{type} {name};')
		elif name == "vm_copy_params":
			for _, name, _ in self.grammar.vm_args:
				printer.write(f'{name},')
		elif name == "vm_dispatch_switch":
			self.write_dispatch(printer)
		elif name == "vm_action_sentinel":
			printer.write(f'{self.shared_data.action_sentinel}')
		elif name == "parser_header":
			printer.include(self.grammar.parser_header.loc, self.grammar.parser_header.contents)
		elif name == "parser_source":
			printer.include(self.grammar.parser_source.loc, self.grammar.parser_source.contents)
		elif name == "sync_dispatch_data":
			self.write_sync_dispatch_data(printer)
		elif name == "sync_base_data":
			self.write_sync_base_data(printer)
		elif name == "sync_entries_data":
			self.write_sync_entries_data(printer)
		elif name == "sync_actions_data":
			self.write_sync_actions_data(printer)
		elif name == "sync_states_data":
			self.write_sync_states_data(printer)
		elif name == "action_panic_skip":
			printer.write(f'{self.shared_data.action_sync_skip_token}')
		elif name == "action_panic_insert":
			printer.write(f'{self.shared_data.action_sync_insert_token}')
		elif name == "action_lec_remove":
			printer.write(f'{self.shared_data.action_lec_remove}')
		elif name == "action_lec_insert":
			printer.write(f'{self.shared_data.action_lec_insert}')
		elif name == "action_lec_replace":
			printer.write(f'{self.shared_data.action_lec_replace}')
		elif name == "sync_token_skip_cost_data":
			printer.writeln(','.join(map(lambda t: '1', self.all_terminals)))
		elif name == "sync_token_insert_cost_data":
			printer.writeln(','.join(map(lambda t: '1', self.all_terminals)))
		elif name == "sync_token_sync_cost_data":
			printer.writeln(','.join(map(lambda t: '1', self.all_terminals)))
		elif name == "sync_state_skip_ref_data":
			for chunk in chunked(self.sync_table.sync_rows, 16):
				printer.write(','.join(map(lambda row: str(row.skip_dispatch[1]), chunk)))
				printer.writeln(',')
		elif name == "sync_state_skip_cost_data":
			for chunk in chunked(self.sync_table.sync_rows, 16):
				printer.write(','.join(map(lambda row: str(row.skip_dispatch[0]), chunk)))
				printer.writeln(',')
		elif name == "vm_action_panic_skip":
			printer.include(*self.grammar.vm_actions["sync_skip"][2])
		elif name == "vm_action_panic_insert":
			printer.include(*self.grammar.vm_actions["sync_insert"][2])
		elif name == "vm_action_lec_insert":
			printer.include(*self.grammar.vm_actions["correction_insert"][2])
		elif name == "vm_action_lec_remove":
			printer.include(*self.grammar.vm_actions["correction_remove"][2])
		elif name == "vm_action_lec_replace":
			printer.include(*self.grammar.vm_actions["correction_replace"][2])
		else:
			raise RuntimeError(f"INTERNAL ERROR: unresolved substitution '{name}'")

	def write_dispatch(self, printer: CodePrinter) -> None:
		for action_id, megaaction in enumerate(self.shared_data.megaactions):
			printer.writeln(f"case {action_id}: {{")
			with printer.indented():
				for action in megaaction.actions:
					self.print_action(printer, action)
			printer.writeln("break; }")

	def write_sync_actions_data(self, printer: CodePrinter) -> None:
		for items in chunked(self.sync_table.sync_actions, 16):
			printer.write(','.join(map(str, items)))
			printer.writeln(',')

	def write_sync_states_data(self, printer: CodePrinter) -> None:
		for items in chunked(self.sync_table.sync_states, 16):
			printer.write(','.join(map(str, items)))
			printer.writeln(',')

	def write_sync_entries_data(self, printer: CodePrinter) -> None:
		for entries in chunked(self.sync_table.sync_entries, 10):
			for entry in entries:
				printer.write(f'{{{entry[0]}, {entry[1]}}},')
			printer.writeln('')

	def write_sync_base_data(self, printer: CodePrinter) -> None:
		for rows in chunked(self.sync_table.sync_rows, 16):
			printer.write(','.join(map(lambda row: str(row.base), rows)))
			printer.writeln(',')

	def write_sync_dispatch_data(self, printer: CodePrinter) -> None:
		def get_offset_of(row: SyncRow, term: SymbolTerminal) -> int:
			if term in row.term_dispatch:
				return row.entries[row.term_dispatch[term]]
			return 0xff

		for term in self.all_terminals:
			printer.write('{')
			for row in self.sync_table.sync_rows:
				printer.write(str(get_offset_of(row, term)))
				printer.write(',')
			printer.writeln('},')

	def compute(self) -> None:
		self.collect_data()
		self.build_tables()
		self.build_recovery()

	def collect_data(self) -> None:
		for terminal in self.grammar.terminals:
			self.max_terminal_value = max(self.max_terminal_value, terminal.terminal.value)
			self.value_to_terminal[terminal.terminal.value] = terminal
			self.eps_terminals.append(terminal)
		self.terminal_table_size = self.max_terminal_value + 1
		for i in range(self.terminal_table_size):
			self.all_terminals.append(self.value_to_terminal.get(i, None))

	def build_tables(self) -> None:
		self.visit_action(self.table.null_action)
		for state in self.table.states:
			self.build_state(state)

	def visit_action(self, megaaction: MegaAction) -> None:
		if megaaction not in self.shared_data.action_to_index:
			self.shared_data.action_to_index[megaaction] = len(self.shared_data.megaactions)
			self.shared_data.megaactions.append(megaaction)

	def get_transition_index(self, transition: Transition) -> int:
		if transition not in self.entry_map:
			self.entry_map[transition] = len(self.entry_data)
			self.entry_data.append(transition)
		return self.entry_map[transition]

	def build_state(self, state: LHState) -> None:
		row = TableRow(state)
		row.base_offset = len(self.table_data)

		def visit_transition(state: LHState, row: TableRow, transition: Transition):
			if transition not in row.transition_map:
				row.transition_map[transition] = len(row.transition_map)
				self.table_data.append(self.get_transition_index(transition))
			self.visit_action(transition[1])

		if state.etransition is not None:
			visit_transition(state, row, state.etransition)
		for term, transition in sorted(state.transitions.items(), key=lambda p: p[0].terminal.value):
			visit_transition(state, row, transition)

		self.shared_data.state_to_index[state] = len(self.states)
		self.state_map[state] = row
		self.states.append(row)

	def build_recovery(self) -> None:
		actions_count = len(self.shared_data.megaactions)
		self.shared_data.action_sync_skip_token = actions_count
		self.shared_data.action_sync_insert_token = actions_count + 1
		self.shared_data.action_lec_insert = actions_count + 2
		self.shared_data.action_lec_remove = actions_count + 3
		self.shared_data.action_lec_replace = actions_count + 4
		self.shared_data.action_sentinel = actions_count + 5

		for row in self.states:
			state = row.state
			sync_row = self.sync_table.add_row()

			for term, (cost, actions, states) in state.sync.items():
				entry = (
					self.sync_table.add_action_sequence(cost, actions),
					self.sync_table.add_state_sequence(states)
				)
				sync_row.register_entry(entry)
				sync_row.term_dispatch[term] = entry

			assert(state.sync_skip is not None)
			cost, actions = state.sync_skip
			sync_row.skip_dispatch = (cost, self.sync_table.add_action_sequence(cost, actions))