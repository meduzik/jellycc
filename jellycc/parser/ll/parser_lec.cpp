static bool parse_lec_parse_single_loop(ParserState* parser, uint16_t tok, bool* success) {
	uint16_t* __restrict stack = parser->stack;
	uint16_t* __restrict output = parser->output;
	uint16_t* __restrict rewind = parser->rewind;
	uint16_t* rewind_end = parser->rewind_end;
	uint16_t* stack_limit = parser->stack_limit;

	while (true) {
		if (rewind >= rewind_end || stack >= stack_limit) {
			goto exit_fail;
		}

		uint16_t state = *stack;
		uint8_t dispatch = data_dispatch[state][tok];
		if (dispatch == 0xff) {
			goto exit_success;
		}
		size_t locus = data_base[state] + dispatch;
		uint16_t entry_id = data_table[locus];
		const table_entry& entry = data_entries[entry_id];

		rewind[0] = state;
		rewind[1] = entry_id;
		rewind += 2;

		memcpy(stack, entry.data, sizeof(entry.data));
		stack += entry.state_change;
		*output = entry.megaaction;
		output++;

		if (entry.shift) {
			*success = true;
			goto exit_success;
		}
	}

#define COPY_STATE \
	{parser->stack = stack;parser->output = output;parser->rewind = rewind;}

exit_success:
	COPY_STATE;
	return true;

exit_fail:
	COPY_STATE;
	return false;

#undef COPY_STATE
}

static ParseResult parse_lec_parse_single(ParserState* parser, uint16_t tok, bool* success) {
	while (true) {
		if (parser->rewind >= parser->rewind_end) {
			return ParseResult::OK;
		}
		if (parser->stack >= parser->stack_limit) {
			JELLYCC_CHECKED(parser_grow_stack(parser));
		}
		if (parse_lec_parse_single_loop(parser, tok, success)) {
			return ParseResult::OK;
		}
	}
}

enum class correction_kind: uint8_t {
	none,
	remove,
	insert,
	replace
};

struct correction {
	correction_kind kind;
	uint8_t offset;
	uint16_t token;
};

static ParseResult parser_lec_apply_one(
	ParserState* parser,
	const uint16_t* input_rewind,
	correction c
) {
	parser->input_end = input_rewind + c.offset;
	JELLYCC_CHECKED(parser_greedy_consume(parser));
	switch (c.kind) {
	case correction_kind::remove: {
		JELLYCC_CHECKED(parser_push_action(parser, ${action_lec_remove}));
		parser->input++;
	} break;
	case correction_kind::replace: {
		parser->insert_terminals = &c.token;
		const uint16_t* old_input = parser->input;
		JELLYCC_CHECKED(parser_push_action(parser, ${action_lec_replace}));
		parser->input = parser->insert_terminals;
		parser->input_end = parser->input + 1;
		JELLYCC_CHECKED(parser_greedy_consume(parser));
		parser->input = old_input + 1;
	} break;
	case correction_kind::insert: {
		const uint16_t* old_input = parser->input;
		parser->insert_terminals = &c.token;
		JELLYCC_CHECKED(parser_push_action(parser, ${action_lec_insert}));
		parser->input = parser->insert_terminals;
		parser->input_end = parser->input + 1;
		JELLYCC_CHECKED(parser_greedy_consume(parser));
		parser->input = old_input;
	} break;
	}
	return parser_drain(parser);
}

static ParseResult parser_lec_apply(
	ParserState* parser,
	const uint16_t* input_error,
	const uint16_t* input_rewind,
	correction c1,
	correction c2
) {
	parser->input = input_rewind;
	if (c1.kind == correction_kind::none) {
		return ParseResult::OK;
	}
	JELLYCC_CHECKED(parser_lec_apply_one(parser, input_rewind, c1));
	if (c2.kind == correction_kind::none) {
		return ParseResult::OK;
	}
	JELLYCC_CHECKED(parser_lec_apply_one(parser, input_rewind, c2));
	return ParseResult::OK;
}

static ParseResult parser_try_parse(ParserState* parser) {
	while (true) {
		if (parser->rewind >= parser->rewind_end) {
			return ParseResult::OK;
		}
		if (parser->stack >= parser->stack_limit) {
			JELLYCC_CHECKED(parser_grow_stack(parser));
		}
		if (parser_run_to_end(parser)) {
			return ParseResult::OK;
		}
	}
}

struct LECState {
	const uint16_t* input_rewind;
	const uint16_t* input_corrected;
	const uint16_t* input_error;
	const uint16_t* input_end;
	uint8_t level;
	correction cs[2];
	correction best_cs[2];
	int32_t best_advance;
	int32_t best_score;
};

static uint8_t data_lec_kind_score[] = {
	0,
	2,
	2,
	3
};

