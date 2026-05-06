# AstrBot Pixivc Crawler Plugin

AstrBot Pixivc Crawler Plugin 是一个面向 AstrBot 的 Pixiv App API 插件，支持 Pixiv 图片、漫画、小说搜索，作品详情，收藏，关注，热门标签，相关作品，自动补全，合并转发预览，以及按需下载 original 原图 ZIP。

## 功能特性

- Pixiv 图片/漫画搜索
- Pixiv 小说搜索和下载
- 支持关键词、标签、AND、OR 搜索
- 支持指定数量和起始页参数
- 搜索后默认只发送合并转发预览
- 只有执行 /pixivc_get_zip 时才下载 original 原图并打包 ZIP
- 支持 Pixiv 自动补全
- 支持热门标签、作品详情、相关作品
- 支持我的收藏、收藏/取消收藏
- 支持关注/取关作者、关注列表、关注动态
- 支持 R18 群聊/私聊开关和 R18 白名单
- 支持 AI 作品过滤
- 支持收藏数、浏览数、点赞数过滤
- 支持每日自动清理缓存
- 支持后台配置 Admin 权限开关
- access token 失效时自动静默刷新并重试
- 内置 Pixiv OAuth PKCE 流程，可通过 /pixivc_get_token 获取 token

## 安装方式

在 AstrBot 插件管理中通过 GitHub 仓库安装：

https://github.com/Jamie793/AstrbotPixivPlugin

或者手动安装：

1. 将本仓库克隆或下载到 AstrBot 插件目录。
2. 确保目录名为 astrbot_plugin_pixivc_crawler 或使用 AstrBot 插件管理安装。
3. 安装依赖：
   pip install -r requirements.txt
4. 重载插件或重启 AstrBot。

## 必填配置

安装后进入 AstrBot 后台插件配置，填写：

- refresh_token：Pixiv Refresh Token

可选配置：

- proxy：Pixiv API 代理地址，例如 http://127.0.0.1:7890
- use_image_proxy_without_proxy：无代理时使用图片反代下载图片，可在后台开关切换
- image_proxy_host：图片反代地址，默认 https://i.pixiv.re
  开关关闭后，即使没有 proxy 也会直接请求 Pixiv 图片原始地址。
- image_quality：合并转发预览图片质量，ZIP 固定 original
- max_count：单次最大返回数量
- allow_r18_group：群聊是否允许 R18
- allow_r18_private：私聊是否允许 R18
- allow_ai：是否允许 AI 作品
- min_bookmarks：最小收藏数，-1 表示关闭过滤
- min_views：最小浏览数，-1 表示关闭过滤
- min_likes：最小点赞数，-1 表示关闭过滤
- search_pages：最多搜索页数，-1 表示不限制
- auto_clean_enabled：每日自动清理缓存
- Admin 权限开关：控制部分功能是否仅 bot 管理者可用

## 获取 Pixiv Refresh Token

本插件只使用 Pixiv refresh_token，不需要 Pixiv 密码。

你可以直接使用本插件内置命令获取 refresh_token：

/pixivc_get_token

流程：

1. 发送 /pixivc_get_token
2. 插件返回 Pixiv 官方 OAuth 登录链接
3. 在浏览器中完成登录授权
4. 将回调链接完整发送给机器人
5. 插件返回 raw JSON、access token 和 refresh token
6. 将 refresh token 填入插件配置

也可以使用其它 OAuth 工具获取 refresh_token，然后填写到插件配置中。

注意：

- 不要把 refresh_token 发到群聊。
- 不要把 refresh_token 提交到 GitHub。
- 本仓库不会包含任何本地 token 或缓存数据。

## 图片命令

1. /pixivc_key xxx [数量]

按关键词搜索图片作品。

示例：

/pixivc_key 原神 20

2. /pixivc_tag xxx [数量]

按标签搜索图片作品。

示例：

/pixivc_tag フリーナ 20

3. /pixivc_key_and xxx,xxx2 [数量]

关键词 AND 搜索。

示例：

/pixivc_key_and 原神,フリーナ 20

4. /pixivc_key_or xxx,xxx2 [数量]

关键词 OR 搜索。

5. /pixivc_tag_and xxx,xxx2 [数量]

标签 AND 搜索。

6. /pixivc_tag_or xxx,xxx2 [数量]

标签 OR 搜索。

7. /pixivc_rank daily [数量]

排行榜。

示例：

/pixivc_rank daily 20

8. /pixivc_user 123456 [数量]

获取指定用户作品。

9. /pixivc_discovery [数量]

获取推荐作品。是否需要 Admin 由后台配置控制。

## 起始页参数

支持在命令中指定从第几页开始获取。

示例：

/pixivc_tag 原神 20 page=3

