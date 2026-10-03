# VendFill 售货机补货

按货道容量、库存与在途量计算缺口，生成不超缺口、非负的补货单。

技术栈：Python 3.12 / FastAPI / SQLAlchemy / PostgreSQL / Vue 3 / TypeScript / Vite

## 启动

```bash
docker compose up --build
```

| 服务 | 地址 |
| --- | --- |
| 前端 | http://localhost:4800 |
| API | http://localhost:9800 |
| API 文档 | http://localhost:9800/docs |
| Postgres | localhost:5449 |

健康检查：`GET http://localhost:9800/api/health`

## 使用说明

1. 在「点位」「货道」查看售货机布局与库存。
2. 在「销量」了解近期出货。
3. 打开「补货单」按缺口生成建议补货量。
4. 在「满仓」「汇总」查看已满货道与补货合计。

## 箱规（按箱取整补货）

- 每条货道可登记箱规（件/箱，正整数）；留空或 1 表示按件补，与旧行为一致；箱规 ≤ 0 直接打回，货道、补货单、汇总都不变。
- 可补量先按缺口封顶，再向下取整到箱规整数倍；取整后为 0 时补量记 0，但只要缺口仍大于 0，状态仍是「待补」，不会记为「满仓」。
- 在「货道」页改箱规并保存时，若点位已有最新补货单，会在同一次提交里按新箱规重写该单全部行：货道箱规、最新补货单、汇总一起变；任一步失败则一并回滚。历史补货单保持不动。

## 开发与测试

```bash
docker compose exec api pytest -q
```
