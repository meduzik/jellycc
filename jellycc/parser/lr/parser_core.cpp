#include <cstdint>
#include <cstddef>

${include:parser_core.h}

const uint8_t ${parser_prefix}_table_dispatch[][${token_count}] = {
	${table_dispatch}
};
const uint16_t ${parser_prefix}_table_payload[][${dispatch_count}] = {
	${table_payload}
};
const uint16_t ${parser_prefix}_table_goto[][${goto_count}] = {
	${table_goto}
};
const uint16_t ${parser_prefix}_resolve[] = {
	${table_resolve}
};
const uint8_t ${parser_prefix}_table_accepts[] = {
	${table_accepts}
};

void ${parser_prefix}_init(${parser_prefix}_Parser* pp) {
	pp->stack = nullptr;
	pp->stack_top = nullptr;
	pp->stack_base = nullptr;

	pp->token_idx = 0;
	pp->tokens = nullptr;
	pp->token_count = 0;

	pp->out = nullptr;
	pp->out_base = nullptr;
	pp->out_end = nullptr;
}

void ${parser_prefix}_push_symbol(${parser_prefix}_Parser* pp, ${parser_prefix}_Symbol symbol) {
	*pp->stack = (uint16_t)symbol;
	pp->stack++;
}

void ${parser_prefix}_set_input(${parser_prefix}_Parser* pp, uint16_t* tokens, size_t count) {
	pp->token_idx = 0;
	pp->tokens = tokens;
	pp->token_count = count;
}

void ${parser_prefix}_set_stack(${parser_prefix}_Parser* pp, uint16_t* stack, size_t size) {
	size_t old_size = pp->stack - pp->stack_base;
	pp->stack = stack + old_size;
	pp->stack_top = stack + size;
	pp->stack_base = stack;
}

void ${parser_prefix}_set_output(${parser_prefix}_Parser* pp, uint16_t* out, size_t size) {
	pp->out = out;
	pp->out_end = out + size;
	pp->out_base = out;
}

size_t ${parser_prefix}_get_input_pos(${parser_prefix}_Parser* pp) {
	return pp->token_idx;
}

size_t ${parser_prefix}_get_output_count(${parser_prefix}_Parser* pp) {
	return pp->out - pp->out_base;
}

${parser_prefix}_Result ${parser_prefix}_run(${parser_prefix}_Parser* pp) {
	uint16_t* tokens = pp->tokens;
	size_t token_idx = pp->token_idx;
	size_t token_end = pp->token_count;

	if (pp->stack == pp->stack_top) {
		return ${parser_prefix}_Result::MoreStack;
	}
	uint16_t* stack = pp->stack - 1;
	uint16_t* stack_top = pp->stack_top - 1;

	uint16_t* out = pp->out;
	uint16_t* out_end = pp->out_end;

	while ((token_idx < token_end) & (stack != stack_top) & (out != out_end)) {
		uint16_t token = tokens[token_idx];
		uint16_t state = *stack;

		uint8_t dispatch = ${parser_prefix}_table_dispatch[state][token];
        if (dispatch == 0xff) {
			break;
		}
        uint16_t action = ${parser_prefix}_table_payload[state][dispatch];

		uint8_t shift = action >> 12;
		uint16_t payload = action & ((1 << 12) - 1);

		stack -= shift;

		uint16_t reduce_state = ${parser_prefix}_table_goto[*stack][${parser_prefix}_resolve[payload]];
		stack += (payload != 0);
		*stack = reduce_state;

		token_idx += (payload <= ${count_shifts});

		*out = payload;
		out++;
	}

	pp->token_idx = token_idx;
	pp->stack = stack + 1;
	pp->out = out;

	if (token_idx >= token_end) {
		return ${parser_prefix}_Result::MoreInput;
	}
	if (stack >= stack_top) {
		return ${parser_prefix}_Result::MoreStack;
	}
	if (out >= out_end) {
		return ${parser_prefix}_Result::MoreOutput;
	}

	if (tokens[token_idx] == ${token_eof}) {
		uint8_t accept = ${parser_prefix}_table_accepts[*stack];
		if (accept) {
			pp->stack -= 2;
			pp->token_idx++;
			return ${parser_prefix}_Result::Accept;
		}
	}
	return ${parser_prefix}_Result::Reject;
}
