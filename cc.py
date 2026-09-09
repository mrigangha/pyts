import sys
import os

src_path = sys.argv[1] if len(sys.argv) > 1 else "test.ts"
try:
    fp = open(src_path, "r")
    src = fp.read()
except FileNotFoundError:
    print(f"Error: source file '{src_path}' not found.", file=sys.stderr)
    print(f"Usage: python {sys.argv[0]} [source.ts]", file=sys.stderr)
    sys.exit(1)


from llvmlite import binding, ir

binding.initialize_all_targets()
binding.initialize_all_asmprinters()

CONST_STR = 1
CONST_INT = 2
CONST_SYM = 3

KEYWORDS = ("function", "let", "if", "else", "for", "while", "const", "return")


def tokenise(code: str):
    isStr = False
    pc = 0
    tokens = []
    while pc < len(code):
        c = code[pc]
        # Inside string literal: preserve everything char-by-char
        # (parser reassembles between quotes), toggle on quote.
        if isStr:
            if c == '"':
                tokens.append((c, "SYM"))
                isStr = False
                pc += 1
            elif c == "\n":
                # Unterminated string: emit newline so parser can error out
                tokens.append(("\n", "SYM"))
                pc += 1
            elif c == " " or c == "\t":
                tokens.append((c, "WS"))
                pc += 1
            else:
                tokens.append((c, "SYM"))
                pc += 1
            continue
        # Outside strings:
        # comments: // to end of line
        if c == "/" and pc + 1 < len(code) and code[pc + 1] == "/":
            while pc < len(code) and code[pc] != "\n":
                pc += 1
            continue
        if c == "\n":
            tokens.append(("\n", "SYM"))
            pc += 1
        elif c == " " or c == "\t" or c == "\r":
            pc += 1
        elif c.isalpha() or c == "_":
            builder = ""
            while pc < len(code) and (code[pc].isalnum() or code[pc] == "_"):
                builder += code[pc]
                pc += 1
            if builder in KEYWORDS:
                tokens.append((builder, "KEYWORD"))
                continue
            tokens.append((builder, "TEXT"))
        elif c.isdigit():
            builder = ""
            isFloat = False
            while pc < len(code) and (code[pc].isdigit() or code[pc] == "."):
                if code[pc] == ".":
                    # Only treat '.' as decimal point if followed by digit,
                    # otherwise stop (e.g. member access or '..')
                    if pc + 1 < len(code) and code[pc + 1].isdigit():
                        isFloat = True
                        builder += code[pc]
                        pc += 1
                    else:
                        break
                else:
                    builder += code[pc]
                    pc += 1
            if isFloat:
                tokens.append((builder, "FLOAT"))
            else:
                tokens.append((builder, "NUM"))
        elif c == '"':
            tokens.append((c, "SYM"))
            isStr = not isStr
            pc += 1
        else:
            # Multi-char operators as single token
            two = code[pc : pc + 2] if pc + 1 < len(code) else ""
            if two in ("==", "!=", ">=", "<=", "&&", "||"):
                tokens.append((two, "SYM"))
                pc += 2
            else:
                tokens.append((c, "SYM"))
                pc += 1

    return tokens


AST_CFUNCTION_DECLARATION = "AST_FUNCTION_DEFINATION"
AST_FUNCTION_DEFINATION = "AST_FUNCTION_DEFINATION"
AST_FUNCTION_CALL = "AST_FUNCTION_CALL"
AST_RETURN = "AST_RETURN"
AST_STRING_CONSTANT = "AST_STRING_CONSTANT"
AST_NUMBER_CONSTANT = "AST_STRING_NUMBER"
AST_OBJECT_VARIABLE_DECLARATION = "AST_VARIABLE_DECLARATION"
AST_VARIABLE_CALL = "AST_VARIABLE_CALL"
AST_SIMPLE_EXPRESSION = "AST_SIMPLE_EXPRESSION"
AST_ARTHIMETIC_OPERATOR = "AST_ARTHIMETIC_OPERATOR"
AST_MATH_ADD = "AST_MATH_ADD"
AST_MATH_SUBTRACT = "AST_MATH_SUBTRACT"
AST_MATH_MULTIPLY = "AST_MATH_MULTIPLY"
AST_MATH_DIVIDE = "AST_MATH_DIVIDE"
AST_CONDITIONAL = "AST_CONDITIONAL"
AST_IF = "AST_IF"
AST_ELSE = "AST_ELSE"
AST_WHILE = "AST_WHILE"
AST_PARAM = "AST_PARAM"
AST_FLOAT_CONSTANT = "AST_FLOAT_CONSTANT"
AST_BOOL_CONSTANT = "AST_BOOL_CONSTANT"


BYTE = ir.IntType(8)
BYTE_PTR = ir.PointerType(BYTE)
STR = BYTE_PTR  # string = i8* (null-terminated)
SHORT = ir.IntType(16)
INT32 = ir.IntType(32)
INT64 = ir.IntType(64)
FLOAT = ir.FloatType()
BOOL = ir.IntType(1)

NONE = -1
VOID = ir.VoidType()
ZERO = ir.Constant(INT32, 0)


class AstFunctionDefination:
    def __init__(self, name, args=[], ret=INT32) -> None:
        self.name = name
        self.type = AST_FUNCTION_DEFINATION
        self.args = args
        self.code = []
        self.ret = ret

    def __str__(self) -> str:
        return self.name + ":,".join([arg for arg in self.args])

    def append(self, block):
        self.code.append(block)


class AstObjectVariableDeclaration:
    def __init__(self, name, value=None, dt=INT32) -> None:
        self.name = name
        self.type = AST_OBJECT_VARIABLE_DECLARATION
        self.val = value
        self.exp = None
        self.dt = dt
        self.is_assignment = False  # True for `x = ...` (no re-alloc)


class AstMathOps:
    def __init__(self, type) -> None:
        self.type = type


class AstSimpleExpression:
    def __init__(self) -> None:
        self.type = AST_SIMPLE_EXPRESSION
        self.operands = []


class AstConditional:
    def __init__(self) -> None:
        self.type = AST_CONDITIONAL
        self.code = []


class AstParam:
    def __init__(self, name, dt=INT32) -> None:
        self.name = name
        self.type = AST_PARAM
        self.dt = dt


class AstIF:
    def __init__(self, exp: AstSimpleExpression) -> None:
        self.type = AST_IF
        self.exp = exp
        self.code = []


class AstWhile:
    def __init__(self, exp: AstSimpleExpression) -> None:
        self.type = AST_WHILE
        self.exp = exp
        self.code = []


class AstElse:
    def __init__(self) -> None:
        self.type = AST_ELSE
        self.code = []


class AstVariableCall:
    def __init__(self, name) -> None:
        self.name = name
        self.type = AST_VARIABLE_CALL


class AstFunctionCall:
    def __init__(self, name, args=[], isNative=False) -> None:
        self.args = []
        self.name = name
        self.type = AST_FUNCTION_CALL


class AstReturn:
    def __init__(self, value=0) -> None:
        self.type = AST_RETURN
        self.value = value


class AstStringConst:
    def __init__(self, val) -> None:
        self.type = AST_STRING_CONSTANT
        self.value = val


class AstNumberConst:
    def __init__(self, val) -> None:
        self.type = AST_NUMBER_CONSTANT
        self.value = val


class AstFloatConst:
    def __init__(self, val) -> None:
        self.type = AST_FLOAT_CONSTANT
        self.value = val


class AstBoolConst:
    def __init__(self, val) -> None:
        self.type = AST_BOOL_CONSTANT
        self.value = bool(val)


class AstBlock:
    pass


RESERVED_LITERALS = ("true", "false")


def _check_not_reserved(name):
    if name in RESERVED_LITERALS:
        raise Exception(f"'{name}' is reserved (bool literal), cannot use as identifier")


