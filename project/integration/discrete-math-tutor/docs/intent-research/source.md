# User
我现在想做好我们项目的意图识别部分，就是怎么能让大模型更好的识别学生输入的问题，还有就是如何解决学生输入不完全，输入信息不完整，不明确，意图不明确的问题，我们可以参考一下github上相关的开源项目或者是相关 agent或者与学生学习相关的论文

# Assistant
我认为你们这个项目的**意图识别（Intent Understanding / Intent Routing）**不能简单做成传统客服那种：

> 用户输入 → 分类器 → intent → 回复

因为你们的场景是**AI 教学 Agent**，学生的问题天然存在：

1. **目标不明确**
2. **知识水平未知**
3. **上下文依赖强**
4. **一句话可能包含多个意图**
5. **学生自己也不知道自己想问什么**

所以应该参考**教育 Agent、多智能体系统、LLM Clarification Agent、Tutor Agent**的设计。

我调研了一些相关项目和论文后，建议你们把意图识别设计成：

> **Intent Detection + Student State Understanding + Ambiguity Detection + Clarification Loop + Agent Routing**

而不是单纯分类。


---

# 一、先看目前优秀学习 Agent 怎么做

## 1. Tutor-Agent（推荐重点参考）

GitHub：
([GitHub][1])

它的设计非常接近你们项目。

它没有直接回答学生问题，而是先经过：

```
学生输入
    |
    ↓
Classification Agent
    |
    ├── 学习新知识？
    |
    ├── 想验证理解？
    |
    ├── 想做练习？
    |
    ↓
对应教学 Agent
```

它识别的不只是：

> "用户想问什么"

而是：

> "这个学生现在处于什么学习状态"


它会判断：

### Topic

学生学习什么？

例如：

```
我要学习链表
```

↓

topic:

```
Data Structure
Linked List
```


---

### Knowledge Level

学生水平：

```
beginner
intermediate
advanced
```


比如：

学生：

> 链表怎么插入


模型应该知道：

这个学生不是问定义，而是：

```
当前知识节点：
链表操作阶段

需要：
代码解释
图示
步骤拆解
```


---

### Learning Goal

学生目的：

```
learn
practice
review
debug
explain
```


例如：

输入：

> 这个代码为什么错


不是：

learn

而是：

debug


---

### Teaching Preference

例如：

```
example
theory
code
visualization
```


这个特别适合你们。


因为你之前一直强调：

> 先通俗，再技术，再源码


其实这就是学生画像。


---

# 二、你们目前最大的问题：学生输入不完整

例如：

学生：

> 链表


传统系统：

无法判断。

因为可能：

1. 什么是链表？
2. 怎么写链表？
3. 链表插入？
4. 链表删除？
5. 链表考试重点？


所以需要：

## Ambiguity Detection（歧义检测）


参考：

([GitHub][2])


它提出：

先判断：

```
这个问题是否存在多个合理解释？
```

例如：

输入：

```
Python
```


模型生成：

可能意图：

```
A 学Python基础
B Python爬虫
C Python数据分析
D Python机器学习
```


计算不确定性。


如果：

不确定性高

↓

不要回答

↓

进入澄清。


---

# 三、推荐你们设计一个 Intent Understanding Agent


整体架构：

```
                 学生输入
                     |
                     ↓
          Intent Understanding Agent
                     |
     ---------------------------------
     |              |                |
 Intent       Ambiguity        Student State
 Detection    Detection        Extraction
     |              |                |
     ---------------------------------
                     |
                     ↓
              Decision Agent
                     |
        ------------------------
        |          |           |
      Tutor     RAG       Tool Agent

```


---

# 四、Intent 不应该设计成固定类别太少

不要：

```
1.提问
2.闲聊
3.搜索
```

太简单。


建议你们定义教育领域 Intent Schema。


例如：

## 一级 Intent


```json
{
"intent":
[
"learn_new",
"concept_explanation",
"example_request",
"code_help",
"debug",
"exercise",
"summary",
"comparison",
"review",
"continue_learning"
]
}
```


---

## 二级 Intent


例如：

学生：

> 快速排序怎么实现


识别：

```json
{
intent:"learn_new",

sub_intent:
{
topic:"快速排序",
goal:"algorithm understanding",
depth:"beginner"
}
}
```


---

学生：

> 为什么这里i++


识别：

```json
{
intent:"code_debug",

context:
{
language:"C++",
topic:"quick sort"
}
}
```


---

# 五、加入 Student State（非常重要）

这是教育 Agent 和普通 Agent 最大区别。


每次对话维护：

```json
StudentState
{

knowledge_level:
"beginner",

current_course:
"数据结构",

current_topic:
"链表",

mastery:
{
pointer:0.7,
linkedlist:0.4
},

learning_style:
{
prefer:"visual"
},

recent_error:
[
"不理解指针"
]

}
```


然后：

学生：

> 插入怎么写


普通 LLM：

回答：

链表插入代码


你们：

看到：

```
当前学习：
链表基础

历史：
刚学完节点结构

掌握：
指针 40%

```

所以回答：

> 我们先回顾节点结构，然后讲插入。


这才像老师。


---

# 六、不明确问题怎么解决？

推荐采用 Clarification Loop


流程：


```
学生问题

↓

判断完整度


↓

是否可以回答？

       |
       |
 --------------
 |            |
可以        不可以

 ↓             ↓

回答       生成澄清问题

             ↓

        学生补充

             ↓

        更新Intent

             ↓

           回答

```


---

但是注意：

不要所有模糊都问。

否则体验很差。


例如：

学生：

> 什么是RAG


不用问。


因为意图明显。


---

学生：

> RAG


需要问。


---

# 七、澄清问题生成不要随便问

这里参考最新研究：

**Uncertainty-Aware Clarification in LLM Agents with Information Gain**

核心思想：

> 一个好的澄清问题应该最大程度降低不确定性。


([Proceedings of Machine Learning Research][3])


例如：

不好：

> 请问你想了解什么？


好：

> 你想了解 RAG 的哪部分？
>
> A. 基础原理  
> B. 系统架构  
> C. 代码实现  
> D. 项目部署


因为一次减少大量可能。


---

# 八、建议你们实现一个 Intent Router Agent


类似：

EduAgent：

([GitHub][4])


它流程：

```
Planner

↓

判断：

learn
practice
answer_question
general


↓

进入不同 Agent

```


你们可以升级：


```
Intent Router


输出：

{
intent:"learn",

confidence:0.82,

need_clarification:false,

route:
"TeacherAgent"
}

```


---

# 九、具体技术实现方案


## 第一层：Prompt + Structured Output

不要让模型直接输出文字。


使用 Pydantic。


例如：

```python
class IntentResult(BaseModel):

    intent:str

    topic:str

    confidence:float

    ambiguity_level:str

    need_clarification:bool

    clarification_question:str

    route:str

```


---

输入：

```
链表
```


输出：

```json
{
"intent":"unknown",

"confidence":0.35,

"ambiguity_level":"high",

"need_clarification":true,

"clarification_question":
"你想学习链表的概念、代码实现还是操作？"
}

```


---

# 十、结合你们教材 RAG 项目，我建议最终架构


你们现在项目：

教材 → Chunk → Retriever → LLM


应该改成：


