#include <cstdint>
#include <cstddef>

${parser_header}

namespace ${parser_namespace} {

enum class ParseResult {
	OK,
	OutOfMemory,
	StackOverflow,
	FatalError
};

enum class NonTerminal: uint16_t {
	${entry_states}
};

struct ParserState;

struct AllocatorCallback {
	void* ud;
	uint8_t* (*allocate) (void* ud, size_t size);
	uint8_t* (*reallocate) (void* ud, uint8_t* ptr, size_t old_size, size_t new_size);
	void (*free) (void* ud, uint8_t* ptr, size_t size);
};

struct ParserConfig {
	size_t stack_initial;
	size_t stack_max;
	size_t data_initial;
	size_t data_max;
	size_t chunk_size;
};

inline constexpr ParserConfig DefaultConfig = {
	/* stack_initial */ 64 * 1024,
	/* stack_max */  1 * 1024 * 1024,

	/* data_initial */ 64 * 1024,
	/* data_max */  8 * 1024 * 1024,

	/* chunk_size */ 64 * 1024
};

ParserState* parser_create(AllocatorCallback cb, ParserConfig cfg);
ParseResult parser_run(ParserState* parser, NonTerminal nt, const uint16_t* input, const uint16_t* input_end ${vm_extra_params});
void parser_destroy(ParserState* parser);

}