def _parse_primary_after_ident(tokens, pc, name):
    """After parsing identifier `name` at use-site: call, bool literal or var."""
    if pc < len(tokens) and tokens[pc][0] == "(":
        if name in RESERVED_LITERALS:
            raise Exception(f"'{name}' is a bool literal, cannot call it")
        sub_args, pc = _parse_call_args(tokens, pc)
        fn = AstFunctionCall(name, [])
        fn.args = sub_args
        return fn, pc
    if name == "true":
        return AstBoolConst(True), pc
    if name == "false":
        return AstBoolConst(False), pc
    return AstVariableCall(name), pc


BOOL_BINOPS = ("&&", "||")
CMP_OPS = ("==", "!=", "<", "<=", ">", ">=")
ARITH_OPS = ("+", "-", "*", "/")


def _parse_expr_sym(tokens, pc, exp, expect_value):
    """Handle one SYM token inside expression parsing.
    Appends to exp.operands. Returns (new_pc, new_expect_value)."""
    t = tokens[pc][0]
    if t in ("+", "-") and expect_value:
        # Unary: fold into next number if possible else 0 +/- x
        if pc + 1 < len(tokens) and tokens[pc + 1][1] in ("NUM", "FLOAT"):
            nt, nk = tokens[pc + 1][0], tokens[pc + 1][1]
            if nk == "NUM":
                exp.operands.append(AstNumberConst(("-" if t == "-" else "") + nt))
            else:
                exp.operands.append(AstFloatConst(("-" if t == "-" else "") + nt))
            return pc + 2, False
        exp.operands.append(AstNumberConst("0"))
        exp.operands.append(t)
        return pc + 1, True
    if t == "!":
        if not expect_value:
            raise Exception("Unexpected '!' (did you mean '!='?)")
        exp.operands.append("!")
        return pc + 1, True
    if t in BOOL_BINOPS or t in CMP_OPS or t in ARITH_OPS:
        if expect_value:
            raise Exception(f"Unexpected operator '{t}' (missing left operand)")
        exp.operands.append(t)
        return pc + 1, True
    if t == "=":
        raise Exception("Did you mean '==' for comparison? '=' is assignment")
    if t in ("&", "|"):
        raise Exception(f"Did you mean '{t}{t}'?")
    raise Exception(f"Unexpected token '{t}' in expression")


def _peek(tokens, pc):
    return tokens[pc] if 0 <= pc < len(tokens) else ("", "")


def _parse_ident(tokens, pc):
    """Parse identifier, supporting both new single-token (a1, my_var)
    and legacy split TEXT+NUM (a + 1) forms. Returns (name, new_pc)."""
    if pc >= len(tokens):
        raise Exception("Unexpected end of input, expected identifier")
    name = tokens[pc][0]
    pc += 1
    # Legacy: TEXT followed immediately by NUM was one identifier (e.g. a1)
    if pc < len(tokens) and tokens[pc][1] == "NUM":
        # Only join if original name doesn't already end with digit
        # (new lexer already includes digits). Joining "a"+"1" is safe;
        # joining "float"+"32" is handled by type parser, not here.
        # Heuristic: join when previous token was pure TEXT without digits.
        if name and not any(ch.isdigit() for ch in name):
            # Peek further: if after NUM comes identifier chars, it was split;
            # with new lexer this branch rarely triggers.
            name += tokens[pc][0]
            pc += 1
    return name, pc


def _parse_type(tokens, pc):
    """Parse a type annotation. Returns (llvm_type, type_name, new_pc).
    Supports i32/number, float32/float, str/string, bool. Handles both
    single-token and legacy split forms."""
    if pc >= len(tokens):
        raise Exception("Unexpected end of input, expected type")
    # Single token forms (new lexer)
    t0 = tokens[pc][0]
    if t0 in ("i32", "number"):
        return INT32, "i32", pc + 1
    if t0 in ("float32", "float"):
        return FLOAT, "float32", pc + 1
    if t0 in ("str", "string"):
        return STR, "str", pc + 1
    if t0 == "bool":
        return BOOL, "bool", pc + 1
    # Legacy split: TEXT("i"/"float") + NUM("32")
    if pc + 1 < len(tokens):
        combined = tokens[pc][0] + tokens[pc + 1][0]
        if combined == "i32":
            return INT32, "i32", pc + 2
        if combined == "float32":
            return FLOAT, "float32", pc + 2
    raise Exception(f"Unknown type '{t0}', expected i32, float32, str or bool")


def _parse_string_literal(tokens, pc):
    """pc at opening quote. Returns (AstStringConst, new_pc past closing quote)."""
    assert tokens[pc][0] == '"'
    pc += 1
    s = ""
    while pc < len(tokens) and tokens[pc][0] != '"':
        s += tokens[pc][0]
        pc += 1
    if pc >= len(tokens):
        raise Exception("Unterminated string literal")
    return AstStringConst(s), pc + 1


def _parse_condition_operands(tokens, pc, stop="{"):
    """Parse a full boolean condition until stop token (e.g. `a > b`,
    `flag`, `!done`, `a && b || c == d`, `isEven(n)`).
    Returns (AstSimpleExpression, new_pc pointing at stop)."""
    exp = AstSimpleExpression()
    expect_value = True
    while pc < len(tokens) and tokens[pc][0] != stop:
        t, k = tokens[pc][0], tokens[pc][1]
        if t == "(" or t == ")":
            exp.operands.append(t)
            pc += 1
            expect_value = t == "("
        elif t == '"':
            sc, pc = _parse_string_literal(tokens, pc)
            exp.operands.append(sc)
            expect_value = False
        elif k == "TEXT":
            name, pc = _parse_ident(tokens, pc)
            node, pc = _parse_primary_after_ident(tokens, pc, name)
            exp.operands.append(node)
            expect_value = False
        elif k == "NUM":
            exp.operands.append(AstNumberConst(t))
            pc += 1
            expect_value = False
        elif k == "FLOAT":
            exp.operands.append(AstFloatConst(t))
            pc += 1
            expect_value = False
        elif k == "SYM":
            pc, expect_value = _parse_expr_sym(tokens, pc, exp, expect_value)
        else:
            raise Exception("Error Invalid token:" + t + " in condition")
    if pc >= len(tokens):
        raise Exception(f"Unterminated condition, expected '{stop}'")
    if not exp.operands:
        raise Exception("Empty condition")
    return exp, pc


def ParseWhile(tokens, pc):

    exp = AstSimpleExpression()
    val = None
    if pc < len(tokens) and tokens[pc][0] == "while":
        pc += 1
        exp, pc = _parse_condition_operands(tokens, pc, stop="{")
        fd = AstWhile(exp)
        pc += 1  # skip '{'

        while pc < len(tokens) and tokens[pc][0] != "}":
            if tokens[pc][0] == "\n" or tokens[pc][0] == ";":
                pc += 1
                continue
            obj = ParseLine(tokens, pc)
            pc = obj[1]
            fd.code.append(obj[0])
            pc += 1
        if pc >= len(tokens):
            raise Exception("Unterminated while block, expected '}'")
        val = fd
        return val, pc


def ParseCondition(tokens, pc):
    exp = AstSimpleExpression()
    val = AstConditional()
    if pc >= len(tokens):
        return val, pc
    # Note: original had `while tokens[pc][0] != " }"` (with space) which
    # never matched; keep single-if behaviour but with bounds checks.
    if pc < len(tokens) and tokens[pc][0] == "if":
        pc += 1
        exp, pc = _parse_condition_operands(tokens, pc, stop="{")
        fd = AstIF(exp)
        pc += 1  # skip '{'
        while pc < len(tokens) and tokens[pc][0] != "}":
            if tokens[pc][0] == "\n" or tokens[pc][0] == ";":
                pc += 1
                continue
            obj = ParseLine(tokens, pc)
            pc = obj[1]
            fd.code.append(obj[0])
            pc += 1
        if pc >= len(tokens):
            raise Exception("Unterminated if block, expected '}'")
        val.code.append(fd)
        pc += 1
        while pc < len(tokens) and tokens[pc][0] == "\n":
            pc += 1
        if pc < len(tokens) and tokens[pc][0] == "else":
            pc += 1
            # skip optional '{' check with error
            if pc >= len(tokens) or tokens[pc][0] != "{":
                raise Exception("Expected '{' after else")
            pc += 1
            fd = AstElse()
            while pc < len(tokens) and tokens[pc][0] != "}":
                if tokens[pc][0] == "\n" or tokens[pc][0] == ";":
                    pc += 1
                    continue
                obj = ParseLine(tokens, pc)
                pc = obj[1]
                fd.code.append(obj[0])
                pc += 1
            if pc >= len(tokens):
                raise Exception("Unterminated else block, expected '}'")
            val.code.append(fd)
        else:
            pc -= 1
        return val, pc