```
学生输入

↓

Intent Understanding Layer

↓

判断：

学习目标

知识节点

教材章节

用户状态


↓

Query Rewrite Agent

↓

RAG Retriever

↓

Teaching Agent

↓

Answer Generator

↓

Learning Memory Update

```


---

# 十一、Query Rewrite 也非常重要

很多学生输入：

```
为什么这个不懂
```

无法检索。


需要：

Query Rewrite Agent:


学生：

> 为什么这个不懂


结合上下文：

```
当前阅读:
离散数学 第三章 关系

选中文字:
关系闭包

最近问题:
传递闭包定义

```

生成：

```
解释离散数学中关系闭包与传递闭包的区别
```


再去 RAG。


---

# 十二、我建议你们第一版实现顺序


不要一次做太复杂。


## V1

实现：

```
Intent Classification Agent

+
Structured Output

+
简单Clarification
```


支持：

10个intent。


---

## V1.5

加入：

```
Student State

+
Conversation Memory
```


---

## V2

加入：

```
Ambiguity Detection

+
Information Gain Clarification
```


---

## V3

加入：

```
Multi Agent Router

Teacher Agent
Quiz Agent
Coding Agent
Evaluation Agent

```


---

# 十三、可以重点参考的项目


|项目|用途|
|-|-|
|Tutor-Agent|学习Agent路由设计，非常推荐|
|EduAgent|完整教育Agent架构|
|MathTutor|数学学习、记忆、意图路由|
|Clarify-AI|模糊输入检测|


来源：
([GitHub][1])


---

结合你们目前的 **DeepTutor Agent / 标注星图项目**，我认为最关键的不是做一个“问题分类器”，而是做一个：

> **学生意图理解中枢（Student Intent Understanding Engine）**

它负责理解：

1. 学生想学什么
2. 学到什么程度
3. 当前卡在哪里
4. 是否需要追问
5. 应该调用哪个教学能力


这部分做好以后，后面的 RAG、工具调用、教学 Agent 效果都会明显提升。下一步我建议可以继续深入设计这一部分的**详细技术方案（Agent节点、Prompt、State结构、数据库表设计、代码实现方案）**。

[1]: https://github.com/ghdkim/tutor-agent?utm_source=chatgpt.com "GitHub - ghdkim/tutor-agent: A multi-agent AI tutor built with LangGraph and OpenAI that assesses learning needs and routes users between teacher, Feynman, and quiz agents for personalized explanations, active recall, and topic research. · GitHub"
[2]: https://github.com/sirutisb/clarify-ai?utm_source=chatgpt.com "GitHub - sirutisb/clarify-ai: Detect and resolve ambiguous user prompts via clarification. · GitHub"
[3]: https://proceedings.mlr.press/v306/deng26l.html?utm_source=chatgpt.com "Uncertainty-Aware Clarification in LLM Agents with Information Gain"
[4]: https://github.com/Varsha-art126/EduAgent?utm_source=chatgpt.com "GitHub - Varsha-art126/EduAgent: EduAgent - AI personal tutoring assistant built on LangGraph + FastAPI + Streamlit + ChromaDB RAG: planner/teacher/quiz/evaluation/memory/recommendation agents, M1-M8 evaluation suite, and RAG configuration experiments. · GitHub"

# User
可以

# Assistant
好的，那我们继续往**工程设计层面**深入。结合你们现在的项目（DeepTutor Agent / 教材 RAG / 学习闭环），我建议把「意图识别」设计成一个独立的 **Student Intent Understanding Engine（学生意图理解引擎）**。

这一部分不是一个简单的 LLM Prompt，而是一个中间层，连接：

```
学生输入
    ↓
意图理解
    ↓
学习状态理解
    ↓
任务规划
    ↓
RAG / 工具 / 教学 Agent
    ↓
回答
    ↓
学习状态更新
```

---

# 一、整体架构设计

## 1. 总体流程


```
                 Student Query
                       |
                       ↓
        ┌────────────────────────┐
        │ Intent Understanding    │
        │ Engine                 │
        └────────────────────────┘
                       |
        ┌──────────────┼───────────────┐
        ↓              ↓               ↓

 Intent Agent   Context Agent   Ambiguity Agent

        ↓              ↓               ↓

        └──────────────┼───────────────┘

                       ↓

              Decision / Router Agent

                       ↓

      ┌──────────┬──────────┬──────────┐
      ↓          ↓          ↓

    RAG      Tutor       Tool

  教材检索   教学解释    代码执行


                       ↓

                Response Agent


                       ↓

             Memory Update Agent

```

---

# 二、Intent Agent 设计

## 作用

回答：

> 学生现在想做什么？


不是判断关键词。

例如：

输入：

> 快排


不能简单认为：

```
算法问题
```


需要理解：

可能：

1. 想学习快速排序
2. 想复习快速排序
3. 想问代码
4. 想解决代码错误


---

## Intent Schema设计


建议第一层：

```json
{
"intent":"learning"
}
```


第二层：

```json
{
"intent":"learning",

"sub_intent":
{
"type":"concept",
"operation":"explain",
"depth":"basic"
}

}
```


---

# 推荐 Intent 分类


## A. 学习类


### learn_new

学习新知识


例：

> 什么是B树


---

### concept_explanation

概念解释


例：

> 为什么B树叫多路平衡树


---

### mechanism_explanation

原理分析


例：

> Transformer为什么可以并行


---

### example_request

请求例子


例：

> 举个例子


---

## B. 实践类


### code_generation


例：

> 写一个链表


---

### code_debug


例：

> 为什么这里报错


---

### implementation_explanation


例：

> 解释这个代码


---

## C. 练习类


### exercise

做题


### answer_check

检查答案


### hint

请求提示


---

## D. 复习类


### summary

总结


### review

复习


### comparison

比较


---

## E. 系统行为类


### continue_learning

继续学习


例如：

> 下一部分


这个非常重要。


因为你们项目有大量：

> 下一部分


这种上下文依赖。


---

# 三、Intent 输出结构

不要输出字符串。

输出结构化 JSON。


例如：

```json
{
"intent":
{
"name":"concept_explanation",

"confidence":0.91,

"topic":
{
"name":"链表",
"chapter":"数据结构第三章"
},

"goal":
"understand",

"level":
"beginner",

"need_rag":
true,

"need_clarification":
false

}

}
```


---

# 四、Student State Agent（核心）


这是普通 Agent 和教学 Agent 最大区别。


## 学生状态


建议维护：

```json
StudentState
{


"user_id":"001",


"current_learning":

{
"course":"数据结构",

"chapter":
"链表",

"section":
"双向循环链表"
},



"knowledge_state":
{

"pointer":
0.5,

"linked_list":
0.6,

"tree":
0.2

},



"preference":

{
"style":
"step_by_step",

"need_example":
true,

"need_code":
true

},



"recent_questions":

[
"节点是什么",
"next指针指向什么"
]


}

```


---

## 举例


学生：

> 双向链表怎么插入


系统读取：

```
历史：

昨天：
学习节点

之前：
不知道next是什么

当前：
链表章节

水平：
初级

```


于是回答：

不会直接：

```
给你代码
```


而是：

```
我们先回顾一下双向链表节点结构，
然后看插入为什么需要修改四个指针。
```


这就是老师感。


---

