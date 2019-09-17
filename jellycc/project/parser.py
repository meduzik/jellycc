import itertools

from typing import Optional, Set, List, Tuple, Dict

from jellycc.lexer.regexp import Re, ReEmpty, ReChar, ReConcat, ReChoice, ReStar, ReRef
from jellycc.parser.template import BinOp, TemplateExpr, TemplateExprVar, TemplateExprBinOp, TemplateExprConst, \
	TemplateSymbol, TemplateAction
from jellycc.project.project import Project
from jellycc.utils.parser import ParserBase, IdChars, IdStartChars, Quotes, Digits, Linebreaks, Whitespaces
from jellycc.utils.source import SourceInput, SrcLoc


Printables = frozenset(map(chr, range(32, 127)))
SectionChars = frozenset(itertools.chain(IdChars, "."))
GroupChars = Printables.difference("^-\\[]")
Graphicals = frozenset(map(chr, range(33, 127)))
RePlainChars = Graphicals.difference(";$^~{}[]+*.?<>()\\\"|")
NameStartChars = frozenset(itertools.chain(IdStartChars, Quotes))


PrecModifier = 30
PrecConcat = 20
PrecChoice = 10
PrecMin = 0


PrecAdd = 40
PrecComparison = 30
PrecAnd = 20
PrecOr = 10


Operators = (
	(PrecOr, "or", BinOp.OR, +1),
	(PrecAnd, "and", BinOp.AND, +1),
	(PrecComparison, "==", BinOp.EQ, +1),
	(PrecComparison, "!=", BinOp.NE, +1),
	(PrecComparison, "<=", BinOp.LE, +1),
	(PrecComparison, ">=", BinOp.GE, +1),
	(PrecComparison, "<", BinOp.LT, +1),
	(PrecComparison, ">", BinOp.GT, +1),
	(PrecAdd, "+", BinOp.Add, +1),
	(PrecAdd, "-", BinOp.Sub, +1),
)