def _parse_call_args(tokens, pc):
    """Parse '(' args ')' starting at pc pointing at '('.
    Each arg is a full expression (var, const, string, call, a+1, f(x)-2...).
    Returns (args, new_pc past ')'). Simple args stay as single nodes for
    backwards compat; complex ones become AstSimpleExpression."""
    assert tokens[pc][0] == "("
    pc += 1
    args = []
    # skip whitespace/newlines
    while pc < len(tokens) and tokens[pc][0] in ("\n", ";"):
        pc += 1
    # empty args: ()
    if pc < len(tokens) and tokens[pc][0] == ")":
        return [], pc + 1
    while True:
        while pc < len(tokens) and tokens[pc][0] in ("\n", ";"):
            pc += 1
        if pc >= len(tokens):
            raise Exception("Unterminated call, expected ')'")
        if tokens[pc][0] == ")":
            pc += 1
            break
        # String literal arg (print("hi")): must be standalone
        if tokens[pc][0] == '"':
            pc += 1
            s = ""
            while pc < len(tokens) and tokens[pc][0] != '"':
                s += tokens[pc][0]
                pc += 1
            if pc >= len(tokens):
                raise Exception("Unterminated string literal in call args")
            pc += 1  # skip closing quote
            args.append(AstStringConst(s))
        else:
            # General expression arg until ',' or ')' at depth 0
            exp = AstSimpleExpression()
            expect_value = True
            depth = 0
            while pc < len(tokens):
                t, k = tokens[pc][0], tokens[pc][1]
                if t == "(":
                    exp.operands.append(t)
                    depth += 1
                    pc += 1
                    expect_value = True
                elif t == ")":
                    if depth == 0:
                        break  # end of this arg, don't consume
                    exp.operands.append(t)
                    depth -= 1
                    pc += 1
                    expect_value = False
                elif t == "," and depth == 0:
                    break  # next arg, don't consume
                elif t == ",":
                    # comma inside grouping parens shouldn't happen; treat as error
                    raise Exception("Unexpected ',' in expression")
                elif t == '"':
                    sc, pc = _parse_string_literal(tokens, pc)
                    exp.operands.append(sc)
                    expect_value = False
                elif k == "TEXT":
                    name, pc = _parse_ident(tokens, pc)
                    node, pc = _parse_primary_after_ident(tokens, pc, name)
                    exp.operands.append(node)
                    expect_value = False
                elif k == "NUM":
                    exp.operands.append(AstNumberConst(t))
                    pc += 1
                    expect_value = False
                elif k == "FLOAT":
                    exp.operands.append(AstFloatConst(t))
                    pc += 1
                    expect_value = False
                elif k == "SYM":
                    pc, expect_value = _parse_expr_sym(tokens, pc, exp, expect_value)
                elif t in ("\n", ";"):
                    raise Exception("Unterminated call argument, expected ',' or ')'")
                else:
                    raise Exception(f"Unexpected token '{t}' in call arguments")
            if not exp.operands:
                raise Exception("Empty call argument")
            if depth != 0:
                raise Exception("Mismatched parenthesis in call argument")
            # Unwrap single-value args for backwards compat
            if len(exp.operands) == 1 and not isinstance(exp.operands[0], str):
                args.append(exp.operands[0])
            else:
                args.append(exp)
        # after arg: expect ',' or ')'
        while pc < len(tokens) and tokens[pc][0] in ("\n", ";"):
            pc += 1
        if pc >= len(tokens):
            raise Exception("Unterminated call, expected ',' or ')'")
        if tokens[pc][0] == ",":
            pc += 1
            continue
        elif tokens[pc][0] == ")":
            pc += 1
            break
        else:
            raise Exception(f"Expected ',' or ')' in call, found '{tokens[pc][0]}'")
    return args, pc


def _parse_expr_operands(tokens, pc):
    """Parse expression until ';' or newline. Keeps parens and operators
    for precedence-aware codegen. Returns (exp, pc at terminator)."""
    exp = AstSimpleExpression()
    expect_value = True  # for unary +/- detection
    while pc < len(tokens) and tokens[pc][0] != ";" and tokens[pc][0] != "\n":
        t, k = tokens[pc][0], tokens[pc][1]
        if t == "(" or t == ")":
            exp.operands.append(t)
            pc += 1
            expect_value = t == "("
        elif t == '"':
            sc, pc = _parse_string_literal(tokens, pc)
            exp.operands.append(sc)
            expect_value = False
        elif k == "TEXT":
            name, pc = _parse_ident(tokens, pc)
            node, pc = _parse_primary_after_ident(tokens, pc, name)
            exp.operands.append(node)
            expect_value = False
        elif k == "FLOAT":
            exp.operands.append(AstFloatConst(t))
            pc += 1
            expect_value = False
        elif k == "NUM":
            exp.operands.append(AstNumberConst(t))
            pc += 1
            expect_value = False
        elif k == "SYM":
            pc, expect_value = _parse_expr_sym(tokens, pc, exp, expect_value)
        else:
            raise Exception(
                "Error Invalid token:" + t + " Expected a variable or a number"
            )
    if not exp.operands:
        raise Exception("Empty expression")
    return exp, pc