static int32_t parser_compute_score(LECState* state) {
	return (
		data_lec_kind_score[(uint8_t)state->cs[0].kind]
		+
		data_lec_kind_score[(uint8_t)state->cs[1].kind]
	);
}

static int32_t parser_compute_skip_all_cost(ParserState* parser) {
	uint16_t* stack = parser->stack;
	int32_t state_discard_cost = 0;
	uint16_t* stack_pos = stack;
	for (
		;
		*stack_pos != ${sentinel_state};
		state_discard_cost += data_sync_state_skip_cost[*stack_pos], stack_pos--
	) {
		// nothing to sync with - just skip
	}
	return state_discard_cost;
}

static ParseResult parser_lec_recursive(
	ParserState* parser,
	LECState* state
) {
	const uint16_t* input_start = parser->input;
	const uint16_t* input_corrected = state->input_corrected;
	uint8_t level = state->level;
	// parse as far as we can
	JELLYCC_CHECKED(parser_try_parse(parser));

	if (level > 0) {
		int32_t advance = (input_start != parser->input) ? (int32_t)std::min(parser->input - state->input_error, parser->input - input_start) : 0;
		int32_t score = parser_compute_score(state);
		if (parser->input == state->input_end) {
			// we are on the end of the input, insert eof
			bool success = false;
			JELLYCC_CHECKED(parse_lec_parse_single(parser, ${token_eof}, &success));
			if (*parser->stack == ${sentinel_state}) {
				advance = LEC_backtrack + LEC_lookahead + 1;
			} else {
				score += parser_compute_skip_all_cost(parser);
			}
		}
		if (
			advance > state->best_advance
			||
			(advance == state->best_advance && score < state->best_score)
		) {
			state->best_advance = advance;
			state->best_score = score;
			memcpy(state->best_cs, state->cs, sizeof(state->cs));
		}
		if (level > 1) {
			rewind(parser, (int32_t)(parser->input - input_start));
			return ParseResult::OK;
		}
	}
	// back up zero tokens
	state->level++;
	rewind(parser, 0);
	while (true) {
		const uint16_t* input_checkpoint = parser->input;
		uint8_t offset = (uint8_t)(parser->input - state->input_rewind);
		if (input_checkpoint != input_corrected) {
			// there are more tokens, consider removal and replace
			parser->input++;
			// try removal
			state->cs[level] = {correction_kind::remove, offset};
			JELLYCC_CHECKED(parser_lec_recursive(parser, state));
			for (uint16_t tok = 0; tok < ${token_count}; tok++) {
				if (tok == parser->input[-1]) {
					continue;
				}
				bool success = false;
				JELLYCC_CHECKED(parse_lec_parse_single(parser, tok, &success));
				if (success) {
					state->cs[level] = {correction_kind::replace, offset, tok};
					JELLYCC_CHECKED(parser_lec_recursive(parser, state));
					parser->input++;
					rewind(parser, 1);
				} else {
					rewind(parser, 0);
				}
			}
			parser->input--;
		}
		for (uint16_t tok = 0; tok < ${token_count}; tok++) {
			bool success = false;
			JELLYCC_CHECKED(parse_lec_parse_single(parser, tok, &success));
			// try insertion
			if (success) {
				state->cs[level] = {correction_kind::insert, offset, tok};
				JELLYCC_CHECKED(parser_lec_recursive(parser, state));
				parser->input++;
				rewind(parser, 1);
			} else {
				rewind(parser, 0);
			}
		}
		if (input_checkpoint == input_start) {
			break;
		}
		// back up another token
		rewind(parser, 1);
	}
	state->level--;
	state->cs[level] = {correction_kind::none};
	return ParseResult::OK;
}

static ParseResult parser_local_error_correction(
	ParserState* parser,
	const uint16_t* input_error,
	const uint16_t* input_rewind,
	bool* recovered
) {
	const uint16_t* input_end = parser->input_end;

	size_t backtrack = std::min(LEC_backtrack, (uint16_t)(input_error - input_rewind));
	size_t lookahead = std::min(LEC_lookahead, (uint16_t)(input_end - input_error));
	size_t worksize = backtrack + lookahead;

	const uint16_t* input_corrected = input_rewind + worksize;

	parser->input = input_rewind;
	parser->input_end = input_corrected;

	LECState state {
		input_rewind,
		input_corrected,
		input_error,
		input_end,
		0,
		{{correction_kind::none}, {correction_kind::none}},
		{{correction_kind::none}, {correction_kind::none}},
		0,
		0,
	};

	JELLYCC_CHECKED(parser_lec_recursive(parser, &state));

	if (state.best_advance >= LEC_accept_threshold) {
		JELLYCC_CHECKED(parser_lec_apply(parser, input_error, input_rewind, state.best_cs[0], state.best_cs[1]));
		JELLYCC_CHECKED(parser_drain(parser));
		*recovered = true;
		return ParseResult::OK;
	}
	*recovered = false;
	return ParseResult::OK;
}
