static ParseResult parser_try_local_correction(
	ParserState* parser,
	const uint16_t* input_end
) {
	while (true) {
		if (parser->rewind >= parser->rewind_end) {
			// if we filled a whole chunk, accept
			return ParseResult::OK;
		}
		if (parser->stack >= parser->stack_limit) {
			JELLYCC_CHECKED(parser_grow_stack(parser));
		}
		if (run_core(parser)) {
			if (parser->input == input_end) {
				// the entire input was consumed
				return ParseResult::OK;
			} else {
				return ParseResult::OK;
			}
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
		if (run_core(parser)) {
			return ParseResult::OK;
		}
	}
}

static ParseResult parser_lec_try_one(
	ParserState* parser,
	const uint16_t* input_rewind,
	correction c,
	bool* success
) {
	*success = false;
	const uint16_t* input_pos = input_rewind + c.offset;
	if (parser->input != input_pos) {
		parser->input_end = input_pos;
		JELLYCC_CHECKED(parser_try_parse(parser));
		if (parser->input != input_pos) {
			return ParseResult::OK;
		}
	}
	switch (c.kind) {
	case correction_kind::insert: {
		parser->input = &c.token;
		parser->input_end = parser->input + 1;
		JELLYCC_CHECKED(parser_try_parse(parser));
		if (parser->input != parser->input_end) {
			parser->input = input_pos;
			return ParseResult::OK;
		}
		parser->input = input_pos;
	} break;
	case correction_kind::replace: {
		parser->input = &c.token;
		parser->input_end = parser->input + 1;
		JELLYCC_CHECKED(parser_try_parse(parser));
		if (parser->input != parser->input_end) {
			parser->input = input_pos;
			return ParseResult::OK;
		}
		parser->input = input_pos + 1;
	} break;
	case correction_kind::remove: {
		parser->input = input_pos + 1;
	} break;
	}
	*success = true;
	return ParseResult::OK;
}

static ParseResult parser_lec_try(
	ParserState* parser,
	const uint16_t* input_rewind,
	const uint16_t* input_end,
	correction c1,
	correction c2,
	bool* success
) {
	*success = false;
	parser->input = input_rewind;
	if (c1.kind != correction_kind::none) {
		JELLYCC_CHECKED(parser_lec_try_one(parser, input_rewind, c1, success));
		if (!*success) {
			return ParseResult::OK;
		}
	}
	if (c2.kind != correction_kind::none) {
		JELLYCC_CHECKED(parser_lec_try_one(parser, input_rewind, c2, success));
		if (!*success) {
			return ParseResult::OK;
		}
	}
	parser->input_end = input_end;
	JELLYCC_CHECKED(parser_try_parse(parser));
	*success = true;
	return ParseResult::OK;
}

static ParseResult parser_lec_score(
	ParserState* parser,
	const uint16_t* input_rewind,
	const uint16_t* input_error,
	const uint16_t* input_end,
	correction c1,
	correction c2,
	uint16_t* score
) {
	*score = 0;
	bool success;
	JELLYCC_CHECKED(parser_lec_try(parser, input_rewind, input_end, c1, c2, &success));
	if (!success) {
		goto exit;
	}
	if (parser->input <= input_error) {
		goto exit;
	}
	{
		uint8_t error_offset = input_error - input_rewind;
		intptr_t forward = parser->input - input_error;
		if (c1.offset >= error_offset && (c1.kind == correction_kind::remove || c1.kind == correction_kind::replace)) {
			forward--;
		}
		if (c2.offset >= error_offset && (c2.kind == correction_kind::remove || c2.kind == correction_kind::replace)) {
			forward--;
		}
		*score = forward;
	}
exit:
	rewind(parser, 0x7fff'ffff);
	parser->input = input_rewind;
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

	uint16_t best_score = 0;
	correction best_c1, best_c2;

	#define UNPAREN(...) __VA_ARGS__
	#define UNFOLD(...) UNPAREN __VA_ARGS__
	#define TRY_CORRECTION(C1, C2) { \
		uint16_t score = 0; \
		correction c1 UNFOLD(C1); \
		correction c2 UNFOLD(C2); \
		JELLYCC_CHECKED(parser_lec_score(parser, input_rewind, input_error, input_corrected, c1, c2, &score)); \
		if (score > best_score) { \
			best_score = score; \
			best_c1 = c1; \
			best_c2 = c2; \
			if (best_score >= lookahead) { \
				goto exit; \
			} \
		} \
	}

	{
		for (uint8_t i = 0; i < std::min(worksize + 1, backtrack + 1); i++) {
			for (uint16_t t = 0; t < ${token_count}; t++) {
				TRY_CORRECTION(({correction_kind::insert, i, t}), ({correction_kind::none}));
			}
		}
	}

	{
		for (uint8_t i = 0; i < std::min(worksize, backtrack + 1); i++) {
			TRY_CORRECTION(({correction_kind::remove, i}), ({correction_kind::none}));
			for (uint16_t t = 0; t < ${token_count}; t++) {
				TRY_CORRECTION(({correction_kind::replace, i, t}), ({correction_kind::none}));
			}
		}
	}

	/*
	{
		for (uint8_t i = 0; i < std::min(worksize + 1, backtrack + 1); i++) {
			for (uint16_t t1 = 0; t1 < ${token_count}; t1++) {
				for (uint8_t j = i; j < worksize; j++) {
					TRY_CORRECTION(({correction_kind::insert, i, t1}), ({correction_kind::remove, j}));
					for (uint16_t t2 = 0; t2 < ${token_count}; t2++) {
						TRY_CORRECTION(({correction_kind::insert, i, t1}), ({correction_kind::replace, j, t2}));
					}
				}
				for (uint8_t j = i; j < worksize + 1; j++) {
					for (uint16_t t2 = 0; t2 < ${token_count}; t2++) {
						TRY_CORRECTION(({correction_kind::insert, i, t1}), ({correction_kind::insert, j, t2}));
					}
				}
			}
		}

		for (uint8_t i = 0; i < std::min(worksize, backtrack + 1); i++) {
			for (uint8_t j = i + 1; j < worksize; j++) {
				TRY_CORRECTION(({correction_kind::remove, i}), ({correction_kind::remove, j}));
				for (uint16_t t2 = 0; t2 < ${token_count}; t2++) {
					TRY_CORRECTION(({correction_kind::remove, i}), ({correction_kind::replace, j, t2}));
				}
			}
			for (uint8_t j = i + 1; j < worksize + 1; j++) {
				for (uint16_t t2 = 0; t2 < ${token_count}; t2++) {
					TRY_CORRECTION(({correction_kind::remove, i}), ({correction_kind::insert, j, t2}));
				}
			}

			for (uint16_t t1 = 0; t1 < ${token_count}; t1++) {
				for (uint8_t j = i + 1; j < worksize; j++) {
					TRY_CORRECTION(({correction_kind::replace, i, t1}), ({correction_kind::remove, j}));
					for (uint16_t t2 = 0; t2 < ${token_count}; t2++) {
						TRY_CORRECTION(({correction_kind::replace, i, t1}), ({correction_kind::replace, j, t2}));
					}
				}
				for (uint8_t j = i + 1; j < worksize + 1; j++) {
					for (uint16_t t2 = 0; t2 < ${token_count}; t2++) {
						TRY_CORRECTION(({correction_kind::replace, i, t1}), ({correction_kind::insert, j, t2}));
					}
				}
			}
		}
	}
	*/
exit:
	if (best_score >= LEC_accept_threshold) {
		JELLYCC_CHECKED(parser_lec_apply(parser, input_error, input_rewind, best_c1, best_c2));
		JELLYCC_CHECKED(parser_drain(parser));
		*recovered = true;
		return ParseResult::OK;
	}

	*recovered = false;
	return ParseResult::OK;
}