def ParseLine(tokens, pc):
    if pc >= len(tokens):
        raise Exception("Unexpected end of input in statement")
    obj = None
    # Skip stray separators
    while pc < len(tokens) and (tokens[pc][0] == ";" or tokens[pc][0] == "\n"):
        pc += 1
    if pc >= len(tokens):
        return (None, pc)
    # if / while dispatch
    if tokens[pc][1] == "KEYWORD" and tokens[pc][0] == "if":
        return ParseCondition(tokens, pc)
    if tokens[pc][1] == "KEYWORD" and tokens[pc][0] == "while":
        return ParseWhile(tokens, pc)

    # Use bounded loop instead of `while token != ;` to avoid IndexError
    # and infinite loops on unexpected tokens.
    start_pc = pc
    while pc < len(tokens) and tokens[pc][0] != ";" and tokens[pc][0] != "\n":
        t, k = tokens[pc][0], tokens[pc][1]
        if k == "TEXT":
            name, npc = _parse_ident(tokens, pc)
            pc = npc
            if pc < len(tokens) and tokens[pc][0] == "(":
                args, pc = _parse_call_args(tokens, pc)
                fc = AstFunctionCall(name)
                fc.args = args
                obj = fc
                # allow trailing tokens? break to terminator check
                # skip to end of statement
                while pc < len(tokens) and tokens[pc][0] not in (";", "\n"):
                    if tokens[pc][0] == ",":
                        pc += 1
                        continue
                    # Unexpected trailing token
                    raise Exception(
                        f"Unexpected token '{tokens[pc][0]}' after call"
                    )
                break
            elif pc < len(tokens) and tokens[pc][0] == "=":
                # Plain assignment:  x = expr;
                pc += 1  # skip '='
                # '==' is comparison, not assignment
                if pc < len(tokens) and tokens[pc][0] == "=":
                    raise Exception("Did you mean '==' for comparison? '=' is assignment")
                exp, pc = _parse_expr_operands(tokens, pc)
                fd = AstObjectVariableDeclaration(name)
                fd.val = exp
                # dt unknown until codegen; leave default, codegen reuses existing alloca
                fd.is_assignment = True
                obj = fd
                break
            else:
                raise Exception(f"Unexpected identifier '{name}', expected '(' or '='")
        elif k == "KEYWORD":
            if t == "let":
                pc += 1
                if pc >= len(tokens) or tokens[pc][1] != "TEXT":
                    raise Exception("Expected variable name after 'let'")
                name, pc = _parse_ident(tokens, pc)
                _check_not_reserved(name)
                if pc >= len(tokens) or tokens[pc][0] != ":":
                    raise Exception(f"Expected ':' after variable '{name}'")
                pc += 1
                llvm_ty, type_, pc = _parse_type(tokens, pc)
                fd = AstObjectVariableDeclaration(name)
                fd.dt = llvm_ty
                if pc >= len(tokens) or tokens[pc][0] not in ("=", ";", "\n"):
                    raise Exception(f"Expected '=' or end after type '{type_}'")
                if pc < len(tokens) and tokens[pc][0] == "=":
                    pc += 1
                    exp, pc = _parse_expr_operands(tokens, pc)
                    fd.val = exp
                else:
                    # Declaration without init: type-appropriate zero value
                    e = AstSimpleExpression()
                    if type_ == "bool":
                        e.operands.append(AstBoolConst(False))
                    elif type_ == "str":
                        e.operands.append(AstStringConst(""))
                    else:
                        e.operands.append(AstNumberConst("0"))
                    fd.val = e
                obj = fd
                break

            elif t == "if":
                return ParseCondition(tokens, pc)
            elif t == "while":
                return ParseWhile(tokens, pc)
            elif t == "return":
                obj = AstReturn()
                pc += 1
                if pc < len(tokens) and tokens[pc][0] not in (";", "\n", "}"):
                    # Full expression: var, const, string, call, a+b, f(x)*2, ...
                    # (type checked in codegen against function return type)
                    exp, pc = _parse_expr_operands(tokens, pc)
                    if len(exp.operands) == 1 and not isinstance(
                        exp.operands[0], str
                    ):
                        obj.value = exp.operands[0]
                    else:
                        obj.value = exp
                else:
                    obj.value = AstNumberConst("0")
                return (obj, pc)
            else:
                raise Exception(f"Unsupported keyword '{t}' here")

        else:
            raise Exception(f"Unexpected token '{t}' at statement start")

    if obj is None and pc == start_pc:
        raise Exception(f"Could not parse statement at token '{tokens[pc][0]}'")
    return (obj, pc)


def ParseFunctionDefination(tokens, pc):

    name = ""
    obj = None
    if pc >= len(tokens):
        raise Exception("Unexpected end, expected 'function'")
    if tokens[pc][0] == "function":
        pc += 1
        if pc >= len(tokens):
            raise Exception("Unexpected end after 'function'")
        if tokens[pc][1] == "TEXT":
            name, pc = _parse_ident(tokens, pc)
            _check_not_reserved(name)
        else:
            raise Exception(f"Expected Function name but found: {tokens[pc][0]}")

        if pc >= len(tokens) or tokens[pc][0] != "(":
            raise Exception("Expected '(' after function name")

        args = []
        pc += 1
        while pc < len(tokens) and tokens[pc][0] != ")":
            if tokens[pc][0] == "," or tokens[pc][0] == "\n":
                pc += 1
                continue
            if tokens[pc][1] == "TEXT":
                pname, pc = _parse_ident(tokens, pc)
                _check_not_reserved(pname)
                # Optional `: type` for params (e.g. s: str). Default i32.
                pdt = INT32
                if pc < len(tokens) and tokens[pc][0] == ":":
                    pc += 1
                    pdt, _, pc = _parse_type(tokens, pc)
                args.append(AstParam(pname, pdt))
            else:
                raise Exception(
                    f"Expected param name but found: {tokens[pc][0]}"
                )
        if pc >= len(tokens):
            raise Exception("Unterminated parameter list, expected ')'")
        pc += 1  # skip ')'

        # Optional return-type annotation `: type` (e.g. `: str`, `: i32`).
        # Default i32 for backwards compat (`: number` also i32).
        ret_ty = INT32
        if pc < len(tokens) and tokens[pc][0] == ":":
            pc += 1
            try:
                ret_ty, _, pc = _parse_type(tokens, pc)
            except Exception:
                # Unknown annotation (e.g. `: number` handled, others skip)
                # `number` is i32; anything else stays i32 for compat.
                while pc < len(tokens) and tokens[pc][0] not in ("{", "\n"):
                    pc += 1
        # Skip anything else until '{'
        while pc < len(tokens) and tokens[pc][0] != "{":
            pc += 1
        if pc >= len(tokens):
            raise Exception(f"Unterminated function '{name}', expected '{{'")
        fd = AstFunctionDefination(name, args, ret_ty)
        pc += 1  # skip '{'
        while pc < len(tokens) and tokens[pc][0] != "}":
            if tokens[pc][0] == "\n" or tokens[pc][0] == ";":
                pc += 1
                continue
            obj = ParseLine(tokens, pc)
            if obj[0] is not None:
                fd.append(obj[0])
            pc = obj[1]
            pc += 1
        if pc >= len(tokens):
            raise Exception(f"Unterminated function '{name}', expected '}}'")
        obj = fd

    pc += 1
    return pc, obj


def ParseToAst(tokens):
    pc = 0
    program = []
    while pc < len(tokens):
        if tokens[pc][0] == "\n" or tokens[pc][0] == ";":
            pc += 1
            continue
        if tokens[pc][0] != "function":
            raise Exception(
                f"Top-level only supports function definitions, found '{tokens[pc][0]}'"
            )
        obj = ParseFunctionDefination(tokens, pc)
        if obj[1] is not None:
            program.append(obj[1])
        pc = obj[0]
    if not program:
        raise Exception("Empty program: no functions found")
    return program


tokens = tokenise(src)
try:
    ast = ParseToAst(tokens)
except Exception as e:
    print(f"Parse error in '{src_path}': {e}", file=sys.stderr)
    sys.exit(1)


# --- codegen helpers -------------------------------------------------
_str_cache = {}
_str_counter = [0]


def _get_string_ptr(builder, module, s, suffix="\n\0"):
    key = (s, suffix)
    if key in _str_cache:
        gv = _str_cache[key]
        return builder.gep(gv, [ZERO, ZERO], inbounds=True)
    msg = s + suffix
    msg_ty = ir.ArrayType(BYTE, len(msg))
    gv = ir.GlobalVariable(module, msg_ty, name=f"str_const_{_str_counter[0]}")
    _str_counter[0] += 1
    gv.linkage = "internal"
    gv.global_constant = True
    gv.initializer = ir.Constant(msg_ty, bytearray(msg.encode("utf8")))
    _str_cache[key] = gv
    return builder.gep(gv, [ZERO, ZERO], inbounds=True)


def _is_float_val(v):
    try:
        return isinstance(v.type, (ir.FloatType, ir.DoubleType))
    except Exception:
        return False


def _is_float_alloca(alloca):
    try:
        pt = alloca.type
        # llvmlite pointer type has .pointee
        base = getattr(pt, "pointee", None)
        return isinstance(base, (ir.FloatType, ir.DoubleType))
    except Exception:
        return False


def _is_str_val(v):
    try:
        t = v.type
        if isinstance(t, ir.PointerType):
            base = getattr(t, "pointee", None)
            return isinstance(base, ir.IntType) and base.width == 8
        return False
    except Exception:
        return False


def _is_str_alloca(alloca):
    try:
        pt = alloca.type
        base = getattr(pt, "pointee", None)  # alloca type is ptr to (i8*)
        if isinstance(base, ir.PointerType):
            inner = getattr(base, "pointee", None)
            return isinstance(inner, ir.IntType) and inner.width == 8
        return False
    except Exception:
        return False


