# Security

- DevFlow 使用独立账号和密码登录，项目成员按组长、组员和产品经理分配权限。
- 密码使用 Argon2 保存，登录会话使用 HttpOnly Cookie。修改密码后，其他登录会话失效。
- 成员自行关联个人 GitHub Token；Token 加密保存，GitHub 操作使用当前成员的 Token。
- 创建 Issue、领取 Issue、创建 PR 和合并 PR 前，后端检查项目角色；GitHub 同时检查账号和仓库权限。
- 开发环境的个人 Token 密钥保存在本机运行数据目录。生产环境需要配置 `PERSONAL_TOKEN_ENCRYPTION_KEY`，并使用 HTTPS。
- 外部写操作草稿由具备权限的成员确认后执行，执行记录包含操作者和项目。
- 日志不记录密码和 Token。
