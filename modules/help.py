def build_help_text(admin_mark):
    ad = admin_mark
    return f"""Pixivc 爬虫帮助：

图片命令：
1. /pixivc_key xxx
2. /pixivc_tag xxx
3. /pixivc_key_and xxx,xxx2
4. /pixivc_key_or xxx,xxx2
5. /pixivc_tag_and xxx,xxx2
6. /pixivc_tag_or xxx,xxx2
7. /pixivc_rank daily
8. /pixivc_user 123456
9. /pixivc_discovery{ad('admin_discovery')}

小说命令：
10. /pixivc_novel_key xxx
11. /pixivc_novel_tag xxx
12. /pixivc_novel_key_and xxx,xxx2
13. /pixivc_novel_key_or xxx,xxx2
14. /pixivc_novel_tag_and xxx,xxx2
15. /pixivc_novel_tag_or xxx,xxx2
16. /pixivc_novel_rank daily
17. /pixivc_novel_user 123456
18. /pixivc_novel_id 123456789
19. /pixivc_novel_recommended{ad('admin_novel_recommended')}

管理命令：
20. /pixivc_help
21. /pixivc_status
22. /pixivc_cache
23. /pixivc_clean{ad('admin_clean')}
24. /pixivc_get_zip
24. /pixivc_r18_add{ad('admin_r18_manage')} QQ 或 @某人
25. /pixivc_r18_del{ad('admin_r18_manage')} QQ 或 @某人
26. /pixivc_r18_list{ad('admin_r18_manage')}
27. /pixivc_auto xxx
28. /pixivc_illust_id 作品ID
29. /pixivc_bookmark_add{ad('admin_bookmark')} 作品ID
30. /pixivc_bookmark_del{ad('admin_bookmark')} 作品ID
31. /pixivc_bookmarks{ad('admin_bookmarks')}
32. /pixivc_trending_tags
33. /pixivc_related 作品ID
34. /pixivc_follow_add{ad('admin_follow')} 用户ID
35. /pixivc_follow_del{ad('admin_follow')} 用户ID
36. /pixivc_following{ad('admin_following')}
37. /pixivc_follow_latest{ad('admin_follow_latest')}
38. /pixivc_new
39. /pixivc_recommended_users{ad('admin_recommended_users')}
40. /pixivc_user_search 关键词
40. /pixiv_get_token

说明：
- 参数格式均可放在命令任意位置。
- n x 表示作品数量为 x，例如 n5 表示 5 个作品；默认 n20，最大值由 max_count 配置决定。数量按作品统计，不按图片页数统计。
- p x 表示从 Pixiv 结果第 x 页开始，例如 p3 表示从第 3 页开始；不是作品图片页。
- m x 表示本次命令最大搜索深度为 x，例如 m30 表示最多搜索 30 页；不写则使用插件配置 search_max_depth。
- t x 表示按作品/小说标签筛选，例如 t女の子,初音ミク；只匹配作品/小说 tags 里的单个标签，不匹配标题、简介、作者或关键词。多个正向标签按 AND 处理，结果需同时包含这些标签。标签为全字精确匹配，t空 只匹配标签“空”，不会匹配“天空”。
- t -x 表示排除标签 x，例如 t原神,-空 表示必须包含“原神”且不能包含“空”。排除标签同样是单标签全字精确匹配。
- 示例：/pixivc_discovery n5 p3 m30 t女の子,初音ミク,-AI生成
- 示例：/pixivc_tag 原神 n20 p3 m30
- /pixivc_tag 本身就是标签搜索，会按作品 tags 做单标签精确过滤。
- 作品数量不够时会继续翻页补足，直到够数、没有下一页或达到 search_max_depth。
- 预览图片质量 medium/large/original 在插件设置 image_quality 中配置；ZIP 固定 original。
- 图片搜索默认只发送合并转发预览，不自动发送 ZIP。
- 如需最近一次搜索的 original ZIP，请发送 /pixivc_get_zip。
- R18 需要对应场景开关开启，并且发送者 QQ 在 R18 白名单内。
- /pixivc_auto xxx 可调用 Pixiv API 获取关键词/标签自动补全。
- /pixiv_get_token 可生成 Pixiv 官方 OAuth 登录链接；回调链接发回后会返回 token。
"""