def _is_bool_val(v):
    try:
        t = v.type
        return isinstance(t, ir.IntType) and t.width == 1
    except Exception:
        return False


def _is_bool_alloca(alloca):
    try:
        base = getattr(alloca.type, "pointee", None)
        return isinstance(base, ir.IntType) and base.width == 1
    except Exception:
        return False


def _to_bool(builder, v):
    """Convert any value to i1 (C-like truthiness for numbers)."""
    if _is_bool_val(v):
        return v
    if _is_str_val(v):
        raise Exception("Cannot use str as bool, use explicit comparison (==, !=, ...)")
    if _is_float_val(v):
        return builder.fcmp_ordered("!=", v, ir.Constant(FLOAT, 0.0), name="tobool")
    return builder.icmp_signed("!=", v, ir.Constant(v.type, 0), name="tobool")


def _bool_not(builder, v):
    return builder.xor(v, ir.Constant(BOOL, True), name="temp")


def _compare_values(builder, cmpop, lhs, rhs):
    """Emit lhs <cmpop> rhs returning i1. Handles str/float/bool/int."""
    if _is_str_val(lhs) or _is_str_val(rhs):
        if not (_is_str_val(lhs) and _is_str_val(rhs)):
            raise Exception("Cannot compare string with non-string value")
        strcmp_fn = std.get("strcmp")
        if strcmp_fn is None:
            raise Exception("String comparison needs strcmp")
        cmp = builder.call(strcmp_fn, [lhs, rhs], name="strcmp")
        return builder.icmp_signed(cmpop, cmp, ir.Constant(INT32, 0), name="temp")
    if _is_float_val(lhs) or _is_float_val(rhs):
        if _is_bool_val(lhs):
            lhs = builder.zext(lhs, INT32, name="bool2int")
        if _is_bool_val(rhs):
            rhs = builder.zext(rhs, INT32, name="bool2int")
        if not _is_float_val(lhs):
            lhs = builder.sitofp(lhs, FLOAT, name="sitofp")
        if not _is_float_val(rhs):
            rhs = builder.sitofp(rhs, FLOAT, name="sitofp")
        return builder.fcmp_ordered(cmpop, lhs, rhs, name="temp")
    if _is_bool_val(lhs) or _is_bool_val(rhs):
        if _is_bool_val(lhs) and _is_bool_val(rhs):
            if cmpop not in ("==", "!="):
                raise Exception(
                    f"Operator '{cmpop}' not supported for bool (use == or !=)"
                )
            return builder.icmp_signed(cmpop, lhs, rhs, name="temp")
        if _is_bool_val(lhs):
            lhs = builder.zext(lhs, INT32, name="bool2int")
        if _is_bool_val(rhs):
            rhs = builder.zext(rhs, INT32, name="bool2int")
        return builder.icmp_signed(cmpop, lhs, rhs, name="temp")
    return builder.icmp_signed(cmpop, lhs, rhs, name="temp")


def _str_concat(builder, module, lhs, rhs):
    """Emit lhs + rhs for strings via malloc+strcpy+strcat. Returns i8*."""
    strlen_fn = std.get("strlen")
    strcpy_fn = std.get("strcpy")
    strcat_fn = std.get("strcat")
    malloc_fn = std.get("malloc")
    if None in (strlen_fn, strcpy_fn, strcat_fn, malloc_fn):
        raise Exception("String concat needs strlen/strcpy/strcat/malloc")
    len1 = builder.call(strlen_fn, [lhs], name="len1")
    len2 = builder.call(strlen_fn, [rhs], name="len2")
    total = builder.add(len1, len2, name="total")
    total1 = builder.add(total, ir.Constant(INT32, 1), name="total1")
    total64 = builder.zext(total1, INT64, name="total64")
    buf = builder.call(malloc_fn, [total64], name="buf")
    builder.call(strcpy_fn, [buf, lhs])
    builder.call(strcat_fn, [buf, rhs])
    return buf


def _binop(builder, op, lhs, rhs):
    """Emit lhs op rhs with int/float promotion, plus string '+' concat."""
    if _is_str_val(lhs) or _is_str_val(rhs):
        if op != "+":
            raise Exception(f"Operator '{op}' not supported for strings (only '+' concat)")
        if not (_is_str_val(lhs) and _is_str_val(rhs)):
            raise Exception("Cannot mix string and numeric with '+'")
        return _str_concat(builder, None, lhs, rhs)
    # bools promote to int in arithmetic (C-like)
    if _is_bool_val(lhs):
        lhs = builder.zext(lhs, INT32, name="bool2int")
    if _is_bool_val(rhs):
        rhs = builder.zext(rhs, INT32, name="bool2int")
    lf, rf = _is_float_val(lhs), _is_float_val(rhs)
    if lf or rf:
        if not lf:
            lhs = builder.sitofp(lhs, FLOAT, name="sitofp")
        if not rf:
            rhs = builder.sitofp(rhs, FLOAT, name="sitofp")
        if op == "+":
            return builder.fadd(lhs, rhs, name="temp")
        elif op == "-":
            return builder.fsub(lhs, rhs, name="temp")
        elif op == "*":
            return builder.fmul(lhs, rhs, name="temp")
        elif op == "/":
            return builder.fdiv(lhs, rhs, name="temp")
        raise Exception(f"Unknown operator '{op}'")
    else:
        if op == "+":
            return builder.add(lhs, rhs, name="temp")
        elif op == "-":
            return builder.sub(lhs, rhs, name="temp")
        elif op == "*":
            return builder.mul(lhs, rhs, name="temp")
        elif op == "/":
            return builder.sdiv(lhs, rhs, name="temp")
        raise Exception(f"Unknown operator '{op}'")


def _emit_condition(builder, module, obj, operands):
    """Evaluate a full boolean condition to i1 (truthiness for numbers)."""
    exp = AstSimpleExpression()
    exp.operands = list(operands)
    v = _eval_expr_value(builder, module, obj, exp)
    return _to_bool(builder, v)


def _eval_expr_value(builder, module, obj, exp):
    """Evaluate an expression (AstSimpleExpression or single node) to an LLVM value."""
    # Single leaf node fast path
    if not isinstance(exp, AstSimpleExpression):
        return _resolve_expr_value(builder, module, obj, exp)
    if len(exp.operands) == 1 and not isinstance(exp.operands[0], str):
        return _resolve_expr_value(builder, module, obj, exp.operands[0])
    rpn = _to_rpn(exp.operands)
    stack = []
    for tok in rpn:
        if tok == "!":
            if len(stack) < 1:
                raise Exception("Invalid expression: not enough operands for '!'")
            v = stack.pop()
            stack.append(_bool_not(builder, _to_bool(builder, v)))
        elif isinstance(tok, str) and tok in ("&&", "||"):
            if len(stack) < 2:
                raise Exception(f"Invalid expression: not enough operands for '{tok}'")
            rhs = _to_bool(builder, stack.pop())
            lhs = _to_bool(builder, stack.pop())
            if tok == "&&":
                stack.append(builder.and_(lhs, rhs, name="temp"))
            else:
                stack.append(builder.or_(lhs, rhs, name="temp"))
        elif isinstance(tok, str) and tok in (
            "==",
            "!=",
            "<",
            "<=",
            ">",
            ">=",
        ):
            if len(stack) < 2:
                raise Exception(f"Invalid expression: not enough operands for '{tok}'")
            rhs = stack.pop()
            lhs = stack.pop()
            stack.append(_compare_values(builder, tok, lhs, rhs))
        elif isinstance(tok, str) and tok in ("+", "-", "*", "/"):
            if len(stack) < 2:
                raise Exception(f"Invalid expression: not enough operands for '{tok}'")
            rhs = stack.pop()
            lhs = stack.pop()
            stack.append(_binop(builder, tok, lhs, rhs))
        else:
            stack.append(_resolve_expr_value(builder, module, obj, tok))
    if len(stack) != 1:
        raise Exception("Invalid expression: leftover operands")
    return stack[0]