# 五、Ambiguity Agent（解决输入不完整）


这是你重点关注的。


## 输入：


```
B+树
```


Intent Agent:

```
可能：

学习概念
代码实现
考试复习
数据库索引
```

概率：


```json
{
"concept":0.4,
"exam":0.3,
"implementation":0.2,
"other":0.1
}

```


---

计算：

Entropy


如果：

不确定性高


进入：

Clarification。


---

# 六、澄清问题生成


不要：

❌

```
请详细描述你的问题
```


应该：

利用候选 Intent。


例如：


学生：

> B+树


生成：


```
你想了解 B+ 树的哪部分？

1. 基本概念和结构
2. B+树插入删除过程
3. 数据库索引中的应用
4. C++代码实现

请选择一个方向。
```


---

# 七、Query Rewrite Agent


这个对于教材 RAG 非常关键。


学生：

```
为什么这个成立？
```


无法检索。


但是：

结合：

```
当前页面：

离散数学
第三章

选中文字：

关系的传递性

```


Rewrite:


```
解释关系传递性定义以及该性质成立原因
```


然后：

RAG。


---

# 八、Router Agent设计


最后决定：

调用什么。


例如：

输出：


```json
{

"route":

[
"教材RAG",
"TeacherAgent"

]

}

```


---

## 路由规则


|情况|Agent|
|-|-|
|概念解释|Teacher|
|教材知识|RAG|
|代码错误|Coding|
|练习|Exercise|
|测评|Evaluation|
|模糊|Clarification|


---

# 九、数据库设计


建议新增三个表。


---

## 1. intent_history


保存：

用户每次意图。


```sql
intent_history

id

user_id

query

intent

confidence

created_time

```


---

## 2. student_state


保存学习状态。


```sql
student_state


user_id

course

chapter

knowledge_json

preference_json

```


---

## 3. conversation_memory


保存长期记忆。


```sql
conversation_memory


user_id

topic

summary

importance

```


---

# 十、Prompt设计


Intent Agent Prompt：


```
你是一名教学AI中的意图理解模块。

你的任务不是回答问题，
而是分析学生需求。


需要判断：

1. 学生想做什么？
2. 涉及哪个知识点？
3. 当前学习阶段？
4. 是否需要追问？


输出JSON。

```


---

# 十一、技术实现推荐


你们当前：

Python + FastAPI


推荐：

## LangGraph


因为你们本质是 Agent Workflow。


结构：

```python
graph.add_node(
"intent_agent"
)


graph.add_node(
"clarification_agent"
)


graph.add_node(
"rag_agent"
)


graph.add_node(
"teacher_agent"
)


```


流程：

```python
START

↓

Intent

↓

if ambiguity:

Clarification


else:

Router

↓

Teacher

↓

END

```


---

# 十二、和你们现有 DeepTutor 对接


你们之前设计：

```
学习
实训
成长
我的

```


那么：

Intent Engine 就是学习入口的大脑。


对应：

## 学习页面


用户输入：

↓

Intent Engine

↓

判断：

学习任务


---

## 实训页面


判断：

practice


调用：

代码执行环境


---

## 成长页面


读取：

Student State


生成：

学习报告。


---

# 十三、建议开发路线


## 第一阶段（1周）

完成：

✅ Intent Agent

✅ JSON输出

✅ Router


支持10种intent。


---

## 第二阶段

加入：

✅ Student State

✅ Memory


---

## 第三阶段

加入：

✅ Ambiguity Detection

✅ Clarification


---

## 第四阶段

加入：

✅ 自适应教学策略


例如：

自动判断：

```
这个学生连续3次问指针

应该降低解释难度
增加图示
```


---

下一步我建议继续做：

**《DeepTutor Agent 学生意图理解引擎详细设计文档 v1.0》**

里面包括：

1. 系统架构图  
2. Agent节点设计  
3. Prompt模板  
4. JSON Schema  
5. 数据库表结构  
6. LangGraph实现方案  
7. 与你们现有RAG、CurrentLearningTask、用户画像的接口设计  

这样可以直接交给 Codex 或开发人员实现。

# User
继续

# Assistant
继续，我们开始整理成**可以落地开发的设计方案**。这一部分重点不是概念，而是按照你们 DeepTutor Agent 当前架构，设计「学生意图理解引擎 v1.0」。

---

# DeepTutor Agent 学生意图理解引擎设计方案 v1.0

## 1. 设计目标

### 目标

构建一个面向教育场景的 LLM 意图理解模块，使系统能够：

1. 理解学生当前真实学习目的；
2. 判断学生输入是否完整；
3. 识别学生当前知识背景；
4. 根据教学目标选择合适 Agent；
5. 在信息不足时主动引导学生补充；
6. 为后续 RAG、教学 Agent、评价 Agent 提供结构化上下文。


---

# 2. 为什么不用传统 Intent Classification？


传统：

```
用户输入
 ↓
分类模型
 ↓
intent=xxx
 ↓
回答
```


例如：

学生：

> 链表


分类：

```
intent=data_structure
```


问题：

它不知道：

- 学生想学习？
- 想写代码？
- 想考试？
- 想解决错误？


---

教育场景真正需要：

```
学生输入
+
学习上下文
+
历史行为
+
教材位置

↓

学生当前任务理解

```


所以：

Intent ≠ 用户目的

而是：

> Student Task Understanding（学生任务理解）


---

# 3. 核心模块设计


整体：

```
                 User Query
                     |
                     ↓

        Intent Understanding Engine


 ┌─────────────────────────────────┐
 │                                 │
 │ 1.Intent Recognition Agent      │
 │                                 │
 │ 2.Context Understanding Agent   │
 │                                 │
 │ 3.Ambiguity Detection Agent     │
 │                                 │
 │ 4.Query Rewrite Agent           │
 │                                 │
 │ 5.Task Planning Agent           │
 │                                 │
 └─────────────────────────────────┘


                     ↓

              Agent Router


        ┌────────┬────────┬────────┐

        ↓        ↓        ↓

      RAG     Tutor    Tool


```

---

# 4. Intent Recognition Agent


## 4.1 输入


包括：

### 当前问题

例如：

```
B+树怎么删除
```


---

### 对话历史


例如：

```
上一轮：

B+树是什么

AI：

介绍结构

学生：

B+树怎么删除

```


---

### 当前学习任务


来自：

CurrentLearningTask


例如：

```json
{
course:"数据库",
chapter:"索引",
section:"B+树"
}

```


---

### 用户画像


例如：

```json
{
level:"beginner",

major:"data science",

learning_style:
"step_by_step"

}

```


---

# 4.2 输出 Schema


定义：

```python
class IntentResult(BaseModel):

    primary_intent:str

    secondary_intent:str

    topic:str

    knowledge_point:str

    learning_goal:str

    difficulty_level:str

    confidence:float

    need_clarification:bool

```


---

例如：


学生：

> B+树怎么删除


输出：


```json
{
"primary_intent":
"concept_learning",

"secondary_intent":
"algorithm_process",

"topic":
"数据库索引",

"knowledge_point":
"B+树删除",

"learning_goal":
"understand",

"difficulty_level":
"intermediate",

"confidence":
0.92,

"need_clarification":
false

}

```

---

# 5. Intent 分类体系


建议采用三级。


---

