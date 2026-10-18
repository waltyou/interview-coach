# Interview Coach Dashboard

这是由 Context Pack 真实数据生成的只读本地 Dashboard。`template.html` 保存页面结构和样式，`index.html` 是生成结果。

运行：

```powershell
python scripts/build_dashboard.py
```

生成器默认先从 AttemptEvent 重建 CycleProgress 和 MasteryState，再写入最新 Dashboard。页面本身不会修改题库、PreparationCycle 或历史记录。

## UI Prototype 结论

正式 Dashboard 顶部展示继续上次练习、今日任务与约用时、优先改善的两个问题及其回答依据、最近可比较的进步，再展示题库、系统流程、历史和操作说明。建议由真实 Event、周期策略与未完成会话生成；页面提供可复制的练习指令。页面是生成时快照，Agent 开始练习时重新核对日期和状态。

## 公共题库预览

公共基础仓库随附 [公共题库预览](public.html)，展示本次发布的公共题库和空白学习状态。个人练习后运行 `python scripts/build_dashboard.py` 生成自己的 `dashboard/index.html`；公共预览与个人页面分开保存。
