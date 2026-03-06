fp = open("test.ts", "r")
src = fp.read()


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
        if code[pc].isalpha():
            builder = ""
            while pc < len(code) and code[pc].isalpha():
                builder += code[pc]
                pc += 1
            if builder in KEYWORDS:
                tokens.append((builder, "KEYWORD"))
                continue
            tokens.append((builder, "TEXT"))
        elif code[pc].isalnum():
            builder = ""
            builder = ""
            while pc < len(code) and code[pc].isalnum():
                builder += code[pc]
                pc += 1
            tokens.append((builder, "NUM"))
        elif code[pc] == " ":
            if isStr:
                tokens.append((code[pc], "WS"))
            pc += 1
        else:
            tokens.append((code[pc], "SYM"))
            if code[pc] == '"':
                isStr = not isStr
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


BYTE = ir.IntType(8)
BYTE_PTR = ir.PointerType(BYTE)
SHORT = ir.IntType(16)
INT32 = ir.IntType(32)
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


class AstIF:
    def __init__(self, exp: AstSimpleExpression) -> None:
        self.type = AST_IF
        self.exp = exp
        self.code = []


class AstElse:
    def __init__(self, block) -> None:
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


class AstBlock:
    pass


def ParseCondition(tokens, pc):
    exp = AstSimpleExpression()
    val = AstConditional()
    while tokens[pc][0] != " }":
        if tokens[pc][0] == "if":
            pc += 1
            while tokens[pc][0] != "{":
                if tokens[pc][0] == "(" or tokens[pc][0] == ")":
                    pc += 1
                    continue
                elif tokens[pc][1] == "TEXT":
                    name = tokens[pc][0]
                    pc += 1
                    if tokens[pc][1] == "NUM":
                        name += tokens[pc][0]
                        pc += 1
                    exp.operands.append(AstVariableCall(name))
                elif tokens[pc][1] == "NUM":
                    exp.operands.append(AstNumberConst(tokens[pc][0]))
                    pc += 1
                elif tokens[pc][1] == "SYM":
                    exp.operands.append(tokens[pc][0])
                    pc += 1
                else:
                    raise Exception(
                        "Error Invalide token:"
                        + tokens[pc][0]
                        + "Expected a variable or a number"
                    )
            fd = AstIF(exp)
            pc += 1
            while tokens[pc][0] != "}":
                obj = ParseLine(tokens, pc)
                pc = obj[1]
                fd.code.append(obj[0])
                pc += 1
            val.code.append(fd)
            return val, pc

        pc += 1


def ParseLine(tokens, pc):
    obj = None
    name = tokens[pc]
    while tokens[pc][0] != ";" and tokens[pc][0] != "\n":
        if tokens[pc][1] == "TEXT":
            name = tokens[pc][0]
            pc += 1
            if tokens[pc][1] == "NUM":
                name += tokens[pc][0]
                pc += 1

            if tokens[pc][0] == "(":
                fc = AstFunctionCall(
                    name,
                )
                pc += 1
                while tokens[pc][0] != ")":
                    arg = ""

                    if tokens[pc][0] == '"':
                        pc += 1

                        while tokens[pc][0] != '"':
                            arg += tokens[pc][0]
                            pc += 1
                        arg = AstStringConst(arg)
                    elif tokens[pc][1] == "NUM":
                        arg += str(tokens[pc][0])
                        arg = AstNumberConst(arg)
                    elif tokens[pc][1] == "TEXT":
                        name = tokens[pc][0]
                        arg = AstVariableCall(name)
                    pc += 1

                    fc.args.append(arg)
                obj = fc
            pc += 1
        elif tokens[pc][1] == "KEYWORD":
            if tokens[pc][0] == "let":
                pc += 1
                name = tokens[pc][0]
                pc += 1
                if tokens[pc][1] == "NUM":
                    name += tokens[pc][0]
                    pc += 1
                if tokens[pc][0] != ":":
                    raise Exception("Expected :")

                pc += 1
                fd = AstObjectVariableDeclaration(name)
                if tokens[pc][0] + tokens[pc + 1][0] == "i32":
                    pc += 1
                    pc += 1
                    if tokens[pc][0] == "=":
                        exp = AstSimpleExpression()
                        pc += 1
                        while tokens[pc][0] != ";" and tokens[pc][0] != "\n":
                            if tokens[pc][0] == "(" or tokens[pc][0] == ")":
                                pc += 1
                                continue
                            elif tokens[pc][1] == "TEXT":
                                name = tokens[pc][0]
                                pc += 1
                                if tokens[pc][1] == "NUM":
                                    name += tokens[pc][0]
                                    pc += 1
                                exp.operands.append(AstVariableCall(name))
                            elif tokens[pc][1] == "NUM":
                                exp.operands.append(AstNumberConst(tokens[pc][0]))
                                pc += 1
                            elif tokens[pc][1] == "SYM":
                                exp.operands.append(tokens[pc][0])
                                pc += 1
                            else:
                                raise Exception(
                                    "Error Invalide token:"
                                    + tokens[pc][0]
                                    + "Expected a variable or a number"
                                )
                        fd.val = exp
                        # print(exp.operands)
                        pc -= 1

                    obj = fd
                    pc += 1
            elif tokens[pc][0] == "if":
                return ParseCondition(tokens, pc)
    return (obj, pc)


