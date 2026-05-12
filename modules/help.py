def build_help_text(admin_mark):
    ad = admin_mark
    return f"""Pixivc 指令帮助：

常用图片指令：
1. /pixivc_key 关键词
   按关键词搜索插画/漫画，匹配标签、标题或简介。
2. /pixivc_tag 标签
   按 Pixiv 标签搜索，并按作品 tags 做精确过滤。
3. /pixivc_key_and 关键词1,关键词2
   多关键词 AND 搜索，结果需同时匹配多个关键词。
4. /pixivc_key_or 关键词1,关键词2
   多关键词 OR 搜索，合并多个关键词结果并去重。
5. /pixivc_tag_and 标签1,标签2
   多标签 AND 搜索，结果需同时包含多个标签。
6. /pixivc_tag_or 标签1,标签2
   多标签 OR 搜索，合并多个标签结果并去重。
7. /pixivc_rank daily|weekly|monthly
   获取插画排行榜，可用 daily、weekly、monthly 等模式。
8. /pixivc_user 用户ID
   获取指定 Pixiv 用户的插画作品。
9. /pixivc_illust_id 作品ID
   获取指定插画/漫画作品。
10. /pixivc_related 作品ID
   获取某个作品的相关推荐。
11. /pixivc_discovery{ad('admin_discovery')}
   获取 Pixiv 推荐/发现流。
12. /pixivc_new
   获取 Pixiv 大家的新作。

常用小说指令：
13. /pixivc_novel_key 关键词
   按关键词搜索小说。
14. /pixivc_novel_tag 标签
   按标签搜索小说。
15. /pixivc_novel_key_and 关键词1,关键词2
   小说多关键词 AND 搜索。
16. /pixivc_novel_key_or 关键词1,关键词2
   小说多关键词 OR 搜索。
17. /pixivc_novel_tag_and 标签1,标签2
   小说多标签 AND 搜索。
18. /pixivc_novel_tag_or 标签1,标签2
   小说多标签 OR 搜索。
19. /pixivc_novel_rank daily
   小说排行；当前会降级为小说推荐。
20. /pixivc_novel_user 用户ID
   获取指定用户小说。
21. /pixivc_novel_id 小说ID
   获取指定小说。
22. /pixivc_novel_recommended{ad('admin_novel_recommended')}
   获取小说推荐。别名：/pixivc_novel_discovery

用户/社交指令：
23. /pixivc_auto 关键词
   调用 Pixiv 自动补全，查看相关标签/关键词。
24. /pixivc_trending_tags
   查看 Pixiv 热门趋势标签。
25. /pixivc_user_search 关键词
   搜索 Pixiv 用户。
26. /pixivc_recommended_users{ad('admin_recommended_users')}
   获取推荐用户。
27. /pixivc_follow_add{ad('admin_follow')} 用户ID
   关注 Pixiv 用户。
28. /pixivc_follow_del{ad('admin_follow')} 用户ID
   取消关注 Pixiv 用户。
29. /pixivc_following{ad('admin_following')}
   查看当前账号关注用户列表。
30. /pixivc_follow_latest{ad('admin_follow_latest')}
   获取关注用户的新作。
31. /pixivc_bookmark_add{ad('admin_bookmark')} 作品ID
   收藏作品。
32. /pixivc_bookmark_del{ad('admin_bookmark')} 作品ID
   取消收藏作品。
33. /pixivc_bookmarks{ad('admin_bookmarks')}
   查看当前账号收藏作品。

缓存/文件指令：
34. /pixivc_get_zip
   发送最近一次搜索结果的 original 原图 ZIP。
35. /pixivc_cache
   查看 Pixivc 下载缓存和最近结果。
36. /pixivc_clean{ad('admin_clean')}
   清理 Pixivc 下载缓存。

R18 管理指令：
37. /pixivc_r18_add{ad('admin_r18_manage')} QQ 或 @某人
   添加 R18 白名单用户。
38. /pixivc_r18_del{ad('admin_r18_manage')} QQ 或 @某人
   移除 R18 白名单用户。
39. /pixivc_r18_list{ad('admin_r18_manage')}
   查看 R18 白名单。

调试/状态指令：
40. /pixivc_status
   查看插件配置摘要、缓存状态和认证状态。
41. /pixivc_debug help{ad('admin_clean')}
   查看调试命令帮助。别名：/pixicv_debug
42. /pixivc_debug enable{ad('admin_clean')}
   运行时开启调试记录。
43. /pixivc_debug disable{ad('admin_clean')}
   运行时关闭调试记录。
44. /pixivc_debug state{ad('admin_clean')}
   查看调试状态。
45. /pixivc_debug api 5{ad('admin_clean')}
   查看最近 API 请求摘要。
46. /pixivc_debug output 5{ad('admin_clean')}
   查看最近输出摘要。
47. /pixivc_debug file 5{ad('admin_clean')}
   查看最近预览图文件状态。
48. /pixivc_debug clean{ad('admin_clean')}
   清空调试记录。
49. /pixivc_debug_last
   查看最近一次过滤/收集调试信息。

认证指令：
50. /pixivc_get_token
   生成 Pixiv 官方 OAuth 登录链接。别名：获取P站Token
51. /pixiv_get_token
   兼容旧指令，若当前版本未注册请使用 /pixivc_get_token。

通用参数：
- n数字：结果数量。例如 n5 表示 5 个作品；默认值由 default_count 决定，最大值由 max_count 决定。
- p数字：从 Pixiv 结果第几页开始。例如 p3 表示从第 3 页开始，不是作品图片页。
- m数字：本次最大搜索深度。例如 m30 表示最多翻 30 页。
- t标签：按作品/小说 tags 精确筛选。例如 t女の子,初音ミク。
- t-标签：排除标签。例如 t原神,-AI生成 表示必须包含“原神”，且不能包含“AI生成”。

使用示例：
- /pixivc_key 初音ミク n5
- /pixivc_tag 原神 n20 p3 m30
- /pixivc_discovery n5 t女の子,初音ミク,-AI生成
- /pixivc_related 123456789 n10
- /pixivc_novel_key_and 魔法,少女 n5

发送说明：
- 图片搜索默认发送预览，不自动发送 ZIP；需要原图 ZIP 时使用 /pixivc_get_zip。
- QQ/OneBot 平台使用合并转发预览。
- Telegram 平台不支持 QQ 合并转发，自动改为普通图片/文本发送。
- ZIP 固定使用 original 原图，预览质量由 image_quality 配置控制。
- R18 需要对应场景开关开启；关闭时管理员也不会放行。
- 若开启调试模式，可用 /pixivc_debug 查看 API、输出和文件状态。
"""
