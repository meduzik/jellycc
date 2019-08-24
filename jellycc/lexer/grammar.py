from typing import Optional

from jellycc.project.grammar import SharedGrammar


class LexerGrammar:
	def __init__(self, shared: SharedGrammar) -> None:
		self.shared: SharedGrammar = shared
		self.prefix: str = "LL"
		self.namespace: str = "ll"
		self.header_path: Optional[str] = None
		self.source_path: Optional[str] = None

