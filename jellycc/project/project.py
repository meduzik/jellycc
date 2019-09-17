from typing import Optional, List, Tuple, Set

from jellycc.lexer.regexp import Re
from jellycc.lexer.run import LexerGenerator
from jellycc.parser.run import ParserGenerator
from jellycc.parser.template import TemplateExpr, TemplateSymbol, TemplateAction
from jellycc.project.grammar import CodeBlock, SharedGrammar
from jellycc.utils.error import CCError
from jellycc.utils.source import SrcLoc


class Project:
	def __init__(self) -> None:
		self.grammar = SharedGrammar()
		self.parser_generator: ParserGenerator = ParserGenerator(self.grammar)
		self.lexer_generator: LexerGenerator = LexerGenerator(self.grammar)

	def add_lexer_fragment(self, loc: SrcLoc, name: str, re: Re) -> None:
		self.lexer_generator.nfa_ctx.add_fragment(loc, name, re)

	def add_lexer_rule(self, loc: SrcLoc, name: str, re: Re) -> None:
		self.lexer_generator.lexer_rules.append((loc, name, re))

	def add_terminal(self, loc: SrcLoc, name: str, lang_name: str, tags: List[Tuple[str, Optional[int]]]) -> None:
		self.grammar.add_terminal(loc, name, lang_name, tags)

	def add_type(self, loc: SrcLoc, name: str, type: str) -> None:
		self.parser_generator.types.append((loc, name, type))

	def add_vm_arg(self, loc: SrcLoc, name: str, type: str) -> None:
		self.parser_generator.grammar.vm_args.append((loc, name, type))

	def add_expose(self, loc: SrcLoc, name: str) -> None:
		self.parser_generator.exposed_nt.append((loc, name))

	def register_vm_action(self, loc: SrcLoc, name: str, action: Tuple[SrcLoc, str]):
		old_val = self.parser_generator.grammar.vm_actions.get(name, None)
		if old_val is not None:
			raise CCError(loc, f"{name} vm action already defined at {old_val[0]}")
		self.parser_generator.grammar.vm_actions[name] = (loc, name, action)

	def add_nt_rule(
		self,
		loc: SrcLoc,
		name: str,
		param_names: List[str],
		cond: Optional[TemplateExpr],
		symbols: List[TemplateSymbol],
		action: Optional[TemplateAction]
	) -> None:
		self.parser_generator.parser_rules.append((loc, name, param_names, cond, symbols, action))

	def set_parser_header(self, loc: SrcLoc, contents: str) -> None:
		if self.parser_generator.grammar.parser_header:
			raise CCError(loc, f"parser.header block already defined at {self.parser_generator.grammar.parser_header.loc}")
		self.parser_generator.grammar.parser_header = CodeBlock(loc, contents)

	def set_parser_source(self, loc: SrcLoc, contents: str) -> None:
		if self.parser_generator.grammar.parser_source:
			raise CCError(loc, f"parser.source block already defined at {self.parser_generator.grammar.parser_source.loc}")
		self.parser_generator.grammar.parser_source = CodeBlock(loc, contents)

	def process(self) -> None:
		self._construct()
		self.lexer_generator.construct()
		self.parser_generator.construct()

	def _construct(self) -> None:
		self._assign_terminal_values()

	def _assign_terminal_values(self) -> None:
		idx: int = 0
		taken_values: Set[int] = set()

		for terminal in self.grammar.terminals_list:
			if terminal.value is not None:
				taken_values.add(terminal.value)

		for terminal in self.grammar.terminals_list:
			if terminal.value is None:
				while idx in taken_values:
					idx += 1
				terminal.value = idx
				idx += 1

