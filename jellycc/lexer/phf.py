import json
import random
from collections import defaultdict
from typing import List, Tuple, Dict, Optional, Set

import sys

from jellycc.lexer.dfa import Keyword
from jellycc.utils.error import CCError

# This was inteded as a mean to reduce lexer table size
# Turns out it makes lexing much slower


class KeywordEntry:
	def __init__(self, kwd: Keyword, s: str, hash: int):
		self.kwd: Keyword = kwd
		self.s: str = s
		self.hash: int = hash
		self.h1: int = hash & 0xff
		self.h2: int = (hash >> 8) & 0xff
		self.state: int = -1


class CuckooHash:
	def __init__(self):
		self.ht: List[Optional[KeywordEntry]] = [None] * 256

	def insert(self, kwd: KeywordEntry) -> bool:
		if self.ht[kwd.h1] is None:
			self.ht[kwd.h1] = kwd
			return True

		if self.ht[kwd.h2] is None:
			self.ht[kwd.h2] = kwd
			return True

		if self.probe(kwd, kwd.h1, set()):
			return True

		if self.probe(kwd, kwd.h2, set()):
			return True

		return False

	def probe(self, kwd: KeywordEntry, bucket: int, loop: Set[int]) -> bool:
		if bucket in loop:
			return False
		push = self.ht[bucket]
		if push is not None:
			loop.add(bucket)
			if bucket == push.h1:
				if not self.probe(push, push.h2, loop):
					return False
			else:
				if not self.probe(push, push.h1, loop):
					return False
		self.ht[bucket] = kwd
		return True


class PHF:
	def __init__(self) -> None:
		self.keywords: List[Keyword] = []
		self.rng: random.Random = random.Random(0x600D5EED)
		self.n: int = 0
		self.cuckoo: CuckooHash = CuckooHash()

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
		values: List[KeywordEntry] = []
		exact_hashes: Dict[int, KeywordEntry] = dict()

		for keyword in self.keywords:
			for string in keyword.strings:
				acc = 0
				for ch in string:
					acc = ((acc + ord(ch)) * n) & 0xffff
				entry = KeywordEntry(keyword, string, acc)
				values.append(entry)
				if acc not in exact_hashes:
					exact_hashes[acc] = entry
				else:
					return False

		resolve = CuckooHash()
		for entry in values:
			if not resolve.insert(entry):
				break
		else:
			self.cuckoo = resolve
			return True

		return False
