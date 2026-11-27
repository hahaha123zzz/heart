# 心理教材目录迁出与旧索引归档（2026-11-27）

## 结论先说

- `8000` 不是心理课程：它是**离散数学**部署（`course_id=discrete-math`、
  `fixed_book.enabled=false`），由另一条产品线的部署目录
  `.runtime/student-release-20261122` 管理，当前用 18010/18011 端口。
- 因此“把心理新发行推到 8000”不成立；该尝试已完整回滚（发行指针、环境变量、资产目录都恢复）。
- 心理教材目录的迁出与 8000 无关，已完成。

## 迁出内容

| 对象 | 位置 |
| --- | --- |
| 旧 SQLite 索引（15,634,432 字节，sha256 `2a052d6d90624119c7bb10d445bcfb7c0a82306021f2af55ed29c71d23b0e7ef`） | `E:\heart-runtime\retired-legacy-index-20261127\rag_index.sqlite3` |
| 教材目录其余内容（2798 个文件，131.9 MB，含 chapters/source/sample/crops、manifest、pdf_manifest、kc_*、practice_candidates） | `E:\heart-runtime\online-textbook-20261127` |
| 迁移清单（路径、哈希、条目、时间） | `E:\heart-runtime\online-textbook-move-20261127.json` |
| 原路径 | `project/integration/discrete-math-tutor/knowledge/courses/experimental-psychology-3` 已移除 |

迁移按“同卷移动”，可直接移回原位恢复；归档销毁需单独确认。

## 影响面

- 候选部署 `phase1-candidate-20261126w`（28002）：不读这个目录，仍用
  `E:\heart-runtime\phase1-textbook-noindex` 和 `private/textbook-assets`，无需改动。
- 测试与离线脚本：把 `TUTOR_PSYCHOLOGY_DIR` 指向新路径
  `E:\heart-runtime\online-textbook-20261127`；仍指向旧路径的会明确报路径不存在。
- 离散数学部署：其环境里的 `TUTOR_PSYCHOLOGY_DIR` 指向
  `E:\项目\heart-discrete\...\experimental-psychology-3`，与本次迁移无关。

## 事故与回滚记录

尝试“先把心理发行部署到 8000”时，8000 的旧发行以 `PSYCHOLOGY=False` 进入旧教材路径，
启动报“旧教材索引已退役”，服务短暂不可用。已回滚：

1. 发行指针恢复到 `discrete-final-20261127b`；
2. 移除我加的 `HEART_SINGLE_BACKEND`、`HEART_TEXTBOOK_ASSETS`，恢复 `LIGHTRAG_CANDIDATE_PATH`；
3. 把误拷的 `private/textbook-assets`（114.9 MB）删除，恢复原有单文件版本；
4. 停止继续操作该部署根——它由另一条产品线的会话管理，期间环境文件被并发改写。

教训：部署前先确认目标根的 `TUTOR_COURSE` 与实际 `/health.course_id`，不要按目录名推断。
