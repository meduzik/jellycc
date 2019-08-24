#include <cstddef>
#include <cstdint>

namespace ${lexer_namespace} {

${lexer_terminals}

struct LexerCallback {
	void* ud;
	void (*on_output) (
		void* ud,
		uint16_t* tokens,
		uint32_t* offsets,
		size_t count
	);
	void (*get_buffer) (
		void* ud,
		uint16_t** tokens,
		uint16_t** hashes,
		uint32_t** offsets,
		size_t* count
	);
};

void run(LexerCallback cb, const uint8_t* data, size_t len);

}
