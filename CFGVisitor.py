from GoParser import GoParser
from GoParserListener import *
from enum import Enum
from graphviz import * 
from re import *

class State(Enum):
	none = 0
	const_decl = 1
	var_decl = 2
	assign = 3

class If(Enum):
	Then = 0
	ThenElse = 1

class NodeStack(list):
	def is_last(self, name):
		if len(self) == 0:
			return False
	
		last = self[-1]
		if type(last) == list and name in last or last == name:
			return True
		
		return False
	def add(self, name):
		if not self.is_last(name):
			self.append(name)
	

def to_str(ctx):
	if ctx.getChildCount()>0:
		children = [ctx.getChild(i) for i in range(ctx.getChildCount())]
		children = map(to_str, children)
		return "["+' '.join(children)+"]"

	return f'"{ctx.getText()}"'

def extract_values(ctx):
	children = [ctx.getChild(i).getText() for i in range(0, ctx.getChildCount(), 2)]
	return children

def style(node, dir):
	if ':' in node:
		return node
	return f'{node}:{dir}'

def guess_type(s):
	dec_lit = '0|[1-9](_?[0-9])*'
	bin_lit = '0[Bb](_?[01])*'
	oct_lit = '0[oO](_?[0-7])*'
	hex_lit = '0[xX](_?[0-9a-fA-F])*'

	DEC =   '([0-9](_?[0-9])*)'
	EXP =  f'([eE][+-]?{DEC})'
	HEXD = f'[0-9a-fA-F]'
	HEXM = f'(_?{HEXD})+(\\.(_?{HEXD})*)?'
	HEXE = f'[pP][+-]?{DEC}'

	dec_float_lit = f'{DEC}(\\.{DEC}?{EXP}?|{EXP})|\\.{DEC}{EXP}'
	hex_float_lit = f'0[xX]{HEXM}{HEXE}'

	ret = ''

	for pat in [dec_lit, bin_lit, oct_lit, hex_lit]:
		if fullmatch(pat, s):
			val = 0

			if len(s)>1 and s[1] in 'bB':
				val = int(s, 2)

			elif len(s)>1 and s[1] in 'oO':
				val = int(s, 8)

			elif len(s)>1 and s[1] in 'xX':
				val = int(s, 16)

			else:
				val = int(s)

			if -128 <= val < 127:
				ret = 'int8'

			elif -2147483648 <= val < 2147483647:
				ret = 'int32'

			else:
				ret = 'int64'


	for pat in [dec_float_lit, hex_float_lit]:
		if fullmatch(pat, s):
			ret = 'float64'

	if s[0] == s[-1] == '"':
		ret = 'string'

	return ret


