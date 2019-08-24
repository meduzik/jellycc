import json
from typing import List, Dict, Set, Tuple, Optional

from jellycc.codegen.codegen import CodePrinter, parse_template


import os

from jellycc.parser.grammar import ParserGrammar, SymbolNonTerminal, Production, SymbolTerminal
from jellycc.parser.lalr import LRTable, LR0Set
from jellycc.parser.lr1 import LR1State, Shift, Reduce, AcceptType, RejectType, Accept

AcceptBit = 1


class Codegen:
	def __init__(self, grammar: ParserGrammar, table: LRTable) -> None:
		self.grammar: ParserGrammar = grammar
		self.table: LRTable = table

		self.states: Dict[int, LR1State] = dict()
		self.state_idx: Dict[LR1State, int] = dict()

		self.nts: Dict[int, SymbolNonTerminal] = dict()
		self.nt_idx: Dict[SymbolNonTerminal, int] = dict()

		self.productions: Dict[int, Production] = dict()
		self.prod_idx: Dict[Production, int] = dict()

		self.dispatch: Dict[LR1State, List[int]] = dict()
		self.payload: Dict[LR1State, List[int]] = dict()
		self.dispatch_dict: Dict[LR1State, Dict[int, int]] = dict()

		self.goto: Dict[LR1State, List[int]] = dict()

		self.resolve: List[int] = []

		self.token_count: int = 0
		self.shift_count: int = 0
		self.dispatch_count: int = 0

	def run(self) -> None:
		self.compute()

		module_dir = os.path.dirname(os.path.abspath(__file__))

		header_path = self.grammar.core_header_path
		if header_path is not None:
			with open(header_path, 'w') as fp:
				parse_template(os.path.join(module_dir, "parser_core.h")).run(header_path, fp, self.subst)

		source_path = self.grammar.core_source_path
		if source_path is not None:
			with open(source_path, 'w') as fp:
				parse_template(os.path.join(module_dir, "parser_core.cpp")).run(source_path, fp, self.subst)

	def subst(self, printer: CodePrinter, name: str) -> None:
		if name == "parser_prefix":
			printer.write(self.grammar.prefix)
		elif name == "token_count":
			printer.write(f"{self.token_count}")
		elif name == "goto_count":
			printer.write(f"{1 + self.shift_count + len(self.nts)}")
		elif name == "dispatch_count":
			printer.write(f"{self.dispatch_count}")
		elif name == "table_resolve":
			for val in self.resolve:
				printer.write(f"{val}u, ")
		elif name == "export_symbols":
			for nt, state in self.table.entries.items():
				printer.writeln(f"{nt.name} = {self.state_idx[state]},")
		elif name == "count_shifts":
			printer.write(f"{self.shift_count}")
		elif name == "table_dispatch":
			printer.write("{")
			for i in range(self.token_count):
				printer.write(f"255u, ")
			printer.writeln("},")
			for i in range(1, len(self.states) + 1):
				state = self.states[i]
				printer.write("{")
				for j in self.dispatch[state]:
					printer.write(f"{j}u, ")
				printer.writeln("},")
		elif name == "table_payload":
			printer.writeln("{},")
			for i in range(1, len(self.states) + 1):
				state = self.states[i]
				printer.write("{")
				for j in self.payload[state]:
					printer.write(f"{j}u, ")
				printer.writeln("},")
		elif name == "table_goto":
			printer.writeln("{},")
			for i in range(1, len(self.states) + 1):
				state = self.states[i]
				printer.write("{")
				for j in self.goto[state]:
					printer.write(f"{j}u, ")
				printer.writeln("},")
		elif name == "table_accepts":
			printer.write("0,")
			eof = self.grammar.eof
			for i in range(1, len(self.states) + 1):
				state = self.states[i]
				if state.actions.get(eof, None) is Accept:
					printer.write("1,")
				else:
					printer.write("0,")
		elif name == "token_eof":
			printer.write(f"{self.grammar.eof.terminal.value}")
		elif name == "debug_grammar":
			with printer.indented('// '):
				for idx in range(len(self.nts)):
					printer.writeln(f"NT {idx}: {self.nts[idx].name}")
				printer.writeln("")
				for idx in range(len(self.productions)):
					printer.writeln(f"PROD {idx}: {self.productions[idx].nt.name} -> {self.productions[idx]}")
				printer.writeln("")
		else:
			raise RuntimeError(f"INTERNAL ERROR: unresolved substitution '{name}'")

	def compute(self) -> None:
		self._pre_visit()
		self._build_tables()

	def _pre_visit(self) -> None:
		visited: Set[LR1State] = set()

		def visit_nt(nt: SymbolNonTerminal) -> None:
			if nt in self.nt_idx:
				return
			idx = len(self.nt_idx)
			self.nt_idx[nt] = idx
			self.nts[idx] = nt

		def visit_prod(prod: Production) -> None:
			if prod in self.prod_idx:
				return
			idx = len(self.prod_idx)
			self.prod_idx[prod] = idx
			self.productions[idx] = prod

		max_unique_shifts: int = 0

		def visit_state(state: LR1State) -> None:
			if state in visited:
				return

			nonlocal max_unique_shifts

			visited.add(state)

			idx = len(self.state_idx) + 1
			self.state_idx[state] = idx
			self.states[idx] = state

			shifts: Set[LR1State] = set()
			for term, action in state.actions.items():
				if isinstance(action, Shift):
					visit_state(action.state)
					shifts.add(action.state)
				elif isinstance(action, Reduce):
					visit_nt(action.nt)
					visit_prod(action.prod)
				elif isinstance(action, AcceptType):
					pass
				else:
					raise RuntimeError("INTERNAL ERROR: invalid LR action")
			max_unique_shifts = max(max_unique_shifts, len(shifts))
			for nt, target_state in state.gotos.items():
				visit_nt(nt)
				visit_state(target_state)

		for state in self.table.entries.values():
			visit_state(state)

		self.shift_count = max_unique_shifts

	def _build_tables(self) -> None:
		terminals: Dict[int, SymbolTerminal] = dict()

		max_term: int = 0
		for terminal in self.grammar.terminals:
			value = terminal.terminal.value
			assert value is not None
			terminals[value] = terminal
			max_term = max(value, max_term)

		self.token_count = max_term + 1
		skip_resolve_idx: int = 0

		max_unique_actions: int = 0

		for state, state_idx in self.state_idx.items():
			token_to_act: List[Optional[Tuple[int, int]]] = [None] * self.token_count
			for term in self.grammar.terminals:
				value = term.terminal.value
				if term.terminal.skip:
					token_to_act[value] = (0, skip_resolve_idx)

			target_states: Dict[LR1State, int] = dict()
			target_states_inv: Dict[int, LR1State] = dict()

			def get_unique_index(state: LR1State) -> int:
				if state not in target_states:
					idx = len(target_states) + 1
					target_states[state] = idx
					target_states_inv[idx] = state
				return target_states[state]

			dispatch: List[int] = [0xff] * self.token_count

			for term, action in state.actions.items():
				value = term.terminal.value
				if isinstance(action, Shift):
					token_to_act[value] = (0, get_unique_index(action.state))
				elif isinstance(action, Reduce):
					token_to_act[value] = (len(action.prod.symbols), 1 + self.shift_count + self.prod_idx[action.prod])

			dispatch_dict: Dict[int, int] = dict()

			def get_unique_dispatch(entry: Tuple[int, int]) -> int:
				val = (entry[0] << 12) | entry[1]
				if val not in dispatch_dict:
					dispatch_dict[val] = len(dispatch_dict)
				return dispatch_dict[val]

			for idx, entry in enumerate(token_to_act):
				if entry is not None:
					dispatch[idx] = get_unique_dispatch(entry)
				else:
					dispatch[idx] = 0xff

			goto: List[int] = [0xDE] * (1 + self.shift_count + len(self.nts))
			# shifts
			for target_state, idx in target_states.items():
				goto[idx] = self.state_idx[target_state]
			# skip
			goto[skip_resolve_idx] = state_idx
			# gotos
			for nt, target_state in state.gotos.items():
				idx = self.shift_count + 1 + self.nt_idx[nt]
				if goto[idx] != 0xDE:
					raise RuntimeError("INTERNAL ERROR: incosistent goto produced")
				goto[idx] = self.state_idx[target_state]

			self.dispatch[state] = dispatch
			self.goto[state] = goto
			self.dispatch_dict[state] = dispatch_dict
			max_unique_actions = max(max_unique_actions, len(dispatch_dict))

		self.dispatch_count = max_unique_actions

		for state, state_idx in self.state_idx.items():
			payload: List[int] = [0xDE] * self.dispatch_count
			for val, idx in self.dispatch_dict[state].items():
				payload[idx] = val
			self.payload[state] = payload

		self.resolve = [0xDE] * (1 + self.shift_count + len(self.productions))
		for i in range(self.shift_count + 1):
			self.resolve[i] = i
		for idx, prod in self.productions.items():
			self.resolve[self.shift_count + 1 + idx] = self.shift_count + 1 + self.nt_idx[prod.nt]

