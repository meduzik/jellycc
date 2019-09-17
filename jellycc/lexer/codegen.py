import json
from typing import List, Dict, Set, Tuple, TextIO, Optional

from jellycc.codegen.codegen import CodePrinter, parse_template
from jellycc.lexer.dfa import DFAState
from jellycc.lexer.grammar import LexerGrammar

import os

from jellycc.project.grammar import Terminal
from jellycc.utils.helpers import head

AcceptBit = 1


class PHFState:
	def __init__(self, ch: Optional[int], token: Optional[Terminal], end_offset: int):
		self.ch: Optional[int] = ch
		self.token: Optional[Terminal] = token
		self.end_offset: int = end_offset


class Codegen:
	def __init__(self, grammar: LexerGrammar, dfa: DFAState) -> None:
		self.grammar: LexerGrammar = grammar
		self.initial_dfa: DFAState = dfa
		self.all_states: List[DFAState] = []
		self.state_idx: Dict[DFAState, int] = dict()
		self.state_accepts: Dict[DFAState, int] = dict()
		self.eq_classes: List[int] = [0] * 256
		self.classes: List[Set[int]] = [set(range(256))]
		self.phf_data: List[PHFState] = []

	def write(self, path: str) -> TextIO:
		os.makedirs(os.path.dirname(path), exist_ok=True)
		return open(path, 'w')

	def run(self) -> None:
		self.compute()

		module_dir = os.path.dirname(os.path.abspath(__file__))

		header_path = self.grammar.header_path
		if header_path is not None:
			with self.write(header_path) as fp:
				parse_template(os.path.join(module_dir, "lexer.h")).run(self.grammar.shared.base_dir, header_path, fp, self.subst)

		source_path = self.grammar.source_path
		if source_path is not None:
			with self.write(source_path) as fp:
				parse_template(os.path.join(module_dir, "lexer.cpp")).run(self.grammar.shared.base_dir, source_path, fp, self.subst)

	def state_to_value(self, state: DFAState) -> int:
		return (self.state_idx[state]) * 2

	def subst(self, printer: CodePrinter, name: str) -> None:
		if name == "lexer_prefix":
			printer.write(self.grammar.prefix)
		elif name == "lexer_namespace":
			printer.write(self.grammar.namespace)
		elif name == "equiv_table":
			for klass in self.eq_classes:
				printer.write(f"{klass * 2 * len(self.all_states)},")
		elif name == "equiv_stride":
			printer.write(f"{len(self.all_states) * 2}")
		elif name == "lexer_unroll_count":
			printer.write("8")
		elif name == "fin_trans_table":
			for state in self.all_states:
				if state.accepts is not None:
					val = AcceptBit
				else:
					val = 0
				printer.write(f"{val}u, ")
		elif name == "accept_table":
			for state in self.all_states:
				val = self.state_accepts[state]
				printer.write(f"{val}u, ")
		elif name == "trans_table":
			for class_set in self.classes:
				class_repr = head(class_set)
				for state in self.all_states:
					transition = state.trans[class_repr]
					if transition is None:
						initial_trans = self.initial_dfa.trans[class_repr]
						assert initial_trans is not None
						val: int = self.state_to_value(initial_trans) | AcceptBit
					else:
						val = self.state_to_value(transition)
					printer.write(f"{val}u, ")
				printer.writeln("")
		elif name == "lexer_terminals":
			printer.writeln(f"#define {self.grammar.prefix}_TOKENS(X) \\")
			with printer.indented():
				for terminal in self.grammar.shared.terminals_list:
					printer.writeln(f"X({terminal.lang_name}, {terminal.value}, {json.dumps(terminal.name)}) \\")
			printer.writeln('')
		else:
			raise RuntimeError(f"INTERNAL ERROR: unresolved substitution '{name}'")

	def compute(self) -> None:
		def visit(state: DFAState) -> None:
			self.state_idx[state] = len(self.all_states)
			self.all_states.append(state)
		self.initial_dfa.visit(visit)
		self._build_classes()
		self._build_accepts()

	def _build_classes(self) -> None:
		classes = self.classes

		unique_refines: Set[Tuple[int, ...]] = set()

		def refine(partition: Tuple[int, ...]):
			if partition in unique_refines:
				return
			unique_refines.add(partition)
			n = len(classes)
			for idx in range(n):
				clss = classes[idx]
				inter = clss.intersection(partition)
				if len(inter) == len(clss):
					continue
				if len(inter) == 0:
					continue
				clss.difference_update(inter)
				classes.append(inter)

		for state in self.all_states:
			state_classes = dict()
			for idx, target_state in enumerate(state.trans):
				if target_state not in state_classes:
					state_classes[target_state] = set()
				state_classes[target_state].add(idx)
			for target_state, chars in state_classes.items():
				refine(tuple(chars))

		for idx, chars in enumerate(classes):
			for ch in chars:
				self.eq_classes[ch] = idx

	def _build_accepts(self) -> None:
		for state in self.all_states:
			if state.accepts is not None:
				terminal_value = state.accepts.terminal.value
				assert terminal_value is not None
				self.state_accepts[state] = terminal_value
			else:
				self.state_accepts[state] = 0