def ParseFunctionDefination(tokens, pc):

    name = ""
    obj = None
    if tokens[pc][0] == "function":
        pc += 1

        if tokens[pc][1] == "TEXT":
            name += tokens[pc][0]
        else:
            raise Exception("Expected Function name but found:", tokens[pc][0])
        pc += 1
        if tokens[pc][1] == "NUM":
            name += tokens[pc][0]
            pc += 1

        if tokens[pc][0] != "(":
            raise Exception("Expected ( :")

        args = []
        while tokens[pc][0] != ")":
            # handle args
            pc += 1

        while tokens[pc][0] != "{":
            pc += 1
        fd = AstFunctionDefination(name, [])
        pc += 1
        while tokens[pc][0] != "}":
            obj = ParseLine(tokens, pc)
            fd.append(obj[0])
            pc = obj[1]
            pc += 1
        obj = fd

    pc += 1
    return pc, obj


def ParseToAst(tokens):
    pc = 0
    program = []
    while pc < len(tokens):
        obj = ParseFunctionDefination(tokens, pc)
        program.append(obj[1])
        pc = obj[0]
        pc += 1
    return program


tokens = tokenise(src)
# print(tokens)
ast = ParseToAst(tokens)


def evalConditional(obj, builder, module, fn, ast: AstConditional):
    blocks = []
    for x in range(len(ast.code)):
        blocks.append(fn.append_basic_block("then"))
    end_block = fn.append_basic_block("end")
    for i, x in enumerate(ast.code):
        if x.type == AST_IF:
            co = None
            stack = []
            opr = x.exp.operands
            val1 = builder.load(obj[opr[0].name], name=opr[0].name + "_val")
            val2 = builder.load(obj[opr[2].name], name=opr[2].name + "_val")
            cond = builder.icmp_signed(opr[1], val1, val2, name="cond")
            builder.cbranch(cond, blocks[i], end_block)
            builder = ir.IRBuilder(blocks[i])
            evalFunction(builder, module, x.code, fn, obj)
            builder.branch(end_block)
    builder = ir.IRBuilder(end_block)
    return builder


def evalFunction(builder, module, code, fn, obj_={}):
    obj = obj_
    val_pool = []
    for x in code:
        if x == None:
            continue
        elif x.type == AST_FUNCTION_CALL:
            if x.name == "print":
                args = []
                for arg in x.args:
                    if arg.type == AST_STRING_CONSTANT:
                        msg = arg.value + "\n\0"
                        msg_ty = ir.ArrayType(BYTE, len(msg))
                        msg_var = ir.GlobalVariable(module, msg_ty, name=arg.value)
                        msg_var.linkage = "internal"
                        msg_var.global_constant = True
                        msg_var.initializer = ir.Constant(
                            msg_ty, bytearray(msg.encode("utf8"))
                        )
                        msg_ptr = builder.gep(msg_var, [ZERO, ZERO], inbounds=True)
                        args.append(msg_ptr)
                    elif arg.type == AST_NUMBER_CONSTANT:
                        msg = arg.value + "\n\0"
                        msg_ty = ir.ArrayType(BYTE, len(msg))
                        msg_var = ir.GlobalVariable(
                            module, msg_ty, name="num" + arg.value
                        )
                        msg_var.linkage = "internal"
                        msg_var.global_constant = True
                        msg_var.initializer = ir.Constant(
                            msg_ty, bytearray(msg.encode("utf8"))
                        )
                        msg_ptr = builder.gep(msg_var, [ZERO, ZERO], inbounds=True)
                        args.append(msg_ptr)
                    elif arg.type == AST_VARIABLE_CALL:
                        msg = "%d\n\0"
                        fmt_ptr = builder.gep(
                            std["i32_fmt_var"], [ZERO, ZERO], inbounds=True
                        )
                        args.append(fmt_ptr)
                        x_val = builder.load(
                            obj[arg.name], name=x.name
                        )  # read x, name=x.name+"val")  # read x
                        args.append(x_val)
                builder.call(std["print"], args)
        elif x.type == AST_OBJECT_VARIABLE_DECLARATION:
            if obj.get(x.name) == None:
                val_pool.append(x.name)
                obj[x.name] = builder.alloca(x.dt, name=x.name)  # int x
            # builder.store(ir.Constant(x.dt, int(x.val)), obj[x.name])  # x = 42
            evalNumericExpression(obj, x.name, module, builder, x.val)
        elif x.type == AST_CONDITIONAL:
            builder = evalConditional(obj, builder, module, fn, x)

    for x in val_pool:
        del obj[x]
    return builder


