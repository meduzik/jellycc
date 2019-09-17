import re
from collections import defaultdict
from typing import Dict, Set, List, Optional, Tuple

from jellycc.parser.ll.builder import LLBuilder
from jellycc.parser.ll.codegen import CodegenLH
from jellycc.parser.ll.lhtable import LHTableBuilder
from jellycc.parser.ll.recovery import LHRecovery
from jellycc.parser.lr.codegen import Codegen
from jellycc.parser.grammar import unify_type, TypeVariable, Type, TypeVoid, SymbolNonTerminal, Action, TypeConstant, \
	ParserGrammar, SymbolTerminal, Void
from jellycc.parser.lr.lalr import LALRBuilder, LRTable
from jellycc.parser.lr.lr1 import LR1State, Shift, Reduce
from jellycc.parser.lr.recovery import RecoveryBuilder
from jellycc.parser.template import TypeConstraint, TemplateNonTerminalRule, TemplateSymbol, CaptureRe, \
	TemplateNonTerminal, TemplateGrammar, TemplateExpr, TemplateAction
from jellycc.project.grammar import SharedGrammar
from jellycc.utils.error import CCError
from jellycc.utils.source import SrcLoc


ParserRule = Tuple[SrcLoc, str, List[str], Optional[TemplateExpr], List[TemplateSymbol], Optional[TemplateAction]]


SimpleNameRe = re.compile("^[a-zA-Z_][a-zA-Z0-9_]*$")