## Level 1：学习行为


```text
Learning
Practice
Evaluation
Interaction

```


---

## Level 2：具体行为


## Learning


|Intent|说明|
|-|-|
|learn_new|学习新知识|
|explain|解释概念|
|deep_explain|深入原理|
|example|请求例子|
|summary|总结|

---

## Practice


|Intent|说明|
|-|-|
|solve_problem|解题|
|code_write|代码实现|
|debug|代码调试|
|experiment|实验|

---

## Evaluation


|Intent|说明|
|-|-|
|check_answer|检查答案|
|quiz|生成练习|
|assessment|能力评价|


---

## Interaction


|Intent|说明|
|-|-|
|continue|继续学习|
|repeat|重新解释|
|simplify|简单解释|
|compare|比较|

---

# 6. Ambiguity Detection Agent


这是你们系统体验提升最大的部分。


---

## 6.1 判断问题完整度


输入：

```
链表
```


分析：


候选任务：

```
学习概念 35%

写代码 25%

插入删除 20%

考试复习 20%

```


不确定：

高


↓

需要澄清。


---

输入：

```
链表插入怎么实现

```


候选：

```
代码实现 80%

概念 20%

```


无需澄清。


---

# 6.2 不确定性计算


可以使用：

Entropy


公式：


\[
H(X)=-\sum p(x)logp(x)
\]


例如：


低熵：

```
代码实现 90%

解释 10%

```

无需询问。


高熵：

```
学习 40%

复习30%

代码30%

```

询问。


---

# 7. Clarification Agent


## 目标

不是问：

> 请重新描述问题


而是：

减少最大不确定性。


---

例如：


学生：

```
排序
```


生成：

```
你想了解哪方面？

A. 常见排序算法原理

B. C++排序代码实现

C. 排序算法复杂度比较

D. 考试复习重点

```


---

# 8. Query Rewrite Agent


这是 RAG 前的重要步骤。


---

## 原始输入


学生：

```
为什么这个成立
```


问题：

无法检索。


---

结合上下文：


```
教材：

离散数学

当前章节：

集合关系

选中文字：

等价关系具有传递性

```


Rewrite:


```
解释等价关系为什么具有传递性
```


---

输出：

```json
{
original_query:
"为什么这个成立",

rewrite_query:
"解释等价关系传递性的证明过程",

retrieval_keywords:
[
"等价关系",
"传递性",
"证明"
]

}

```


---

# 9. Task Planner Agent


负责决定下一步。


例如：

Intent:

```
concept_learning
```


Planner：


```json
{

steps:
[
"retrieve textbook",
"generate explanation",
"add example",
"check understanding"
]

}

```


---

如果：

debug


```json
{
steps:
[
"retrieve code context",
"analyze error",
"provide fix"
]

}

```

---

# 10. Router Agent


最终路由。


---

输入：

```json
{
intent:"code_debug",
topic:"链表",
need_rag:true
}

```


输出：

```json
{

agent:

"ProgrammingTutorAgent",

tools:
[
"CodeInterpreter",
"TextbookRetriever"
]

}

```


---

# 11. 与现有系统连接


你们已有：

## CurrentLearningTask


现在：

增加：

```json
{
current_intent:
"learn_new",

current_goal:
"understand",

current_problem:
"不会理解next指针"

}

```


---

## RAG


之前：

```
用户问题

↓

Embedding

↓

Retriever

```


修改：

```
用户问题

↓

Intent Understanding

↓

Query Rewrite

↓

Retriever

↓

RAG

```


---

## 用户画像


增加：

```
student_learning_state

```


例如：

```
学生连续5次询问：

指针

↓

系统判断：

pointer concept weak

↓

后续自动增加图示

```


---

# 12. 技术选型


## Agent框架

推荐：

### LangGraph


原因：

你们不是聊天机器人。

而是：

状态机。


流程：

```
Intent

↓

Condition

↓

Router

↓

Agent

```


非常匹配。


---

## LLM


支持：

- GPT
- Qwen
- DeepSeek


---

## Structured Output


推荐：

Pydantic。


---

# 13. 第一版代码结构


建议：

```
backend/

agent/

 ├── intent/
 │
 │   ├── intent_agent.py
 │   ├── ambiguity_agent.py
 │   ├── rewrite_agent.py
 │
 ├── router/
 │
 │   └── router_agent.py
 │
 ├── memory/
 │
 │   └── student_state.py
 │
 └── workflow/

     └── graph.py

```


---

# 14. V1实现范围


不要一开始做全部。


第一版：

实现：


✅ Intent Agent

✅ Router Agent

✅ Query Rewrite

✅ Clarification


暂时不做：

❌ 自动知识评估

❌ 长期学习画像


---

# 15. 下一阶段（继续设计）

下一部分我建议继续整理：

**《Intent Understanding Engine Prompt 工程设计》**

包括：

1. Intent Agent System Prompt  
2. Ambiguity Agent Prompt  
3. Query Rewrite Prompt  
4. Router Prompt  
5. Few-shot 示例设计  
6. 如何用教材章节增强意图识别  
7. 如何评估意图识别效果（测试集设计）


这一部分会直接影响你们后面模型回答质量。你们项目如果想达到“像老师一样教学”，Prompt + State + Intent 三部分必须一起设计。

# User
继续

# Assistant
继续，我们进入 **DeepTutor Agent 学生意图理解引擎 v1.0 —— Prompt 工程与评估设计部分**。

这一部分非常关键，因为前面的架构决定“有哪些能力”，但是 Prompt 和数据设计决定“这个 Agent 到底聪不聪明”。

---

# 16. Intent Understanding Engine Prompt 设计

## 16.1 设计原则

普通 ChatGPT：

> 根据用户问题回答。


教学 Agent：

> 先理解学生当前学习任务，再决定教学策略。


所以 Intent Agent 的 Prompt 不应该：

```
判断用户的问题属于什么类别
```

而应该：

```
你是一名教学智能体中的学生意图分析模块。

你的任务不是回答学生问题，而是分析：
1. 学生想完成什么学习任务？
2. 当前涉及什么知识点？
3. 学生可能遇到什么困难？
4. 是否需要进一步询问？
5. 下一步应该调用什么教学能力？
```

---

# 17. Intent Agent System Prompt


## Prompt模板


```
你是 DeepTutor Agent 的学生意图理解模块。


你的职责：

分析学生输入，并生成结构化学习意图。


请不要直接回答学生。


你需要分析：

【1. 用户行为】
判断学生当前行为：

- 学习新知识
- 请求解释
- 请求举例
- 请求代码
- 调试代码
- 做题
- 复习总结
- 比较知识点
- 继续学习


【2. 知识定位】

识别：

课程：
章节：
知识点：


【3. 学习目标】

判断：

学生希望：

- 理解概念
- 掌握方法
- 完成任务
- 解决错误
- 准备考试


【4. 信息完整性】

判断：

当前输入是否足够回答。


如果不足：

生成最有效澄清问题。


【5. 教学策略】

判断：

应该：

- 直接解释
- 结合教材
- 举例
- 代码演示
- 反问引导


输出 JSON。

```

---

# 18. Few-shot 示例设计

LLM 的意图识别效果，很大程度依赖 Few-shot。


不要只给类别。

应该给：

输入 → 分析过程 → 输出。


