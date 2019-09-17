${include:parser_vm.h}

${parser_vm_source}

void PP_vm_init(PP_VM* vm) {
	vm->output = nullptr;
	vm->output_end = nullptr;
}

void PP_vm_set_output(PP_VM* vm, uint16_t* output, size_t len) {
	vm->output = output;
	vm->output_end = output + len;
}

void PP_vm_run(PP_VM* vm, ${parser_vm_ctx} ctx) {
	uint16_t* output = vm->output;
	uint16_t* output_end = vm->output_end;
	while (output != output_end) {
		switch (*output) {
		${vm_switch}
		}
		output++;
	}
}

