# Interview Coach Dashboard

这是由 Context Pack 真实数据生成的只读本地 Dashboard。`template.html` 保存页面结构和样式，`index.html` 是生成结果。

运行：

```powershell
python scripts/build_dashboard.py
```

生成器默认先从 AttemptEvent 重建 CycleProgress 和 MasteryState，再写入最新 Dashboard。页面本身不会修改题库、PreparationCycle 或历史记录。

## UI Prototype 结论

临时原型验证了系统地图、复习旅程和操作手册三种信息层级。正式 Dashboard 采用状态优先的单页结构：顶部展示当前复习数据，下面依次提供题库、系统流程、历史和操作说明。数据由 Python 生成器注入，原型切换器和硬编码统计已经删除。
