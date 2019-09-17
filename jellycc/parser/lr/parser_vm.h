#include <cstdlib>
#include <cstddef>

${parser_vm_header}

struct PP_VM {
	uint16_t* output;
	uint16_t* output_end;
};

void PP_vm_init(PP_VM* vm);
void PP_vm_set_output(PP_VM* vm, uint16_t* output, size_t len);
void PP_vm_run(PP_VM* vm, ${parser_vm_ctx} ctx);