等价写法：

/pixivc_tag 原神 20 p=3
/pixivc_tag 原神 20 start=3
/pixivc_tag 原神 20 start_page=3
/pixivc_tag 原神 20 第3页
/pixivc_tag 原神 20 p3
/pixivc_tag 原神 20 3

最后一种写法中：

- 20 表示数量
- 3 表示起始页

## ZIP 下载逻辑

图片搜索后默认只发送合并转发预览，不会立刻下载 original 原图，也不会自动发送 ZIP。

小说搜索默认也只发送合并转发预览，并附带每篇小说正文前一半作为预览；不会自动发送 ZIP。

如果需要 ZIP，发送：

/pixivc_get_zip

插件会根据最近一次任务类型自动判断：

1. 上一次是图片搜索：下载 original 原图并打包为图片 ZIP
2. 上一次是小说搜索：打包小说 TXT/封面为小说 ZIP
3. 直接作为聊天文件发送

如果同一批结果已经生成过 ZIP，再次执行 /pixivc_get_zip 会直接发送已有 ZIP。

## 小说命令

1. /pixivc_novel_key xxx [数量]
2. /pixivc_novel_tag xxx [数量]
3. /pixivc_novel_key_and xxx,xxx2 [数量]
4. /pixivc_novel_key_or xxx,xxx2 [数量]
5. /pixivc_novel_tag_and xxx,xxx2 [数量]
6. /pixivc_novel_tag_or xxx,xxx2 [数量]
7. /pixivc_novel_rank daily [数量]
8. /pixivc_novel_user 123456 [数量]
9. /pixivc_novel_id 123456789
10. /pixivc_novel_recommended [数量]

## App API 扩展命令

- /pixivc_auto xxx：Pixiv 自动补全
- /pixivc_illust_id 作品ID：获取作品详情
- /pixivc_bookmark_add 作品ID：收藏作品
- /pixivc_bookmark_del 作品ID：取消收藏作品
- /pixivc_bookmarks [数量]：获取我的收藏作品
- /pixivc_trending_tags：获取热门标签
- /pixivc_related 作品ID [数量]：获取相关作品
- /pixivc_follow_add 用户ID：关注作者
- /pixivc_follow_del 用户ID：取关作者
- /pixivc_following [数量]：获取关注列表
- /pixivc_follow_latest [数量]：获取已关注作者最新作品
- /pixivc_new [数量]：获取新作
- /pixivc_recommended_users [数量]：获取推荐作者列表
- /pixivc_user_search 关键词 [数量]：搜索用户
- /pixivc_debug_last：查看最近一次提取和过滤调试信息
- /pixivc_novel_recommended [数量]：获取推荐小说，支持 page 参数
- /pixivc_get_token：生成 Pixiv 官方 OAuth 登录链接，获取 token

## R18 说明

R18 由两层控制：

1. 场景总开关
   - allow_r18_group
   - allow_r18_private

2. R18 白名单
   - bot 管理者默认允许
   - 普通用户需要加入 R18 白名单

R18 白名单命令：

- /pixivc_r18_add QQ 或 @某人
- /pixivc_r18_del QQ 或 @某人
- /pixivc_r18_list

这些命令是否需要 Admin 可在后台配置。

## Admin 权限开关

后台配置中可以控制以下功能是否需要 bot 管理者权限：

- 推荐作品
- 推荐小说
- 收藏/取消收藏
- 我的收藏列表
- 关注/取关作者
- 关注列表
- 已关注动态
- 推荐作者列表
- 清理缓存
- R18 白名单管理

开启表示仅 bot 管理者可用。

关闭表示普通用户也可用。

建议涉及账号写操作的功能保持 Admin 限制。

## 缓存与自动清理

默认缓存目录：

data/downloads

缓存内容包括：

- 预览图片
- original ZIP
- 小说文件
- 临时目录

插件支持每日自动清理缓存，默认每天 04:00 清理。

相关配置：

- auto_clean_enabled
- auto_clean_hour
- auto_clean_minute

手动清理命令：

/pixivc_clean

## 注意事项

1. 本插件依赖 Pixiv App API，网络环境需要能访问 Pixiv。无代理时可通过图片反代下载图片，但 Pixiv API 本身仍需要可访问。
2. refresh_token 失效后需要重新获取。
3. original 原图可能体积较大，请合理设置 max_count 和 max_zip_mb。
4. 群聊开启 R18 请谨慎。
5. 不要提交本地 config、token、下载缓存到仓库。

## 目录结构

- main.py：插件主程序
- _conf_schema.json：AstrBot 插件配置 schema
- metadata.yaml：插件元数据
- requirements.txt：Python 依赖
- README.md：说明文档

## License

GPL-3.0-or-later