---

## 示例1：简单问题


输入：

```
什么是链表
```


输出：

```json
{
"intent":
"concept_explanation",

"topic":
"数据结构",

"knowledge_point":
"链表",

"goal":
"understand",

"need_clarification":
false,

"teaching_strategy":
[
"basic_explanation",
"visual_example"
]

}
```


---

## 示例2：模糊问题


输入：

```
链表
```


输出：


```json
{
"intent":
"unknown",

"confidence":
0.35,

"need_clarification":
true,

"clarification":

"你想了解链表的哪部分？
1.基本概念
2.C++实现
3.插入删除操作
4.考试重点"

}

```

---

## 示例3：结合上下文


历史：

```
学生：
什么是节点

AI：
介绍节点

学生：
那next呢
```


当前：

```
next
```


输出：

```json
{
"intent":
"concept_explanation",

"topic":
"链表",

"knowledge_point":
"节点next指针",

"context_dependency":
"high"

}

```


---

# 19. Ambiguity Agent Prompt


## 作用

判断：

> 这个问题是否需要问学生？


---

Prompt：


```
你是教学系统中的歧义检测模块。


分析学生输入。


如果存在多个合理解释：

1. 列出可能意图
2. 给出概率
3. 判断是否需要澄清


原则：

如果80%以上概率可以确定，
直接回答。

如果多个方向概率接近，
生成澄清问题。


```


---

# 20. 澄清问题生成策略


不要让 LLM 自由发挥。


设计模板。


---

## 类型1：知识方向


学生：

```
Transformer
```


模板：

```
你想了解 Transformer 哪方面？

A. 基本原理
B. 网络结构
C. Attention机制
D. 代码实现
```


---

## 类型2：难度


学生：

```
讲一下神经网络
```


模板：


```
你的学习目标是：

A. 入门理解
B. 数学推导
C. 代码实现
D. 考研复习
```


---

## 类型3：任务


学生：

```
帮我看看
```


模板：

```
请发送：

A. 代码
B. 题目
C. 报错信息
D. 教材内容
```


---

# 21. Query Rewrite Prompt


这个针对 RAG。


Prompt：

```
你是教材检索优化模块。


你的任务：

将学生自然语言问题转换为适合教材检索的问题。


要求：

1. 保留核心知识点
2. 补充上下文缺失信息
3. 使用教材专业术语
4. 不改变学生真实意图


输入：

学生问题：
{{query}}

学习上下文：
{{context}}

输出：

{
rewrite_query:"",
keywords:[]
}

```


---

案例：


学生：

```
这个为什么
```


上下文：

```
数据库
关系代数
除法运算
```


生成：


```
关系代数中除法运算满足条件限制的原因
```


---

# 22. Router Agent Prompt


作用：

决定调用哪个 Agent。


Prompt：

```
你是教学任务调度器。


根据：

学生意图
学习状态
知识位置


选择最佳处理模块。


可选：

TeacherAgent
RAGAgent
CodingAgent
ExerciseAgent
EvaluationAgent
ClarificationAgent


输出：

{
agent:"",
reason:"",
tools:[]
}

```


---

# 23. 如何让 Agent 更像老师？

重点增加：

## Teaching Strategy


不要只输出：

```json
intent
```


增加：

```json
teaching_plan

```


例如：

学生：

```
什么是递归
```


输出：


```json
{

teaching_plan:
{

first:
"生活例子解释",

second:
"数学定义",

third:
"代码实现",

fourth:
"练习检查"

}

}

```


---

这一步非常重要。

因为：

优秀老师不是知道答案。

而是知道：

> 应该怎么教。


---

# 24. 评估体系设计


意图识别不能靠感觉。


需要测试集。


---

## Intent Accuracy


例如：

1000个学生问题。


人工标注：


真实：

```
code_debug
```


模型：

```
code_generation
```


错误。


计算：

Accuracy

F1


---

# 25. 教育场景特殊指标


## 1. Clarification Rate


澄清率。


公式：

```
需要澄清的问题中，
系统主动澄清比例
```


---

## 2. Wrong Answer Avoidance


错误回答避免率。


例如：

学生：

```
排序
```


系统：

直接讲冒泡排序。


错误。


应该：

询问。


---

## 3. Teaching Alignment


教学一致性。


评价：

是否符合：

- 学生水平
- 当前章节
- 学习目标


---

# 26. 构建测试集


建议你们建立：

## Student Intent Benchmark


来源：

### 1. 真实学生问题


例如：

数据库：

```
除法怎么理解
```

数据结构：

```
next是什么
```

机器学习：

```
为什么梯度下降会收敛
```


---

### 2. 人工构造


覆盖：


|类型|数量|
|-|-:|
|明确问题|200|
|模糊问题|200|
|上下文问题|200|
|连续追问|200|
|错误表达|200|

---

总：

1000条。


---

# 27. 和 RAG 的结合优化


这里特别强调：

你们之前讨论教材 RAG。


意图识别层必须输出：

```json
{
need_textbook:true,

chapter:"第三章",

knowledge_point:"关系代数除法",

retrieval_mode:
"precise"

}

```


否则 Retriever 不知道：

该怎么搜。


---

# 28. 最终完整链路


最终：

```
学生输入

↓

Student Intent Engine

↓

{
intent,
topic,
goal,
difficulty,
state,
need_clarification
}

↓

Query Rewrite

↓

Retriever

↓

Teaching Planner

↓

Response Generator

↓

Learning Memory Update

```

---

# 29. 下一步建议

下一部分我们继续设计：

## 《DeepTutor Agent 意图理解引擎后端实现方案》

会具体到：

1. LangGraph 工作流代码结构  
2. Agent 节点如何写  
3. State 如何设计  
4. Pydantic Schema  
5. FastAPI 接口设计  
6. Redis / PostgreSQL 保存学生状态  
7. 如何和你们现有 CurrentLearningTask、RAG、用户画像连接  


这一部分就可以直接进入开发阶段。

# User
继续

# Assistant
继续进入 **《DeepTutor Agent 学生意图理解引擎后端实现方案》**。

这一部分开始从设计转向工程落地，目标是：

> 开发人员拿到这个设计，可以直接开始写代码。

---

# 30. 后端整体技术架构

结合你们目前：

- Python
- FastAPI
- RAG
- 教材知识库
- 用户画像
- CurrentLearningTask

推荐架构：

```text
                 Frontend
                    |
                    |
              FastAPI API
                    |
                    ↓

        Student Intent Service

                    |
     ┌──────────────┼───────────────┐
     ↓              ↓               ↓

Intent Agent   Memory Agent   Context Agent


                    ↓

             LangGraph Workflow


                    ↓

          Task Planning Router


     ┌──────────┬──────────┬──────────┐
     ↓          ↓          ↓

 Textbook    Tutor       Tool
 RAG Agent   Agent       Agent


                    ↓

             Response Agent


                    ↓

            Memory Update

```

---

# 31. 为什么选择 LangGraph

你们这个项目不适合简单：

```python
answer = llm.invoke(question)
```


因为流程存在：

条件判断：

```text
如果问题明确
    ↓
回答

如果问题模糊
    ↓
询问

如果需要教材
    ↓
RAG

如果代码问题
    ↓
代码Agent

```


这本质是：

