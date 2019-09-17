static int rewind(ParserState* parser, int tokens) {
	uint16_t* __restrict stack = parser->stack;
	const uint16_t* __restrict input = parser->input;
	uint16_t* __restrict output = parser->output;
	uint16_t* __restrict rewind = parser->rewind;
	uint16_t* rewind_begin = parser->rewind_begin;

	while (true) {
		if (rewind == rewind_begin) {
			break;
		}

		rewind -= 2;

		uint16_t state = rewind[0];
		uint16_t entry_id = rewind[1];
		table_entry entry = data_entries[entry_id];

		tokens -= entry.shift;
		if (tokens < 0) {
			break;
		}
		input -= entry.shift;

		stack -= entry.state_change;
		*stack = state;

		if (entry.megaaction) {
			output--;
		}
	}

	COPY_STATE;
	return tokens;
}

static ParseResult parser_push_action(ParserState* parser, uint16_t action) {
	if (parser->output == parser->output_end) {
		JELLYCC_CHECKED(parser_cycle_chunks(parser));
	}
	*parser->output = action;
	parser->output++;
	return ParseResult::OK;
}

static ParseResult parser_push_state(ParserState* parser, uint16_t state) {
	if (parser->stack == parser->stack_limit) {
		JELLYCC_CHECKED(parser_grow_stack(parser));
	}
	parser->stack++;
	*parser->stack = state;
	return ParseResult::OK;
}

static ParseResult parser_local_error_correction(ParserState* parser, const uint16_t* input_error, const uint16_t* input_rewind, bool* recovered);
static ParseResult parser_panic_resync(ParserState* parser);
static ParseResult parser_greedy_consume(ParserState* parser);

static constexpr uint16_t LEC_lookahead = 6;
static constexpr uint16_t LEC_backtrack = 8;
static constexpr uint16_t LEC_accept_threshold = 2;

static ParseResult parser_recovery(ParserState* parser) {
	// remember the error token
	const uint16_t* input_error = parser->input;
	const uint16_t* input_end = parser->input_end;

	// recovery via local correction
	{
		// rewind N tokens (or as much as possible)
		int more_rewind = rewind(parser, LEC_backtrack);
		if (more_rewind >= 0) {
			parser_backtrack_chunk(parser);
			rewind(parser, more_rewind);
		}
	}

	// remember the point where recovery starts
	const uint16_t* input_rewind = parser->input;

	{
		// commit everything prior to the recovery point
		// to make room for parsing and prevent from ever rewinding further
		JELLYCC_CHECKED(parser_drain(parser));

		// try local correction
		bool recovered = false;
		JELLYCC_CHECKED(parser_local_error_correction(parser, input_error, input_rewind, &recovered));

		if (recovered) {
			parser->input_end = input_end;
			return ParseResult::OK;
		}
	}

	// didn't recover correctly, going into panic mode
	{
		// rewind everything
		if (parser->rewind != parser->rewind_begin) {
			rewind(parser, 0x7fff'ffff);
		}
		// consume input back to the error point
		parser->input = input_rewind;
		parser->input_end = input_error;
		JELLYCC_CHECKED(parser_greedy_consume(parser));

		// recovery via sync sets
		parser->input_end = input_end;
		JELLYCC_CHECKED(parser_panic_resync(parser));
	}

	return ParseResult::OK;
}

