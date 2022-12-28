# V3重构plan

## 核心(core):

### orm:

- [x] AsyncORM

### 配置:

bot基础配置:

- [x] bot_accounts:[]
- [x] default_account
- [x] master_qq
- [x] admins:[]
- [x] host_url
- [x] verify_key

### 	控制组件（control）:

Function功能开关:

- [ ] 开关判断->Function.require("模组名")

Permission 权限判断:

- [x] 成员权限判断
- [x] 群权限判断

Frequency频率限制:

- [ ] 在n秒内触发n次功能后开始限制

- [ ] cd时间

Distribute多账户消息分发:

- [ ] 分发require 
  

多账户响应模式:

- [ ] 随机响应(默认)
- [ ]   指定bot响应(指定模式)

## 插件结构:

modules:

```json
{
  "module_name": {
        "level": "插件等级1/2/3",
        "name": "包名/文件名",
        "display_name": "显示/展示名字",
        "author": ["作者"],
        "description": "描述",
        "usage": ["用法"],
        "eg": ["例子"]
      }
}
```

modules_data.json:

```json
{
    "module_name":{
        "groups": {
            "group_id":{
            	"switch": "bool"
            }
		},
        "available": "bool"
    }
}
```