**State Machine（状态机）**

而 LangGraph 就是为这种场景设计。

---

# 32. LangGraph 状态设计

核心：

所有 Agent 共享一个状态。


例如：

```python
from typing import TypedDict


class TutorState(TypedDict):

    # 用户输入
    query:str


    # 对话历史
    history:list


    # 用户信息
    student_id:str


    # 当前学习任务
    current_task:dict


    # 意图结果
    intent:dict


    # 是否需要澄清
    need_clarification:bool


    # 重写后的查询
    rewritten_query:str


    # 检索结果
    documents:list


    # 最终答案
    response:str

```

---

# 33. Intent Agent 实现


目录：

```
agent/

 └── intent/

      ├── intent_agent.py
      ├── schema.py
      └── prompt.py

```


---

## schema.py


定义输出。


```python
from pydantic import BaseModel



class IntentResult(BaseModel):

    primary_intent:str

    secondary_intent:str | None

    topic:str | None

    knowledge_point:str | None


    goal:str


    difficulty:str


    confidence:float


    need_clarification:bool


```

---

# 34. Intent Agent代码结构


```python
class IntentAgent:


    def __init__(self,llm):

        self.llm=llm



    async def run(self,state):


        result = await self.llm.with_structured_output(
            IntentResult
        ).ainvoke(
            self.build_prompt(state)
        )


        state["intent"]=result.model_dump()


        return state

```

---

这里有一个关键点：

不要让 LLM 自己输出 JSON 字符串。


不要：

```python
response = llm.invoke(prompt)

json.loads(response)

```


容易错误。


应该：

```python
structured_output

```


让模型直接符合 Schema。

---

# 35. Ambiguity Agent


目录：

```
agent/

 └── ambiguity/

      ├── detector.py
      └── prompt.py

```


---

输入：

```json
{
query:"链表"
}

```


输出：

```json
{

ambiguity_score:0.82,

possible_intents:
[
"learn",
"code",
"debug"
],

need_clarification:true

}

```

---

# 36. Router Agent


这是整个系统的大脑。


例如：


```python
def router(state):


    intent = state["intent"]


    if intent["need_clarification"]:

        return "clarification"



    if intent["primary_intent"]=="code_debug":

        return "coding_agent"



    if intent["need_rag"]:

        return "rag_agent"



    return "teacher_agent"

```

---

对应 LangGraph：


```python
graph.add_conditional_edges(

"intent",

router,

{

"clarification":
"clarification_agent",

"rag_agent":
"rag",

"teacher_agent":
"teacher"

}

)

```

---

# 37. Query Rewrite Agent


位置：

非常重要。


应该：

```
用户输入

↓

Intent

↓

Rewrite

↓

Retriever

```


而不是：

```
用户输入

↓

Retriever

```


---

代码：


```python
class QueryRewriteAgent:


    async def run(self,state):


        query=state["query"]

        context=state["current_task"]


        result=await llm.invoke(
        prompt
        )


        state["rewritten_query"]=result


        return state

```

---

# 38. Context Agent


作用：

补充：

学生是谁？


读取：

数据库：

```sql
student_state
```


例如：

```json
{
"user":"001",

"course":
"数据结构",

"current_section":
"双向链表",

"weakness":
[
"指针"
]

}

```


---

然后加入 Prompt：


```
学生当前：

初学者

已经学习节点结构

指针理解较弱

请避免直接给复杂代码

```

---

# 39. Student Memory 更新 Agent


回答结束后：

不要结束。


更新：

学生状态。


例如：

学生：

问：

> next是什么


回答之后：

系统记录：

```json
{

knowledge_point:
"next pointer",

interaction:
"asked explanation",

mastery_change:
+0.05

}

```


---

# 40. 数据库设计


## student_profile


长期信息。


```sql
CREATE TABLE student_profile
(
id bigint,

student_id varchar,


major varchar,


learning_preference json,


created_time timestamp

);

```


---

## learning_state


动态状态。


```sql
CREATE TABLE learning_state
(

student_id varchar,


course varchar,


chapter varchar,


knowledge_state json,


weak_points json,


update_time timestamp

);

```

---

## conversation_intent


保存每一次判断。


```sql
CREATE TABLE conversation_intent
(

id bigint,


student_id varchar,


query text,


intent json,


confidence float,


created_time timestamp

);

```

---

# 41. FastAPI接口设计


## 用户发送问题


POST:


```
/api/chat
```


请求：

```json
{

student_id:
"001",

message:
"B+树怎么删除"

}

```


---

内部：

```text
API

↓

Intent Engine

↓

LangGraph

↓

Answer

```

---

返回：

```json
{

answer:
"B+树删除过程..."

learning_state:

{

topic:
"B+树",

mastery:
0.6

}

}

```

---

# 42. 和你们 CurrentLearningTask 集成


你们之前设计：

统一：

CurrentLearningTask


这里非常适合。


新增字段：


```json
{
current_learning_task:

{

course:
"数据库",


chapter:
"索引",


goal:
"理解B+树删除",


intent:
"concept_learning",


difficulty:
"beginner"


}

}

```


---

# 43. 一个完整例子


## 学生输入：

> B+树


---

## Intent Agent


输出：

```json
{
intent:
"unknown",

confidence:
0.35,

need_clarification:
true

}

```

---

## Clarification Agent


返回：

```
你想了解B+树哪方面？

1.基本结构
2.插入删除
3.数据库索引应用
4.代码实现

```


---

学生：

> 数据库索引


---

重新识别：

```json
{

intent:
"concept_learning",

topic:
"数据库",

knowledge_point:
"B+树索引"

}

```

---

Rewrite：

```
数据库系统中B+树索引结构和查询过程

```


---

RAG：

检索教材。


---

Teacher Agent：

根据学生水平解释。


---

Memory：

记录：

```
学生正在学习：
数据库索引

```


---

# 44. 第一版开发任务拆解


## Sprint 1

完成：

### 后端框架

- FastAPI
- LangGraph
- LLM调用


---

## Sprint 2

完成：

- Intent Agent
- Router Agent
- Query Rewrite


---

## Sprint 3

完成：

- Student State
- Memory


---

## Sprint 4

完成：

- Ambiguity
- Clarification


---

# 45. 下一部分

下一步继续整理：

## 《DeepTutor Agent 意图理解引擎训练与优化方案》

重点解决：

1. **怎么让模型越来越懂学生**
2. 如何构建真实学生问题数据集
3. 如何自动生成训练数据
4. 是否需要微调模型
5. RAG + Intent 是否需要联合优化
6. 如何评测“像老师”的程度
7. 参考论文中的 Self-Reflection / Planning / Teacher Agent 方法

这一部分会决定你们项目能不能从“普通聊天机器人”提升到“智能教学 Agent”。

# User
现在我们一开始说的解决用户输入问题这个问题解决了吗

# Assistant
这个问题需要区分一下：**我们前面设计的方案已经覆盖了解决“用户输入问题”的大部分机制，但是还没有完全解决。**

如果按照你最开始提出的问题：

> **如何让大模型更好识别学生输入的问题，以及如何解决学生输入不完全、输入信息不完整、不明确、意图不明确的问题？**

目前设计完成度如下：

