import re
from abc import abstractmethod
from enum import Enum

from typing import Dict, Any, cast, NamedTuple, List, Optional, Tuple, Iterable

from jellycc.parser.grammar import SymbolNonTerminal, Type, Symbol, Action, TypeVariable, ParserGrammar, unify_type
from jellycc.utils.error import CCError
from jellycc.utils.source import SrcLoc


InstanceVars = Dict[str, Any]


CaptureRe = re.compile("\\$([a-zA-Z_0-9]+)")


class TemplateExpr:
	def __init__(self, loc: SrcLoc):
		self.loc = loc

	@abstractmethod
	def eval(self, vars: InstanceVars) -> Any:
		pass


class TemplateExprConst(TemplateExpr):
	def __init__(self, loc: SrcLoc, val: Any):
		super().__init__(loc)
		self.val: Any = val

	def eval(self, vars: InstanceVars) -> Any:
		return self.val


class TemplateExprVar(TemplateExpr):
	def __init__(self, loc: SrcLoc, name: str):
		super().__init__(loc)
		self.name = name

	def eval(self, vars: InstanceVars) -> Any:
		return vars[self.name]


class BinOp(Enum):
	LT = "<", lambda vars, x, y: x.eval(vars) < y.eval(vars)
	GT = ">", lambda vars, x, y: x.eval(vars) > y.eval(vars)
	LE = "<=", lambda vars, x, y: x.eval(vars) <= y.eval(vars)
	GE = ">=", lambda vars, x, y: x.eval(vars) >= y.eval(vars)
	EQ = "==", lambda vars, x, y: x.eval(vars) == y.eval(vars)
	NE = "!=", lambda vars, x, y: x.eval(vars) != y.eval(vars)
	AND = "and", lambda vars, x, y: x.eval(vars) and y.eval(vars)
	OR = "or", lambda vars, x, y: x.eval(vars) or y.eval(vars)
	Add = "+", lambda vars, x, y: x.eval(vars) + y.eval(vars)
	Sub = "-", lambda vars, x, y: x.eval(vars) - y.eval(vars)


class TemplateExprBinOp(TemplateExpr):
	def __init__(self, loc: SrcLoc, op: BinOp, lhs: Any, rhs: Any):
		super().__init__(loc)
		self.op: BinOp = op
		self.lhs: Any = lhs
		self.rhs: Any = rhs

	def eval(self, vars: InstanceVars) -> Any:
		return cast(Any, self.op.value[1](vars, self.lhs, self.rhs))


TypeParam = Tuple[Optional[str], Type]


TemplateSymbol = NamedTuple('TemplateSymbol', (
	('loc', SrcLoc),
	('name', str),
	('params', Optional[List[TemplateExpr]]),
	('capture', Optional[str])
))

TemplateAction = NamedTuple('TemplateAction', (
	('loc', SrcLoc),
	('text', str),
))


class TypeConstraint:
	def __init__(self, loc: SrcLoc, nt: SymbolNonTerminal, type: Type, params: Tuple[TypeParam, ...]):
		self.loc: SrcLoc = loc
		self.nt: SymbolNonTerminal = nt
		self.type: Type = type
		self.params: Tuple[TypeParam, ...] = params


