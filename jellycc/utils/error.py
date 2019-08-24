from typing import Optional

from jellycc.utils.source import SrcLoc


class CCError(RuntimeError):
	def __init__(self, loc: Optional[SrcLoc], message: str):
		if loc:
			super().__init__(f"{loc}: {message}")
		else:
			super().__init__(f"{message}")
