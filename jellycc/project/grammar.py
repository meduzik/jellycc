from typing import Dict, Set, Optional, List, Tuple

from jellycc.utils.error import CCError
from jellycc.utils.source import SrcLoc


class Terminal:
	def __init__(self, loc: SrcLoc, name: str, lang_name: str) -> None:
		self.loc: SrcLoc = loc
		self.name: str = name
		self.lang_name: str = lang_name
		self.value: Optional[int] = None
		self.skip: bool = False


class CodeBlock:
	def __init__(self, loc: SrcLoc, contents: str) -> None:
		self.loc: SrcLoc = loc
		self.contents: str = contents


class SharedGrammar:
	def __init__(self) -> None:
		self.terminals_list: List[Terminal] = []
		self.terminals: Dict[str, Terminal] = dict()
		self.term_error: Optional[Terminal] = None
		self.term_eof: Optional[Terminal] = None
		self.base_dir: str = ""

	def add_terminal(self, loc: SrcLoc, name: str, lang_name: str, tags: List[Tuple[str, Optional[int]]]) -> None:
		if name in self.terminals:
			raise CCError(loc, f"terminal '{name}' already defined at {self.terminals[name].loc}")
		terminal = Terminal(loc, name, lang_name)
		self.terminals[name] = terminal
		self.terminals_list.append(terminal)
		for tag, value in tags:
			if tag == "skip":
				terminal.skip = True
			elif tag == "error":
				if self.term_error:
					raise CCError(loc, f"error terminal {self.term_error.name} already defined at {self.term_error.loc}")
				self.term_error = terminal
			elif tag == "eof":
				if self.term_eof:
					raise CCError(loc,  f"eof terminal {self.term_eof.name} already defined at {self.term_eof.loc}")
				self.term_eof = terminal
			else:
				raise CCError(loc, f"invalid tag {tag}")

