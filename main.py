from antlr4 import *
from GoLexer import *
from GoParser import *
from CFGListner import *

def main(argv):
	f = open(argv[1])
	text = f.read()
	
	istream = InputStream(text)
	lexer = GoLexer(istream)
	tstream = CommonTokenStream(lexer)
	parser = GoParser(tstream)

	tree = parser.sourceFile()

	if parser.getNumberOfSyntaxErrors() > 0:
		print("Some syntax errors are present")
	else:
		print("Ok")

	cfg = CFGListener()

	walker = ParseTreeWalker()
	walker.walk(cfg, tree)

	cfg.graph.render()

main(sys.argv)