#include <cstddef>
#include <cstdint>
#include <cstring>

${include:lexer.shared.inc}

namespace ${lexer_namespace} {

struct LexerState {
	uint16_t state;

	const uint8_t* input_begin;
	const uint8_t* input_end;
	const uint8_t* input;

	uint16_t* tokens;
	uint32_t* offsets;

	size_t token_idx;
	size_t token_offset;
	size_t token_max;

	LexerCallback cb;
};


static const uint32_t equiv_table[256] = {
	${equiv_table}
};
static const uint16_t trans_table[] = {
	${trans_table}
};
static const uint16_t accept_table[] = {
	${accept_table}
};
static const uint16_t trans_fin_table[] = {
	${fin_trans_table}
};

#define JCC_LEXER_UNROLL_ITERATIONS ${lexer_unroll_count}

static void request_buffer(LexerState* lex) {
	size_t count;
	lex->cb.get_buffer(lex->cb.ud, &lex->tokens, &lex->offsets, &count);
	lex->token_offset = lex->token_idx;
	lex->token_max = count + lex->token_idx;
}

static void flush_output(LexerState* lex) {
	if (lex->token_idx > lex->token_offset) {
		lex->cb.on_output(lex->cb.ud, lex->tokens, lex->offsets, lex->token_idx - lex->token_offset);
	}
}

static void loop(LexerState* lex) {
	uint16_t state = lex->state;

	uintptr_t input_pos = (uintptr_t)(lex->input - lex->input_begin);
	uintptr_t input_base = (uintptr_t)lex->input_begin;
	uintptr_t input_len = (uintptr_t)(lex->input_end - lex->input_begin);

	size_t token_idx = lex->token_idx;
	size_t token_end = lex->token_max;

	uintptr_t tokens_base = (uintptr_t)(lex->tokens - lex->token_offset);
	uintptr_t offsets_base = (uintptr_t)(lex->offsets - lex->token_offset);

	#define token(idx) (*(uint16_t*)(tokens_base + idx * sizeof(uint16_t)))
	#define offset(idx) (*(uint32_t*)(offsets_base + idx * sizeof(uint32_t)))

	size_t input_avail = input_len - input_pos;
	size_t output_avail = token_end - token_idx;

	if (
		(input_avail >= JCC_LEXER_UNROLL_ITERATIONS)
		&
		(output_avail >= JCC_LEXER_UNROLL_ITERATIONS)
	) {
		size_t input_unroll_stop = input_pos + input_avail / JCC_LEXER_UNROLL_ITERATIONS * JCC_LEXER_UNROLL_ITERATIONS;
		size_t output_unroll_stop = token_idx + (output_avail - JCC_LEXER_UNROLL_ITERATIONS) / JCC_LEXER_UNROLL_ITERATIONS * JCC_LEXER_UNROLL_ITERATIONS;
		while ((input_pos != input_unroll_stop) & (token_idx < output_unroll_stop)) {
			uint8_t chars[JCC_LEXER_UNROLL_ITERATIONS];
			memcpy(chars, (const uint8_t*)(input_base + input_pos), JCC_LEXER_UNROLL_ITERATIONS);
			for (int i = 0; i < JCC_LEXER_UNROLL_ITERATIONS; i++) {
				uint16_t trans = *(const uint16_t*)((const char*)trans_table + equiv_table[chars[i]] + state);

				token(token_idx) = *(const uint16_t*)((const char*)accept_table + state);
				offset(token_idx) = (uint32_t)input_pos + i;

				state = (uint16_t)(trans & ~1);
				token_idx += (trans & 1);
			}
			input_pos += JCC_LEXER_UNROLL_ITERATIONS;
		}
	}

	while ((input_pos != input_len) & (token_idx != token_end)) {
		uint8_t ch = *(const uint8_t*)(input_base + input_pos);
		uint32_t equiv = equiv_table[ch];
		uint16_t trans = *(const uint16_t*)((const char*)trans_table + equiv + state);

		token(token_idx) = *(const uint16_t*)((const char*)accept_table + state);
		offset(token_idx) = (uint32_t)input_pos;

		state = (uint16_t)(trans & ~1);
		token_idx += (trans & 1);

		input_pos++;
	}

	size_t first_token = lex->token_idx;

	lex->input = lex->input_begin + input_pos;
	lex->token_idx = token_idx;
	lex->state = state;
}

static void finalize(LexerState* lex) {
	uint16_t state = lex->state;

	size_t token_idx = lex->token_idx;
	uint16_t* token = lex->tokens + (lex->token_idx - lex->token_offset);

	uint16_t trans = *(const uint16_t*)((const char*)trans_fin_table + state);
	uint32_t* offset = lex->offsets + (lex->token_idx - lex->token_offset);

	*token = *(const uint16_t*)((const char*)accept_table + state);
	*offset = (uint32_t)(lex->input - lex->input_begin);

	token_idx += (trans & 1);

	lex->token_idx = token_idx;
}

void run(LexerCallback cb, const uint8_t* data, size_t len) {
	LexerState lex;
	memset(&lex, 0, sizeof(LexerState));
	lex.cb = cb;
	lex.input_begin = lex.input = data;
	lex.input_end = data + len;
	while (true) {
		if (lex.token_idx >= lex.token_max) {
			flush_output(&lex);
			request_buffer(&lex);
		}
		if (lex.input >= lex.input_end) {
			break;
		}
		loop(&lex);
	}
	finalize(&lex);
	flush_output(&lex);
}

}