def _emit_call_value(builder, module, obj, fn_name, fn_args, result_name="result"):
    """Emit call to user/C fn; returns LLVM value. Raises on unknown fn.
    Args may be single nodes or full AstSimpleExpression (a+1, f(x))."""
    # malloc takes i64; zext i1/i32 sizes (bool ok: true -> 1)
    if fn_name == "alloc" and len(fn_args) == 1:
        a = fn_args[0]
        n = (
            _eval_expr_value(builder, module, obj, a)
            if isinstance(a, AstSimpleExpression)
            else _resolve_expr_value(builder, module, obj, a)
            if getattr(a, "type", None) != AST_STRING_CONSTANT
            else None
        )
        if n is None:
            raise Exception("alloc() needs an integer size")
        if _is_str_val(n):
            raise Exception("alloc() needs an integer size, got string")
        if _is_bool_val(n):
            n = builder.zext(n, INT32, name="alloc_i")
        if _is_float_val(n):
            n = builder.fptosi(n, INT32, name="alloc_i")
        n64 = builder.zext(n, INT64, name="alloc64")
        return builder.call(std["malloc"], [n64], name=result_name)
    if fn_name not in std:
        raise Exception(f"Call to undefined function '{fn_name}'")
    args = []
    for arg in fn_args:
        if isinstance(arg, AstSimpleExpression):
            args.append(_eval_expr_value(builder, module, obj, arg))
        elif getattr(arg, "type", None) == AST_STRING_CONSTANT:
            args.append(_get_string_ptr(builder, module, arg.value, suffix="\0"))
        elif getattr(arg, "type", None) == AST_NUMBER_CONSTANT:
            args.append(ir.Constant(INT32, int(float(arg.value))))
        elif getattr(arg, "type", None) == AST_FLOAT_CONSTANT:
            args.append(ir.Constant(FLOAT, float(arg.value)))
        elif getattr(arg, "type", None) == AST_BOOL_CONSTANT:
            args.append(ir.Constant(BOOL, arg.value))
        elif getattr(arg, "type", None) == AST_VARIABLE_CALL:
            if arg.name not in obj:
                raise Exception(f"Undefined variable '{arg.name}' in call")
            args.append(builder.load(obj[arg.name], name=arg.name + "_val"))
        elif getattr(arg, "type", None) == AST_FUNCTION_CALL:
            args.append(_emit_call_value(builder, module, obj, arg.name, arg.args))
        else:
            raise Exception(f"Unsupported call argument {arg}")
    callee = std[fn_name]
    # Arity check
    try:
        expected = len(callee.args) if hasattr(callee, "args") else None
    except Exception:
        expected = None
    # llvmlite Function.args is tuple of args; use function type instead
    try:
        n_expected = len(callee.function_type.args) if hasattr(callee, "function_type") else None
        if n_expected is not None and len(args) != n_expected:
            raise Exception(
                f"Function '{fn_name}' expects {n_expected} args, got {len(args)}"
            )
    except Exception as e:
        if "expects" in str(e):
            raise
    # Auto-convert to callee param types; strings must match.
    try:
        ptypes = list(callee.function_type.args)
        conv = []
        for v, pt in zip(args, ptypes):
            if isinstance(pt, ir.PointerType):
                if not _is_str_val(v):
                    raise Exception(
                        f"Function '{fn_name}' expects str, got numeric"
                    )
                conv.append(v)
            elif isinstance(pt, ir.IntType) and pt.width == 1:
                # bool param: truthiness conversion
                if _is_str_val(v):
                    raise Exception(
                        f"Function '{fn_name}' expects bool, got str"
                    )
                conv.append(v if _is_bool_val(v) else _to_bool(builder, v))
            elif isinstance(pt, (ir.FloatType, ir.DoubleType)):
                if _is_str_val(v):
                    raise Exception(
                        f"Function '{fn_name}' expects float, got str"
                    )
                if _is_bool_val(v):
                    conv.append(builder.uitofp(v, FLOAT, name="bool2fp"))
                else:
                    conv.append(v if _is_float_val(v) else builder.sitofp(v, FLOAT))
            else:  # int param
                if _is_str_val(v):
                    raise Exception(
                        f"Function '{fn_name}' expects int, got str"
                    )
                if _is_bool_val(v):
                    conv.append(builder.zext(v, INT32, name="bool2int"))
                else:
                    conv.append(v if not _is_float_val(v) else builder.fptosi(v, INT32))
        args = conv
    except Exception as e:
        if "expects" in str(e) or "bool" in str(e):
            raise
    return builder.call(callee, args, name=result_name)


def evalWhile(obj, builder, module, fn, ast: AstWhile):
    cond_block = fn.append_basic_block("cond")
    body_block = fn.append_basic_block("body")
    if builder.block.is_terminated:
        # Unreachable while after return; create dead entry
        builder = ir.IRBuilder(fn.append_basic_block("dead"))
    else:
        builder.branch(cond_block)

    # cond block
    builder = ir.IRBuilder(cond_block)
    cond = _emit_condition(builder, module, obj, ast.exp.operands)

    end_block = fn.append_basic_block("end")
    builder.cbranch(cond, body_block, end_block)

    # body block
    builder = ir.IRBuilder(body_block)
    builder = evalFunction(builder, module, ast.code, fn, obj)
    if not builder.block.is_terminated:
        builder.branch(cond_block)

    # end block (while exit)
    builder = ir.IRBuilder(end_block)
    return builder


def evalConditional(obj, builder, module, fn, ast: AstConditional):
    blocks = []
    for x in range(len(ast.code)):
        blocks.append(fn.append_basic_block("then"))
    end_block = fn.append_basic_block("end")
    for i, x in enumerate(ast.code):
        if x.type == AST_IF:
            opr = x.exp.operands
            # Emit condition in current builder (entry or previous end)
            if builder.block.is_terminated:
                builder = ir.IRBuilder(fn.append_basic_block("dead_cond"))
            cond = _emit_condition(builder, module, obj, opr)
            if len(ast.code) == 2:
                builder.cbranch(cond, blocks[i], blocks[i + 1])
            else:
                builder.cbranch(cond, blocks[i], end_block)
            builder = ir.IRBuilder(blocks[i])
            builder = evalFunction(builder, module, x.code, fn, obj)
            if not builder.block.is_terminated:
                builder.branch(end_block)
        elif x.type == AST_ELSE:
            builder = ir.IRBuilder(blocks[i])
            builder = evalFunction(builder, module, x.code, fn, obj)
            if not builder.block.is_terminated:
                builder.branch(end_block)
    builder = ir.IRBuilder(end_block)
    return builder


