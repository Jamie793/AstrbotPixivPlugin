# AstrBot Pixivs Crawler Plugin

AstrBot Pixivs Crawler Plugin 是一个面向 AstrBot 的 Pixiv App API 插件，支持 Pixiv 图片、漫画、小说搜索，作品详情，收藏，关注，热门标签，相关作品，自动补全，合并转发预览，以及按需下载 original 原图 ZIP。

## 功能特性

- Pixiv 图片/漫画搜索
- Pixiv 小说搜索和下载
- 支持关键词、标签、AND、OR 搜索
- 支持指定数量和起始页参数
- 搜索后默认只发送合并转发预览
- 只有执行 /pixivs_get_zip 时才下载 original 原图并打包 ZIP
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

## 安装方式

在 AstrBot 插件管理中通过 GitHub 仓库安装：

https://github.com/Jamie793/AstrbotPixivPlugin

或者手动安装：

1. 将本仓库克隆或下载到 AstrBot 插件目录。
2. 确保目录名为 astrbot_plugin_pixivs_crawler 或使用 AstrBot 插件管理安装。
3. 安装依赖：
   pip install -r requirements.txt
4. 重载插件或重启 AstrBot。

## 必填配置

安装后进入 AstrBot 后台插件配置，填写：

- refresh_token：Pixiv Refresh Token

可选配置：

- proxy：Pixiv API 代理地址，例如 http://127.0.0.1:7890
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

你可以使用其它 OAuth 工具获取 refresh_token，然后填写到插件配置中。

注意：

- 不要把 refresh_token 发到群聊。
- 不要把 refresh_token 提交到 GitHub。
- 本仓库不会包含任何本地 token 或缓存数据。

## 图片命令

1. /pixivs_key xxx [数量]

按关键词搜索图片作品。

示例：

/pixivs_key 原神 20

2. /pixivs_tag xxx [数量]

按标签搜索图片作品。

示例：

/pixivs_tag フリーナ 20

3. /pixivs_key_and xxx,xxx2 [数量]

关键词 AND 搜索。

示例：

/pixivs_key_and 原神,フリーナ 20

4. /pixivs_key_or xxx,xxx2 [数量]

关键词 OR 搜索。

5. /pixivs_tag_and xxx,xxx2 [数量]

标签 AND 搜索。

6. /pixivs_tag_or xxx,xxx2 [数量]

标签 OR 搜索。

7. /pixivs_rank daily [数量]

排行榜。

示例：

/pixivs_rank daily 20

8. /pixivs_user 123456 [数量]

获取指定用户作品。

9. /pixivs_discovery [数量]

获取推荐作品。是否需要 Admin 由后台配置控制。

## 起始页参数

支持在命令中指定从第几页开始获取。

示例：

/pixivs_tag 原神 20 page=3

等价写法：

/pixivs_tag 原神 20 p=3
/pixivs_tag 原神 20 start=3
/pixivs_tag 原神 20 start_page=3
/pixivs_tag 原神 20 第3页
/pixivs_tag 原神 20 p3
/pixivs_tag 原神 20 3

最后一种写法中：

- 20 表示数量
- 3 表示起始页

## ZIP 下载逻辑

图片搜索后默认只发送合并转发预览，不会立刻下载 original 原图，也不会自动发送 ZIP。

如果需要 original ZIP，发送：

/pixivs_get_zip

插件会根据最近一次图片搜索结果：

1. 下载 original 原图
2. 打包为 ZIP
3. 直接作为聊天文件发送

如果同一批结果已经生成过 ZIP，再次执行 /pixivs_get_zip 会直接发送已有 ZIP。

## 小说命令

1. /pixivs_novel_key xxx [数量]
2. /pixivs_novel_tag xxx [数量]
3. /pixivs_novel_key_and xxx,xxx2 [数量]
4. /pixivs_novel_key_or xxx,xxx2 [数量]
5. /pixivs_novel_tag_and xxx,xxx2 [数量]
6. /pixivs_novel_tag_or xxx,xxx2 [数量]
7. /pixivs_novel_rank daily [数量]
8. /pixivs_novel_user 123456 [数量]
9. /pixivs_novel_id 123456789

## App API 扩展命令

- /pixivs_auto xxx：Pixiv 自动补全
- /pixivs_illust_id 作品ID：获取作品详情
- /pixivs_bookmark_add 作品ID：收藏作品
- /pixivs_bookmark_del 作品ID：取消收藏作品
- /pixivs_bookmarks [数量]：获取我的收藏作品
- /pixivs_trending_tags：获取热门标签
- /pixivs_related 作品ID [数量]：获取相关作品
- /pixivs_follow_add 用户ID：关注作者
- /pixivs_follow_del 用户ID：取关作者
- /pixivs_following [数量]：获取关注列表
- /pixivs_follow_latest [数量]：获取已关注作者最新作品
- /pixivs_new [数量]：获取新作
- /pixivs_recommended_users [数量]：获取推荐作者列表
- /pixivs_user_search 关键词 [数量]：搜索用户

## R18 说明

R18 由两层控制：

1. 场景总开关
   - allow_r18_group
   - allow_r18_private

2. R18 白名单
   - bot 管理者默认允许
   - 普通用户需要加入 R18 白名单

R18 白名单命令：

- /pixivs_r18_add QQ 或 @某人
- /pixivs_r18_del QQ 或 @某人
- /pixivs_r18_list

这些命令是否需要 Admin 可在后台配置。

## Admin 权限开关

后台配置中可以控制以下功能是否需要 bot 管理者权限：

- 推荐作品
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

/pixivs_clean

## 注意事项

1. 本插件依赖 Pixiv App API，网络环境需要能访问 Pixiv。
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