class ProjectParser(ParserBase):
	def __init__(self, project: Project, input: SourceInput) -> None:
		super().__init__(input)
		self.project: Project = project

	def run(self) -> Project:
		self.parse_sections()
		return self.project

	def parse_sections(self) -> None:
		while True:
			self.skip_ws()
			ch = self.peek()
			if ch is None:
				break
			if ch == '[':
				self.advance()
				self.skip_inline_ws()
				loc, section_name = self.loc(), self.collect(SectionChars)
				self.skip_inline_ws()
				self.expect(']')
				self.skip_empty_line()
				if section_name == "lexer.fragments":
					self.section_lexer_fragments()
				elif section_name == "lexer.grammar":
					self.section_lexer_grammar()
				elif section_name == "parser.types":
					self.section_parser_types()
				elif section_name == "parser.vm_args":
					self.section_parser_vm_args()
				elif section_name == "parser.vm_actions":
					self.section_parser_vm_actions()
				elif section_name == "parser.grammar":
					self.section_parser_grammar()
				elif section_name == "parser.expose":
					self.section_parser_expose()
				elif section_name == "parser.header":
					self.project.set_parser_header(self.loc(), self.section_code())
				elif section_name == "parser.source":
					self.project.set_parser_source(self.loc(), self.section_code())
				elif section_name == "terminals":
					self.section_terminals()
				else:
					self.report(f"unknown section {section_name}")
			else:
				self.report("expected section")

	def section_code(self) -> str:
		s = []
		line_is_clear = True
		while True:
			ch = self.peek()
			if ch is None:
				break
			elif ch == '[' and line_is_clear:
				break
			else:
				if ch in Linebreaks:
					line_is_clear = True
				elif ch not in Whitespaces:
					line_is_clear = False
				s.append(ch)
				self.advance()
		return ''.join(s)

	def section_parser_types(self) -> None:
		while True:
			self.skip_ws()
			loc, name = self.loc(), self.try_name()
			if name is None:
				break
			self.colon()
			type = self.parse_name()
			self.semi()
			self.project.add_type(loc, name, type)

	def section_parser_vm_args(self) -> None:
		while True:
			self.skip_ws()
			loc, name = self.loc(), self.try_name()
			if name is None:
				break
			self.colon()
			type = self.parse_name()
			self.semi()
			self.project.add_vm_arg(loc, name, type)

	def section_parser_expose(self) -> None:
		while True:
			self.skip_ws()
			loc, name = self.loc(), self.try_name()
			if name is None:
				break
			self.semi()
			self.project.add_expose(loc, name)

	def section_parser_grammar(self) -> None:
		while True:
			self.skip_ws()
			loc, name = self.loc(), self.try_name()
			if name is None:
				break
			param_names, cond = self.parse_template_params()
			self.colon()
			symbols = self.parse_nt_symbols()
			action = self.try_nt_action()
			self.semi()
			self.project.add_nt_rule(loc, name, param_names, cond, symbols, action)

	def section_parser_vm_actions(self) -> None:
		while True:
			self.skip_ws()
			loc, name = self.loc(), self.try_name()
			if name is None:
				break
			self.colon()
			action = self.parse_action()
			self.semi()
			self.project.register_vm_action(loc, name, action)

	def parse_action(self) -> Tuple[SrcLoc, str]:
		self.skip_ws()
		if self.peek() != '{':
			self.report("expected action", self.loc())
		counter = 0
		while self.peek() == '{':
			counter += 1
			self.advance()
		self.skip_ws()
		loc = self.loc()
		text = []
		while True:
			ch = self.peek()
			if ch == '}':
				n = 0
				flag = False
				while self.peek() == '}':
					n += 1
					self.advance()
					if n == counter:
						flag = True
						break
				else:
					text.append('}' * n)
				if flag:
					break
			elif ch is None:
				self.report("action is not terminated")
			else:
				self.advance()
				text.append(ch)
		return (loc, ''.join(text).strip())

	def try_nt_action(self) -> Optional[TemplateAction]:
		self.skip_ws()
		if self.peek() != '{':
			return None
		counter = 0
		while self.peek() == '{':
			counter += 1
			self.advance()
		self.skip_ws()
		loc = self.loc()
		text = []
		while True:
			ch = self.peek()
			if ch == '}':
				n = 0
				flag = False
				while self.peek() == '}':
					n += 1
					self.advance()
					if n == counter:
						flag = True
						break
				else:
					text.append('}' * n)
				if flag:
					break
			elif ch is None:
				self.report("action is not terminated")
			else:
				self.advance()
				text.append(ch)
		return TemplateAction(loc, ''.join(text).strip())

	def parse_nt_symbols(self) -> List[TemplateSymbol]:
		acc: List[TemplateSymbol] = []
		forced_captures: Dict[str, SrcLoc] = dict()
		while True:
			self.skip_ws()
			loc = self.loc()
			name = self.try_name()
			capture = None
			if name is None:
				break
			self.skip_ws()
			if self.peek() == '=':
				self.advance()
				capture, name = name, self.try_name()
				if name is None:
					self.report("expected symbol name")
				self.skip_ws()
				if capture in forced_captures:
					self.report(f"capture {capture} already used at {forced_captures[capture]}")
				forced_captures[capture] = loc
			params = self.parse_template_list()
			acc.append(TemplateSymbol(loc, name, params, capture))
		return acc

	def parse_template_list(self) -> Optional[List[TemplateExpr]]:
		if self.peek() != '[':
			return None
		self.advance()
		params = []
		while True:
			expr = self.parse_expr(PrecMin)
			params.append(expr)
			self.skip_ws()
			if self.peek() == ',':
				self.advance()
			else:
				break
		self.expect(']')
		return params

	def parse_template_params(self) -> Tuple[List[str], Optional[TemplateExpr]]:
		loc = self.loc()
		base_params = self.parse_template_list()
		if base_params is None:
			return ([], None)
		self.skip_ws()
		cond = None
		if self.lookahead("where"):
			cond = self.parse_expr(PrecMin)
			self.skip_ws()
		# give params names (use @1 for placeholders)
		param_names: List[str] = []
		used_names: Set[str] = set()
		conds: List[TemplateExpr] = []
		next_id = 1
		for param in base_params:
			if isinstance(param, TemplateExprVar) and param not in used_names:
				param_names.append(param.name)
				used_names.add(param.name)
			else:
				placeholder_name = f'@{next_id}'
				param_names.append(placeholder_name)
				conds.append(TemplateExprBinOp(
					param.loc,
					BinOp.EQ,
					TemplateExprVar(param.loc, placeholder_name),
					param
				))
				next_id += 1
		if cond is not None:
			conds.append(cond)
		filter = None
		for cond in conds:
			if not filter:
				filter = cond
			else:
				filter = TemplateExprBinOp(loc, BinOp.AND, filter, cond)
		return param_names, filter

	def section_terminals(self) -> None:
		while True:
			self.skip_ws()
			loc, name = self.loc(), self.try_name()
			if name is None:
				break
			self.colon()
			lang_name = self.parse_name()
			self.skip_ws()
			if self.peek() == '{':
				self.advance()
				self.skip_ws()
				tags = self.parse_tags()
				self.expect('}')
			else:
				tags = []
			self.semi()
			self.project.add_terminal(loc, name, lang_name, tags)

	def parse_tags(self) -> List[Tuple[str, Optional[int]]]:
		vals: List[Tuple[str, Optional[int]]] = []

		while True:
			self.skip_ws()
			name = self.parse_id()
			self.skip_ws()

			if self.peek() == '=':
				self.advance()
				val: Optional[int] = self.parse_int()
			else:
				val = None

			vals.append((name, val))

			if self.peek() == ',':
				self.advance()
			else:
				break

		return vals

	def section_lexer_fragments(self) -> None:
		while True:
			self.skip_ws()
			ch = self.peek()
			if ch in IdStartChars:
				loc, name = self.loc(), self.parse_id()
				self.colon()
				self.skip_ws()
				re = self.parse_re()
				self.semi()
				self.project.add_lexer_fragment(loc, name, re)
			else:
				break

	def section_lexer_grammar(self) -> None:
		while True:
			self.skip_ws()
			loc, name = self.loc(), self.try_name()
			if name is None:
				break
			self.skip_ws()
			if self.peek() == ':':
				self.colon()
				self.skip_ws()
				re = self.parse_re()
			else:
				re = self.make_str_re(name)
			self.semi()
			self.project.add_lexer_rule(loc, name, re)

	def parse_name(self) -> str:
		name = self.try_name()
		if name is None:
			self.report("expected identifier or string")
		return name

	def try_name(self) -> Optional[str]:
		self.skip_ws()
		ch = self.peek()
		if ch in IdStartChars:
			return self.parse_id()
		elif ch in Quotes:
			return self.parse_string()
		else:
			return None

	def parse_re(self) -> Re:
		re = self.try_re_at(PrecMin)
		if re is None:
			self.report("expected regular expression")
		return re

	def try_re_at(self, prec: int) -> Optional[Re]:
		lhs = self.try_re_prim()

		if lhs is None:
			return None

		while True:
			self.skip_ws()
			ch = self.peek()
			if prec <= PrecModifier and ch == '?':
				self.advance()
				lhs = ReChoice(lhs, ReEmpty())
			elif prec <= PrecModifier and ch == '+':
				self.advance()
				lhs = ReConcat(lhs, ReStar(lhs))
			elif prec <= PrecModifier and ch == '*':
				self.advance()
				lhs = ReStar(lhs)
			elif prec <= PrecModifier and ch == '{':
				self.advance()
				self.skip_ws()
				min_count = self.parse_int()
				self.skip_ws()
				if self.peek() == ',':
					self.advance()
					self.skip_ws()
					max_count = self.parse_int()
					self.skip_ws()
				else:
					max_count = min_count
				self.expect('}')
				if max_count < min_count:
					self.report("max count must be greater than or equal to min count")
				tail: Re = ReEmpty()
				while max_count > min_count:
					tail = ReChoice(ReConcat(lhs, tail), ReEmpty())
					max_count -= 1
				while min_count > 0:
					tail = ReConcat(lhs, tail)
					min_count -= 1
				lhs = tail
			elif prec <= PrecChoice and ch == '|':
				self.advance()
				rhs = self.try_re_at(PrecChoice + 1)
				if rhs is None:
					rhs = ReEmpty()
				lhs = ReChoice(lhs, rhs)
			elif prec <= PrecConcat:
				rhs = self.try_re_at(PrecConcat + 1)
				if rhs is not None:
					lhs = ReConcat(lhs, rhs)
				else:
					break
			else:
				break

		return lhs

	def make_str_re(self, s: str) -> Re:
		bytes = s.encode('utf-8')
		if len(bytes) == 0:
			return ReEmpty()
		else:
			re: Re = ReChar((bytes[0],))
			for byte in bytes[1:]:
				re = ReConcat(re, ReChar((byte,)))
			return re

	def try_re_prim(self) -> Optional[Re]:
		self.skip_ws()
		ch = self.peek()
		if ch in Quotes:
			return self.make_str_re(self.parse_string())
		elif ch == '\\':
			self.advance()
			ch = self.parse_esc()
			return self.make_str_re(ch)
		elif ch == '.':
			self.advance()
			return ReChar(range(256))
		elif ch == '(':
			self.advance()
			re = self.try_re_at(PrecMin)
			if re is None:
				re = ReEmpty()
			self.skip_ws()
			self.expect(')')
			return re
		elif ch == '<':
			self.advance()
			self.skip_ws()
			loc, name = self.loc(), self.parse_id()
			self.skip_ws()
			self.expect('>')
			return ReRef(loc, name)
		elif ch == '[':
			self.advance()
			re = self.parse_group()
			self.expect(']')
			return re
		elif ch in RePlainChars:
			self.advance()
			return self.make_str_re(ch)
		else:
			return None

	def parse_group(self) -> Re:
		invert = False

		if self.peek() == '^':
			self.advance()
			invert = True

		group: Set[int] = set()

		while True:
			char = self.parse_group_char()
			if char is None:
				break
			if self.peek() == '-':
				self.advance()
				char2 = self.parse_group_char()
				if char2 is None:
					self.report("expected second range character")
				if char2 < char:
					self.report("invalid range")
				group.update(range(char, char2 + 1))
			else:
				group.add(char)

		if invert:
			group.symmetric_difference_update(range(256))

		return ReChar(group)

	def parse_group_char(self) -> Optional[int]:
		ch = self.peek()
		if ch == '\\':
			self.advance()
			val = ord(self.parse_esc())
			if val > 255:
				self.report("escape sequence does not encode single byte")
			return val
		elif ch == ']':
			return None
		elif ch in GroupChars:
			self.advance()
			return ord(ch)
		else:
			self.report("invalid group character")

	def semi(self) -> None:
		self.skip_ws()
		self.expect(';')

	def colon(self) -> None:
		self.skip_ws()
		self.expect(':')

	def parse_expr(self, prec: int) -> TemplateExpr:
		expr = self.try_parse_expr(prec)
		if not expr:
			self.report("expected expression")
		return expr

	def try_parse_expr(self, prec: int) -> Optional[TemplateExpr]:
		lhs = self.try_parse_prim()
		if not lhs:
			return None
		while True:
			self.skip_ws()
			loc = self.loc()
			for op_prec, tok, op, acc in Operators:
				if prec <= op_prec and self.lookahead(tok):
					rhs = self.parse_expr(prec + 1)
					lhs = TemplateExprBinOp(loc, op, lhs, rhs)
					break
			else:
				break
		return lhs

	def lookahead(self, token: str) -> bool:
		savepoint = self.input.save()
		pos = 0
		while True:
			if len(token) <= pos:
				return True
			ch = self.peek()
			if ch == token[pos]:
				self.advance()
				pos += 1
			else:
				break
		self.input.restore(savepoint)
		return False

	def try_parse_prim(self) -> Optional[TemplateExpr]:
		self.skip_ws()
		loc = self.loc()
		ch = self.peek()
		if ch in IdStartChars:
			id = self.parse_id()
			return TemplateExprVar(loc, id)
		elif ch in Digits:
			num = self.parse_int()
			return TemplateExprConst(loc, num)
		elif ch == '(':
			self.advance()
			expr = self.parse_expr(PrecMin)
			self.skip_ws()
			self.expect(')')
			return expr
		else:
			return None


def parse_project(input: SourceInput) -> Project:
	return ProjectParser(Project(), input).run()