def evalFunction(builder, module, code, fn, obj_={}):
    obj = obj_
    val_pool = []
    for x in code:
        if x is None:
            continue
        # Dead code after return in same block: start fresh unreachable block
        if builder.block.is_terminated:
            builder = ir.IRBuilder(fn.append_basic_block("dead"))
        if x.type == AST_FUNCTION_CALL:
            if x.name == "print" or x.name == "printf":
                for arg in x.args:
                    if getattr(arg, "type", None) == AST_STRING_CONSTANT:
                        ptr = _get_string_ptr(builder, module, arg.value, "\n\0")
                        builder.call(std["print"], [ptr])
                    elif getattr(arg, "type", None) in (
                        AST_NUMBER_CONSTANT,
                        AST_FLOAT_CONSTANT,
                    ):
                        ptr = _get_string_ptr(builder, module, arg.value, "\n\0")
                        builder.call(std["print"], [ptr])
                    else:
                        # var, call, or full expression: print(add(2,3)), print(a+1)
                        if isinstance(arg, AstSimpleExpression):
                            v = _eval_expr_value(builder, module, obj, arg)
                            is_s = _is_str_val(v)
                            is_b = _is_bool_val(v)
                            is_f = _is_float_val(v)
                        elif getattr(arg, "type", None) == AST_VARIABLE_CALL:
                            if arg.name not in obj:
                                raise Exception(
                                    f"Undefined variable '{arg.name}' in print"
                                )
                            alloca = obj[arg.name]
                            v = builder.load(alloca, name=arg.name + "_val")
                            is_s = _is_str_val(v) or _is_str_alloca(alloca)
                            is_b = _is_bool_val(v) or _is_bool_alloca(alloca)
                            is_f = _is_float_val(v) or _is_float_alloca(alloca)
                        elif getattr(arg, "type", None) == AST_FUNCTION_CALL:
                            v = _emit_call_value(
                                builder, module, obj, arg.name, arg.args
                            )
                            is_s = _is_str_val(v)
                            is_b = _is_bool_val(v)
                            is_f = _is_float_val(v)
                        elif getattr(arg, "type", None) == AST_BOOL_CONSTANT:
                            v = ir.Constant(BOOL, arg.value)
                            is_s, is_b, is_f = False, True, False
                        else:
                            raise Exception(f"Unsupported print argument {arg}")
                        if is_s:
                            # strings print directly (already \n-terminated? add \n)
                            # v is i8*; if it came from a var it has no trailing
                            # newline, so print with "%s\n" format.
                            fmt_ptr = builder.gep(
                                std["str_fmt_var"], [ZERO, ZERO], inbounds=True
                            )
                            builder.call(std["print"], [fmt_ptr, v])
                        elif is_b:
                            # bools print as true/false
                            t_ptr = _get_string_ptr(builder, module, "true", "\0")
                            f_ptr = _get_string_ptr(builder, module, "false", "\0")
                            s = builder.select(v, t_ptr, f_ptr, name="boolstr")
                            fmt_ptr = builder.gep(
                                std["str_fmt_var"], [ZERO, ZERO], inbounds=True
                            )
                            builder.call(std["print"], [fmt_ptr, s])
                        elif is_f:
                            fmt_ptr = builder.gep(
                                std["f32_fmt_var"], [ZERO, ZERO], inbounds=True
                            )
                            if isinstance(v.type, ir.FloatType):
                                v = builder.fpext(v, ir.DoubleType(), name="print_d")
                            builder.call(std["print"], [fmt_ptr, v])
                        else:
                            # int value (or i32 call result); float results already handled
                            if _is_float_val(v):
                                v = builder.fptosi(v, INT32, name="print_i")
                            fmt_ptr = builder.gep(
                                std["i32_fmt_var"], [ZERO, ZERO], inbounds=True
                            )
                            builder.call(std["print"], [fmt_ptr, v])
            else:
                # Discarded-result call: foo(x+1), foo(bar(2))
                _emit_call_value(builder, module, obj, x.name, x.args, "calltmp")

        elif x.type == AST_OBJECT_VARIABLE_DECLARATION:
            if getattr(x, "is_assignment", False):
                if obj.get(x.name) is None:
                    raise Exception(
                        f"Assignment to undefined variable '{x.name}' (did you mean 'let'?)"
                    )
                # reuse existing alloca, ignore declared dt
            else:
                if obj.get(x.name) is None:
                    val_pool.append(x.name)
                    obj[x.name] = builder.alloca(x.dt, name=x.name)
                # else: re-let of existing var (e.g. loop `let a = a-1`)
                # reuses alloca for backwards compat
            if x.val is None:
                raise Exception(f"Variable '{x.name}' has no value")
            evalNumericExpression(obj, x.name, module, builder, x.val)
        elif x.type == AST_CONDITIONAL:
            builder = evalConditional(obj, builder, module, fn, x)
        elif x.type == AST_WHILE:
            builder = evalWhile(obj, builder, module, fn, x)
        elif x.type == AST_RETURN:
            v = x.value
            ret_ty = fn.function_type.return_type
            if isinstance(v, AstSimpleExpression):
                x_val = _eval_expr_value(builder, module, obj, v)
            elif isinstance(v, AstVariableCall):
                if v.name not in obj:
                    raise Exception(f"Return of undefined variable '{v.name}'")
                x_val = builder.load(obj[v.name], name=v.name + "_val")
            elif isinstance(v, AstFunctionCall):
                x_val = _emit_call_value(builder, module, obj, v.name, v.args, "ret")
            elif isinstance(v, AstStringConst):
                x_val = _get_string_ptr(builder, module, v.value, suffix="\0")
            elif isinstance(v, AstBoolConst):
                x_val = ir.Constant(BOOL, v.value)
            elif isinstance(v, AstNumberConst):
                x_val = ir.Constant(INT32, int(float(v.value)))
            elif isinstance(v, AstFloatConst):
                x_val = ir.Constant(FLOAT, float(v.value))
            elif isinstance(v, int):
                x_val = ir.Constant(INT32, int(v))
            else:
                raise Exception(f"Unsupported return value {v}")
            # Convert to function return type if needed
            if isinstance(ret_ty, ir.PointerType):
                if not _is_str_val(x_val):
                    raise Exception("Cannot return numeric value from str function")
            elif isinstance(ret_ty, ir.IntType) and ret_ty.width == 1:
                if _is_str_val(x_val):
                    raise Exception("Cannot return str from bool function")
                if not _is_bool_val(x_val):
                    x_val = _to_bool(builder, x_val)
            elif isinstance(ret_ty, ir.FloatType) and not _is_float_val(x_val):
                if _is_str_val(x_val):
                    raise Exception("Cannot return str from numeric function")
                if _is_bool_val(x_val):
                    x_val = builder.uitofp(x_val, FLOAT, name="bool2fp")
                else:
                    x_val = builder.sitofp(x_val, FLOAT)
            elif isinstance(ret_ty, ir.IntType) and _is_float_val(x_val):
                x_val = builder.fptosi(x_val, INT32)
            elif isinstance(ret_ty, ir.IntType) and _is_bool_val(x_val):
                x_val = builder.zext(x_val, INT32, name="bool2int")
            elif isinstance(ret_ty, ir.IntType) and _is_str_val(x_val):
                raise Exception("Cannot return str from numeric function")
            builder.ret(x_val)

    for vname in val_pool:
        obj.pop(vname, None)
    return builder


def _resolve_expr_value(builder, module, obj, operand):
    """Resolve single expression operand to LLVM value (emits call/load)."""
    if isinstance(operand, AstNumberConst):
        return ir.Constant(INT32, int(float(operand.value)))
    elif isinstance(operand, AstFloatConst):
        return ir.Constant(FLOAT, float(operand.value))
    elif isinstance(operand, AstBoolConst):
        return ir.Constant(BOOL, operand.value)
    elif isinstance(operand, AstStringConst):
        return _get_string_ptr(builder, module, operand.value, suffix="\0")
    elif isinstance(operand, AstVariableCall):
        if operand.name not in obj:
            raise Exception(f"Undefined variable '{operand.name}' in expression")
        return builder.load(obj[operand.name], name=operand.name + "_val")
    elif isinstance(operand, AstFunctionCall):
        return _emit_call_value(builder, module, obj, operand.name, operand.args)
    else:
        raise Exception(f"Invalid expression operand {operand}")


_PREC = {
    "||": 1,
    "&&": 2,
    "==": 3,
    "!=": 3,
    "<": 3,
    "<=": 3,
    ">": 3,
    ">=": 3,
    "+": 4,
    "-": 4,
    "*": 5,
    "/": 5,
    "!": 6,  # unary, right-associative
}
_RIGHT_ASSOC = ("!",)


