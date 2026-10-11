"""受限符号表达式：只从白名单 AST 构造 SymPy Poly，不执行输入。"""
import ast
import math
import re
from fractions import Fraction
from sympy import Poly, Rational, Symbol


def canonical(text, variables, exponential=None):
    from knowledge.exercise_graders import normalized
    source=normalized(re.sub(r'\^\{([^{}]+)\}',r'^(\1)',str(text)))
    if len(source)>256:raise ValueError("表达式过长")
    if any(abs(int(e))>100 for e in re.findall(r"[eE]([+-]?\d+)",source)):
        raise ValueError("科学计数法指数过大")
    tree=ast.parse(source,mode="eval")
    if sum(1 for _ in ast.walk(tree))>80:raise ValueError("表达式过于复杂")
    names={name:Symbol(name) for name in variables}
    if not names or len(names)>3:raise ValueError("规则变量无效")
    exp_symbol=Symbol("_exponential")
    gens=tuple(names.values())+((exp_symbol,) if exponential else ())
    def poly(value):return Poly(value,*gens,domain="QQ")
    def checked(value):
        terms=value.terms()
        if len(terms)>256 or value.total_degree()>12:raise ValueError("多项式规模过大")
        if any(max(abs(int(c.p)).bit_length(),int(c.q).bit_length())>1024 for _,c in terms):
            raise ValueError("系数过大")
        return value
    def visit(node):
        if isinstance(node,ast.Expression):return visit(node.body)
        if isinstance(node,ast.Constant) and type(node.value) in (int,float):
            f=Fraction(ast.get_source_segment(source,node))
            if max(f.numerator.bit_length(),f.denominator.bit_length())>1024:raise ValueError("常数过大")
            return poly(Rational(f.numerator,f.denominator))
        if isinstance(node,ast.Name) and node.id in names:return poly(names[node.id])
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):
            p=visit(node.operand);return p if isinstance(node.op,ast.UAdd) else -p
        if not isinstance(node,ast.BinOp):raise ValueError("不支持的表达式节点")
        a,b=visit(node.left),visit(node.right)
        if isinstance(node.op,ast.Add):result=a+b
        elif isinstance(node.op,ast.Sub):result=a-b
        elif isinstance(node.op,ast.Mult):
            if len(a.terms())*len(b.terms())>1024 or a.total_degree()+b.total_degree()>12:
                raise ValueError("乘积规模过大")
            result=a*b
        elif isinstance(node.op,ast.Div):
            if not b.is_ground or b.is_zero:raise ValueError("只支持非零常数分母")
            result=a.mul_ground(1/b.TC())
        elif isinstance(node.op,ast.Pow):
            if b.is_ground:
                exponent=b.TC()
                if exponent.q!=1 or abs(exponent)>12:raise ValueError("只支持有限整数次幂")
                power=int(exponent)
                if power<0:
                    if not a.is_ground or a.is_zero:raise ValueError("不支持符号负次幂")
                    result=poly(a.TC()**power)
                else:
                    if a.total_degree()*power>12 or math.comb(len(a.terms())+power-1,power)>1024:
                        raise ValueError("幂展开规模过大")
                    result=a**power
            elif exponential and a.is_ground and a.TC()==exponential["base"]:
                variable=names[exponential["variable"]]
                coefficient=b.coeff_monomial(variable);offset=b.TC()
                if b!=poly(coefficient*variable+offset) or coefficient.q!=1 or offset.q!=1 or not 0<=coefficient<=12 or abs(offset)>12:
                    raise ValueError("只支持指定变量的有限线性整数指数")
                result=poly(Rational(exponential["base"])**int(offset)*exp_symbol**int(coefficient))
            else:raise ValueError("不支持此类指数")
        else:raise ValueError("不支持此类运算")
        return checked(result)
    return checked(visit(tree))


def equivalent(answer, expected, key):
    return canonical(answer,key["variables"],key.get("exponential"))==canonical(expected,key["variables"],key.get("exponential"))