def evalNumericExpression(obj, name, module, builder, expression: AstSimpleExpression):
    co = None
    stack = []
    for x in expression.operands:
        if x in ("+", "/", "*", "-"):
            co = x
        elif x.type == AST_NUMBER_CONSTANT:
            const = ir.Constant(INT32, int(x.value))
            if co != None:
                val2 = stack.pop()

                if co == "+":
                    temp = builder.add(const, val2, name="temp")
                    stack.append(temp)
                    co = None
                elif co == "/":
                    temp = builder.sdiv(val2, const, name="temp")
                    stack.append(temp)
                elif co == "*":
                    temp = builder.mul(val2, const, name="temp")
                    stack.append(temp)
                elif co == "-":
                    temp = builder.sub(val2, const, name="temp")
                    stack.append(temp)
            else:
                stack.append(const)
        elif x.type == AST_VARIABLE_CALL:
            var1 = builder.load(obj[x.name], name=x.name + "_val")
            if co != None:
                val2 = stack.pop()
                if co == "+":
                    temp = builder.add(var1, val2, name="temp")
                    stack.append(temp)
                    co = None
                elif co == "/":
                    temp = builder.sdiv(val2, var1, name="temp")
                    stack.append(temp)
                elif co == "*":
                    temp = builder.mul(val2, var1, name="temp")
                    stack.append(temp)
                elif co == "-":
                    temp = builder.sub(val2, var1, name="temp")
                    stack.append(temp)
            else:
                stack.append(var1)

    builder.store(stack[-1], obj[name])


std = {}


def evalAST(tr):
    obj = {}
    module = ir.Module(name="mymod")

    # ── declare printf ──────────────────────────────
    printf_ty = ir.FunctionType(
        INT32, [BYTE_PTR], var_arg=True
    )  # returns i32 char* == ir.pointer of i8 and variable arguments=True
    std["print"] = ir.Function(module, printf_ty, name="printf")
    fmt = "%d\n\0"
    std["i32_fmt_ty"] = ir.ArrayType(BYTE, len(fmt))
    std["i32_fmt_var"] = ir.GlobalVariable(module, std["i32_fmt_ty"], name="fmt")
    std["i32_fmt_var"].linkage = "internal"
    std["i32_fmt_var"].global_constant = True
    std["i32_fmt_var"].initializer = ir.Constant(
        std["i32_fmt_ty"], bytearray(fmt.encode("utf8"))
    )

    for x in tr:
        if x.type == AST_FUNCTION_DEFINATION:
            fn_ty = ir.FunctionType(x.ret, x.args)
            fn = ir.Function(module, fn_ty, name=x.name)
            block = fn.append_basic_block("entry")
            builder = ir.IRBuilder(block)
            builder = evalFunction(builder, module, x.code, fn)
            builder.ret(ir.Constant(INT32, 0))
    target = binding.Target.from_default_triple()
    tm = target.create_target_machine(reloc="static")
    mod = binding.parse_assembly(str(module))
    mod.verify()
    with open("output.o", "wb") as f:
        f.write(tm.emit_object(mod))


evalAST(ast)


fp.close()