class CFGListener(GoParserVisitor):
	def __init__(self, *args, **kwargs):
		self.graph = Digraph('cfg', format='png')
		self.graph.attr(splines='polyline')
		self.state = State.none
		self.typed_const = False
		self.stack = []

		self.cur_text = ''
		self.text_stack = []
		self.errors = []
		self.names_set = False
		self.values_set = False
		self.level = 0
		self.ind = 0

		self.nodes = []
		self.if_levels_stack = []
		self.firsts_stack = NodeStack()
		self.lasts_stack = NodeStack()
		self.ends = []
		self.if_stack = []

		self.for_stack = []

	def assign(self, keyword='', op='='):
		vals = self.stack.pop()
		t = self.stack.pop()
		names = self.stack.pop()

		# TODO compare len(vals) and len(names)

		for i in range(len(vals)):
			if keyword:
				if t == 'guess':
					self.cur_text += f'{keyword} {names[i]} = {vals[i]} \n'

				else:
					self.cur_text += f'{keyword} {names[i]} {t} = {vals[i]} \n'
			else:
				self.cur_text += f'{names[i]} {op} {vals[i]} \n'

		self.names_set = False
		self.values_set = False

	def enterFunctionDecl(self, ctx):
		text = ctx.getChild(1).getText()
		node = self.new_node('f', text, 'box')
		self.ends.append(node)

	def exitFunctionDecl(self, ctx):
		text = ctx.getChild(1).getText()
		node = self.new_node('b', f'{text} end')

	def enterBlock(self, ctx):
		self.level += 1

		if self.nodes[-1][0] != 'f':
			self.firsts_stack.add(self.nodes[-1])

		self.lasts_stack.add(self.nodes[-1])

	def exitBlock(self, ctx):
		self.level -= 1 

		if not self.cur_text:
			return

		if self.cur_text:
			self.new_node('b', shape='box')

		self.cur_text = ''

	def enterConstSpec(self, ctx):
		self.state = State.const_decl

	def exitConstSpec(self, ctx):
		self.assign('const')
		self.state = State.none
		self.typed_const = False

	def enterVarDecl(self, ctx):
		self.state = State.var_decl

	def enterAssignment(self, ctx):
		names = extract_values(ctx.getChild(0))
		op = ctx.getChild(1).getText()
		t = 'guess'
		values = extract_values(ctx.getChild(2))

		self.stack.append(names)
		self.stack.append(t)
		self.stack.append(values)

		self.assign(op=op)

	def exitVarDecl(self, ctx):
		self.assign('var')
		self.state = State.none
		self.typed_const = False		

	def exitIdentifierList(self, ctx):
		if self.state in [State.const_decl, State.var_decl, State.assign]:
			if self.names_set:
				return
			
			self.names_set = True

			self.stack.append(extract_values(ctx))

	def exitType_(self, ctx):
		if self.state in [State.const_decl, State.var_decl, State.assign]:
			self.stack.append(ctx.getChild(0).getChild(0).getText())
			self.typed_const = True

	def exitExpressionList(self, ctx):
		if self.state in [State.const_decl, State.var_decl]:
			if self.values_set:
				self.stack.pop()

			self.values_set = True
			if not self.typed_const:
				self.stack.append('guess')
			self.stack.append(extract_values(ctx))
	
	def new_node(self, t, content="", shape='box'):
		self.ind += 1

		if t == 'b':
			if self.nodes and self.if_stack:
				if self.nodes[-1][0] == 'i':
					t = 't'

				elif self.if_stack[-1] == If.ThenElse:
					t = 'e'

		ret = f'{t}{self.ind}'		

		if content == "" and t in 'bte':
			content = self.cur_text

		self.nodes.append(ret)
		self.graph.node(ret, content+f' {ret}', shape=shape)
		# self.graph.node(ret, content, shape=shape)


		if self.lasts_stack:
			lasti = self.lasts_stack.pop()

			if not self.if_levels_stack or self.if_levels_stack[-1] != self.level and lasti[0] != 'il':
				last = self.ends.pop()
				self.connect(last, ret)
			else: 
				self.lasts_stack.add(lasti)
				self.ends.append(ret)

			self.lasts_stack.add(ret)

		# self.graph.render()
		return ret

	def connect(self, fr, to, manual= False, **kwargs):
		if type(fr) == list:
			for f in fr:
				self.connect(f, to)
		else:
			self.graph.edge(
					style(fr, 's'), 
					style(to, 'n'), **kwargs)
			
		if not manual:
			if not self.ends:
				self.ends.append(to)

			else:
				last = self.ends[-1]

				if (type(last) == list and to not in last) or (to!=last):
					self.ends.append(to)

	def enterIfStmt(self, ctx):
		t = 0

		if self.cur_text:
			self.new_node('b', shape='box')
		self.cur_text = ''

		self.new_node('if', ctx.getChild(1).getText(), shape='diamond')

		self.if_levels_stack.append(self.level)

		if ctx.getChildCount() == 3: # no else
			self.if_stack.append(If.Then)

		if ctx.getChildCount() == 5: # with else
			self.if_stack.append(If.ThenElse)

	def exitIfStmt(self, ctx):
		if ctx.getChildCount() == 5:
			elsenodebegin = self.firsts_stack.pop()

			elsenodebegin = self.advance(elsenodebegin)

			elsenodeend = self.lasts_stack.pop()

			thennodebegin = self.firsts_stack.pop()
			thennodebegin = self.advance(thennodebegin)

			thennodeend = self.lasts_stack.pop()

			if thennodeend in self.lasts_stack:
				thenindex = self.lasts_stack[::-1].index(thennodeend)
				del self.lasts_stack[-1-thenindex]

			ifnode = self.nodes[self.nodes.index(thennodebegin.split(':')[0])-1] # probaly refectorable

			self.connect(ifnode, thennodebegin, manual=True, label='true', headport='n', tailport='w')
			self.connect(ifnode, elsenodebegin, manual=True, label='false', headport='n', tailport='e')

			self.lasts_stack.add([thennodeend, elsenodeend])

			self.ends.pop()
			self.ends.pop()
			self.ends.pop()
			if type(thennodeend) == list and type(elsenodeend) == list:
				self.ends.append(thennodeend + elsenodeend)

			elif type(thennodeend) == list:
				self.ends.append(thennodeend + [elsenodeend])

			elif type(elsenodeend) == list:
				self.ends.append([thennodeend] + elsenodeend)

			else: 
				self.ends.append([thennodeend, elsenodeend])

		else:
			thennodebegin = self.firsts_stack.pop()
			thennodebegin = self.advance(thennodebegin)
			thennodeend = self.lasts_stack.pop()

			if thennodeend in self.lasts_stack:
				thenindex = self.lasts_stack[::-1].index(thennodeend)
				del self.lasts_stack[-1-thenindex]

			ifnode = self.nodes[self.nodes.index(thennodebegin.split(':')[0])-1]

			self.connect(ifnode, thennodebegin, manual=True, label='true')

			self.ends.pop()
			self.ends.pop()
			self.ends.append([f'{ifnode}:e', thennodeend])

			self.lasts_stack.add(thennodeend)

		self.graph.render()
		self.if_stack.pop()
		self.if_levels_stack.pop()

	def advance(self, nodes):
		if type(nodes) == list:
			return [self.advance(nodes[0]), self.advance(nodes[1])]
		
		ind = self.nodes.index(nodes)
		return self.nodes[ind+1]

	def enterForStmt(self, ctx):
		if self.cur_text:
			self.new_node('b', shape='box')
		self.cur_text = ''

		self.new_node('l', ctx.getChild(1).getText(), shape='egg')


	def exitForStmt(self, ctx):
		loopnodebegin = self.firsts_stack.pop()
		loopnodebegin = self.advance(loopnodebegin)
		loopnodeend = self.lasts_stack.pop()

		if loopnodeend in self.lasts_stack:
			thenindex = self.lasts_stack[::-1].index(loopnodeend)
			del self.lasts_stack[-1-thenindex]

		loopnode = self.nodes[self.nodes.index(loopnodebegin.split(':')[0])-1]

		self.connect(loopnode, loopnodebegin, manual=True)
		self.connect(loopnodeend, loopnode, headport='e', tailport='e')

		self.ends.pop()
		self.ends.pop()
		self.ends.append([f'{loopnode}:w', loopnodeend])

		self.lasts_stack.add(f'{loopnode}:w')

