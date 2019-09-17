#pragma once
#include <cstdint>
#include <cstddef>

inline constexpr uint16_t ${parser_prefix}_token_eof = ${token_eof};

enum class ${parser_prefix}_Symbol {
	${export_symbols}
};

enum class ${parser_prefix}_Result {
	Accept,
	Reject,
	MoreStack,
	MoreOutput,
	MoreInput
};

struct ${parser_prefix}_Parser {
	uint16_t* tokens;
	size_t token_idx;
	size_t token_count;

	uint16_t* stack;
	uint16_t* stack_base;
	uint16_t* stack_top;

	uint16_t* out;
	uint16_t* out_base;
	uint16_t* out_end;
};

void ${parser_prefix}_push_symbol(${parser_prefix}_Parser* pp, ${parser_prefix}_Symbol symbol);
void ${parser_prefix}_set_input(${parser_prefix}_Parser* pp, uint16_t* tokens, size_t count);
void ${parser_prefix}_set_stack(${parser_prefix}_Parser* pp, uint16_t* stack, size_t size);
void ${parser_prefix}_set_output(${parser_prefix}_Parser* pp, uint16_t* out, size_t size);
size_t ${parser_prefix}_get_input_pos(${parser_prefix}_Parser* pp);
size_t ${parser_prefix}_get_output_count(${parser_prefix}_Parser* pp);
${parser_prefix}_Result ${parser_prefix}_run(${parser_prefix}_Parser* pp);