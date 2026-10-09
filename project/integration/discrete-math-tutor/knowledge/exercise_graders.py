"""确定性判分：不用 eval，数值用有理数精确比较，逻辑逐项穷举。"""
import ast,itertools,re,unicodedata
from fractions import Fraction

def normalized(text):
 s=unicodedata.normalize('NFKC',str(text)).strip().replace('−','-').replace('，',',').replace('、',',')
 for token in (r'\left',r'\right',r'\displaystyle',r'\,',r'\;'):s=s.replace(token,'')
 s=s.replace(r'\{','{').replace(r'\}','}').replace(r'\cdot','*').replace(r'\times','*').replace('×','*').replace('÷','/')
 for _ in range(12):
  new=re.sub(r'\\(?:d?frac)\{([^{}]+)\}\{([^{}]+)\}',r'((\1)/(\2))',s)
  if new==s:break
  s=new
 s=re.sub(r'\^\{([^{}]+)\}',r'^(\1)',s)
 return s.replace('^','**')

def rational(text):
 s=normalized(text)
 if len(s)>256:raise ValueError('表达式过长')
 if any(abs(int(e))>100 for e in re.findall(r'[eE]([+-]?\d+)',s)):raise ValueError('科学计数法指数过大')
 tree=ast.parse(s,mode='eval')
 if sum(1 for _ in ast.walk(tree))>80:raise ValueError('表达式复杂')
 def visit(n):
  if isinstance(n,ast.Expression):return visit(n.body)
  if isinstance(n,ast.Constant) and type(n.value) in (int,float):
   # AST 仅作为语法树，保留小数的原始字面量精度。
   value=Fraction(ast.get_source_segment(s,n))
  elif isinstance(n,ast.UnaryOp) and isinstance(n.op,(ast.UAdd,ast.USub)):value=visit(n.operand)*(1 if isinstance(n.op,ast.UAdd) else -1)
  elif isinstance(n,ast.BinOp):
   a,b=visit(n.left),visit(n.right)
   if isinstance(n.op,ast.Add):value=a+b
   elif isinstance(n.op,ast.Sub):value=a-b
   elif isinstance(n.op,ast.Mult):value=a*b
   elif isinstance(n.op,ast.Div):value=a/b
   elif isinstance(n.op,ast.Pow) and b.denominator==1 and abs(b)<=12:value=a**int(b)
   else:raise ValueError('不支持的表达式')
  else:raise ValueError('只支持有限有理数的算术表达式')
  if max(value.numerator.bit_length(),value.denominator.bit_length())>2048:raise ValueError('数值过大')
  return value
 return visit(tree)

def finite_set(text):
 s=normalized(text).replace(' ','')
 if s in ('∅','Ø',r'\emptyset',r'\varnothing','{}'):return frozenset()
 if not s.startswith('{') or not s.endswith('}'):raise ValueError('请输入列举形式的集合')
 inner=s[1:-1];items=[];start=0;level=0
 for i,c in enumerate(inner):
  if c in '{(':level+=1
  elif c in '})':level-=1
  if level<0:raise ValueError('括号不匹配')
  if c==',' and level==0:items.append(inner[start:i]);start=i+1
 if level!=0:raise ValueError('括号不匹配')
 items.append(inner[start:])
 if len(items)>200:raise ValueError('集合过大')
 def item(t,depth=0):
  if t.startswith('{'):return ('set',finite_set(t))
  return ('number',rational(t))
 return frozenset(item(t) for t in items)

# 递归下降解析：否定 > 合取 > 析取 > 蕴涵(右结合) > 等价。
def logic_tree(formula):
 s=re.sub(r'\s+','',formula)
 tokens=re.findall(r'<->|->|[a-zA-Z]|[01]|[()¬┐~!∧&∨|→↔]',s)
 if ''.join(tokens)!=s or len(tokens)>120:raise ValueError('命题公式格式无效')
 at=0
 def atom():
  nonlocal at
  if at>=len(tokens):raise ValueError('公式不完整')
  t=tokens[at];at+=1
  if t in ('¬','┐','~','!'):return ('not',atom())
  if t=='(':
   n=eq()
   if at>=len(tokens) or tokens[at]!=')':raise ValueError('括号不匹配')
   at+=1;return n
  if re.fullmatch('[a-zA-Z01]',t):return ('atom',t)
  raise ValueError('公式格式无效')
 def combine(next_fn,ops,kind):
  nonlocal at
  n=next_fn()
  while at<len(tokens) and tokens[at] in ops:at+=1;n=(kind,n,next_fn())
  return n
 def conjunction():return combine(atom,('∧','&'),'and')
 def disjunction():return combine(conjunction,('∨','|'),'or')
 def implication():
  nonlocal at
  n=disjunction()
  if at<len(tokens) and tokens[at] in ('→','->'):at+=1;n=('implies',n,implication())
  return n
 def eq():return combine(implication,('↔','<->'),'eq')
 n=eq()
 if at!=len(tokens):raise ValueError('原子命题之间缺少联结词')
 return n

