<!-- 两段 user 消息，用分隔行隔开；第一段对同一道题的所有学生相同（便于命中缓存） -->
【题目】{title}（知识点：{knowledge_points}）
【题目说明】{spec_summary}
<!-- 第二段 -->
【学生代码（带行号）】
{code_with_line_numbers}
【诊断】{judge_json_compact}
【预测对照】{prediction_diff}
【学生状态】象限：{quadrant}；本题已用最高提示等级：{max_level}；最近误区：{recent_tags}
【请求】给出 {level} 级提示（1 思路 / 2 定位 / 3 代码提示）
