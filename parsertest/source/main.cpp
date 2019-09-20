#include <iostream>
#include <vector>
#include <cstddef>

using u16 = uint16_t;
using u32 = uint32_t;
using u64 = uint64_t;

#include "../../.output/jellyscript/lexer.h"
#include "../../.output/jellyscript/parser.h"
/*
const unsigned char test_input[] = {
	"y=75;\n  x=sin(y/180+;a=4;a=a+ 1; import 'c'; a=a*3;b=2+2*2;x=2;"
	"x=sin(1+2);"
	"import 'a'; a = a*3; impoty 'axcas' {a; b};"
	"import 'aasc' as qwe;"
	"import '' as a {b,c as we}; ID = 10;"
	"import 'q'; a=a*3;"
};
*/
enum class Token: u16 {
#define X(t,v,n) t=v,
	LEX_TOKENS(X)
#undef X
};

std::vector<u16> Tokens;
std::vector<u16> Input;
std::vector<u16> MoreTokens;
std::vector<u32> Offsets;
std::vector<u32> IDs;

u16 TokenBuffer[16384];
u32 OffsetBuffer[sizeof(TokenBuffer) / sizeof(TokenBuffer[0])];

u16 ParserStack[16384];
u16 ParserOutput[16384];
u16 ParserRewind[16384];

FuncMap funcs;

const char* NameOf(uint16_t t) {
	switch (t) {
#define X(t,v,n) case v: return n;
	LEX_TOKENS(X)
#undef X
	}
	return "<unknown_token>";
}

std::vector<uint8_t> read_file(const char* path) {
	std::vector<uint8_t> r;
	FILE* f = fopen(path, "rb");
	fseek(f, 0, SEEK_END);
	int size = ftell(f);
	r.resize(size);
	fseek(f, 0, SEEK_SET);
	fread(r.data(), size, 1, f);
	fclose(f);
	return r;
}

std::vector<uint8_t> input;

int main() {
	input = read_file("test/test1.test");

	Offsets.push_back(0);
	lex::run(
		{
			nullptr,
			[](void* ud, uint16_t* tokens, uint32_t* offsets, size_t count) {
				std::copy(tokens, tokens + count, std::back_inserter(Tokens));
				std::copy(offsets, offsets + count, std::back_inserter(Offsets));
			},
			[](void* ud, uint16_t** tokens, uint32_t** offsets, size_t* count) {
				*tokens = TokenBuffer;
				*offsets = OffsetBuffer;
				*count = sizeof(TokenBuffer) / sizeof(TokenBuffer[0]);
			}
		},
		input.data(),
		input.size()
	);
	Tokens.push_back((u16)Token::EoF);
	Offsets.push_back(Offsets.back());
	pp::ParserState* parser = pp::parser_create({
		nullptr,
		[](void* ud, size_t size) -> uint8_t* {
			return (uint8_t*)malloc(size);
		},
		[] (void* ud, uint8_t* ptr, size_t old_size, size_t new_size) -> uint8_t* {
			return (uint8_t*)realloc(ptr, new_size);
		},
		[] (void* ud, uint8_t* ptr, size_t size) {
			free(ptr);
		}
	}, pp::DefaultConfig);

	IDs.push_back(0);
	for (size_t i = 0; i < Tokens.size(); i++) {
		Token tok = (Token)Tokens[i];
		if (tok == Token::Space || tok == Token::MLComment || tok == Token::Comment || tok == Token::Error) {
			
		} else {
			IDs.push_back(i);
			Input.push_back((u16)tok);
		}
	}
	IDs.push_back(Tokens.size());

	VarMap vars;
	
	funcs["sin"] = [](DoubleList* dl) {
		return sin(dl->val);
	};

	CBData cb = {
		nullptr,
		[](void*, uint32_t pos) -> std::string {
			return {(const char*)input.data() + Offsets[pos], Offsets[pos + 1] - Offsets[pos]};
		},
		[](void*, uint32_t pos) -> double {
			try{
				return std::stod({(const char*)input.data() + Offsets[pos], Offsets[pos + 1] - Offsets[pos]});
			} catch (...) {
				return std::numeric_limits<double>::quiet_NaN();
			}
		},
		[](void*, const std::string & fname, DoubleList * args) -> double {
			std::cout << "invoking '" << fname << "' with (";
			DoubleList* orig_args = args;
			while (args) {
				std::cout << args->val;
				if (args->next) {
					std::cout << ", ";
				}
				args = args->next;
			}
			std::cout << ")\n";
			if (funcs.count(fname)) {
				return funcs.at(fname)(orig_args);
			}
			return std::numeric_limits<double>::quiet_NaN();
		},
		[](void*, uint32_t * &tokid, size_t num) -> void {
			std::cout << "panic skips " << num << " tokens starting at " << Offsets[*tokid] << "\n";
			tokid += num;
		},
		[](void*, uint32_t* &tokid, uint16_t terminal) -> void {
			u32 pos = Offsets[*tokid];
			std::cout << "panic inserts '" << NameOf(terminal) << "' at " << pos << "\n";
			tokid--;
			*tokid = Offsets.size();
			Offsets.push_back(pos);
			Offsets.push_back(pos);
			MoreTokens.push_back(terminal);
			MoreTokens.push_back(0);
		},
		[](void*, uint32_t*& tokid, uint16_t terminal) -> void {
			u32 pos = Offsets[*tokid];
			std::cout << "lec inserts '" << NameOf(terminal) << "' at " << pos << "\n";
			tokid--;
			*tokid = Offsets.size();
			Offsets.push_back(pos);
			Offsets.push_back(pos);
			MoreTokens.push_back(terminal);
			MoreTokens.push_back(0);
		},
		[](void*, uint32_t*& tokid) -> void {
			std::cout << "lec skips '" << NameOf(Tokens[*tokid]) << "' at " << Offsets[*tokid] << "\n";
			tokid++;
		},
		[](void*, uint32_t*& tokid, uint16_t terminal) -> void {
			u32 pos = Offsets[*tokid];
			std::cout << "lec replaces '" << NameOf(Tokens[*tokid]) << "' with '" << NameOf(terminal) << "' at " << pos << "\n";
			*tokid = Offsets.size();
			Offsets.push_back(pos);
			Offsets.push_back(pos);
			MoreTokens.push_back(terminal);
			MoreTokens.push_back(0);
		},
	};

	pp::parser_run(
		parser,
		pp::NonTerminal::program,
		Input.data(),
		Input.data() + Input.size() - 1,
		&vars,
		IDs.data() + 1,
		cb
	);
	for (auto [k,v]: vars) {
		std::cout << k << " = " << v << std::endl;
	}
	return 0;
}

