import ast
from Redy.Magic.Pattern import Pattern
from bytecode import *
from bytecode.concrete import FreeVar, CellVar


class NonlocalManager:
    def __init__(self, ctx: 'Context'):
        self.ctx = ctx

    def __iadd__(self, name):
        self.ctx.parent += name

    def __contains__(self, name):
        return name in self.ctx.parent


class NestedUpFetchManager:
    __slots__ = ['ctx']

    def __init__(self, ctx: 'Context'):
        self.ctx = ctx

    def __contains__(self, name):
        return name in self.ctx or (self.ctx.parent and
                                    name in self.ctx.parent.available_symbols)


class Context:
    def __init__(self,
                 bytecode: Bytecode,
                 locals: set,
                 nonlocals: set,
                 ctx_depth: int,
                 parent: 'Context' = None):
        self.parent = parent or None
        self.bc = bytecode
        self.locals = locals
        self.nonlocals = nonlocals
        self.ctx_depth = ctx_depth

    def lens(self,
             bc=None,
             locals=None,
             nonlocals=None,
             parent=None,
             ctx_depth=None):
        return Context(
            bytecode=bc or self.bc,
            locals=locals or self.locals,
            nonlocals=nonlocals or self.nonlocals,
            ctx_depth=ctx_depth or self.ctx_depth,
            parent=parent or self.parent)

    def fix_bytecode(self):
        bc = self.bc
        for each in bc:
            if not isinstance(each, Instr):
                continue
            arg = each.arg
            if not isinstance(arg, FreeVar):
                continue
            name = arg.name

            if name not in bc.freevars and self.ctx_depth > 1:
                bc.freevars.append(name)

    def add_nonlocal(self, nonlocal_name):
        self.nonlocals.add(nonlocal_name)

    def __iadd__(self, name):
        if name in self.nonlocals:
            raise NameError(f'`{name}` is nonlocal .')
        return self.locals.add(name)

    def __contains__(self, name):
        return name in self.locals

    @property
    def available_symbols(self):
        return NestedUpFetchManager(self)

    def load_name(self, node: ast.Name):
        id = node.id
        if id in self:
            if id not in self.bc.cellvars:
                self.bc.append(Instr('LOAD_FAST', id, lineno=node.lineno))
            else:
                self.bc.append(
                    Instr('LOAD_DEREF', CellVar(id), lineno=node.lineno))
            return

        if id in self.available_symbols:
            self.bc.append(
                Instr("LOAD_DEREF", FreeVar(id), lineno=node.lineno))
        else:
            self.bc.append(Instr('LOAD_GLOBAL', id, lineno=node.lineno))


@Pattern
def py_emit(node: ast.AST, ctx: Context):
    return type(node)


@py_emit.case(ast.Name)
def py_emit(node: ast.Name, ctx: Context):
    ctx.load_name(node)


@py_emit.case(ast.Expr)
def py_emit(node: ast.Expr, ctx: Context):
    py_emit(node, ctx)
    ctx.bc.append('POP_TOP')


@py_emit.case(ast.YieldFrom)
def py_emit(node: ast.YieldFrom, ctx: Context):
    append = ctx.bc.append
    py_emit(node.value, ctx)
    append(Instr('GET_YIELD_FROM_ITER', lineno=node.lineno))
    append(Instr('LOAD_CONST', None, lineno=node.lineno))
    append(Instr("YIELD_FROM", lineno=node.lineno))


@py_emit.case(ast.Yield)
def py_emit(node: ast.Yield, ctx: Context):
    py_emit(node.value)
    ctx.bc.append(Instr('YIELD_VALUE', lineno=node.lineno))


@py_emit.case(ast.Return)
def py_emit(node: ast.Return, ctx: Context):
    py_emit(node.value)
    ctx.bc.append(Instr('RETURN_VALUE', lineno=node.lineno))


@py_emit.case(ast.Pass)
def py_emit(node: ast.Pass, ctx: Context):
    pass


@py_emit.case(ast.UnaryOp)
def py_emit(node: ast.UnaryOp, ctx: Context):
    py_emit(node.value, ctx)
    if isinstance(node.op,ast.Not):
        ctx.bc.append(Instr('UNARY_NOT', lineno=node.lineno))
    elif isinstance(node.op,ast.USub):
        ctx.bc.append(Instr('UNARY_NEGATIVE', lineno=node.lineno))
    else:
        raise TypeError("type mismatched")


@py_emit.case(ast.BinOp)
def py_emit(node: ast.BinOp, ctx: Context):
    py_emit(node.left, ctx)
    py_emit(node.right, ctx)
    if isinstance(node.op,ast.Add):
        ctx.bc.append(Instr('BINARY_ADD', lineno=node.lineno))
    elif isinstance(node.op,ast.BitAnd):
        ctx.bc.append(Instr('BINARY_AND', lineno=node.lineno))
    elif isinstance(node.op, ast.Sub):
        ctx.bc.append(Instr('BINARY_SUBTRACT', lineno=node.lineno))
    elif isinstance(node.op, ast.FloorDiv):
        ctx.bc.append(Instr('BINARY_FLOOR_DIVIDE', lineno=node.lineno))
    elif isinstance(node.op, ast.BitXor):
        ctx.bc.append(Instr('BINARY_XOR', lineno=node.lineno))
    elif isinstance(node.op, ast.Mult):
        ctx.bc.append(Instr('BINARY_MULTIPLY', lineno=node.lineno))
    elif isinstance(node.op, ast.Mod):
        ctx.bc.append(Instr('BINARY_MODULO', lineno=node.lineno))
    else:
        raise TypeError("type mismatched")

