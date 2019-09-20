#include <cstdint>
#include <cstddef>
#include <cstring>
#include <bitset>
#include <algorithm>

${include:parser.shared.inc}

${parser_source}

namespace ${parser_namespace} {

extern const uint8_t skippable_flag[${token_count}] = {
	${token_skippable_data}
};

struct VMArgs {
	${vm_struct}
};

struct ParserState {
	uint16_t* stack;
	uint16_t* stack_limit;

	const uint16_t* input;

	uint16_t* output;
	uint16_t* output_end;

	uint16_t* rewind;
	uint16_t* rewind_end;

	uint16_t* rewind_begin;
	uint16_t* stack_begin;
	uint16_t* stack_end;
	const uint16_t* input_end;

	uint16_t* output_chunks[2];
	uint16_t* rewind_chunks[2];
	uint16_t* other_output;
	uint16_t* other_rewind;

	uint8_t* data;
	uint8_t* data_end;
	uint8_t* data_begin;

	uint8_t active_chunk;

	AllocatorCallback allocator;
	ParserConfig config;

	VMArgs vm_args;

	size_t tokens_to_skip;
	const uint16_t* insert_terminals;

	size_t total_size;
};

static bool run_core(ParserState* state);
static int rewind(ParserState* state, int tokens);
static ParseResult parser_recovery(ParserState* state);
static ParseResult parser_run_vm(ParserState* state, uint16_t* output, uint16_t* output_end);

${include:parser_tables.cpp}

static uint8_t* parser_allocate(ParserState* state, size_t size) {
	return state->allocator.allocate(state->allocator.ud, size);
}

static uint8_t* parser_reallocate(ParserState* state, uint8_t* ptr, size_t old_size, size_t new_size) {
	return state->allocator.reallocate(state->allocator.ud, ptr, old_size, new_size);
}

static void parser_free(ParserState* state, uint8_t* ptr, size_t size) {
	state->allocator.free(state->allocator.ud, ptr, size);
}

static ParseResult parser_reallocate_data(ParserState* state, size_t new_size) {
	size_t data_offset = state->data - state->data_begin;
	uint8_t* new_data;
	if (state->data_begin) {
		new_data = (uint8_t*)parser_reallocate(state, state->data_begin, (state->data_end - state->data_begin), new_size);
	} else {
		new_data = (uint8_t*)parser_allocate(state, new_size);
	}
	if (!new_data) {
		return ParseResult::OutOfMemory;
	}
	state->data_begin = new_data;
	state->data = state->data_begin + data_offset;
	state->data_end = state->data_begin + new_size;
	return ParseResult::OK;
}

static ParseResult parser_reallocate_stack(ParserState* state, size_t new_size) {
	size_t stack_offset = state->stack - state->stack_begin;
	uint16_t* new_stack;
	if (state->stack_begin) {
		new_stack = (uint16_t*)parser_reallocate(state, (uint8_t*)state->stack_begin, (state->stack_end - state->stack_begin), new_size);
	} else {
		new_stack = (uint16_t*)parser_allocate(state, new_size);
	}
	if (!new_stack) {
		return ParseResult::OutOfMemory;
	}
	state->stack_begin = new_stack;
	state->stack = state->stack_begin + stack_offset;
	state->stack_end = state->stack_begin + new_size;
	state->stack_limit = state->stack_end - 4;
	return ParseResult::OK;
}

ParserState* parser_create(AllocatorCallback cb, ParserConfig cfg) {
	size_t total_allocation_size = (
		sizeof(ParserState)
		+
		2 * (sizeof(uint16_t) * (cfg.chunk_size + 1) + 2 * sizeof(uint16_t) * cfg.chunk_size)
	);
	uint8_t* ptr = cb.allocate(cb.ud, total_allocation_size);
	ParserState* state = (ParserState*)ptr;
	if (!state) {
		return nullptr;
	}
	memset(state, 0, sizeof(ParserState));
	state->allocator = cb;
	state->config = cfg;
	state->total_size = total_allocation_size;

	ptr += sizeof(ParserState);
	for (int i = 0; i < 2; i++) {
		state->output_chunks[i] = (uint16_t*)ptr;
		ptr += sizeof(uint16_t) * (cfg.chunk_size + 1);
		state->rewind_chunks[i] = (uint16_t*)ptr;
		ptr += 2 * sizeof(uint16_t) * cfg.chunk_size;
	}
	return state;
}

#define JELLYCC_CHECKED(expr) if (ParseResult _result = (expr); _result != ParseResult::OK) { return _result; } else

ParseResult parser_initialize(ParserState* parser) {
	JELLYCC_CHECKED(parser_reallocate_stack(parser, parser->config.stack_initial));
	JELLYCC_CHECKED(parser_reallocate_data(parser, parser->config.data_initial));

	return ParseResult::OK;
}

void parser_destroy(ParserState* parser) {
	if (!parser) {
		return;
	}
	if (parser->stack_begin) {
		parser_free(parser, (uint8_t*)parser->stack_begin, parser->stack_end - parser->stack_begin);
	}
	parser->allocator.free(parser->allocator.ud, (uint8_t*)parser, parser->total_size);
}

void parser_select_chunk(ParserState* parser, uint8_t chunk) {
	parser->output = parser->output_chunks[chunk];
	parser->output_end = parser->output + parser->config.chunk_size;
	parser->rewind_begin = parser->rewind = parser->rewind_chunks[chunk];
	parser->rewind_end = parser->rewind + parser->config.chunk_size * 2;
	parser->active_chunk = chunk;
}

ParseResult parser_cycle_chunks(ParserState* parser) {
	uint8_t other_chunk = 1 - parser->active_chunk;
	if (parser->other_output != parser->output_chunks[other_chunk]) {
		JELLYCC_CHECKED(parser_run_vm(parser, parser->output_chunks[other_chunk], parser->other_output));
	}
	parser->other_output = parser->output;
	parser->other_rewind = parser->rewind;
	parser_select_chunk(parser, other_chunk);
	return ParseResult::OK;
}

ParseResult parser_drain(ParserState* parser) {
	JELLYCC_CHECKED(parser_cycle_chunks(parser));
	return parser_cycle_chunks(parser);
}

void parser_backtrack_chunk(ParserState* parser) {
	uint8_t chunk = parser->active_chunk;
	uint8_t other_chunk = 1 - chunk;
	parser_select_chunk(parser, other_chunk);
	parser->output = parser->other_output;
	parser->rewind = parser->other_rewind;
	parser->other_output = parser->output_chunks[chunk];
	parser->other_rewind = parser->rewind_chunks[chunk];
}

ParseResult parser_grow_stack(ParserState* parser) {
	size_t old_size = (parser->stack_end - parser->stack_begin);
	size_t new_size = old_size * 2;
	if (new_size > parser->config.stack_max) {
		new_size = parser->config.stack_max;
	}
	if (new_size <= old_size) {
		return ParseResult::StackOverflow;
	}
	return parser_reallocate_stack(parser, new_size);
}

ParseResult parser_grow_data(ParserState* parser) {
	size_t old_size = (parser->data_end - parser->data_begin);
	size_t new_size = old_size * 2;
	if (new_size > parser->config.data_max) {
		new_size = parser->config.data_max;
	}
	if (new_size <= old_size) {
		return ParseResult::StackOverflow;
	}
	return parser_reallocate_data(parser, new_size);
}

ParseResult parser_run(ParserState* parser, NonTerminal nt, const uint16_t* input, const uint16_t* input_end ${vm_extra_params}) {
	if (!parser->stack) {
		ParseResult result = parser_initialize(parser);
		if (result != ParseResult::OK) {
			return result;
		}
	}

	// copy vm arguments
	parser->vm_args = {${vm_copy_params}};

	// reset data chunks
	parser->other_output = parser->output_chunks[1];
	parser->other_rewind = parser->rewind_chunks[1];
	parser_select_chunk(parser, 0);

	// reset and configure stack
	parser->stack = parser->stack_begin;
	parser->stack[0] = ${sentinel_state};
	parser->stack[1] = (uint16_t)nt;
	parser->stack++;

	// set input
	parser->input = input;
	parser->input_end = input_end;

	while (true) {
		if (parser->rewind >= parser->rewind_end) {
			JELLYCC_CHECKED(parser_cycle_chunks(parser));
		}
		if (parser->stack >= parser->stack_limit) {
			JELLYCC_CHECKED(parser_grow_stack(parser));
		}
		if (run_core(parser)) {
			if (*parser->stack == ${sentinel_state} && parser->input == parser->input_end) {
				// accept
				JELLYCC_CHECKED(parser_drain(parser));
				break;
			} else {
				// recovery
				JELLYCC_CHECKED(parser_recovery(parser));
			}
		}
	}

	return ParseResult::OK;
}

static bool run_core(ParserState* parser) {
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

${include:parser_recovery.cpp}
${include:parser_panic.cpp}
${include:parser_lec.cpp}

${include:parser_vm.cpp}

}

