# 🚀 Claude Skills Downloader

一个用于批量下载 [SkillsMP](https://skillsmp.com) 平台上 Claude Skills 的强大工具。

## ✨ 功能特性

- 🔍 **智能搜索**：支持关键词搜索、Top N 模式和全量下载
- ⭐ **星级过滤**：根据 star 数量过滤高质量 skills
- ⚡ **并行下载**：支持多线程并发下载，提升效率
- 🔄 **自动重试**：下载失败时自动重试，确保下载成功
- 📦 **断点续传**：自动跳过已下载的 skills
- 🎯 **标准化结构**：自动保持官方 skill 目录结构
- 📁 **多级目录组织**：支持按功能/流程/权限自动分类存储（使用 `--organize` 参数）

## 📋 前置要求

- Python 3.7+
- pip (Python 包管理器)

## 🔧 安装

1. 克隆或下载本项目：
```bash
git clone <your-repo-url>
cd skill-download
```

2. 安装依赖：
```bash
pip install requests
```

3. 配置环境变量（可选）：
```bash
cp .env.example .env
# 编辑 .env 文件，设置你的 API tokens
```

## 🎮 使用方法

### 基本用法

```bash
python download_skills.py <搜索关键词> [最小star数]
```

### 使用模式

#### 1️⃣ 搜索模式（默认）
根据关键词搜索并下载符合条件的 skills：

```bash
# 下载所有 SEO 相关且 star >= 1000 的 skills
python download_skills.py SEO 1000

# 下载所有 React 相关且 star >= 500 的 skills
python download_skills.py React 500
```

#### 2️⃣ Top N 模式
下载排名前 N 的 skills：

```bash
# 下载 top 100 skills（star >= 500）
python download_skills.py --top 100 500

# 下载 top 50 skills（默认最小 star）
python download_skills.py --top 50
```

#### 3️⃣ 全量下载模式
下载所有符合星级要求的 skills：

```bash
# 下载所有 star >= 500 的 skills
python download_skills.py --all 500

# 使用 10 个并发线程
python download_skills.py --all 500 --workers 10
```

### 高级选项

- `--workers N`：设置并发线程数（默认 5）
- `--retry N`：设置失败重试次数（默认 3）
- `--organize`：启用多级目录组织模式（按功能/流程/权限分类）

```bash
# 使用 10 个并发线程，失败重试 5 次
python download_skills.py --all 500 --workers 10 --retry 5

# 启用多级目录组织，下载所有 star >= 500 的 skills
python download_skills.py --all 500 --organize
```

## 📁 下载位置

### 默认模式（扁平结构）

所有 skills 将下载到：
```
~/.claude/skills/
```

每个 skill 保持其原始目录结构：
```
~/.claude/skills/<skill-name>/
  ├── SKILL.md           # Skill 主文件
  ├── scripts/           # 脚本目录（如果有）
  ├── references/        # 参考文档（如果有）
  └── ...                # 其他文件
```

### 多级目录组织模式（`--organize`）

启用 `--organize` 参数后，skills 将按照"功能/流程/权限"原则自动分类存储：

```
~/.claude/skills/
  ├── Development/
  │   ├── Frontend/
  │   │   ├── react/
  │   │   │   └── SKILL.md
  │   │   └── vue/
  │   │       └── SKILL.md
  │   ├── Backend/
  │   │   └── nodejs/
  │   │       └── SKILL.md
  │   └── Mobile/
  │       └── flutter/
  │           └── SKILL.md
  ├── Data/
  │   ├── DataScience/
  │   │   └── pandas/
  │   │       └── SKILL.md
  │   └── MachineLearning/
  │       └── pytorch/
  │           └── SKILL.md
  ├── Testing/
  │   ├── UnitTesting/
  │   │   └── pytest/
  │   │       └── SKILL.md
  │   └── E2ETesting/
  │       └── playwright/
  │           └── SKILL.md
  ├── Documentation/
  │   └── Technical/
  │       └── api-docs/
  │           └── SKILL.md
  ├── Security/
  │   └── Auth/
  │       └── oauth/
  │           └── SKILL.md
  └── ...

```

#### 支持的分类体系

**主分类（一级目录）：**
- `Development` - 开发相关
- `Data` - 数据处理与分析
- `Testing` - 测试相关
- `Documentation` - 文档编写
- `Security` - 安全相关
- `Design` - 设计相关
- `Business` - 业务相关
- `Research` - 研究相关
- `Uncategorized` - 未分类（无法识别的 skills）

**子分类（二级目录）：**
- Development: `Frontend`, `Backend`, `Mobile`, `DevOps`
- Data: `DataScience`, `MachineLearning`, `DataEngineering`
- Testing: `UnitTesting`, `E2ETesting`, `Performance`
- Documentation: `Technical`, `UserGuides`, `Blog`
- Security: `Auth`, `Compliance`, `Audit`
- Design: `UIDesign`, `UXDesign`, `Graphics`
- Business: `ProductManagement`, `Marketing`, `Analytics`
- Research: `Scientific`, `Academic`, `Medical`

**分类原则：**
- 通过 skill 的 description 内容进行关键词匹配
- 优先匹配子分类，未匹配到子分类时归入主分类
- 无法识别的 skills 归入 `Uncategorized` 分类

## 🔑 环境变量

创建 `.env` 文件（参考 `.env.example`）：

```env
# SkillsMP API Token (必需)
SKILLSMP_API_TOKEN=sk_live_skillsmp_xxx

# GitHub Token (可选，用于访问私有仓库)
GITHUB_TOKEN=ghp_xxx
```

## 📊 示例输出

```
🔍 Searching for skills: React
📦 Found 45 skills matching criteria (stars >= 500)

⬇️  Downloading skills (workers: 5)...
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 45/45 [00:23<00:00, 1.92it/s]

✅ Download complete!
📊 Stats:
   • Total: 45 skills
   • Success: 43 skills
   • Failed: 2 skills
   • Skipped: 0 skills (already exists)
```

## ⚠️ 注意事项

1. **API Token**：确保在 `.env` 文件中配置有效的 `SKILLSMP_API_TOKEN`
2. **网络连接**：下载需要稳定的网络连接
3. **磁盘空间**：确保有足够的磁盘空间存储 skills
4. **并发数量**：根据网络状况调整 `--workers` 参数，避免请求过多被限流

## 🐛 故障排除

### 下载失败
- 检查网络连接
- 验证 API token 是否有效
- 增加 `--retry` 重试次数

### 权限错误
- 确保对 `~/.claude/skills/` 目录有写权限
- 尝试使用 `sudo` 或修改目录权限

### API 限流
- 减少 `--workers` 并发数
- 增加重试延迟时间

## 📝 许可证

本项目采用 MIT 许可证。

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📮 联系方式

如有问题或建议，请通过 GitHub Issues 联系。
