import json
import random
from collections import defaultdict
from typing import List, Tuple, Dict, Optional

import sys

from jellycc.lexer.dfa import Keyword
from jellycc.utils.error import CCError


class PHF:
	def __init__(self) -> None:
		self.keywords: List[Keyword] = []
		self.rng: random.Random = random.Random(0x600D5EED)
		self.n: int = 0

	def add_keyword(self, keyword: Keyword) -> None:
		self.keywords.append(keyword)

	def build(self) -> None:
		n = self.find_n()
		if n is None:
			print(f"KEYWORDS:", file=sys.stderr)
			for keyword in self.keywords:
				for string in keyword.strings:
					print(f" {json.dumps(string)}", file=sys.stderr)
			raise CCError(None, "too many (or conflicting) keywords, cannot compute perfect hash functions")
		self.n = n

	def find_n(self) -> Optional[int]:
		for i in range(1, 256):
			if self.calc_for_n(i):
				return i
		return None

	def calc_for_n(self, n: int) -> bool:
		values: List[Tuple[Keyword, str, int]] = []
		exact_hashes: Dict[int, Tuple[Keyword, str]] = dict()

		for keyword in self.keywords:
			for string in keyword.strings:
				acc = 0
				for ch in string:
					acc = (acc * n + ord(ch)) & 0xffff
				values.append((keyword, string, acc))
				if acc not in exact_hashes:
					exact_hashes[acc] = (keyword, string)
				if exact_hashes[acc] != (keyword, string):
					return False

		resolve: Dict[int, List[Optional[Tuple[Keyword, str]]]] = defaultdict(lambda: [None, None])
		for keyword, string, value in values:

			tuple = resolve[value & 0xff]
			if tuple[0] is None:
				tuple[0] = (keyword, string)
				continue

			tuple = resolve[(value >> 8) & 0xff]
			if tuple[1] is None:
				tuple[1] = (keyword, string)
				continue

			break
		else:
			return True

		return False
