from jellycc.project.parser import parse_project
from jellycc.project.project import Project
from jellycc.utils.source import source_file
import argparse
import os


parser = argparse.ArgumentParser(
	description="Generate lexer and parser from formal description"
)

parser.add_argument('--lexer-header', dest='lexer_header', nargs=1, help='path to lexer header')
parser.add_argument('--lexer-source', dest='lexer_source', nargs=1, help='path to lexer source')
parser.add_argument('--parser-header', dest='parser_header', nargs=1, help='path to parser header')
parser.add_argument('--parser-source', dest='parser_source', nargs=1, help='path to parser source')
parser.add_argument('--base-dir', dest='base_dir', nargs=1, help='overrides the base location for #line directives')
parser.add_argument('--lexer-ns', dest='lexer_ns', default='ll')
parser.add_argument('--lexer-prefix', dest='lexer_prefix', default='LL')
parser.add_argument('--parser-ns', dest='parser_ns', default='pp')
parser.add_argument('--parser-prefix', dest='parser_prefix', default='PP')
parser.add_argument('input', metavar='input', type=str, nargs=1, help='grammar file')


args = parser.parse_args()


input_file = args.input

project: Project = parse_project(source_file(input_file[0]))
project.process()

if args.base_dir:
	project.grammar.base_dir = args.base_dir[0]
else:
	project.grammar.base_dir = os.getcwd()

dry_run = True

if args.lexer_header or args.lexer_source:
	dry_run = False

	project.lexer_generator.lexer_grammar.prefix = args.lexer_prefix
	project.lexer_generator.lexer_grammar.namespace = args.lexer_ns

	if args.lexer_header:
		project.lexer_generator.lexer_grammar.header_path = args.lexer_header[0]
	if args.lexer_source:
		project.lexer_generator.lexer_grammar.source_path = args.lexer_source[0]

	project.lexer_generator.run()


if args.parser_header or args.parser_source:
	dry_run = False
	print("WARNING! Parser generation is incomplete and should not be used")

	project.lexer_generator.lexer_grammar.prefix = args.parser_prefix
	project.lexer_generator.lexer_grammar.namespace = args.parser_ns

	if args.parser_header:
		project.parser_generator.grammar.core_header_path = args.parser_header[0]
	if args.parser_source:
		project.parser_generator.grammar.core_source_path = args.parser_source[0]

	project.parser_generator.run_lh()

if dry_run:
	print("Dry run: no files generated")
