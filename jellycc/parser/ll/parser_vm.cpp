
template<class T>
constexpr intptr_t Aligned = (sizeof(T) + 7) & ~7;

template<class... Args>
constexpr intptr_t ListOffset = (Aligned<Args> + ... + 0);

static ParseResult parser_vm_dispatch(ParserState* parser, uint16_t* actions);

static ParseResult parser_run_vm(ParserState* parser, uint16_t* output, uint16_t* output_end) {
	*output_end = ${vm_action_sentinel};
	return parser_vm_dispatch(parser, output);
}

static ParseResult parser_vm_dispatch(ParserState* parser, uint16_t* actions) {
	uint8_t* data = parser->data;
	uint8_t* data_end = parser->data_end;
	uint8_t* data_limit = data_end - 256;

	${vm_extract_vm_args}

	while (true) {
		if (data >= data_limit) {
			parser->data = data;
			JELLYCC_CHECKED(parser_grow_data(parser));
			data = parser->data;
			data_end = parser->data_end;
			data_limit = data_end - 64;
		}
		switch (*actions) {
		${vm_dispatch_switch}
		case ${action_panic_skip}: {
			size_t num = parser->tokens_to_skip;
			${vm_action_panic_skip}
		} break;
		case ${action_panic_insert}: {
			uint16_t terminal = *parser->insert_terminals;
			parser->insert_terminals++;
			${vm_action_panic_insert}
		} break;
		case ${action_lec_insert}: {
			uint16_t terminal = *parser->insert_terminals;
			${vm_action_lec_insert}
		} break;
		case ${action_lec_replace}: {
			uint16_t terminal = *parser->insert_terminals;
			${vm_action_lec_replace}
		} break;
		case ${action_lec_remove}: {
			${vm_action_lec_remove}
		} break;
		case ${vm_action_sentinel}: {
			goto exit;
		} break;
		}
		actions++;
	}
exit:
	parser->data = data;
	return ParseResult::OK;
}
