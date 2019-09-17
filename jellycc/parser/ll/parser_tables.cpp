
struct table_entry {
	uint8_t shift;
	int8_t state_change;
	uint16_t megaaction;
	uint16_t data[4];
};

static const size_t data_base[] = {
	${base_data}
};

static const uint8_t data_dispatch[][${token_count}] = {
	${dispatch_data}
};

static const uint16_t data_table[] = {
	${table_data}
};

static const table_entry data_entries[] = {
	${entries_data}
};



static const uint8_t data_sync_dispatch[][${state_count}] = {
	${sync_dispatch_data}
};

static const size_t data_sync_base[] = {
	${sync_base_data}
};

struct sync_entry {
	uint16_t actions;
	uint16_t states;
};

static const sync_entry data_sync_entries[] = {
	${sync_entries_data}
};

static const uint16_t data_sync_actions[] = {
	${sync_actions_data}
};

static const uint16_t data_sync_states[] = {
	${sync_states_data}
};

static const uint16_t data_sync_token_skip_cost[] = {
	${sync_token_skip_cost_data}
};

static const uint16_t data_sync_token_insert_cost[] = {
	${sync_token_insert_cost_data}
};

static const uint16_t data_sync_token_sync_cost[] = {
	${sync_token_sync_cost_data}
};

static const uint16_t data_sync_state_skip_ref[] = {
	${sync_state_skip_ref_data}
};

static const uint16_t data_sync_state_skip_cost[] = {
	${sync_state_skip_cost_data}
};
