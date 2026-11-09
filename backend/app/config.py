"""后端配置：全部从环境变量读取。密钥（ANON_SALT 等）不写进仓库，见 .env.example。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_VERSION = "0.3.0"
CONSENT_VERSION = "v1-draft"          # 知情同意文本版本；阶段 6 定稿后改为 v1


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    app_env: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    database_url: str = field(default_factory=lambda: os.getenv(
        "DATABASE_URL", f"sqlite:///{REPO_ROOT / 'backend' / 'dev.db'}"))
    anon_salt: str = field(default_factory=lambda: os.getenv("ANON_SALT", ""))
    problems_dir: Path = field(default_factory=lambda: Path(os.getenv("PROBLEMS_DIR", REPO_ROOT / "problems")))
    cookie_secure: bool = field(default_factory=lambda: _bool("COOKIE_SECURE", False))
    session_days: int = field(default_factory=lambda: int(os.getenv("SESSION_DAYS", "14")))
    jobs_inline: bool = field(default_factory=lambda: _bool("JOBS_INLINE", False))
    judge_timeout: float = field(default_factory=lambda: float(os.getenv("JUDGE_TIMEOUT_SECONDS", "10")))
    # 学情参数（docs/learner-model.md）
    pred_threshold: float = field(default_factory=lambda: float(os.getenv("PRED_THRESHOLD", "0.8")))
    f_window: int = 5          # F 值：最近 n 次带预测的尝试
    mastery_window: int = 3    # 掌握等级：最近 m 次
    # 提交频率限制（docs/data-api.md 第 2 节）
    submit_limit: int = 20
    submit_window_minutes: int = 10
    # 提示阶梯：两次提示之间的最短间隔（秒）
    hint_interval_seconds: int = field(default_factory=lambda: int(os.getenv("HINT_INTERVAL_SECONDS", "30")))
    review_daily_limit: int = 5
    # 大模型（docs/llm-deepseek.md 第 3 节）。API Key 只从环境变量读取
    llm_api_key: str = field(default_factory=lambda: os.getenv("DEEPSEEK_API_KEY", ""))
    llm_base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", "https://api.deepseek.com"))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "deepseek-flash"))
    llm_timeout: float = field(default_factory=lambda: float(os.getenv("LLM_TIMEOUT_SECONDS", "30")))
    llm_max_retries: int = field(default_factory=lambda: int(os.getenv("LLM_MAX_RETRIES", "2")))
    llm_daily_budget_cny: float = field(default_factory=lambda: float(os.getenv("LLM_DAILY_BUDGET_CNY", "20")))
    # 每百万 token 单价（元），按官方价格页的高峰价；价格会变，上线前核对
    llm_price_hit: float = field(default_factory=lambda: float(os.getenv("LLM_PRICE_HIT_CNY", "0.04")))
    llm_price_miss: float = field(default_factory=lambda: float(os.getenv("LLM_PRICE_MISS_CNY", "2")))
    llm_price_out: float = field(default_factory=lambda: float(os.getenv("LLM_PRICE_OUT_CNY", "8")))
    # 熔断：连续失败 N 次后若干秒内不再请求
    llm_breaker_failures: int = 5
    llm_breaker_cooldown: float = 120.0
    # 助教对话：每个学生每小时最多条数
    chat_hourly_limit: int = field(default_factory=lambda: int(os.getenv("CHAT_HOURLY_LIMIT", "30")))

    def salt(self) -> str:
        if self.anon_salt:
            return self.anon_salt
        if self.app_env == "production":
            raise RuntimeError("生产环境必须设置环境变量 ANON_SALT")
        return "dev-only-salt-not-secret"   # 仅开发、测试使用；生产环境必须由环境变量提供


def get_settings() -> Settings:
    return Settings()
