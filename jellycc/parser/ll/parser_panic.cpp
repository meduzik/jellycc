static ParseResult parser_sync_run_actions(ParserState* parser, const uint16_t* actions) {
	uint16_t num_actions = actions[1];
	parser->insert_terminals = actions + 2 + num_actions;
	for (uint32_t i = 0; i < num_actions; i++) {
		JELLYCC_CHECKED(parser_push_action(parser, actions[2 + i]));
	}
	return parser_drain(parser);
}

static ParseResult parser_sync_discard_state(ParserState* parser, uint16_t state)  {
	uint16_t skip_actions_ref = data_sync_state_skip_ref[state];
	const uint16_t* actions = &data_sync_actions[skip_actions_ref];
	return parser_sync_run_actions(parser, actions);
}

static ParseResult parser_sync_resync_state(ParserState* parser, uint16_t state, uint16_t token)  {
	uint8_t dispatch = data_sync_dispatch[token][state];
	size_t locus = data_sync_base[state] + dispatch;
	sync_entry entry = data_sync_entries[locus];
	const uint16_t* actions = &data_sync_actions[entry.actions];
	const uint16_t* states = &data_sync_states[entry.states];
	JELLYCC_CHECKED(parser_sync_run_actions(parser, actions));
	JELLYCC_CHECKED(parser_drain(parser));
	uint16_t num_states = states[0];
	for (uint32_t i = 0; i < num_states; i++) {
		JELLYCC_CHECKED(parser_push_state(parser, states[i + 1]));
	}
	return ParseResult::OK;
}


static ParseResult parser_panic_resync(ParserState* parser) {
	const uint16_t* input = parser->input;
	const uint16_t* input_end = parser->input_end;
	uint16_t* stack = parser->stack;
	uint16_t* stack_begin = parser->stack_begin;

	std::bitset<${token_count}> visited_tokens;
	std::bitset<${state_count}> visited_states;

	uint32_t best_cost = UINT_MAX;
	const uint16_t* best_stack = nullptr;
	const uint16_t* best_input = nullptr;

	uint32_t token_discard_cost = 0;
	const uint16_t* input_pos = input;
	for (
		;
		input_pos != input_end && token_discard_cost < best_cost;
		token_discard_cost += data_sync_token_skip_cost[*input_pos], input_pos++
	) {
		uint16_t tok = *input_pos;
		if (visited_tokens.test(tok)) {
			continue;
		}
		visited_tokens.set(tok);
		visited_states.reset();
		uint32_t state_discard_cost = token_discard_cost + data_sync_token_sync_cost[tok];
		for (
			uint16_t* stack_pos = stack;
			*stack_pos != ${sentinel_state} && state_discard_cost < best_cost;
			state_discard_cost += data_sync_state_skip_cost[*stack_pos], stack_pos--
		) {
			uint16_t state = *stack_pos;
			if (visited_states.test(state)) {
				continue;
			}
			visited_states.set(state);
			uint8_t dispatch = data_sync_dispatch[tok][state];
			if (dispatch == 0xff) {
				continue;
			}
			size_t locus = data_sync_base[state] + dispatch;
			uint16_t cost = data_sync_actions[data_sync_entries[locus].actions];
			uint32_t total_cost = state_discard_cost + cost;
			if (total_cost < best_cost) {
				best_stack = stack_pos;
				best_input = input_pos;
				best_cost = total_cost;
			}
		}
	}

	if (input_pos == input_end) {
		uint32_t state_discard_cost = token_discard_cost;
		uint16_t* stack_pos = stack;
		for (
			;
			*stack_pos != ${sentinel_state} && state_discard_cost < best_cost;
			state_discard_cost += data_sync_state_skip_cost[*stack_pos], stack_pos--
		) {
			// nothing to sync with - just skip
		}
		if (state_discard_cost < best_cost) {
			best_stack = stack_pos;
			best_input = input_pos;
			best_cost = state_discard_cost;
		}
	}

	if (best_cost < UINT_MAX) {
		size_t tokens_to_skip = best_input - input;
		input += tokens_to_skip;
		if (tokens_to_skip > 0) {
			parser->tokens_to_skip = tokens_to_skip;
			JELLYCC_CHECKED(parser_push_action(parser, ${action_panic_skip}));
		}
		while (stack != best_stack) {
			JELLYCC_CHECKED(parser_sync_discard_state(parser, *stack));
			stack--;
		}
		if (input != input_end) {
			uint16_t state = *stack;
			parser->stack = stack - 1;
			JELLYCC_CHECKED(parser_sync_resync_state(parser, state, *input));
		} else {
			parser->stack = stack;
		}
		parser->input = input;
		return parser_drain(parser);
	}

	return ParseResult::FatalError;
}


static bool parser_run_to_end(ParserState* parser) {
	uint16_t* __restrict stack = parser->stack;
	const uint16_t* __restrict input = parser->input;
	const uint16_t* input_end = parser->input_end;
	uint16_t* __restrict output = parser->output;
	uint16_t* __restrict rewind = parser->rewind;
	uint16_t* rewind_end = parser->rewind_end;
	uint16_t* stack_limit = parser->stack_limit;

	while (true) {
		if (rewind >= rewind_end || stack >= stack_limit) {
			goto exit_fail;
		}
		if (input == input_end) {
			goto exit_success;
		}

		uint16_t state = *stack;
		uint16_t tok = *input;
		uint8_t dispatch = data_dispatch[state][tok];
		if (dispatch == 0xff) {
			goto exit_success;
		}
		size_t locus = data_base[state] + dispatch;
		uint16_t entry_id = data_table[locus];
		table_entry entry = data_entries[entry_id];

		rewind[0] = state;
		rewind[1] = entry_id;
		rewind += 2;

		input += entry.shift;
		memcpy(stack, entry.data, sizeof(entry.data));
		stack += entry.state_change;
		*output = entry.megaaction;

		if (entry.megaaction) {
			output++;
		}
	}

#define COPY_STATE \
	{parser->stack = stack;parser->input = input;parser->output = output;parser->rewind = rewind;}

exit_success:
	COPY_STATE;
	return true;

exit_fail:
	COPY_STATE;
	return false;

#undef COPY_STATE
}


static ParseResult parser_greedy_consume(ParserState* parser) {
	while (true) {
		if (parser->rewind >= parser->rewind_end) {
			return ParseResult::FatalError;
		}
		if (parser->stack >= parser->stack_limit) {
			JELLYCC_CHECKED(parser_grow_stack(parser));
		}
		if (parser_run_to_end(parser)) {
			if (parser->input == parser->input_end) {
				break;
			} else {
				return ParseResult::FatalError;
			}
		}
	}
	return ParseResult::OK;
}
