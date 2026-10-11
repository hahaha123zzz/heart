可以。我会专门围绕**Agent 的 Memory（记忆系统）**进行调研，不讨论意图识别、RAG 检索优化、工具调用等其他模块。

由于这个主题比较大，我会按照“调研报告”的方式分轮输出，每一轮明确当前进度，包括：

- 已调研方向
- 代表项目/论文
- 核心思想
- 技术实现方式
- 对我们「AI 学习 Agent」项目的可借鉴点
- 下一轮计划

我会重点看以下几类：

1. **通用 Agent Memory 架构**
   - MemGPT
   - Generative Agents
   - LangGraph Memory
   - Zep / Graphiti
   - Letta
   - Mem0 等

2. **学习型 Agent 的记忆设计**
   - AI Tutor
   - Personalized Learning Agent
   - Student Modeling
   - Intelligent Tutoring System (ITS)

3. **Memory 技术路线**
   - Conversation Memory（对话记忆）
   - Episodic Memory（经历记忆）
   - Semantic Memory（知识记忆）
   - Procedural Memory（行为策略记忆）
   - User Profile Memory（用户画像）
   - Knowledge Graph Memory（知识图谱记忆）
   - Reflection Memory（反思记忆）
   - Memory Consolidation（记忆巩固）

4. **实现层面**
   - 存储结构
   - 数据库选择
   - 向量数据库
   - Graph Database
   - Memory Write
   - Memory Retrieval
   - Memory Update
   - Memory Forgetting


---

# 调研进度 1/？：Agent Memory 的整体发展路线

## 一、先回答一个核心问题：

> 为什么 Agent 需要 Memory？

传统 ChatGPT：

```
用户输入
    ↓
LLM
    ↓
回答
```

每次都是新的。

问题：

- 不知道用户是谁
- 不知道之前学过什么
- 不知道犯过什么错误
- 不知道长期目标
- 无法持续成长


Agent：

```
用户
 ↓
Agent
 ↓
Memory
 ↓
LLM
 ↓
行动
```

Memory 让 Agent 从：

> “一次性问答机器人”

变成：

> “长期陪伴型智能体”

---

# 二、目前主流 Memory 架构演化

大概经历了 4 个阶段：

---

# Stage 1：简单 Conversation Buffer

时间：
2022 前后


代表：

- LangChain ConversationBufferMemory


思想：

直接保存聊天记录。


例如：

数据库：

```json
[
 {
  "user":"我正在学习数据结构"
 },
 {
  "assistant":"好的，我们学习链表"
 }
]
```


下一次：

直接：

```
历史聊天
+
当前问题
+
LLM
```


## 优点

简单。


## 缺点

巨大问题：

### 1. 无限增长

100轮：

```
token爆炸
```


### 2. 没有重点

比如：

用户说：

> 我喜欢C++


半年以后：

Agent 还需要从几万句话里找。


所以出现第二代。

---

# Stage 2：Summary Memory

核心：

> 不保存所有历史，而是让LLM总结。


例如：

原始：

```
用户：
我正在学习数据结构

用户：
我C++基础已经学完

用户：
希望代码逐行解释

用户：
喜欢教材式学习
```


总结：

```json
{
 "learning_background":
 "用户已经掌握C++基础",

 "learning_style":
 "喜欢教材化、逐行解释",

 "current_goal":
 "学习数据结构"
}
```


架构：

```
历史对话

    ↓

LLM总结

    ↓

Summary Memory

    ↓

下一次Prompt
```


代表：

LangChain early memory


---

问题：

总结会丢信息。


例如：

原始：

```
2026-10-01:
用户链表学习困难

2026-10-05:
用户已经掌握链表
```

总结：

```
用户学习过链表
```


但是：

丢失：

- 曾经哪里不会
- 如何解决
- 教学策略


所以出现第三代。

---

# Stage 3：Retrieval Memory（目前主流）

核心思想：

> Memory 不直接塞给LLM，而是像RAG一样检索。


架构：

```
                 Memory Database

                       |
                       |
用户问题
 ↓
Embedding
 ↓
Memory Retrieval
 ↓
相关记忆
 ↓
LLM
 ↓
回答
```


例如：

用户：

> 给我讲一下树


Memory：

```
用户以前：
- 链表基础较弱
- 喜欢图示
- 需要先讲直观概念

用户目标：
- 数据结构考研
```


检索：

返回：

```
教学风格:
先直观，再代码

知识水平:
链表已经掌握
```


LLM：

自动调整回答。


---

这一阶段代表：

## 1. Generative Agents (Stanford 2023)

论文：

《Generative Agents: Interactive Simulacra of Human Behavior》

核心提出：

### Memory Stream [GitHub](https://github.com/agentpatterns-ai/website/blob/main/patterns/agent-design/generative-agents-memory-stream.md?utm_source=chatgpt.com)




不是简单存储。

而是：

```
Experience

 ↓

Memory Stream

 ↓

Retrieve

 ↓

Reflection

 ↓

New Memory
```


---

## Memory Stream结构


每条记忆：

```json
{
"id":1,

"content":
"用户今天学习了链表插入",

"time":
"2026-10-11",

"importance":
8,

"embedding":
[...]

}
```


三个评分：

---

### 1. Recency

最近发生：

```
昨天学习
>
去年学习
```


---

### 2. Importance

重要程度。


例如：

普通：

```
用户问了一个语法
importance=2
```


重要：

```
用户准备考研
importance=10
```


---

### 3. Relevance

和当前问题相关。


最终：

```
score=

recency

×

importance

×

relevance
```


---

# Reflection（非常重要）


Generative Agent 最大创新：

> Agent 会自己总结过去。


例如：

原始：

```
第1天:
学生不会链表

第2天:
学生理解节点

第3天:
学生完成代码
```


Reflection：

生成：

```
学生已经掌握链表基础，
后续可以进入树结构。
教学方式应该继续采用代码实践。
```


然后保存：

```
Reflection Memory
```


这非常接近：

优秀老师的教学过程。


---

# Stage 4：Hierarchical Memory（现在主流）

代表：

## MemGPT

论文：

