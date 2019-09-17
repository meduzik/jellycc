from typing import List, Tuple

from jellycc.lexer.dfa import DFAState, Builder
from jellycc.lexer.dfa_minimize import minimize
from jellycc.lexer.codegen import Codegen
from jellycc.lexer.grammar import LexerGrammar
from jellycc.lexer.nfa import NFAContext, NFAState, NFARule
from jellycc.lexer.phf import PHF
from jellycc.lexer.regexp import Re
from jellycc.project.grammar import SharedGrammar
from jellycc.utils.error import CCError
from jellycc.utils.source import SrcLoc


class LexerGenerator:
	def __init__(self, shared: SharedGrammar) -> None:
		self.shared = shared
		self.lexer_grammar = LexerGrammar(shared)
		self.nfa_ctx: NFAContext = NFAContext()
		self.nfa_init: NFAState = NFAState()
		self.nfa_ends: List[NFAState] = []
		self.lexer_rules: List[Tuple[SrcLoc, str, Re]] = []
		self.nfa_rules: List[NFARule] = []

	def construct(self) -> None:
		for idx, (loc, name, re) in enumerate(self.lexer_rules):
			if name not in self.shared.terminals:
				raise CCError(loc, f"terminal '{name}' not found")
			term = self.shared.terminals[name]
			end_state = NFAState()
			rule = NFARule(idx, loc, term)
			end_state.rule = rule
			re.build_nfa(self.nfa_ctx, self.nfa_init, end_state)
			self.nfa_rules.append(rule)
			self.nfa_ends.append(end_state)

	def run(self) -> None:
		if not self.shared.term_error:
			raise CCError(None, "no {error} terminal found")

		builder = Builder(self.shared.term_error, self.nfa_rules, 0)
		dfa = builder.build(self.nfa_init)
		keywords = builder.keywords
		min_dfa = minimize(dfa)

		self.inject_error_state(min_dfa)

		list_states: List[DFAState] = []
		min_dfa.visit(lambda state: list_states.append(state))

		codegen = Codegen(self.lexer_grammar, min_dfa)
		codegen.run()

	def inject_error_state(self, initial_state: DFAState) -> None:
		error_state = DFAState()
		error_terminal = self.shared.term_error
		accept_error = NFARule(-1, error_terminal.loc, error_terminal)
		error_state.accepts = accept_error

		def visitor(state: DFAState) -> None:
			if (state.accepts is None) and (state is not initial_state):
				state.accepts = accept_error

		initial_state.visit(visitor)

		bad_characters: List[int] = []
		for idx, target in enumerate(initial_state.trans):
			if target is None:
				bad_characters.append(idx)
				initial_state.trans[idx] = error_state

		for char in bad_characters:
			error_state.trans[char] = error_state