def _to_rpn(operands):
    """Shunting-yard: infix operands (with '(' ')') to RPN list."""
    out = []
    ops = []
    for tok in operands:
        if isinstance(tok, str) and tok in _PREC:
            while (
                ops
                and ops[-1] != "("
                and (
                    _PREC.get(ops[-1], 0) > _PREC[tok]
                    or (
                        _PREC.get(ops[-1], 0) == _PREC[tok]
                        and tok not in _RIGHT_ASSOC
                    )
                )
            ):
                out.append(ops.pop())
            ops.append(tok)
        elif tok == "(":
            ops.append(tok)
        elif tok == ")":
            while ops and ops[-1] != "(":
                out.append(ops.pop())
            if not ops:
                raise Exception("Mismatched ')' in expression")
            ops.pop()  # discard '('
        else:
            out.append(tok)
    while ops:
        if ops[-1] in ("(", ")"):
            raise Exception("Mismatched parenthesis in expression")
        out.append(ops.pop())
    return out


def evalNumericExpression(
    obj,
    name,
    module,
    builder,
    expression: AstSimpleExpression,
):
    if not expression.operands:
        raise Exception(f"Empty expression for '{name}'")
    if name not in obj:
        raise Exception(f"Undefined variable '{name}'")
    v = _eval_expr_value(builder, module, obj, expression)
    # Convert/store to target alloca type (str pointers stored directly)
    target = obj[name]
    if _is_str_alloca(target):
        if not _is_str_val(v):
            raise Exception(f"Cannot assign numeric value to str variable '{name}'")
        builder.store(v, target)
        return
    if _is_str_val(v):
        raise Exception(f"Cannot assign str value to numeric variable '{name}'")
    if _is_bool_alloca(target):
        if not _is_bool_val(v):
            v = _to_bool(builder, v)
        builder.store(v, target)
        return
    if _is_bool_val(v):
        if _is_float_alloca(target):
            v = builder.uitofp(v, FLOAT, name="bool2fp")
        else:
            v = builder.zext(v, INT32, name="bool2int")
        builder.store(v, target)
        return
    want_float = _is_float_alloca(target)
    if want_float and not _is_float_val(v):
        v = builder.sitofp(v, FLOAT, name="tofloat")
    elif not want_float and _is_float_val(v):
        v = builder.fptosi(v, INT32, name="toint")
    builder.store(v, target)


std = {}


def evalAST(tr, out_path="output.o"):
    global std, _str_cache, _str_counter
    std = {}
    _str_cache = {}
    _str_counter = [0]
    obj = {}
    module = ir.Module(name="mymod")

    # ── declare printf ──────────────────────────────
    printf_ty = ir.FunctionType(
        INT32, [BYTE_PTR], var_arg=True
    )  # returns i32 char* == ir.pointer of i8 and variable arguments=True
    std["print"] = ir.Function(module, printf_ty, name="printf")
    int_fmt = "%d\n\0"
    float_fmt = "%f\n\0"

    # --- Integer format ---
    std["i32_fmt_ty"] = ir.ArrayType(BYTE, len(int_fmt))
    std["i32_fmt_var"] = ir.GlobalVariable(module, std["i32_fmt_ty"], name="i32_fmt")
    std["i32_fmt_var"].linkage = "internal"
    std["i32_fmt_var"].global_constant = True
    std["i32_fmt_var"].initializer = ir.Constant(
        std["i32_fmt_ty"], bytearray(int_fmt.encode("utf8"))
    )

    # --- Float format ---
    std["f32_fmt_ty"] = ir.ArrayType(BYTE, len(float_fmt))
    std["f32_fmt_var"] = ir.GlobalVariable(module, std["f32_fmt_ty"], name="f32_fmt")
    std["f32_fmt_var"].linkage = "internal"
    std["f32_fmt_var"].global_constant = True
    std["f32_fmt_var"].initializer = ir.Constant(
        std["f32_fmt_ty"], bytearray(float_fmt.encode("utf8"))
    )

    # --- String format (%s) for print(str) ---
    str_fmt = "%s\n\0"
    std["str_fmt_ty"] = ir.ArrayType(BYTE, len(str_fmt))
    std["str_fmt_var"] = ir.GlobalVariable(module, std["str_fmt_ty"], name="str_fmt")
    std["str_fmt_var"].linkage = "internal"
    std["str_fmt_var"].global_constant = True
    std["str_fmt_var"].initializer = ir.Constant(
        std["str_fmt_ty"], bytearray(str_fmt.encode("utf8"))
    )

    # ── C string / memory functions (linked from libc via gcc) ──
    # strlen(str) -> i32, strcmp(a,b) -> i32, strcpy/strcat(dst,src) -> str
    std["strlen"] = ir.Function(
        module, ir.FunctionType(INT32, [BYTE_PTR]), name="strlen"
    )
    std["strcmp"] = ir.Function(
        module, ir.FunctionType(INT32, [BYTE_PTR, BYTE_PTR]), name="strcmp"
    )
    std["strcpy"] = ir.Function(
        module, ir.FunctionType(BYTE_PTR, [BYTE_PTR, BYTE_PTR]), name="strcpy"
    )
    std["strcat"] = ir.Function(
        module, ir.FunctionType(BYTE_PTR, [BYTE_PTR, BYTE_PTR]), name="strcat"
    )
    std["malloc"] = ir.Function(
        module, ir.FunctionType(BYTE_PTR, [INT64]), name="malloc"
    )
    std["free"] = ir.Function(
        module, ir.FunctionType(VOID, [BYTE_PTR]), name="free"
    )
    # Friendly alias: len(s) -> strlen(s)
    std["len"] = std["strlen"]
    # Pass 1: declare all functions first (enables forward refs,
    # mutual recursion, and functional composition regardless of order).
    fns = {}
    for x in tr:
        if x.type == AST_FUNCTION_DEFINATION:
            if x.name in std or x.name in fns:
                raise Exception(f"Duplicate function '{x.name}'")
            args = []
            for e in x.args:
                args.append(e.dt)
            fn_ty = ir.FunctionType(x.ret, args)
            fn = ir.Function(module, fn_ty, name=x.name)
            fns[x.name] = fn
            if not x.name == "main":
                std[x.name] = fn
    # Pass 2: compile bodies (calls now resolve forward + recursive).
    for x in tr:
        if x.type == AST_FUNCTION_DEFINATION:
            fn = fns[x.name]
            block = fn.append_basic_block("entry")
            builder = ir.IRBuilder(block)
            for index, e in enumerate(x.args):
                fn.args[index].name = e.name
                alloca = builder.alloca(e.dt, name=e.name)
                # 2. store the incoming value into it
                builder.store(fn.args[index], alloca)
                obj[e.name] = alloca
            try:
                builder = evalFunction(builder, module, x.code, fn, obj)
            except Exception as e_:
                raise Exception(f"In function '{x.name}': {e_}") from e_
            for index, e in enumerate(x.args):
                obj.pop(e.name, None)
            # Implicit return 0 if missing (fixes test2/test3 style programs)
            if not builder.block.is_terminated:
                ret_ty = fn.function_type.return_type
                if isinstance(ret_ty, ir.VoidType):
                    builder.ret_void()
                elif isinstance(ret_ty, (ir.FloatType, ir.DoubleType)):
                    builder.ret(ir.Constant(ret_ty, 0.0))
                elif isinstance(ret_ty, ir.PointerType):
                    builder.ret(ir.Constant(ret_ty, None))
                else:
                    builder.ret(ir.Constant(ret_ty, 0))
    target = binding.Target.from_default_triple()
    tm = target.create_target_machine(reloc="static")
    print(str(module))
    try:
        mod = binding.parse_assembly(str(module))
        mod.verify()
    except Exception as e:
        print("Generated LLVM IR was invalid:", file=sys.stderr)
        print(str(module), file=sys.stderr)
        raise
    with open(out_path, "wb") as f:
        f.write(tm.emit_object(mod))


out_file = sys.argv[2] if len(sys.argv) > 2 else "output.o"
try:
    evalAST(ast, out_file)
except Exception as e:
    print(f"Codegen error: {e}", file=sys.stderr)
    sys.exit(1)


fp.close()
