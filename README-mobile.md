# 词伙手机版：Supabase 云同步版

## 创建 Supabase 云端数据库

1. 打开 Supabase，创建免费项目。
2. 进入 SQL Editor，把 `supabase-schema.sql` 全部粘贴执行。
3. 进入 Project Settings > API，复制：
   - Project URL
   - anon / public key
4. 发布这个文件夹到 HTTPS 网站。
5. 手机和电脑打开同一个网址，在右上角“云端同步”中填写相同的：
   - Supabase 项目地址
   - anon key
   - 同步 ID（自己设置一串随机文字，例如 `tyc-collocate-7f3a`）
6. 有数据的设备点“上传到云端”，另一台点“从云端读取”。之后可以勾选自动上传。

## 安全和备份

网页中只能填写 anon key，不能填写 service_role key。同步 ID 相当于这份数据的私密口令，不要发给别人。页面仍保留“导入与备份”，建议定期下载完整备份。

当前同步以整份 state 为单位，并带版本冲突保护。如果两台设备都改过数据，先从云端读取，再上传，避免覆盖较新的记录。

## 手机界面

页面使用窄屏优先布局：顶部固定状态栏、横向导航、卡片式学习入口、整宽输入框和大触控按钮；可以直接添加到手机主屏幕。