《MemGPT: Towards LLMs as Operating Systems》 [arXiv](https://arxiv.org/abs/2310.08560?utm_source=chatgpt.com)



核心思想：

把LLM看成操作系统。


类似：

计算机：

```
CPU
 |
高速缓存
 |
内存
 |
硬盘
```


Agent：

```
LLM Context

    ↑

Working Memory

    ↑

Recall Memory

    ↑

Archive Memory
```


---

## MemGPT 三层


### 1. Main Context

当前正在使用：

```
最近聊天
当前任务
```


类似：

RAM


---

### 2. Recall Memory


最近历史：

例如：

```
上一次学习内容
```


---

### 3. Archival Memory


长期保存：

例如：

```
用户学习记录
长期目标
能力变化
```


---

工作流程：

用户：

```
讲一下二叉树
```


Agent：

先检查：

```
Working Memory
```


没有。


调用：

```
Recall Memory
```


找到：

```
用户已经掌握链表
```


继续：

```
可以从链表和树的区别开始
```


---

# 第一轮总结

目前 Agent Memory 主流思想：

|阶段|方法|问题|
|-|-|-|
|Buffer|保存全部聊天|爆token|
|Summary|总结历史|丢细节|
|Retrieval Memory|检索重要记忆|需要设计检索|
|Hierarchical Memory|分层管理|目前主流|

---

# 对我们「学习 Agent」最重要的启发

结合你的项目（教材约束 AI 教学 Agent），Memory 不应该只是：

> 保存聊天记录


而应该设计成：

```
Student Memory System
```


至少包括：

```
学生画像
    |
    |
学习经历 Memory
    |
    |
知识掌握 Memory
    |
    |
错误 Memory
    |
    |
学习策略 Memory
    |
    |
成长轨迹 Memory
```


例如：

学生A：

```
姓名:
xxx

专业:
大数据

当前课程:
数据结构


已掌握:
数组
链表


薄弱:
递归


学习方式:
喜欢图示+代码


历史错误:
把next理解错误


目标:
考研
```


这比普通聊天Memory复杂很多。

---

## 当前调研完成度：

✅ Agent Memory 基础架构演化  
✅ Generative Agents Memory Stream  
✅ MemGPT 分层Memory  
✅ Retrieval Memory思想  


---

下一轮我准备深入：

**第二轮：重点分析学习类 Agent（AI Tutor / Intelligent Tutoring System）如何设计学生记忆**

重点看：

- 学生模型（Student Model）
- Knowledge Tracing（知识追踪）
- Bayesian Knowledge Tracing
- Deep Knowledge Tracing
- AI Tutor 如何判断“学生会不会”
- 如何记录学习状态
- 如何根据历史调整教学策略

这一部分会直接对应你们项目里的：

> “学生闭环、用户画像、学习成长、个性化教学”


我下一轮继续。


# 调研进度 2/？：学习型 Agent 的 Memory —— 从「聊天记忆」到「学生知识状态记忆」

本轮重点：

> 不再讨论通用 Agent Memory，而是研究**教育领域 Agent（AI Tutor / Intelligent Tutoring System）如何理解和保存“学生”这个人的状态**。

这一部分对你的项目非常关键，因为你的目标不是普通聊天机器人，而是：

> 一个长期陪伴学生学习，根据学生历史调整教学策略的 AI 老师。


---

# 一、先明确一个区别

普通 Agent Memory：

> “记住用户说过什么”

例如：

```
用户：
我是大二学生

Memory:
用户是大二学生
```


---

学习 Agent Memory：

> “理解学生现在会什么，不会什么，为什么不会，应该怎么教”

例如：

```
学生：
二叉树不会


普通Memory:
用户问过二叉树


学习Memory:
学生:
- 链表掌握程度 80%
- 指针理解良好
- 递归薄弱
- 树节点结构概念缺失
- 适合图示教学
- 不适合直接源码教学

教学策略:
先讲树和链表关系
再进入代码
```

这实际上对应教育领域几十年的研究：

## Student Model（学生模型）

---

# 二、教育 Agent 的核心 Memory：Student Model

传统 Intelligent Tutoring System（ITS）一般有四个模块：

```
                教学系统


        Domain Model
        （知识模型）

             |
             |

Student Model
（学生模型）

             |

Pedagogical Model
（教学策略）

             |

Interface
（交互）
```

其中：

**Student Model 就是 Memory。**


---

# 三、Student Model 里面存什么？

目前主流分成 5 类。


---

# 1. Knowledge State Memory（知识掌握记忆）

这是教育 Agent 最核心的。


目标：

回答：

> 学生到底掌握了哪些知识？


例如数据结构：

```
数据结构知识图谱


数组
 |
链表
 |
栈
 |
队列
 |
树
 |
图
```


学生状态：

```json
{
"数组":{
 mastery:0.9
},

"链表":{
 mastery:0.8
},

"递归":{
 mastery:0.3
},

"树":{
 mastery:0.2
}
}
```


这个方向叫：

## Knowledge Tracing（知识追踪）


---

# 四、Knowledge Tracing 的发展


## 1. Bayesian Knowledge Tracing（BKT）

1994提出。


核心：

把学生知识看成概率。


例如：

刚开始：

```
学生掌握概率:

链表:
30%
```


做一道题：

答对：

更新：

```
链表:
55%
```


再答：

```
75%
```


类似：

贝叶斯更新。


公式思想：

```
P(掌握|新证据)

=
根据旧状态
+
学习行为
更新
```


优点：

可解释。


缺点：

简单。


---

# 2. Deep Knowledge Tracing（DKT）


2015 Stanford 提出。


论文：

《Deep Knowledge Tracing》

核心：

用 RNN 记录学生学习过程。[arXiv](https://arxiv.org/abs/1506.05908?utm_source=chatgpt.com)


以前：

人工设计：

```
链表掌握程度
树掌握程度
```


DKT：

直接输入：

```
学生历史行为序列

↓

RNN

↓

隐藏状态

↓

当前知识状态
```


例如：

输入：

```
第1次:
链表题 √


第2次:
链表删除 ×


第3次:
指针题 √
```


模型学习：

```
隐藏状态:

链表:
0.82

指针:
0.65
```


---

结构：

```
学习行为

(question, answer)

       ↓

     RNN


       ↓


Student Knowledge State

       ↓

预测下一题正确率
```


---

# 五、Memory Network：把学生知识变成“可读写Memory”

这是对 Agent 最有启发的部分。


代表：

## DKVMN

Dynamic Key-Value Memory Network

2017。


论文：

《Dynamic Key-Value Memory Networks for Knowledge Tracing》[arXiv](https://arxiv.org/abs/1611.08108?utm_source=chatgpt.com)


它提出：

学生知识不是一个向量。

而是：

一个 Memory。


---

结构：

```
Memory


Key Memory

+
Value Memory

```


---

## Key Memory

存：

知识概念。


例如：

```
Key:


M1:
数组


M2:
链表


M3:
递归


M4:
树

```


---

## Value Memory

存：

学生当前掌握程度。


例如：

```
Value:


M1:
0.9


M2:
0.8


M3:
0.3


M4:
0.2

```


---

如果学生学习：

```
链表删除
```


系统：

找到：

```
Key:
链表

↓

更新Value

0.8 → 0.85

```


这其实已经非常接近：

Agent Memory。


---

# 六、现代研究：Hierarchical Memory（层级学生记忆）

最近教育领域也开始借鉴 Agent Memory。


例如：

Hierarchical memory-enhanced knowledge tracing。

核心：

认为学生记忆不是一层。


而是：

```
短期记忆

↓

长期知识

```


论文提出：

- shallow memory
- deep memory

模拟：

学习增长

遗忘衰减

知识沉淀 [科学直接](https://www.sciencedirect.com/science/article/pii/S0167865526000036?utm_source=chatgpt.com)



---

类似人脑：

刚学：

```
昨天学链表
```


短期：

```
链表删除步骤
```


经过练习：

长期：

```
理解链表思想
```


---

# 七、AI Tutor Agent 如何利用 Memory？

现在结合 LLM Agent。


典型流程：

```
学生提问


↓

Memory Retrieval


↓

获取学生状态


↓

LLM生成回答


↓

更新Memory

```


---

举例：


学生：

> 为什么二叉树遍历这么难？


系统先查：

Student Memory：

```
知识:

链表:
80%

递归:
30%

树:
20%


历史:

曾经问过递归


学习偏好:

喜欢图示

```


Agent 推理：

```
问题不是树

根因:
递归基础不足

```


回答：

```
不要直接讲树遍历

先复习递归调用栈

然后映射到树
```


这就是：

**Memory → Teaching Strategy**

---

# 八、目前学习 Agent Memory 的核心设计模式


总结：

## 第一层：用户画像 Memory

回答：

> 这个学生是谁？


存：

```
专业
年级
目标
学习习惯
```


---

## 第二层：Learning History Memory

回答：

> 他学过什么？


存：

```
课程
章节
时间
行为
```


---

## 第三层：Knowledge State Memory

回答：

> 他会不会？


存：

```
知识点 mastery
```


---

## 第四层：Error Memory

回答：

> 他哪里容易错？


例如：

```
错误:

把next理解成地址

原因:

指针概念弱


解决方式:

图示解释
```


---

## 第五层：Teaching Strategy Memory

回答：

> 怎么教他最有效？


例如：

```
避免:
直接源码


采用:
案例+图示+代码
```


---

# 九、对你们项目的直接启发

结合你之前的 DeepTutor Agent：

目前很多项目容易做成：

```
聊天记录Memory
+
RAG教材
```


但是学习 Agent 应该升级：

```
                 Student Memory


        用户画像

            |

        学习轨迹

            |

        知识状态

            |

        错题/误解

            |

        教学策略

```


---

# 推荐你的项目 Memory 架构（初步）


数据库：

## Student Profile

```sql
student_profile

id

major

grade

goal

learning_style

```


---

## Learning Event

记录行为：

```json
{
"time":"2026-10-11",

"chapter":"链表",

"action":"ask_question",

"difficulty":"medium",

"result":"understand"
}
```


---

## Knowledge State


```json
{
"linked_list":

{
mastery:0.8,

confidence:0.7,

last_learned:"2026-10-10"
}

}
```


---

## Error Memory


```json
{
concept:"pointer",

error:
"next理解错误",

frequency:3,

solution:
"使用图示"
}
```


---

# 本轮完成情况

✅ 学习 Agent Memory 与普通 Agent Memory 区别  
✅ Student Model 理论  
✅ Knowledge Tracing 体系  
✅ BKT  
✅ DKT  
✅ DKVMN Key-Value Memory  
✅ Hierarchical Student Memory  
✅ 对 DeepTutor 类项目的映射


---

# 下一轮计划（3/？）

下一轮我准备调研：

## 「真正基于 LLM 的学习 Agent Memory 实现」

重点：

1. **Mem0**
   - LLM Memory 如何自动抽取事实
   - Memory Write 怎么做

2. **Zep / Graphiti**
   - 时间知识图谱 Memory
   - 为什么适合长期学习记录

3. **Letta（MemGPT 开源实现）**
   - Memory 管理代码结构

4. **LangGraph Agent Memory**
   - 工程实现方式

5. 最后整理：
   
> 如果我们实现 DeepTutor 的学生 Memory，应该复用哪些开源方案，哪些需要自己设计。


下一轮进入工程实现层。


# 调研进度 3/？：LLM Agent 长期记忆系统的工程实现（Mem0、Letta、Zep/Graphiti）

本轮重点：

> 从理论上的 Student Model，进入现在主流 Agent Memory 框架的真实实现。

核心问题：

1. Agent 怎么决定**哪些信息值得记忆**？
2. Memory 怎么写入？
3. Memory 怎么更新？
4. Memory 怎么检索？
5. 这些方案能不能用于 DeepTutor / AI 学习 Agent？


本轮调研对象：

- Mem0
- Letta（原 MemGPT）
- Zep / Graphiti

---

# 一、先建立一个统一认识

现在主流 Agent Memory 基本都不是：

```
聊天记录数据库
```

而是：

```
Memory Pipeline
```

即：

```
用户输入

 ↓

Memory Extraction
（提取值得保存的信息）

 ↓

Memory Storage
（结构化存储）

 ↓

Memory Retrieval
（需要时召回）

 ↓

Context Assembly
（拼入LLM）

 ↓

Memory Update
（更新旧状态）
```

---

# 二、Mem0：目前最工程化的 Memory Layer

GitHub：

[Mem0 GitHub Repository](https://github.com/mem0ai/mem0?utm_source=chatgpt.com)


定位：

> 给任何 LLM Agent 增加长期记忆能力。


它解决的问题：

传统聊天：

```
conversation history

越来越长

↓

token爆炸
```

Mem0：

```
conversation

↓

memory extraction

↓

短小、高价值记忆
```

---

# 1. Mem0 的核心思想

一句话：

> 不保存对话，而保存“事实”。

例如：

用户：

```
我是一名大二学生，
正在学习数据结构，
喜欢代码逐行解释。
```

不会保存：

```
用户说：
xxxx
```

而抽取：

```json
{
"user":"student",

"fact":
"用户正在学习数据结构",

"type":
"learning_goal"
}
```


再比如：

用户：

```
我昨天终于理解链表插入了
```

Memory:

```json
{
"concept":
"链表插入",

"status":
"mastered",

"time":
"2026-10-10"
}
```

---

# 2. Memory Write 流程


大概：

```
Conversation

      |

      v

LLM Extractor

      |

      v

Candidate Memories

      |

      v

Deduplication

      |

      v

Update Existing Memory

      |

      v

Database
```


---

## 举例


已有：

```json
{
"linked_list":
"用户不理解next指针"
}
```


新对话：

```
我现在理解next指针了
```


不是新增：

```json
[
旧问题,
新理解
]
```


而是：

Update：

```json
{
"linked_list":

{
"pointer_understanding":
"good"

}
}
```


---

# 3. Memory Retrieval

不是全部取。


例如：

用户：

```
给我讲树
```


Memory搜索：

关键词：

```
树
```

找到：

```
用户:
链表已经掌握

用户:
递归薄弱

用户:
喜欢图示
```


返回：

```json
{
knowledge_level:

{
linked_list:0.8,
recursion:0.3
},

style:
visual
}
```


---

# 4. Mem0 的存储结构


它本质：

多级 Memory：

官方也强调：

- User Memory
- Session Memory
- Agent Memory [GitHub](https://github.com/mem0ai/mem0?utm_source=chatgpt.com)



可以理解：


## User Memory

长期：

```
姓名
专业
学习目标
习惯
```


---

## Session Memory

当前：

```
今天正在学习:
二叉树
```


---

## Agent Memory

Agent自身：

```
回答风格
工具使用经验
```


---

# 对学习 Agent 的启发


Mem0 很适合：

## 自动抽取学生事实


例如：

学生聊天：

```
为什么递归这里return？
```


Memory系统自动发现：

```
学生可能递归理解不足
```


保存：

```json
{
"weakness":

"recursion",

"evidence":

"multiple recursion questions"
}
```


---

# 三、Letta（MemGPT）：把 Memory 当操作系统

GitHub：

[Letta GitHub Repository](https://github.com/Learn2Solve/memgpt?utm_source=chatgpt.com)


论文：

MemGPT:

《MemGPT: Towards LLMs as Operating Systems》


核心思想：

> LLM Context 就像电脑 RAM，Memory 就像硬盘。


---

# 1. 为什么提出这个？

LLM最大限制：

Context Window。


例如：

模型：

128k token。


但是长期用户：

一年聊天：

100万token。


怎么办？


MemGPT：

模拟操作系统：

```
CPU

↓

RAM

↓

SSD
```


对应：

```
LLM Context

↓

Working Memory

↓

Long-term Memory
```

---

# 2. Letta Memory 三层结构


## 第一层：Core Memory


永远放在 Prompt。


类似：

CPU缓存。


例如：

```
Human:

用户是大二学生

正在学习数据结构


Persona:

你是一名耐心老师
```


特点：

小，但是高价值。


---

## 第二层：Recall Memory


历史对话。


例如：

```
10月1日：
学习链表


10月5日：
完成链表代码
```


需要搜索。


---

## 第三层：Archival Memory


长期知识。


例如：

```
用户所有学习记录
错误记录
成长记录
```


---

结构：

```
              LLM

               |

        Core Memory

               |

        Recall Memory

               |

       Archival Memory
```


---

# 3. 最大创新：Agent 自己管理 Memory


普通系统：

程序决定：

```
什么时候保存
保存什么
```


MemGPT：

Agent 可以调用工具：

例如：

```
save_memory()

search_memory()

update_memory()
```


让 Agent 自己决定：

```
这个重要，需要保存
```


---

# 对学习 Agent 的启发


非常适合：

教师型 Agent。


例如：

学生说：

```
我终于理解指针了
```


Agent判断：

这是重要学习事件：

调用：

```
save_memory()
```


保存：

```
学生突破：
指针概念
```


未来：

遇到链表：

主动调用。

---

# 四、Zep / Graphiti：知识图谱 Memory

GitHub：

[Graphiti GitHub Repository](https://github.com/Memory-Agents/graphiti/?utm_source=chatgpt.com)


这是目前非常热门方向。


核心：

> 不把 Memory 看成文本，而看成不断变化的关系网络。


---

# 1. 为什么需要图？

传统 Memory：

```
用户喜欢图示解释
```


但是复杂关系：

不好表示。


学习场景：

例如：

```
学生

↓

学习

↓

课程

↓

章节

↓

知识点

↓

错误

↓

解决方案

```


天然图结构。


---

# 2. Graphiti Memory结构


核心：

Node：

实体


例如：

```
学生A

链表

指针

数据结构课程

```


Edge：

关系：

```
学生A

--不会-->

指针


学生A

--学习-->

链表
```


---

例如：

```
          数据结构

              |

            链表

              |

           指针

              |

学生A ------薄弱
```


---

# 3. 时间因素


这是 Graphiti 最大特点。


普通KG：

```
学生会链表
```


但是：

学习过程中变化：

```
10月1日

学生不会链表


10月10日

学生掌握链表
```


Graphiti：

保存时间：

```
Relation:

学生A --不会--> 链表

valid:
10.1-10.5


学生A --掌握--> 链表

valid:
10.6-
```


支持动态变化。[GitHub](https://github.com/Memory-Agents/graphiti/?utm_source=chatgpt.com)

---

# 4. Retrieval


不是简单向量搜索。


而是：

混合：

```
Vector Search

+

Keyword Search

+

Graph Traversal
``` :chatgpt-content-reference{index="5"}




例如：

问题：

```
为什么我不会二叉树？
```


搜索：

找到：

```
学生A

↓

递归薄弱

↓

树遍历困难

↓

之前错误:
递归调用栈理解错误
```


推理能力更强。


---

# 五、三个方案比较


| |Mem0|Letta|Graphiti|
|-|-|-|-|
|定位|Memory基础设施|Agent操作系统|知识图谱Memory|
|核心|事实抽取|分层管理|关系建模|
|Memory形式|JSON事实|Block+Archive|Graph|
|自动更新|强|强|强|
|适合个人画像|⭐⭐⭐⭐⭐|⭐⭐⭐⭐|⭐⭐⭐⭐|
|适合学习轨迹|⭐⭐⭐⭐|⭐⭐⭐⭐⭐|⭐⭐⭐⭐⭐|
|复杂关系|⭐⭐⭐|⭐⭐⭐|⭐⭐⭐⭐⭐|

---

# 六、如果做 DeepTutor，我认为不能直接照搬一个

应该组合：


```
                 Student Memory


          用户画像
              |
            Mem0思想


              |

        学习状态模型
              |
        Knowledge Tracing


              |

       学习关系图谱
              |
        Graphiti思想


              |

       Agent Memory管理
              |
          Letta思想

```


---

# 七、对应你的项目设计（初步方案）


## Memory 数据层


### 1. Profile Memory

数据库：

MySQL


保存：

```json
{
major:
"大数据",

goal:
"考研",

style:
"喜欢图示"
}
```


---

### 2. Knowledge Memory


图数据库：

Neo4j


例如：

```
学生

学习

知识点

掌握程度

错误
```


---

### 3. Event Memory


向量数据库：

Milvus / Qdrant


保存：

```
学习事件

提问

错题

突破
```


---

### 4. Strategy Memory


保存：

```
怎样教这个学生有效
```


---

# 本轮调研完成度

✅ Mem0 工程实现思想  
✅ Memory Extraction  
✅ Memory Update  
✅ Letta/MemGPT 三层Memory  
✅ Agent主动管理Memory  
✅ Graphiti时间知识图谱Memory  
✅ 三种方案比较  
✅ 映射到 DeepTutor 架构


---

# 下一轮（4/？）计划：

重点研究：

## 「学习 Agent 如何实现 Memory + 教学决策闭环」

也就是：

Memory 有了以后：

**Agent 如何决定下一步怎么教？**

重点：

1. Reflection Memory（反思记忆）
2. Self-Reflection Agent
3. Voyager Agent 的 Skill Memory
4. SWE-Agent / AutoGPT 的经验记忆
5. AI Tutor 中：
   - 学习诊断
   - 个性化路径规划
   - 遗忘机制
   - 学习反馈循环


这一轮会直接对应你之前项目里的：

> 学习闭环、成长页、AI 教学引导、学生状态追踪。

# 调研进度 4/？：Memory 如何驱动 Agent 教学决策 —— 从“记住学生”到“会教学生”

本轮重点：

前面三轮解决：

- **Memory 为什么需要存在**
- **Memory 存什么**
- **Memory 怎么存储**

但是对于学习 Agent，真正核心的问题是：

> 有了学生 Memory 后，Agent 如何利用这些记忆做教学决策？


也就是：

```
学生行为
    ↓
Memory更新
    ↓
学生状态理解
    ↓
教学策略选择
    ↓
教学行为
    ↓
新的学习反馈
    ↓
Memory再次更新
```

这才形成真正的：

**Learning Loop（学习闭环）**

---

# 一、普通 Agent Memory 和教学 Agent Memory 最大区别

普通 Agent：

```
用户说：
我喜欢Python

Memory:
用户喜欢Python

以后：
推荐Python内容
```

只是信息调用。


---

学习 Agent：

用户：

> 我不会理解递归


Memory：

```
历史：
3次递归相关问题

错误：
无法理解函数调用栈

知识状态：
递归 mastery = 0.35

学习方式：
喜欢图示

```

Agent需要进一步推理：

```
不是简单解释递归

应该：

1. 先检查函数调用概念
2. 使用图示
3. 给简单例子
4. 让学生练习
5. 判断是否掌握
```

这叫：

## Pedagogical Decision（教学决策）

---

# 二、核心技术 1：Reflection Memory（反思记忆）

来源：

## Generative Agents（Stanford）

论文：

《Generative Agents: Interactive Simulacra of Human Behavior》

---

前面说过：

Memory Stream：

保存经历：

```
学生今天学习链表
学生问next指针
学生完成练习
```

但是：

这些只是：

Experience（经历）


人类学习不会只保存经历。

人会总结：

> 我发现自己指针理解一直不好。


这就是 Reflection。


---

# 三、Reflection 的工作方式


流程：

```
Raw Memory

   ↓

重要事件积累

   ↓

Reflection Trigger

   ↓

LLM总结

   ↓

Higher-level Memory

```


---

例如：

原始Memory：

```
10月1日：

学生：
next是什么？


10月3日：

学生：
为什么修改next会影响后面的节点？


10月5日：

学生：
链表删除还是不会
```


Reflection：

生成：

```
学生对链表结构有基本理解，
但是节点引用关系理解不足。

后续教学应该：
减少代码量，
增加指针关系图示。
```


保存：

```
Teaching Strategy Memory
```


---

# 四、Reflection 对学习 Agent 非常重要

因为：

普通 Memory：

知道：

```
学生问过三次链表
```

但是不知道：

```
为什么问三次
```


Reflection：

得到：

```
根因：
抽象结构理解不足

解决：
视觉化教学
```


这接近真实老师：

老师不会记录：

```
学生第几次问问题
```

而会形成：

```
这个学生的问题在哪里
```


---

# 五、案例：Voyager Agent 的 Skill Memory


论文：

《Voyager: An Open-Ended Embodied Agent with Large Language Models》


GitHub：

https://github.com/MineDojo/Voyager


虽然它不是教育 Agent。

但是它的 Memory 设计非常值得借鉴。


---

Voyager 的核心：

不是保存聊天。


而是保存：

## Skill Library（技能库）


结构：

```
Experience

↓

总结技能

↓

Skill Memory

↓

未来复用
```


---

例如 Minecraft：

第一次：

Agent学习：

```
如何制作工具
```

保存：

```javascript
craft_tool()

输入:
wood

输出:
pickaxe
```

以后：

遇到：

```
需要挖矿
```

直接调用技能。


---

# 六、映射到学习 Agent

学习过程也有 Skill。


例如：

学生学习数据结构。


Agent发现：

解释链表时：

方法A：

```
先画节点关系图
```

效果很好。


保存：

```
Teaching Skill:

链表教学方法:

visual-first
```


以后：

其他学生：

遇到链表：

调用：

```
Teaching Skill
```


---

所以学习 Agent Memory 不应该只有：

```
学生Memory
```

还应该有：

```
Teacher Memory
```

---

# 七、Teacher Memory（教师经验记忆）

这是目前很多学习Agent缺少的。


优秀教师：

不仅记学生。

还积累：

```
什么方法有效
```

例如：

知识点：

```
递归
```


历史：

100个学生。


发现：

方法：

```
画递归树
+
模拟调用栈
```


成功率高。


保存：

```
Teaching Strategy Memory
```


---

未来：

Agent：

遇到：

学生不会递归。


检索：

```
Teaching Memory

↓

最佳教学策略

```


---

# 八、Self-Reflection Agent（自我反思）

近几年 Agent 论文大量研究。


代表：

## Reflexion

论文：

《Reflexion: Language Agents with Verbal Reinforcement Learning》


GitHub：

https://github.com/noahshinn/reflexion


---

核心：

Agent执行任务后：

不是结束。


而是：

问自己：

```
哪里做错？

为什么失败？

下次怎么改？
```


---

结构：

```
Agent Action

      ↓

Evaluation

      ↓

Reflection

      ↓

Memory

      ↓

Next Attempt
```


---

例如：

学习 Agent：

回答：

```
学生不满意
```


反馈：

```
太难，没有例子
```


Reflection：

```
以后讲新概念：
增加案例
降低首次抽象程度
```


保存。


---

# 九、把这些组合成学习 Agent 闭环


最终结构：

```
                 Student


                    |
                    |

              Learning Event

                    |
                    |

              Memory System


       ----------------------------

       |             |             |

   Profile      Knowledge      Experience


       |             |             |

       ----------------------------

                    |

              Reflection


                    |

          Teaching Strategy Memory


                    |

              AI Tutor


                    |

             Next Teaching Action

```

---

# 十、对应 DeepTutor 项目的设计建议

结合你之前的项目：

目前已有：

- 教材RAG
- 用户画像
- 学习流程
- Agent回答


Memory部分建议增加：

---

## 1. 学习事件记录层

不要只保存聊天。

记录：

```json
{
"time":

"2026-10-11",

"chapter":

"链表",

"action":

"ask_question",

"concept":

"next指针",

"result":

"still confused"
}
```


---

## 2. 学生状态层


类似：

Student Model：

```json
{
"linked_list":

{
knowledge:0.8,

confidence:0.5,

difficulty:"pointer"
}
}
```


注意：

knowledge 和 confidence 分开。


因为：

学生可能：

```
会做

但是没信心
```


---

## 3. Reflection层


定期生成：

```json
{
"recent_pattern":

"学生连续询问指针相关问题",

"root_cause":

"抽象结构理解不足",

"recommendation":

"增加可视化解释"
}
```


---

## 4. 教学策略层


保存：

```json
{
concept:

"linked_list",

strategy:

[
"先画结构",
"再讲代码",
"最后练习"
],

success_rate:

0.87
}
```


---

# 十一、目前主流 Agent Memory 技术路线总结


|技术|解决问题|
|-|-|
|Conversation Memory|记住聊天|
|Mem0|自动提取事实|
|MemGPT/Letta|管理长期上下文|
|Graphiti|关系和时间变化|
|Knowledge Tracing|判断学生掌握程度|
|Reflection|总结经验|
|Voyager Skill Memory|复用成功策略|
|Reflexion|Agent自我改进|

---

# 本轮完成情况

✅ Reflection Memory  
✅ Generative Agents 反思机制  
✅ Voyager Skill Memory  
✅ Teacher Memory 概念  
✅ Reflexion Agent  
✅ Memory → Teaching Decision 闭环  
✅ 映射 DeepTutor 实现方案  


---

# 下一轮（5/？）计划：

下一轮进入更工程化的部分：

## 「Memory 的具体实现架构设计」

重点：

1. Memory Schema 怎么设计
2. MySQL / PostgreSQL / MongoDB / Neo4j / Vector DB 如何组合
3. Memory 写入策略：
   - 什么情况写
   - 谁决定写
   - 如何避免垃圾记忆
4. Memory 检索策略：
   - 向量检索
   - 图检索
   - 时间衰减
   - 重要性评分
5. 给 DeepTutor 设计一套完整 Student Memory Architecture

这一轮会更接近你们项目真正落地。



# 调研进度 5/？：学习 Agent Memory 的工程架构设计 —— 如何真正落地 Student Memory System

本轮进入实现层。

前四轮解决：

1. 为什么 Agent 需要 Memory
2. 学习 Agent 应该记什么
3. 主流 Memory 框架怎么实现
4. Memory 如何影响教学决策


现在讨论：

> 如果我们真的开发一个 DeepTutor / AI 教学 Agent，Memory 系统应该怎么设计？


重点：

- 数据结构
- 存储方案
- 写入机制
- 更新机制
- 检索机制
- 遗忘机制


---

# 一、先确定一个核心原则

学习 Agent 的 Memory 不是一个数据库。


错误设计：

```
chat_history 表

+
vector database
```


这只是：

聊天机器人。


真正学习 Agent：

应该：

```
                 Student Memory


        ┌─────────────────┐
        │ Profile Memory  │
        └─────────────────┘

        ┌─────────────────┐
        │ Knowledge State │
        └─────────────────┘

        ┌─────────────────┐
        │ Learning Event  │
        └─────────────────┘

        ┌─────────────────┐
        │ Error Memory    │
        └─────────────────┘

        ┌─────────────────┐
        │ Strategy Memory │
        └─────────────────┘

```

---

# 二、Memory 总体架构


推荐采用：

## Hybrid Memory Architecture（混合记忆）


目前很多先进 Agent 都采用类似思想：

```
                 LLM Agent


                    |
                    |

              Memory Manager


                    |

 -------------------------------------------------

 |             |             |            |

SQL          Vector        Graph       Cache

长期事实     语义记忆       关系记忆     当前状态

```


---

# 三、第一类：Profile Memory（学生画像记忆）

## 作用：

回答：

> 这个学生是谁？


属于长期稳定信息。


例如：

```
学生：

专业:
大数据

年级:
大二

目标:
考研

学习偏好:
喜欢代码+图示

```

---

## 存储方式

关系数据库。


例如 PostgreSQL：

表：

student_profile


|字段|说明|
|-|-|
|student_id|学生ID|
|major|专业|
|grade|年级|
|goal|目标|
|learning_style|学习方式|

---

示例：


```json
{
"user_id":"001",

"major":
"Big Data",

"goal":
"graduate_exam",

"style":
[
"visual",
"example_first"
]

}
```


---

特点：

变化慢。

更新：

低频。


例如：

不会每次聊天更新。

---

# 四、第二类：Learning Event Memory（学习事件记忆）

这是最重要的。

因为学习不是静态。


学生每天：

- 看教材
- 提问
- 做题
- 修改错误
- 完成任务


都形成事件。


---

## Event Schema


例如：


```json
{
"student_id":

001,


"time":

"2026-10-11",


"course":

"数据结构",


"concept":

"链表插入",


"action":

"ask_question",


"result":

"understood"

}
```


---

类似：

Generative Agents 的 Memory Stream。


---

存储：

推荐：

PostgreSQL。


原因：

事件有：

- 时间
- 用户
- 类型
- 状态


适合关系查询。


---

# 五、第三类：Knowledge State Memory（知识状态）


这是教育 Agent 和普通 Agent 最大区别。


目标：

知道：

> 学生掌握程度。


---

参考：

Knowledge Tracing。


设计：

知识点表：

```
Knowledge_Point


id

name

parent

difficulty

```


例如：

```
数据结构

 |
 链表

 |
 节点

 |
 指针

```


---

学生掌握表：

```
Student_Knowledge_State

student_id

knowledge_id

mastery

confidence

last_time

```


例如：

|知识|掌握|信心|
|-|-|-|
|数组|0.9|0.9|
|链表|0.8|0.6|
|递归|0.3|0.4|

---

注意：

这里非常重要：

不要只记录：

mastery。


应该：

mastery + confidence。


因为：

教学场景：

学生：

```
会，但是不敢做

```

和：

```
完全不会

```

教学策略不同。


---

# 六、第四类：Error Memory（错误记忆）

优秀老师最重要的能力：

记住学生为什么错。


---

普通系统：

记录：

```
错题：
二叉树遍历
```


不够。


应该：

记录：

```
错误模式

```

---

例如：

```json
{
"concept":

"pointer",


"error":

"认为next保存节点内容",


"cause":

"对象和引用概念混淆",


"solution":

"使用节点图解释"

}
```


---

为什么重要？


因为：

很多学习问题会重复。


例如：

学生：

第一次：

```
next是什么？
```


第二周：

```
为什么next改变链表变化？
```


表面不同。


根因：

一样。


---

# 七、第五类：Strategy Memory（教学策略记忆）


这是目前很多 AI Tutor 缺少的。


它不是记学生。


而是：

记：

> 什么教学方式有效。


---

例如：

历史：

100次教学。


发现：

知识点：

递归。


策略：

```
递归树图示

+
手动模拟栈

+
简单代码

```


成功率：

90%。


保存：

```json
{
"concept":

"recursion",

"strategy":

"visual_stack",

"success":

0.9

}
```


---

以后：

遇到学生：

自动调用。


---

# 八、Memory 写入机制

这是工程中最难的问题。


不是所有聊天都保存。


错误：

```
用户：
你好

↓

保存Memory

```


会产生垃圾。


---

目前主流：

Memory Gate。


结构：


```
Conversation

      |

      ↓

Memory Evaluator

      |

      ↓

是否重要？

      |

 Yes

      |

Extract Memory

```


---

# 九、Memory Evaluator 怎么判断？


可以设计：

## 规则 + LLM


---

规则：

以下情况必记录：

### 1. 学习目标变化

例如：

```
我要准备考研

```


---

### 2. 知识掌握变化


例如：

```
我终于理解链表了

```


---

### 3. 错误出现


例如：

```
为什么一直报错

```


---

### 4. 学习偏好


例如：

```
不要只讲理论，给代码

```


---

### 5. 教学反馈


例如：

```
这种方式我听懂了

```


---

# 十、Memory Update（更新）


不能无限增加。


需要：

Update。


例如：

旧：

```json
{
pointer:

weak

}
```


新：

```
已经理解next

```


不能：

增加：

```
pointer weak

pointer good

```

应该：

更新：

```
pointer:

mastered

```


---

类似 Mem0：

```
New Memory

↓

Conflict Detection

↓

Merge

↓

Update

```

---

# 十一、Memory Retrieval（调用）


重点：

不是：

全部Memory给LLM。


应该：

Memory Router。


---

例如：

学生问：

> 为什么二叉树遍历这么难？


Router判断：

需要：

```
Knowledge State

+
Error Memory

+
Learning History

```


不要：

Profile。


---

检索：

```
Query

↓

Memory Router

↓

Multiple Retrieval

↓

Rank

↓

Context Builder

↓

LLM

```


---

# 十二、Memory Ranking


参考 Generative Agents：

综合：

## Relevance

相关性


## Importance

重要程度


## Recency

最近程度


公式：


```
Score

=

αR

+

βI

+

γT

```


---

例如：

用户：

问链表。


Memory：

A：

```
昨天链表学习

相关:
0.9

重要:
0.8

时间:
0.9

```

高。


B：

```
半年前Python学习

相关:
0.2
```


低。


---

# 十三、是否需要知识图谱？

针对 DeepTutor：

我认为：

需要。


原因：

学习关系天然是图。


例如：

```
学生

 |
掌握程度

 |

知识点

 |
依赖关系

 |

章节

```


---

推荐：

Neo4j。


结构：

```
(Student)

    |
 KNOWS

    |

(Knowledge)


    |
 PREREQUISITE

    |

(Knowledge)

```


---

例如：

```
学生A

弱

↓

递归

↓

导致

↓

树遍历困难

```


这个关系：

数据库表不好表达。


---

# 十四、推荐最终架构


结合：

Mem0 + Letta + Graphiti + Knowledge Tracing


设计：

```
                 Learning Agent


                       |

                 Memory Manager


                       |


 ------------------------------------------------


 PostgreSQL        VectorDB          Neo4j


 Profile           Experience        Knowledge Graph


 Event             Error             Relation


 State             Reflection        Dependency



 ------------------------------------------------


                       |


                  LLM Reasoning


```

---

# 十五、对应 DeepTutor V2 Memory 模块


建议拆成：


## Memory Service


独立服务。


接口：

```python
write_memory()

retrieve_memory()

update_memory()

reflect_memory()

```


---

例如：

学生完成一次学习：


```
POST

/memory/event


{
chapter:
"链表",

action:
"complete",

result:
"success"

}

```


---

Memory Service：

自动：

1. 更新学习记录
2. 更新知识状态
3. 判断是否生成反思
4. 更新教学策略


---

# 本轮完成情况

✅ Student Memory 数据模型  
✅ 五类 Memory 设计  
✅ Memory 写入机制  
✅ Memory 更新机制  
✅ Memory 检索机制  
✅ Memory Router  
✅ Hybrid Storage 架构  
✅ DeepTutor Memory Service 初步设计  


---

# 下一轮（6/？）

下一轮重点调研：

## 「真实开源项目代码分析」

不再讲概念。

直接看：

1. Mem0 源码结构：
   - memory.py
   - extraction pipeline
   - update logic

2. Letta 源码：
   - memory block
   - archival storage

3. Graphiti：
   - entity extraction
   - graph update


然后回答：

> 如果我们自己的 DeepTutor 要实现 Memory，哪些代码可以直接参考，哪些必须自己写。


这会进入真正工程复用分析。

# 调研进度 6/？：主流 Agent Memory 开源项目源码级分析 —— Mem0、Letta、Graphiti 如何实现

本轮开始进入**代码架构层面**。

目标：

> 不再讨论 Memory 理论，而是分析真实开源项目内部怎么组织代码、哪些部分可以复用到 DeepTutor，哪些需要自己实现。

本轮分析：

1. Mem0 Memory Pipeline
2. Letta/MemGPT Memory Architecture
3. Graphiti Temporal Knowledge Graph Memory

---

# 一、Mem0 源码设计分析

项目定位：

> 一个给 LLM Agent 提供长期记忆能力的 Memory Layer。

官方架构：

```
User Input

    ↓

Memory Extraction

    ↓

Memory Storage

    ↓

Memory Retrieval

    ↓

Prompt Enrichment

    ↓

LLM Response
```

Mem0 的核心流程可以概括：

```
add()
 |
 |
Extract
 |
 |
Deduplicate
 |
 |
Embed
 |
 |
Store


search()
 |
 |
Retrieve
 |
 |
Rank
 |
 |
Return Memory
``` :chatgpt-content-reference{index="0"}


---

# 二、Mem0 的核心模块拆解


## 1. Memory Client 层

开发者调用：

```python
memory.add()

memory.search()
```

类似：

```python
class Memory:

    def add(messages):
        ...

    def search(query):
        ...
```

这一层负责：

- 接收聊天
- 调用LLM
- 管理存储


对于 DeepTutor：

对应：

```
MemoryService
```

例如：

```python
student_memory.add_event()

student_memory.retrieve()
```

---

# 三、Memory Extraction（记忆抽取）

这是最重要部分。


用户聊天：

```
学生：
我现在大二，
正在学习数据结构，
但是递归比较差。
```

不会直接保存。


首先进入：

```
Extractor
```


LLM 提取：

```json
[
 {
  "type":"profile",
  "fact":
  "学生是大二"
 },


 {
  "type":"weakness",
  "fact":
  "递归能力较弱"
 }
]
```


---

对应 DeepTutor：

应该设计：

```
Conversation

      ↓

Memory Extractor


      ↓


Student Facts
```

---

# 四、Mem0 的 Memory Object


核心结构类似：

```json
{
"id":

"xxx",


"memory":

"用户喜欢代码解释",


"user_id":

"001",


"metadata":

{
"type":
"learning_preference"
}

}
``` :chatgpt-content-reference{index="1"}



---

但是：

对于学习 Agent：

这个结构不够。


因为学生记忆需要：

```
知识状态
错误
成长
策略
```

所以应该扩展。


例如：

```json
{
"id":"001",

"type":
"knowledge_state",

"concept":
"递归",

"mastery":
0.3,

"confidence":
0.4
}
```

---

# 五、Mem0 的去重与更新思想


普通数据库：

新增：

```
A

A

A
```

会爆炸。


Mem0：

加入：

```
Deduplication
```

判断：

已有：

```
用户喜欢图示
```


新：

```
我喜欢画图理解
```


合并：

```
用户偏好视觉化学习
``` :chatgpt-content-reference{index="2"}




---

对于学习 Agent：

非常重要。


例如：

第一次：

```
学生不会递归
```


第二周：

```
学生掌握递归
```


不能：

保存：

```
不会
掌握
```


应该形成：

状态变化：

```
递归:

0.3

↓

0.8
```

---

# 六、Mem0 可以直接复用什么？


## 可以直接借鉴：

### 1. Memory Extractor

★★★★★


聊天：

↓

自动提取事实。


非常适合：

学生画像。


---

### 2. Memory Retrieval Pipeline

★★★★★


尤其：

```
semantic search

+
keyword

+
metadata filter
``` :chatgpt-content-reference{index="3"}



---

### 3. Memory Metadata设计


例如：

```
source:

chat

priority:

high

category:

learning
```

---

# 不能直接用：

## Knowledge State


原因：

Mem0不知道：

```
学生掌握程度
```

需要：

自己设计。


---

# 七、Letta / MemGPT 源码思想


Letta 最大特点：

不是 Memory Database。


而是：

> Memory 管理操作系统。 :chatgpt-content-reference{index="4"}




---

# 八、Letta Memory 三个核心组件


## 1. Core Memory


永远放入 Context。


例如：

```
Human:

用户:
大二学生

正在学习数据结构


Persona:

你是一名耐心老师
``` :chatgpt-content-reference{index="5"}



类似：

系统Prompt的一部分。


---

## 2. Recall Memory


历史对话：

```
过去聊天
```


需要搜索。


---

## 3. Archival Memory


长期资料。


例如：

```
一年学习记录
``` :chatgpt-content-reference{index="6"}




---

# 九、为什么 Letta 对学习 Agent 很有价值？


因为：

学习 Agent 有两个状态：

---

## 当前教学状态

例如：

```
正在学习链表插入
```

应该放：

Core Memory


---

## 长期成长状态

例如：

```
三个月前递归薄弱

现在已经掌握
```

放：

Archival Memory


---

类似：

老师脑子：

短期：

```
今天给这个学生讲什么
```

长期：

```
这个学生一直哪里不好
```

---

# 十、Letta 最大创新：Agent 可以修改 Memory


传统：

程序：

```
保存Memory
```


Letta：

Agent：

```
判断是否保存
```

例如：

学生：

```
以后不要只给代码，
先解释思想
```


Agent调用：

```
update_memory()
```


修改：

```
learning_style:
concept_first
``` :chatgpt-content-reference{index="7"}



---

# 十一、DeepTutor 可以借鉴 Letta 什么？


非常推荐：

## Memory Block


设计：

```
Student Memory Block
```


例如：

```yaml
student_profile:

grade:
大二

major:
大数据

style:
先理论后代码


current_learning:

数据结构-树

```

---

## Weakness Block


```yaml
weakness:

递归:

0.3


pointer:

0.5

```

---

## Goal Block


```yaml
goal:

考研

target:

河北工业大学
```

---

# 十二、Graphiti 源码思想


Graphiti：

定位：

> 给 Agent 建立动态时间知识图谱。 [GitHub](https://github.com/Agentopia/Graphiti?utm_source=chatgpt.com)




---

# 十三、Graphiti 核心流程


输入：

聊天：

```
我昨天终于理解链表了
```


进入：

Entity Extraction


得到：

节点：

```
学生A

链表

```


关系：

```
学生A

理解

链表

```


时间：

```
2026-10-10
```


形成：

```
(Student)

   |
understands

   |

(LinkedList)

time:
10-10
```

---

# 十四、为什么 Graphiti 对学习 Agent 重要？


因为学习天然是图。


例如：

```
课程

 |
章节

 |
知识点

 |
前置知识

 |
错误

 |
学生

```


关系复杂。


---

# 十五、Graphiti 最大价值：时间变化


学生状态不是固定。


例如：


10月1：

```
学生

不会

递归
```


10月20：

```
学生

掌握

递归
```


普通数据库：

两个冲突。


Graph：

保存：

```
过去状态

+
当前状态
``` :chatgpt-content-reference{index="9"}




---

# 十六、三个项目组合关系


实际上：

它们解决不同问题。


```
                 Student Memory


                     |

        -----------------------------

        |             |             |


      Mem0          Letta       Graphiti


      事实          管理        关系


      提取          上下文      知识网络



```


---

# 十七、如果实现 DeepTutor Memory


我的推荐：

不要复制。


组合：

---

## 第一层：Letta思想

管理：

```
Current Student State
```

例如：

当前学习：

```
数据结构-树
```

---

## 第二层：Mem0思想

自动抽取：

```
学生事实
学习偏好
错误
反馈
```

---

## 第三层：Graphiti思想

保存：

```
知识关系
学习路径
成长变化
```

---

## 第四层：Knowledge Tracing

计算：

```
掌握程度
```


---

# 十八、最终架构


```
                    AI Tutor


                       |

                 Memory Manager


                       |


 ------------------------------------------------

 |                 |                |

Student DB      Vector DB       Knowledge Graph


Profile         Events          Concepts


State           Errors          Relations


 ------------------------------------------------


                       |

               Reflection Engine


                       |

              Teaching Strategy


```


---

# 本轮完成情况

已完成：

✅ Mem0 源码思想分析  
✅ Memory Extraction  
✅ Memory Object  
✅ Deduplication  
✅ Letta Core Memory  
✅ Letta Archival Memory  
✅ Agent 自修改 Memory  
✅ Graphiti 时间知识图谱  
✅ 三者组合方案  


---

# 下一轮（7/？）计划：

下一轮进入**最关键部分：**

## 「学习 Agent Memory 的完整技术方案设计」

目标：

结合：

- Mem0
- Letta
- Graphiti
- Knowledge Tracing
- Student Model

设计：

> DeepTutor Student Memory System v1.0


内容包括：

1. 数据库设计
2. 表结构
3. Neo4j节点设计
4. Memory API设计
5. Memory Agent流程
6. 和现有 RAG / Agent 如何连接
7. MVP实现路线

这一轮会直接形成你们项目可以写进设计文档的部分。
