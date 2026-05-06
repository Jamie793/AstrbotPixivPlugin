def build_help_text(admin_mark):
    ad = admin_mark
    return f"""Pixivc 爬虫帮助：

图片命令：
1. /pixivc_key xxx [数量]
2. /pixivc_tag xxx [数量]
3. /pixivc_key_and xxx,xxx2 [数量]
4. /pixivc_key_or xxx,xxx2 [数量]
5. /pixivc_tag_and xxx,xxx2 [数量]
6. /pixivc_tag_or xxx,xxx2 [数量]
7. /pixivc_rank daily [数量]
8. /pixivc_user 123456 [数量]
9. /pixivc_discovery{ad('admin_discovery')} [数量]

小说命令：
10. /pixivc_novel_key xxx [数量]
11. /pixivc_novel_tag xxx [数量]
12. /pixivc_novel_key_and xxx,xxx2 [数量]
13. /pixivc_novel_key_or xxx,xxx2 [数量]
14. /pixivc_novel_tag_and xxx,xxx2 [数量]
15. /pixivc_novel_tag_or xxx,xxx2 [数量]
16. /pixivc_novel_rank daily [数量]
17. /pixivc_novel_user 123456 [数量]
18. /pixivc_novel_id 123456789

管理命令：
19. /pixivc_help
20. /pixivc_status
21. /pixivc_clean{ad('admin_clean')}
22. /pixivc_get_zip
23. /pixivc_r18_add{ad('admin_r18_manage')} QQ 或 @某人
24. /pixivc_r18_del{ad('admin_r18_manage')} QQ 或 @某人
25. /pixivc_r18_list{ad('admin_r18_manage')}
26. /pixivc_auto xxx
27. /pixivc_illust_id 作品ID
28. /pixivc_bookmark_add{ad('admin_bookmark')} 作品ID
29. /pixivc_bookmark_del{ad('admin_bookmark')} 作品ID
30. /pixivc_bookmarks{ad('admin_bookmarks')} [数量]
31. /pixivc_trending_tags
32. /pixivc_related 作品ID [数量]
33. /pixivc_follow_add{ad('admin_follow')} 用户ID
34. /pixivc_follow_del{ad('admin_follow')} 用户ID
35. /pixivc_following{ad('admin_following')} [数量]
36. /pixivc_follow_latest{ad('admin_follow_latest')} [数量]
37. /pixivc_new [数量]
38. /pixivc_recommended_users{ad('admin_recommended_users')} [数量]
39. /pixivc_user_search 关键词 [数量]
40. /pixiv_get_token

说明：
- 默认数量为20；最大数量由 max_count 配置决定。
- 可用 page 参数指定从第几页开始，例如：/pixivc_tag 原神 20 page=3，或 /pixivc_tag 原神 20 3。
- 预览图片质量 medium/large/original 在插件设置 image_quality 中配置；ZIP 固定 original。
- 图片搜索默认只发送合并转发预览，不自动发送 ZIP。
- 如需最近一次搜索的 original ZIP，请发送 /pixivc_get_zip。
- R18 需要对应场景开关开启，并且发送者 QQ 在 R18 白名单内。
- /pixivc_auto xxx 可调用 Pixiv API 获取关键词/标签自动补全。
- /pixiv_get_token 可生成 Pixiv 官方 OAuth 登录链接；回调链接发回后会返回 token。
"""