def logic_value(n,assignment):
 if n[0]=='atom':return bool(int(n[1])) if n[1] in ('0','1') else assignment[n[1]]
 if n[0]=='not':return not logic_value(n[1],assignment)
 a,b=logic_value(n[1],assignment),logic_value(n[2],assignment)
 return a and b if n[0]=='and' else a or b if n[0]=='or' else (not a or b) if n[0]=='implies' else a==b

def truth(value):
 s=str(value).strip().casefold()
 if s in ('1','t','true','真'):return True
 if s in ('0','f','false','假'):return False
 raise ValueError('真值只接受 0/1、T/F 或真/假')
def compare_truth_table(cells,spec):
 vars=spec['variables'];n=logic_tree(spec['formula'])
 if len(cells)!=2**len(vars) or any(len(r)!=len(vars)+1 for r in cells):return (False,0,'行数或列数不符合全部真值指派的要求。')
 seen=set();correct=0;mistakes=[]
 for row in cells:
  values=tuple(truth(x) for x in row);assignment=values[:-1]
  if assignment in seen:return (False,0,'真值指派重复，请每种指派填写一次。')
  seen.add(assignment);expected=logic_value(n,dict(zip(vars,assignment)));correct+=values[-1]==expected
  if values[-1]!=expected:mistakes.append(', '.join(v+'='+str(int(x)) for v,x in zip(vars,assignment))+' 时公式应为 '+str(int(expected)))
 score=round(100*correct/len(cells))
 return (score==100,score,f'已穷举核对 {len(cells)} 种指派，其中 {correct} 行公式真值正确。'+'；'.join(mistakes))

def evaluate_rule(part,answer,key):
 kind=key['kind'];message=key.get('explanation','')
 try:
  if kind=='choice':score=100 if set(answer)==set(key['expected']) else 0
  elif kind=='judgement':score=100 if answer==key['expected'] else 0
  elif kind in ('set_fill','numeric_fill'):
   compare=finite_set if kind=='set_fill' else rational
   results=[compare(v)==compare(e) if str(v).strip() else False for v,e in zip(answer,key['expected'])]
   if len(answer)!=len(key['expected']):raise ValueError('作答空数与题面不一致')
   score=round(100*sum(results)/len(results));message='；'.join(f'第{i+1}空'+('正确' if v else '需要改正') for i,v in enumerate(results))+'。'+message
  elif kind=='matrix':
   expected=key['expected'];cells=answer['cells']
   if len(cells)!=len(expected) or any(len(r)!=len(expected[0]) for r in cells):score=0;message='矩阵维度不正确。'+message
   else:score=round(100*sum(rational(v)==rational(e) for row,exp in zip(cells,expected) for v,e in zip(row,exp))/(len(expected)*len(expected[0])))
  elif kind=='truth_table':_,score,message=compare_truth_table(answer['cells'],key)
  else:raise ValueError('判分规则未实现')
  if kind=='truth_table':
   tree=logic_tree(key['formula']);reference='\n'.join(' '.join(str(int(x)) for x in values)+' | '+str(int(logic_value(tree,dict(zip(key['variables'],values))))) for values in itertools.product((False,True),repeat=len(key['variables'])))
  else:reference=key['expected']
  return {'part_id':part['id'],'verdict':'correct' if score==100 else 'incorrect' if score==0 else 'partial','score':score,'confirmed':True,'feedback':message,'reference_answer':reference,'method':'rule'}
 except (ValueError,SyntaxError,ZeroDivisionError,OverflowError,RecursionError):
  return {'part_id':part['id'],'verdict':'uncertain','score':None,'confirmed':False,'feedback':'当前格式超出这道题的规则解析范围，请按题面的输入约定填写，或使用 AI 讲解核对；本次不会据此判错。','reference_answer':'','method':'rule'}
