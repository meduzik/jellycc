from typing import Optional, Dict, Tuple, List, Set

from jellycc.parser.grammar import ParserGrammar, SymbolTerminal, SymbolNonTerminal, Production
from jellycc.parser.lr.lalr import LRTable
from jellycc.parser.lr.lr1 import LR1State, Shift, Reduce


class Node:
	def __init__(self, state: LR1State, lookahead: SymbolTerminal) -> None:
		self.state: LR1State = state
		self.lookahead: SymbolTerminal = lookahead
		self.reduce: Optional[Production] = None

		self.in_shift: Set[Node] = set()
		self.in_goto:  Set[Tuple[Node, SymbolNonTerminal]] = set()


class RecoveryBuilder:
	def __init__(self, grammar: ParserGrammar, table: LRTable) -> None:
		self.table = table
		self.grammar = grammar
		self.nodes: Dict[Tuple[LR1State, SymbolTerminal], Node] = dict()
		self.worklist: List[Node] = []

	def get_node(self, state: LR1State, lookahead: SymbolTerminal) -> Node:
		key = (state, lookahead)
		node = self.nodes.get(key, None)
		if node is None:
			node = Node(state, lookahead)
			self.nodes[key] = node
			self.worklist.append(node)
			return node
		return node

	def build(self) -> None:
		print("Constructing recovery")

		for entry in self.table.entries.values():
			for term in self.grammar.terminals:
				if term in entry.actions:
					self.get_node(entry, term)

		i = 0
		while i < len(self.worklist):
			self.process(self.worklist[i])
			i += 1

		print(f"Total states: {len(self.table.states)}");
		print(f"Total nodes: {len(self.nodes)}")

	def process(self, node: Node) -> None:
		state = node.state
		action = state.actions.get(node.lookahead, None)
		if action is not None:
			if isinstance(action, Shift):
				for term in self.grammar.terminals:
					target_state = action.state
					if term in target_state.actions:
						target_node = self.get_node(target_state, term)
						if target_node:
							target_node.in_shift.add(node)
			elif isinstance(action, Reduce):
				node.reduce = action.prod
			for nt, target_state in state.gotos.items():
				for term in self.grammar.terminals:
					if term in target_state.actions:
						target_node = self.get_node(target_state, term)
						target_node.in_goto.add((node, nt))