|问题|是否解决|对应模块|
|-|-|-|
|学生输入是什么问题？|✅ 基本解决|Intent Agent|
|学生真正想做什么？|✅ 基本解决|Intent + Student State|
|一句话多个含义|✅ 基本解决|Ambiguity Agent|
|输入不完整|✅ 基本解决|Clarification Agent|
|上下文缺失|✅ 基本解决|Context Agent|
|学生表达口语化|✅ 基本解决|Query Rewrite Agent|
|不知道调用哪个能力|✅ 基本解决|Router Agent|
|学生水平不同导致回答不合适|⚠️ 部分解决|Student State|
|长期理解学生|⚠️ 部分解决|Memory Agent|
|像老师一样主动发现问题|❌ 未完全解决|需要教学策略层|

所以目前我们解决的是：

> **让系统理解学生的问题**

但是还没有完全解决：

> **让系统像老师一样理解学生为什么问这个问题，以及学生下一步需要什么。**

---

## 一、回到最初的问题拆解

学生输入问题其实有五个层次：

例如学生输入：

> “链表”

表面看：

```
用户输入：
链表
```

实际上系统需要推理：

---

### 第1层：字面理解

学生说了什么？

```
关键词：
链表
```

这是 NLP 基础。

已经解决：

✅ LLM 本身能力

---

### 第2层：意图理解

学生想干什么？

可能：

```
学习链表
复习链表
写链表代码
问考试重点
解决代码错误
```

解决：

✅ Intent Agent

---

### 第3层：上下文理解

为什么现在问？

例如：

前面：

```
学生：
什么是节点？

AI：
讲节点

学生：
那链表呢？
```

这里：

“链表”

其实意思是：

> 继续学习链表结构


解决：

✅ Conversation Context + CurrentLearningTask

---

### 第4层：缺失信息补全

学生没有说：

- 哪本教材？
- 哪个章节？
- 想了解哪部分？


解决：

✅ Clarification Agent

例如：

学生：

> 链表


系统：

不要回答。

应该：

> 你想学习链表的基本概念，还是 C++ 实现？

---

### 第5层：教学目的推断

这是最难的。


比如：

学生：

> 链表为什么不用数组？


普通 AI：

回答区别。


优秀老师：

知道：

这个学生正在学习线性表。

可能：

刚学完顺序表。

他的真实问题：

> 为什么需要链表这种结构？


所以回答：

应该连接：

顺序表 → 链表产生原因。


这个目前：

⚠️ 还没有完全解决。

需要：

Teaching Strategy Agent。

---

# 二、目前方案解决了多少？

如果按照 AI Agent 能力分层：


## Level 0：普通聊天

```
用户
 ↓
LLM
 ↓
回答
```

你们已经超过。


---

## Level 1：意图识别

```
用户
 ↓
Intent
 ↓
回答
```

已经完成设计。


---

## Level 2：上下文教学 Agent

```
用户
 ↓
Intent
 ↓
Student State
 ↓
RAG
 ↓
回答
```

已经设计。


---

## Level 3：主动教学 Agent

```
用户
 ↓
理解问题
 ↓
理解学生状态
 ↓
判断学生真正困难
 ↓
调整教学策略
 ↓
主动引导
```

目前没有完全设计。

---

# 三、真正还缺一个模块：Student Problem Diagnosis Agent

我认为这是你们项目下一步最应该补充的。


现在：

```
Intent Agent
```

回答：

> 学生想干什么


但是老师还会判断：

> 学生为什么不会？


例如：

学生：

> 快速排序不会


Intent：

```
learn_algorithm
```


但是老师判断：


可能原因：

```
A. 不理解递归
B. 不理解分治
C. 不理解partition
D. 不理解代码
```


所以需要：

```
Student Diagnosis Agent
```


结构：

```
学生输入

↓

Intent Agent

↓

Problem Diagnosis Agent

↓

判断：

知识缺口

错误原因

前置知识缺失

↓

Teaching Planner

↓

回答

```

---

# 四、最终完整学生理解链路应该是


```text
学生输入

    ↓

① Intent Understanding
    我想做什么？

    ↓

② Context Understanding
    我为什么现在问？

    ↓

③ Ambiguity Detection
    信息够不够？

    ↓

④ Problem Diagnosis
    我真正卡在哪里？

    ↓

⑤ Teaching Planning
    应该怎么教？

    ↓

⑥ Response Generation
    输出答案

```


---

# 五、举一个完整例子


学生：

> 为什么这里next为空？


---

普通 ChatGPT：

回答：

> next为空表示没有下一个节点。


---

你们未来系统：

## Intent Agent

识别：

```
code_explanation
```

---

## Context Agent

读取：

```
当前：
数据结构
链表
节点定义
```

---

## Diagnosis Agent

发现：

历史：

```
之前问过：
指针是什么
地址是什么
```

判断：

```
问题根源：
没有理解指针关系
```

---

## Teaching Planner

决定：

不要直接解释next。

先：

1. 回顾节点
2. 解释指针
3. 画链表图
4. 解释NULL


---

这才是真正的智能教学。


---

# 六、所以回答你的问题：

**我们现在设计的方案已经解决了“学生输入不完整、不明确、意图识别”的80%左右问题。**

已经有：

✅ Intent Agent  
✅ Ambiguity Agent  
✅ Clarification Agent  
✅ Context Agent  
✅ Query Rewrite Agent  
✅ Router Agent  


但是还缺：

1. **Student Problem Diagnosis Agent（学生问题诊断）**
   
解决：

> 学生真正不会什么？


2. **Teaching Planner Agent（教学规划）**

解决：

> 应该怎样教？


3. **Adaptive Response Agent（自适应回答）**

解决：

> 根据学生水平调整答案。


---

对于你们 DeepTutor 项目，我建议下一步不是继续扩展 Intent，而是补上：

**“学生问题诊断 + 教学规划”这一层。**

因为这两层才是普通 RAG Agent 和“AI 老师”的核心区别。你们前面做的教材 RAG 解决的是“知识来源”，Intent 解决的是“学生需求”，下一步应该解决“教学决策”。

# User
继续

# Assistant
继续进入：

# 《DeepTutor Agent 学生意图理解引擎训练与优化方案 v1.0》

这一部分解决的问题是：

> 我们设计了 Intent Agent，但是如何让它越来越懂学生？  
> 如何避免它变成一个简单分类器？  
> 如何让它像真正老师一样理解学生？

---

# 46. 核心思想：不要训练“意图分类”，训练“学生任务理解”

传统 NLP：

```
输入文本
    ↓
分类模型
    ↓
intent label
```

例如：

```
"链表怎么插入"

↓

code_help
```

但是教学场景：

同一句话：

> 链表怎么插入

可能对应：

学生A：

> 刚学链表，想理解思想

学生B：

> 考试马上到了，只想背步骤

学生C：

> 写代码报错

所以真正任务：

不是：

```
What is the intent?
```

而是：

```
What learning task is this student trying to complete?
```

---

# 47. 建立 Student Intent Dataset

## 47.1 数据来源


建议三个来源。


---

## 来源1：真实学生对话（最高价值）

你们项目运行后：

保存：

```
用户问题
+
上下文
+
AI回答
+
学生反馈
```


例如：

```json
{
query:
"next是什么",

context:
"正在学习单链表",

answer:
"解释next指针",

feedback:
"还是不懂"

}

```