class ParserGenerator:
	def __init__(self, shared: SharedGrammar) -> None:
		self.shared: SharedGrammar = shared
		self.grammar = ParserGrammar(shared)
		self.template = TemplateGrammar(self.grammar)
		self.parser_rules: List[ParserRule] = []
		self.type_values: Dict[str, Type] = dict()
		self.exposed_nt: List[Tuple[SrcLoc, str]] = []
		self.types: List[Tuple[SrcLoc, str, str]] = []

	def construct(self) -> None:
		self._construct_terminals()
		self._construct_nonterminals()
		self._apply_types()
		self._populate_parser()
		self._typecheck_parser()
		self._simplify_actions()

	def is_simple_name(self, name: str) -> bool:
		return SimpleNameRe.match(name) is not None

	def _get_nt(self, loc: SrcLoc, name: str, param_count: int) -> TemplateNonTerminal:
		term = self.grammar.find_terminal(name)
		if term is not None:
			raise CCError(loc, f"name '{name}' is already assigned to a terminal at {term.terminal.loc}")
		nt = self.template.find_template(name)
		if not nt:
			nt = TemplateNonTerminal(self.template, loc, name, param_count)
			self.template.add_template(nt)
			return nt
		return nt

	def _construct_terminals(self) -> None:
		for terminal in self.shared.terminals.values():
			self.grammar.add_terminal(SymbolTerminal(terminal))
		if not self.shared.term_eof:
			raise CCError(None, "no terminal designated for {eof}")
		self.grammar.eof = self.grammar.find_terminal(self.shared.term_eof.name)

	def _construct_nonterminals(self) -> None:
		for (loc, name, param_names, cond, symbols, action) in self.parser_rules:
			nt = self._get_nt(loc, name, len(param_names))
			if nt.param_count != len(param_names):
				raise CCError(loc, f"nonterminal '{name}' has conflicting definitions, first definition at {nt.loc}")

			forced_captures: Dict[str, SrcLoc] = dict()
			unforced_captures: Dict[str, int] = defaultdict(lambda: 0)
			implicit_captures: Set[str] = set()
			used_captures: Set[str] = set()
			for symbol in symbols:
				if symbol.capture is not None:
					if symbol.capture in forced_captures:
						raise CCError(symbol.loc, f"capture '{symbol.capture}' already made at {forced_captures[symbol.capture]}")
					forced_captures[symbol.capture] = symbol.loc
					unforced_captures[symbol.name] += 1
				elif self.is_simple_name(symbol.name):
					unforced_captures[symbol.name] += 1
			new_symbols: List[TemplateSymbol] = []
			if action is not None:
				for capture_group in CaptureRe.finditer(action.text):
					capture = capture_group.group(1)
					if capture in forced_captures:
						used_captures.add(capture)
					elif (capture in unforced_captures):
						if unforced_captures[capture] > 1:
							raise CCError(action.loc, f"ambiguous capture '${capture}'")
						implicit_captures.add(capture)
					else:
						raise CCError(action.loc, f"undefined capture '${capture}'")
			for capture, capture_loc in forced_captures.items():
				if capture not in used_captures:
					raise CCError(capture_loc, f"capture '${capture}' is not used")
			for symbol in symbols:
				symbol_capture = symbol.capture
				if (symbol_capture is None) and (symbol.name in implicit_captures):
					symbol_capture = symbol.name
				new_symbols.append(TemplateSymbol(symbol.loc, symbol.name, symbol.params, symbol_capture))
			rule = TemplateNonTerminalRule(loc, nt, param_names, cond, new_symbols, action)
			nt.add_rule(rule)

	def _get_type(self, loc: SrcLoc, name: str) -> Type:
		if name not in self.type_values:
			if len(name) == 0:
				self.type_values[name] = Void
			else:
				self.type_values[name] = TypeConstant(loc, name)
		return self.type_values[name]

	def _simplify_actions(self) -> None:
		action_reprs: Dict[Tuple[Type, Tuple[Tuple[Optional[str], Type], ...], str], Action] = dict()

		def simplify_action(action: Action) -> Optional[Action]:
			action.type = action.type.repr()
			action.args = tuple(map(lambda param: (param[0], param[1].repr()), action.args))

			nonnulls: List[Tuple[Optional[str], Type]] = []
			captures: Set[str] = set()
			for param in action.args:
				if not isinstance(param[1], TypeVoid):
					nonnulls.append(param)
					if param[0] is not None:
						captures.add('$' + param[0])

			# case 1 (id): there is only one non-null type, and the action == its param name
			if len(nonnulls) == 1 and nonnulls[0][0] is not None and ('$' + nonnulls[0][0] == action.source.strip()):
				return None

			# case 2 (null): there are no non-null types, and the action == some param name or is empty
			if len(nonnulls) == 0:
				if len(action.source.strip()) == 0 or (action.source.strip() in captures):
					return None

			key = (action.type, action.args, action.source)
			if key not in action_reprs:
				action_reprs[key] = action
				self.grammar.register_action(action)
			return action_reprs[key]

		for nt in self.grammar.nonterminals:
			for prod in nt.prods:
				if prod.action:
					prod.action = simplify_action(prod.action)

	def _populate_parser(self) -> None:
		for loc, name in self.exposed_nt:
			template = self.template.find_template(name)
			if not template:
				raise CCError(loc, f"nonterminal '{name}' not found")
			nt_export = SymbolNonTerminal(f"{name}")
			nt_export.exported = True
			nt_export.add_rule([template.instantiate(loc, ())], None)
			self.grammar.add_nonterminal(nt_export)
			self.grammar.exports[name] = nt_export
			self.grammar.keep.add(nt_export)

	def _typecheck_parser(self) -> None:
		while True:
			progress = False
			discarded_constraints: Set[TypeConstraint] = set()
			for constraint in self.template.type_constraints:
				nonnull_types: List[Type] = []
				for _, type in constraint.params:
					if not isinstance(type.repr(), TypeVoid):
						nonnull_types.append(type)
				consumed = False
				if len(nonnull_types) == 0:
					unify_type(constraint.loc, constraint.type, Void)
					consumed = True
				elif len(nonnull_types) == 1:
					unify_type(constraint.loc, constraint.type, nonnull_types[0])
					consumed = True
				if consumed:
					discarded_constraints.add(constraint)
					progress = True
			if progress:
				self.template.type_constraints = list(filter(
					lambda c: c not in discarded_constraints,
					self.template.type_constraints
				))
			else:
				break
		for template in self.template.templates.values():
			repr = template.type.repr()
			if isinstance(repr, TypeVariable):
				raise CCError(template.loc, f"cannot infer type for '{template.name}'")

	def _apply_types(self) -> None:
		type_locs: Dict[str, SrcLoc] = dict()
		for (loc, name, type_name) in self.types:
			type = self._get_type(loc, type_name)
			if name in type_locs:
				raise CCError(loc, f"'{name}' type already assigned at {type_locs[name]}")
			if name == "terminal":
				unify_type(loc, self.grammar.terminal_type, type)
			else:
				nt = self.template.find_template(name)
				if nt is None:
					raise CCError(loc, f"nonterminal '{name}' not found")
				unify_type(loc, nt.type, type)
			type_locs[name] = loc

	def run_lr(self) -> None:
		print("Constructing parser")
		print("LALR builder")
		table = LALRBuilder(self.grammar).build()
		print("Recovery builder")
		recovery = RecoveryBuilder(self.grammar, table)
		recovery.build()
		print("Codegen")
		codegen = Codegen(self.grammar, table)
		codegen.run()
		print("Parser done")

	def run_lh(self) -> None:
		print("Constructing parser")
		table = LHTableBuilder(self.grammar).build()
		print("Computing recovery")
		recovery = LHRecovery(table)
		recovery.compute()
		print("Codegen")
		codegen = CodegenLH(self.grammar, table)
		codegen.run()
		print("Parser done")


