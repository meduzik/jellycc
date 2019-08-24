import json
from abc import abstractmethod
from typing import Dict, List, Tuple, Iterable, Optional, Set

from jellycc.project.grammar import Terminal, CodeBlock
from jellycc.utils.error import CCError
from jellycc.utils.source import SrcLoc


class Type:
	def __init__(self) -> None:
		pass

	def get_origin(self) -> Optional[SrcLoc]:
		return None

	@abstractmethod
	def repr(self) -> 'Type':
		return self


class TypeVoid(Type):
	def __init__(self) -> None:
		super().__init__()

	def repr(self) -> 'TypeVoid':
		return self

	def __str__(self) -> str:
		return "void"


class TypeConstant(Type):
	def __init__(self, loc: SrcLoc, name: str):
		super().__init__()
		self.loc: SrcLoc = loc
		self.name: str = name

	def repr(self) -> 'TypeConstant':
		return self

	def __str__(self) -> str:
		return self.name


NextVarName = 1


class TypeVariable(Type):
	def __init__(self, name: Optional[str] = None):
		super().__init__()
		if name is None:
			global NextVarName
			name = str(NextVarName)
			NextVarName += 1
		self.name = name
		self._parent: Optional[Type] = None
		self._merge_loc: Optional[SrcLoc] = None

	def get_origin(self) -> Optional[SrcLoc]:
		assert self._parent is not None
		parent_origin = self._parent.get_origin()
		if parent_origin is None:
			return self._merge_loc
		return parent_origin

	def __str__(self) -> str:
		if self._parent:
			return str(self._parent)
		return f"%{self.name}"

	def merge(self, loc: SrcLoc, other: Type) -> None:
		other = other.repr()
		if self is other:
			return
		if isinstance(self._parent, TypeVariable):
			self._parent.merge(loc, other)
		else:
			self._merge_loc = loc
			self._parent = other.repr()

	def repr(self) -> Type:
		if self._parent:
			return self._parent.repr()
		return self


def unify_type(loc: SrcLoc, ty1: Type, ty2: Type) -> None:
	rty1 = ty1.repr()
	rty2 = ty2.repr()
	if isinstance(rty1, TypeVariable):
		rty1.merge(loc, rty2)
	elif isinstance(rty2, TypeVariable):
		rty2.merge(loc, rty1)
	elif rty1 == rty2:
		return
	else:
		origin = ty2.get_origin()
		if origin:
			origin_str = f" (from {origin})"
		else:
			origin_str = ""
		raise CCError(
			loc,
			f"cannot unify type '{rty1}' with '{rty2}'{origin_str}"
		)


class Symbol:
	def __init__(self) -> None:
		pass

	@abstractmethod
	def to_inline_str(self) -> str:
		pass


class Action:
	def __init__(self, loc: SrcLoc, args: Iterable[Tuple[Optional[str], Type]], type: Type, source: str):
		self.loc = loc
		self.args: Tuple[Tuple[Optional[str], Type], ...] = tuple(args)
		self.source: str = source
		self.type: Type = type
		self.idx: Optional[int] = None

	def to_inline_str(self) -> str:
		return "{" + str(self) + "}"

	def __str__(self) -> str:
		def arg_to_val(arg: Tuple[Optional[str], Type]) -> str:
			if arg[0]:
				return f"{arg[0]}:{arg[1]}"
			else:
				return str(arg[1])
		post_type = ""
		if not isinstance(self.type, TypeVoid):
			post_type = f"->{self.type}"
		return f"({','.join(map(arg_to_val, self.args))}){post_type}=>{{{self.source}}}"


class SymbolTerminal(Symbol):
	def __init__(self, terminal: 'Terminal'):
		super().__init__()
		self.terminal = terminal
		self.idx = -1

	def to_inline_str(self) -> str:
		return str(self)

	def __str__(self) -> str:
		return json.dumps(self.terminal.name)


class Production:
	def __init__(self, nt: 'SymbolNonTerminal', symbols: Iterable[Symbol], action: Optional[Action]):
		self.nt: SymbolNonTerminal = nt
		self.symbols: Tuple[Symbol, ...] = tuple(symbols)
		self.action: Optional[Action] = action

	def __str__(self) -> str:
		s = ' '.join(map(lambda s: s.to_inline_str(), self.symbols))
		if self.action:
			s += ' ' + self.action.to_inline_str()
		return s


class SymbolNonTerminal(Symbol):
	def __init__(self, name: str):
		super().__init__()
		self.name: str = name
		self.prods: List[Production] = []
		self.exported = False
		self.first: Set[SymbolTerminal] = set()
		self.nullable: bool = False
		self.idx: int = -1

	def to_inline_str(self) -> str:
		return self.name

	def __str__(self) -> str:
		return self.name

	def add_rule(self, symbols: Iterable[Symbol], action: Optional[Action]) -> None:
		self.prods.append(Production(self, symbols, action))


class ParserGrammar:
	def __init__(self) -> None:
		self.terminal_map: Dict[str, SymbolTerminal] = dict()
		self.terminals: List[SymbolTerminal] = []
		self.nonterminals: List[SymbolNonTerminal] = []
		self.actions: List[Action] = []
		self.exports: Dict[str, SymbolNonTerminal] = dict()
		self.keep: Set[SymbolNonTerminal] = set()
		self.terminal_type: Type = TypeVariable()
		self.eof: Optional[SymbolTerminal] = None
		self.parser_header: Optional[CodeBlock] = None
		self.parser_source: Optional[CodeBlock] = None
		self.prefix: str = "PP"
		self.core_header_path: Optional[str] = None
		self.core_source_path: Optional[str] = None
		self.vm_header_path: Optional[str] = None
		self.vm_source_path: Optional[str] = None

	def register_action(self, action: Action) -> None:
		action.idx = len(self.actions)
		self.actions.append(action)

	def add_terminal(self, terminal: SymbolTerminal) -> SymbolTerminal:
		self.terminal_map[terminal.terminal.name] = terminal
		self.terminals.append(terminal)
		return terminal

	def add_nonterminal(self, nt: SymbolNonTerminal) -> None:
		self.nonterminals.append(nt)

	def find_terminal(self, name: str) -> Optional[SymbolTerminal]:
		return self.terminal_map.get(name, None)