这种数据价值最高。

---

## 来源2：教材知识自动生成


利用教材：

例如：

章节：

```
第三章 链表
```

让 LLM 生成：

不同学生问法。


例如：

知识点：

```
头节点
```


生成：

初学者：

```
头节点是什么？
```

口语：

```
链表第一个节点有什么特殊？
```

考试：

```
头节点作用是什么？
```

代码：

```
为什么链表要设置head？
```


---

## 来源3：开源教育数据集


可以参考：

### EduChat

教育大模型数据集。


GitHub：

[EduChat GitHub](https://github.com/THUDM/ChatGLM-Edu?utm_source=chatgpt.com)


特点：

包含：

- 教育问答
- 学习辅导
- 作业帮助


---

# 48. Intent 数据格式设计


不要只存：

```
question → intent
```

应该：

```json
{
"query":
"B+树怎么删除",


"student_context":
{

"course":
"数据库",

"level":
"beginner",

"chapter":
"B+树"

},


"intent":

{

"primary":
"concept_learning",

"secondary":
"algorithm_process"

},


"learning_goal":
"understand"


}
```

---

这样以后才能训练。


---

# 49. Intent 标注体系


人工标注时：

不要只标 intent。


建议五层。


---

## Layer 1：学习行为


例如：

```
learn
practice
review
debug
evaluate
```


---

## Layer 2：知识目标


例如：

```
concept
principle
operation
implementation
application
```


---

## Layer 3：学生状态


例如：

```
beginner
intermediate
advanced
```


---

## Layer 4：教学需求


例如：

```
need_example

need_visualization

need_code

need_formula

```


---

## Layer 5：是否需要澄清


例如：

```
clear

ambiguous

incomplete

```


---

最终：

一个样本：

```json
{

intent:
{
action:
"learn",

target:
"principle"

},

level:
"beginner",


teaching_need:
[
"example",
"visual"
],


clarification:
false

}

```

---

# 50. Prompt Optimization

在第一阶段：

不要急着微调。


优先：

Prompt + Few-shot。


原因：

Intent 任务本身：

语义能力要求高。


GPT/Qwen/DeepSeek 这种模型已经有能力。


主要问题：

不是不会分类。


而是不知道：

你们想要什么分类标准。


---

# 51. Prompt 版本迭代


建议：

维护：

```
prompt/

intent_v1.md

intent_v2.md

intent_v3.md

```


每次测试。


例如：

v1：

```
判断用户意图
```


效果：

70%


---

v2：

增加：

```
结合学生学习状态
```


效果：

82%


---

v3：

增加：

```
教学策略输出
```


效果：

90%


---

# 52. Self-Reflection Agent


参考：

Reflexion:
Language Agents with Verbal Reinforcement Learning


论文：

Reflexion: Language Agents with Verbal Reinforcement Learning


核心：

Agent 不直接结束。


而是：

```
生成结果

↓

检查自己

↓

修正
```


---

应用到 Intent：

第一次：

```json
{
intent:
"code_help"
}

```


Reflection：

检查：

```
学生历史：
一直问概念

当前：
没有代码

判断错误
```


修改：

```json
{
intent:
"concept_explanation"
}

```

---

# 53. Intent + RAG 联合优化


很多项目的问题：

Intent 和 RAG 分离。


实际上：

二者应该互相影响。


---

错误流程：

```
用户问题

↓

RAG

↓

回答

```

---

优化：

```
用户问题

↓

Intent

↓

确定知识目标

↓

Query Rewrite

↓

RAG

↓

教学生成

```

---

例如：


学生：

> 除法怎么理解


Intent：

```
concept_explanation
```


所以：

Retriever：

优先：

```
定义
性质
例子
```


而不是：

```
习题答案
```

---

# 54. 引入 Learning Objective


教育领域非常重要。


参考：

Bloom's Taxonomy（布鲁姆教育目标分类）


学生目标分：

```
记忆
理解
应用
分析
评价
创造
```


对应：

AI 教学策略。


---

例如：

学生：

> 什么是索引


目标：

理解


回答：

概念 + 例子。


---

学生：

> 写一个B树索引


目标：

应用


回答：

代码 + 实践。


---

学生：

> 比较B树和B+树


目标：

分析


回答：

对比表。


---

所以 Intent 输出增加：


```json
{
learning_level:
"understand"
}

```

---

# 55. Teaching Strategy Generator


这是让 AI 像老师的重要模块。


Intent 输出：

不要结束。


增加：

教学策略。


例如：


学生：

```
不会理解指针
```


输出：

```json
{

strategy:

[
"使用生活类比",

"画内存结构图",

"给简单代码",

"检查理解"

]

}

```

---

# 56. 自动评估机制


## 1. Intent Accuracy


基本。


---

## 2. Clarification Quality


评价：

澄清是否有效。


例如：

输入：

```
树
```


好：

```
你想了解二叉树还是B树？
```


差：

```
请详细说明
```


---

## 3. Teaching Alignment Score


人工评价：

1-5分。


评价：

AI 是否：

- 符合学生水平
- 符合教材
- 符合学习目标


---

# 57. 是否需要微调？


我的建议：

## 第一阶段

不用。


使用：

GPT/Qwen + Prompt。


---

## 第二阶段

数据积累：

5000-10000条。


考虑：

LoRA 微调。


模型：

例如：

Qwen2.5-7B / Qwen3。


训练任务：

输入：

```
学生问题+上下文
```

输出：

```
Intent JSON
```

---

# 58. Agent训练路线


推荐：


## V1

Prompt Engineering


↓

## V2

Few-shot


↓

## V3

RAG增强


↓

## V4

SFT微调


↓

## V5

Preference Optimization


例如：

DPO：

让模型更偏向：

```
像老师的判断
```


---

# 59. 和你们项目当前功能结合


你们已有：

## 学习入口


增加：

```
Intent Layer
```


---

## 教材RAG


增加：

```
Query Rewrite
```


---

## 用户画像


增加：

```
Learning State
```


---

## 成长评价


增加：

```
Intent History
```


例如：

统计：

学生：

过去一个月：

```
60% 概念问题
30% 编程问题
10% 复习
```


形成学习画像。

---

# 60. 最终成熟架构


完整：

```
                 Student

                    |
                    ↓

        Student Intent Engine


    ┌───────────────┐
    │               │
Intent Agent   Context Agent

    │               │

    └───────┬───────┘

            ↓

    Ambiguity Detector

            ↓

    Query Rewrite Agent

            ↓

    Task Planner

            ↓

       Agent Router


 ┌─────────┬──────────┬──────────┐

RAG     Tutor       Tool

Agent   Agent       Agent


            ↓

       Response


            ↓

 Learning Memory Update

```

---

## 下一部分建议继续：

**《DeepTutor Agent 意图理解引擎与当前项目详细融合方案》**

重点会结合你们之前已经设计的：

- CurrentLearningTask
- 学习/实训/成长/我的四入口
- 教材 RAG
- 标注教练
- 用户画像
- 学习闭环

具体说明：

> Intent Engine 应该插在哪些模块？  
> 哪些已有设计需要修改？  
> 数据结构如何统一？  
> 前后端接口怎么调整？

这一部分会直接对应你们项目 v1.2/v2 的架构优化。