class TemplateNonTerminalRule:
	def __init__(
		self,
		loc: SrcLoc,
		parent: 'TemplateNonTerminal',
		param_names: Iterable[str],
		condition: Optional[TemplateExpr],
		symbols: Iterable[TemplateSymbol],
		action: Optional[TemplateAction]
	):
		self.loc: SrcLoc = loc
		self.parent: TemplateNonTerminal = parent
		self.condition: Optional[TemplateExpr] = condition
		self.param_names: Tuple[str, ...] = tuple(param_names)
		self.symbols: List[TemplateSymbol] = list(symbols)
		self.action: Optional[TemplateAction] = action

	def _instantiate_symbol(
		self,
		ctx: 'TemplateGrammar',
		symbol: TemplateSymbol,
		vars: InstanceVars,
		type_stack: List[TypeParam],
		symbols: List[Symbol]
	) -> None:
		template = ctx.find_template(symbol.name)
		if template:
			vals = []
			if symbol.params is not None:
				for expr in symbol.params:
					vals.append(expr.eval(vars))
			symbols.append(template.instantiate(symbol.loc, tuple(vals)))
			type_stack.append((symbol.capture, template.type))
		else:
			terminal = ctx.grammar.find_terminal(symbol.name)
			if not terminal:
				raise CCError(symbol.loc, f"unresolved name '{symbol.name}'")
			if symbol.params is not None:
				raise CCError(symbol.loc, f"terminal '{symbol.name}' doesn't expect template arguments")
			symbols.append(terminal)
			assert ctx.grammar.terminal_type is not None
			type_stack.append((symbol.capture, ctx.grammar.terminal_type))

	def _instantiate_action(
		self,
		ctx: 'TemplateGrammar',
		action: TemplateAction,
		type_stack: List[TypeParam]
	) -> Action:
		source = action.text.strip()
		prod_action: Action = Action(action.loc, type_stack, TypeVariable(None), action.text)
		param_names = set()

		for type in type_stack:
			if type[0] is not None:
				param_names.add(type[0])
				if source == "$" + type[0]:
					unify_type(prod_action.loc, prod_action.type, type[1])

		for param_match in CaptureRe.finditer(source):
			param_name = param_match.group(1)
			if param_name not in param_names:
				raise CCError(prod_action.loc, f"unresolved reference '{param_name}'")

		type_stack.clear()
		type_stack.append((None, prod_action.type))
		return prod_action

	def instantiate(
		self,
		ctx: 'TemplateGrammar',
		nt: SymbolNonTerminal,
		values: Tuple[int, ...]
	) -> Optional[Tuple[Tuple[Symbol, ...], Optional[Action]]]:
		symbols: List[Symbol] = []
		action = None
		vars = dict()
		for name, value in zip(self.param_names, values):
			vars[name] = value
		if self.condition and not self.condition.eval(vars):
			return None

		type_stack: List[TypeParam] = []
		for symbol in self.symbols:
			self._instantiate_symbol(ctx, symbol, vars, type_stack, symbols)

		if self.action:
			action = self._instantiate_action(ctx, self.action, type_stack)

		ctx.type_constraints.append(TypeConstraint(
			self.loc,
			nt,
			self.parent.type,
			tuple(type_stack)
		))

		return tuple(symbols), action


class TemplateNonTerminal:
	def __init__(self, ctx: 'TemplateGrammar', loc: SrcLoc, name: str, param_count: int):
		self.ctx: 'TemplateGrammar' = ctx
		self.name: str = name
		self.loc: SrcLoc = loc
		self.param_count: int = param_count
		self.rules: List[TemplateNonTerminalRule] = []
		self.type: Type = TypeVariable(self.name)
		self.instances: Dict[Tuple[int, ...], SymbolNonTerminal] = dict()

	def add_rule(self, rule: TemplateNonTerminalRule) -> None:
		self.rules.append(rule)

	def instantiate(self, loc: SrcLoc, values: Tuple[int, ...]) -> SymbolNonTerminal:
		if values in self.instances:
			return self.instances[values]
		if len(values) != self.param_count:
			raise CCError(
				loc,
				f"mismatch number of template arguments " +
				f"for {self.name}: " +
				f"got {self.param_count}, expected {len(values)}"
			)
		return self._create_instance(values)

	def _create_instance(self, values: Tuple[int, ...]) -> SymbolNonTerminal:
		name = self.name
		if len(values) > 0:
			name = name + "[" + ','.join(map(str, values)) + "]"
		nt = SymbolNonTerminal(name)
		self.instances[values] = nt
		self.ctx.grammar.add_nonterminal(nt)
		for rule_template in self.rules:
			rule_instance = rule_template.instantiate(self.ctx, nt, values)
			if rule_instance is not None:
				nt.add_rule(*rule_instance)
		return nt


class TemplateGrammar:
	def __init__(self, grammar: ParserGrammar):
		self.templates: Dict[str, TemplateNonTerminal] = dict()
		self.grammar = grammar
		self.type_constraints: List[TypeConstraint] = []

	def add_template(self, nt: TemplateNonTerminal) -> None:
		self.templates[nt.name] = nt

	def find_template(self, name: str) -> Optional[TemplateNonTerminal]:
		return self.templates.get(name, None)


