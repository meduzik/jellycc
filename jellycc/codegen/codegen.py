import json
import re
import os
from abc import abstractmethod
from typing import ContextManager, IO, List, Callable

from jellycc.utils.source import SrcLoc


class TemplateCommand:
	def __init__(self) -> None:
		pass

	@abstractmethod
	def run(self, printer: 'CodePrinter', subst: Callable[['CodePrinter', str], None]) -> None:
		pass


class TemplateCommandPlain(TemplateCommand):
	def __init__(self, text: str) -> None:
		super().__init__()
		self.text: str = text

	def run(self, printer: 'CodePrinter', subst: Callable[['CodePrinter', str], None]) -> None:
		printer.write(self.text)


class TemplateCommandSubst(TemplateCommand):
	def __init__(self, indent: List[str], subst: str) -> None:
		super().__init__()
		self.indent: List[str] = indent
		self.subst: str = subst

	def run(self, printer: 'CodePrinter', subst: Callable[['CodePrinter', str], None]) -> None:
		old_indent = printer.set_indent(self.indent)
		subst(printer, self.subst)
		printer.set_indent(old_indent)


class TemplateCommandInclude(TemplateCommand):
	def __init__(self, template: 'Template') -> None:
		super().__init__()
		self.template: Template = template

	def run(self, printer: 'CodePrinter', subst: Callable[['CodePrinter', str], None]) -> None:
		self.template.print(printer, subst)


class Template:
	def __init__(self, path: str) -> None:
		self.path: str = path
		self.cmds: List[TemplateCommand] = []

	def run(self, base_dir: str, file: str, fp: IO[str], subst: Callable[['CodePrinter', str], None]) -> None:
		printer = CodePrinter(base_dir, file, fp)
		self.print(printer, subst)

	def print(self, printer: 'CodePrinter', subst: Callable[['CodePrinter', str], None]) -> None:
		for cmd in self.cmds:
			cmd.run(printer, subst)


Spaces = frozenset(" \t")
ReSubst = re.compile("\\$\\{([:.a-zA-Z0-9_]*)}")


def parse_template(path: str) -> Template:
	template = Template(path)
	with open(path, 'r') as fp:
		for line in fp.readlines():
			i = 0
			n = len(line)
			indent = []
			while i < n and line[i] in Spaces:
				indent.append(line[i])
				i += 1
			end = 0
			for match in ReSubst.finditer(line):
				pos = match.start()
				if pos != end:
					template.cmds.append(TemplateCommandPlain(line[end:pos]))
				subst_name = match.group(1)
				if subst_name.find("include:") == 0:
					rel_path = subst_name[len("include:"):]
					template.cmds.append(TemplateCommandInclude(parse_template(
						os.path.join(os.path.dirname(path), rel_path)
					)))
				else:
					template.cmds.append(TemplateCommandSubst(indent, subst_name))
				end = match.end()
			if end != n:
				template.cmds.append(TemplateCommandPlain(line[end:]))
	return template


class CodePrinter:
	def __init__(self, base_path: str, file: str, fp: IO[str]) -> None:
		self.file: str = file
		self.line: int = 0
		self.col: int = 0

		self._fp: IO[str] = fp

		self._indent: List[str] = []
		self._line_empty: bool = True

		self.base_path: str = base_path

	def _write_inline(self, text: str) -> None:
		if len(text) == 0:
			return
		if self._line_empty:
			self._write_indent()
		self._line_empty = False
		self._fp.write(text)
		self.col += len(text)

	def _write_indent(self) -> None:
		for s in self._indent:
			self._fp.write(s)
			self.col += len(s)

	def _endl(self) -> None:
		self._fp.write('\n')
		self._line_empty = True
		self.line += 1
		self.col = 0

	def write(self, text: str) -> None:
		begin = 0
		pos = 0
		n = len(text)
		while True:
			if pos >= n:
				self._write_inline(text[begin:pos])
				break
			if text[pos] == '\r' or text[pos] == '\n':
				r_pos = pos
				pos += 1
				if pos < n and text[pos - 1] == '\n' and text[pos] == '\n':
					pos += 1
				self._write_inline(text[begin:r_pos])
				self._endl()
				begin = pos
			else:
				pos += 1

	def writeln(self, text: str) -> None:
		self.write(text)
		self.write("\n")

	def push_indent(self, s: str) -> None:
		self._indent.append(s)

	def pop_indent(self) -> None:
		self._indent.pop()

	def set_indent(self, new_indent: List[str]) -> List[str]:
		old_indent = self._indent
		self._indent = new_indent
		return old_indent

	def include(self, loc: SrcLoc, text: str) -> None:
		if not self._line_empty:
			self._endl()
		old_indent = self.set_indent([])
		# self.writeln(f"#line {loc.line + 1} {json.dumps(os.path.relpath(loc.file, self.base_path))}")
		self.write(' ' * loc.col)
		self.writeln(text)
		# self.writeln(f"#line {self.line + 2} {json.dumps(os.path.relpath(self.file, self.base_path))}")
		self.set_indent(old_indent)

	def indented(self, s: str = '\t') -> ContextManager[None]:
		class Indenter(ContextManager[None]):
			def __init__(self, printer: CodePrinter):
				self.printer = printer

			def __enter__(self):
				self.printer.push_indent(s)
				return None

			def __exit__(self, type, value, traceback):
				self.printer.pop_indent()

		return Indenter(self)


