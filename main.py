#!/usr/bin/env python3
"""Premium-style Telegram bot with interactive menus and admin tooling.

This file rewrites the former Termux utility into a fully asynchronous,
button-driven Telegram bot powered by ``python-telegram-bot``. The bot ships
with:
- Reply and inline keyboard navigation similar to popular moderation bots
- Inline query support
- Auto-response and basic moderation hooks
- Persistent JSON-based storage for user preferences and audit logs
- Admin-only commands for privileged flows

Environment variable required: ``BOT_TOKEN`` for the bot's HTTP API token.
Update ``ADMIN_USER_IDS`` to match the accounts that should access admin-only
commands.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Iterable, List

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent,
    KeyboardButton,
    ReplyKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    AIORateLimiter,
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    InlineQueryHandler,
    MessageHandler,
    filters,
)

DATA_DIR = Path("data")
PREFS_FILE = DATA_DIR / "user_prefs.json"
AUDIT_FILE = DATA_DIR / "audit_log.json"
LOG_FILE = DATA_DIR / "bot.log"

ADMIN_USER_IDS: tuple[int, ...] = ()  # Populate with real admin Telegram user IDs


@dataclass
class UserPreferences:
    """Simple user preference payload stored per user ID."""

    auto_reply: bool = True
    moderation_enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "auto_reply": self.auto_reply,
            "moderation_enabled": self.moderation_enabled,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "UserPreferences":
        return cls(
            auto_reply=payload.get("auto_reply", True),
            moderation_enabled=payload.get("moderation_enabled", True),
        )


@dataclass
class AuditEntry:
    """Structured audit log entry for user actions."""

    user_id: int
    action: str
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"user_id": self.user_id, "action": self.action, "meta": self.meta}


def ensure_data_files() -> None:
    """Create data directory and seed JSON stores if missing."""

    DATA_DIR.mkdir(exist_ok=True)
    if not PREFS_FILE.exists():
        PREFS_FILE.write_text(json.dumps({}, indent=2))
    if not AUDIT_FILE.exists():
        AUDIT_FILE.write_text(json.dumps([], indent=2))


def load_preferences(user_id: int) -> UserPreferences:
    """Read user preferences from disk, falling back to defaults."""

    ensure_data_files()
    payload = json.loads(PREFS_FILE.read_text())
    prefs = payload.get(str(user_id), {})
    return UserPreferences.from_dict(prefs)


def save_preferences(user_id: int, prefs: UserPreferences) -> None:
    """Persist user preferences to disk."""

    ensure_data_files()
    payload = json.loads(PREFS_FILE.read_text())
    payload[str(user_id)] = prefs.to_dict()
    PREFS_FILE.write_text(json.dumps(payload, indent=2))


def append_audit(entry: AuditEntry) -> None:
    """Append an audit entry, trimming the log to a manageable size."""

    ensure_data_files()
    log_payload: List[Dict[str, Any]] = json.loads(AUDIT_FILE.read_text())
    log_payload.append(entry.to_dict())
    # Keep the newest 200 entries to avoid unbounded growth
    trimmed = log_payload[-200:]
    AUDIT_FILE.write_text(json.dumps(trimmed, indent=2))


def log_action(action: str) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Decorator to log handler execution and capture errors."""

    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            user_id = update.effective_user.id if update.effective_user else 0
            logging.info("Action %s by user %s", action, user_id)
            append_audit(
                AuditEntry(
                    user_id=user_id,
                    action=action,
                    meta={"chat": update.effective_chat.id if update.effective_chat else None},
                )
            )
            try:
                return await func(update, context, *args, **kwargs)
            except Exception:  # pragma: no cover - defensive logging
                logging.exception("Handler %s failed", func.__name__)
                await update.effective_message.reply_text(
                    "⚠️ Something went wrong. The team has been notified.", quote=True
                )
                raise

        return wrapper

    return decorator


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_USER_IDS


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("Help"), KeyboardButton("Support")],
            [KeyboardButton("Features"), KeyboardButton("Logs")],
            [KeyboardButton("Settings")],
        ],
        resize_keyboard=True,
    )


def help_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Commands", callback_data="help:commands")],
            [InlineKeyboardButton("Admin Tools", callback_data="help:admin")],
            [InlineKeyboardButton("Support", callback_data="help:support")],
        ]
    )


def settings_keyboard(prefs: UserPreferences) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    f"Auto-Reply: {'On' if prefs.auto_reply else 'Off'}",
                    callback_data="settings:auto_reply",
                )
            ],
            [
                InlineKeyboardButton(
                    f"Moderation: {'On' if prefs.moderation_enabled else 'Off'}",
                    callback_data="settings:moderation",
                )
            ],
        ]
    )


@log_action("start")
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome users and provide the main navigation keyboard."""

    user = update.effective_user
    prefs = load_preferences(user.id)
    welcome = (
        "👋 Welcome to the Reaction Assistant!\n"
        "Navigate with the menu below to explore help, support, and admin tools."
    )

    inline = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Open Help", callback_data="help:commands")],
            [InlineKeyboardButton("Contact Support", url="https://t.me/your_support_handle")],
        ]
    )

    await update.effective_message.reply_text(
        welcome,
        reply_markup=main_menu_keyboard(),
        parse_mode=ParseMode.MARKDOWN,
    )
    await update.effective_message.reply_text(
        "Quick actions:", reply_markup=inline, parse_mode=ParseMode.MARKDOWN
    )
    save_preferences(user.id, prefs)


@log_action("help")
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "🤖 *Help Center*\n"
        "Use the buttons to navigate through the available topics."
    )
    await update.effective_message.reply_text(
        text, reply_markup=help_keyboard(), parse_mode=ParseMode.MARKDOWN
    )


@log_action("support")
async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = (
        "📞 *Support Desk*\n"
        "Reach out to the developer or join the community channel for updates."
    )
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Chat with Developer", url="https://t.me/your_handle")],
            [InlineKeyboardButton("Community Channel", url="https://t.me/your_channel")],
        ]
    )
    await update.effective_message.reply_text(
        message, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
    )


@log_action("features")
async def features_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "✨ *Feature Overview*\n"
        "- Rich inline + reply keyboards\n"
        "- Inline query shortcuts\n"
        "- Auto-replies & moderation\n"
        "- Admin-only commands with audit logging\n"
        "- Persistent JSON storage for user preferences and logs"
    )
    await update.effective_message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


@log_action("logs")
async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Recent Activity", callback_data="logs:recent")],
            [InlineKeyboardButton("Bot Status", callback_data="logs:status")],
        ]
    )
    await update.effective_message.reply_text(
        "📊 Choose what you want to inspect.", reply_markup=keyboard
    )


async def send_recent_logs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id if update.effective_user else 0
    if not is_admin(user_id):
        await update.effective_message.reply_text("Only admins can view audit entries.")
        return

    entries: List[Dict[str, Any]] = json.loads(AUDIT_FILE.read_text())[-10:]
    if not entries:
        await update.effective_message.reply_text("No audit entries yet.")
        return

    lines = [f"• {entry['action']} by {entry['user_id']}" for entry in entries]
    await update.effective_message.reply_text("Recent logs:\n" + "\n".join(lines))


async def send_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    entries: List[Dict[str, Any]] = json.loads(AUDIT_FILE.read_text())
    unique_users: Iterable[int] = {entry.get("user_id", 0) for entry in entries}
    stats = (
        f"🛰️ *Bot Status*\n"
        f"Tracked actions: {len(entries)}\n"
        f"Unique users: {len(unique_users)}\n"
        f"Admins: {len(ADMIN_USER_IDS)}"
    )
    await update.effective_message.reply_text(stats, parse_mode=ParseMode.MARKDOWN)


async def handle_logs_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    if query.data == "logs:recent":
        await send_recent_logs(update, context)
    elif query.data == "logs:status":
        await send_status(update, context)


async def handle_help_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    messages = {
        "help:commands": (
            "\n".join(
                [
                    "🛠️ *User Commands*:",
                    "/start – open the main menu",
                    "/help – open this help center",
                    "/support – reach the developer",
                    "/features – discover capabilities",
                    "/logs – view status and audit info",
                    "/settings – update your preferences",
                ]
            )
        ),
        "help:admin": (
            "\n".join(
                [
                    "🛡️ *Admin Commands*:",
                    "/login – verify admin identity",
                    "/report – file a report to the team",
                    "/link – fetch integration links",
                ]
            )
        ),
        "help:support": (
            "\n".join(
                [
                    "☎️ *Support Options*:",
                    "- DM the developer",
                    "- Join the community channel",
                    "- Use inline queries for quick answers",
                ]
            )
        ),
    }

    response = messages.get(query.data, "Select a topic from the menu.")
    await query.edit_message_text(response, parse_mode=ParseMode.MARKDOWN, reply_markup=help_keyboard())


@log_action("settings")
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    prefs = load_preferences(update.effective_user.id)
    await update.effective_message.reply_text(
        "⚙️ Settings", reply_markup=settings_keyboard(prefs), parse_mode=ParseMode.MARKDOWN
    )


async def handle_settings_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id if update.effective_user else 0
    prefs = load_preferences(user_id)

    if query.data == "settings:auto_reply":
        prefs.auto_reply = not prefs.auto_reply
    elif query.data == "settings:moderation":
        prefs.moderation_enabled = not prefs.moderation_enabled

    save_preferences(user_id, prefs)
    await query.edit_message_reply_markup(reply_markup=settings_keyboard(prefs))


async def require_admin(update: Update) -> bool:
    user_id = update.effective_user.id if update.effective_user else 0
    if not is_admin(user_id):
        await update.effective_message.reply_text("This command is reserved for admins.")
        return False
    return True


@log_action("admin_login")
async def admin_login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await require_admin(update):
        return
    await update.effective_message.reply_text("✅ Admin identity confirmed. Welcome back!")


@log_action("admin_report")
async def admin_report(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await require_admin(update):
        return
    issue = " ".join(context.args) if context.args else "(no summary provided)"
    append_audit(
        AuditEntry(user_id=update.effective_user.id, action="admin_report", meta={"issue": issue})
    )
    await update.effective_message.reply_text(
        "📝 Report recorded. The team will review it shortly."
    )


@log_action("admin_link")
async def admin_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await require_admin(update):
        return
    await update.effective_message.reply_text(
        "🔗 Admin integrations:\n- Dashboard: https://example.com/admin\n- API Docs: https://example.com/docs"
    )


async def inline_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.inline_query
    prompt = query.query or "Reaction bot"

    results = [
        InlineQueryResultArticle(
            id="help",
            title="Help Center",
            description="Open the bot's help menu",
            input_message_content=InputTextMessageContent(
                "Use /help to explore commands and admin tools."
            ),
        ),
        InlineQueryResultArticle(
            id="support",
            title="Support Links",
            description="Contact the developer or join the channel",
            input_message_content=InputTextMessageContent(
                "Need assistance? Ping @your_handle or join https://t.me/your_channel"
            ),
        ),
        InlineQueryResultArticle(
            id="echo",
            title="Echo Prompt",
            description="Send your text back with markdown styling",
            input_message_content=InputTextMessageContent(
                f"*You said:* {prompt}", parse_mode=ParseMode.MARKDOWN
            ),
        ),
    ]

    await query.answer(results, cache_time=0)


async def auto_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Auto-respond to common prompts and perform light moderation."""

    message = update.effective_message
    user_id = update.effective_user.id if update.effective_user else 0
    prefs = load_preferences(user_id)
    text = message.text or ""
    lowered = text.lower()

    banned_keywords = {"spam", "scam", "abuse"}
    if prefs.moderation_enabled and any(word in lowered for word in banned_keywords):
        await message.reply_text(
            "🚫 Your message triggers moderation filters. Please keep the chat professional."
        )
        append_audit(AuditEntry(user_id=user_id, action="moderation_flag", meta={"text": text}))
        return

    if prefs.auto_reply:
        quick_replies = {
            "hello": "Hello! Tap *Help* to see what I can do.",
            "support": "Need help? Use /support or try inline: @YourBot support",
            "settings": "Use /settings to update preferences.",
            "help": "Use /help to open the interactive help center.",
            "features": "Use /features to see everything I can do.",
        }
        for keyword, reply in quick_replies.items():
            if keyword in lowered:
                await message.reply_text(reply, parse_mode=ParseMode.MARKDOWN)
                return


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logging.exception("Update %s caused error", update, exc_info=context.error)


def getenv_token() -> str | None:
    return os.environ.get("BOT_TOKEN")


def build_application() -> Application:
    token_files = [Path(".env"), Path(".token")]
    token_from_file = None
    for token_file in token_files:
        if token_file.exists():
            token_from_file = token_file.read_text().strip()
            break

    token = getenv_token() or token_from_file
    if not token:
        raise RuntimeError("BOT_TOKEN is required. Set the environment variable before running.")

    application = (
        ApplicationBuilder()
        .token(token)
        .rate_limiter(AIORateLimiter())
        .concurrent_updates(True)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("support", support_command))
    application.add_handler(CommandHandler("features", features_command))
    application.add_handler(CommandHandler("logs", logs_command))
    application.add_handler(CommandHandler("settings", settings_command))

    application.add_handler(CommandHandler("login", admin_login))
    application.add_handler(CommandHandler("report", admin_report))
    application.add_handler(CommandHandler("link", admin_link))

    application.add_handler(CallbackQueryHandler(handle_help_callbacks, pattern=r"^help:"))
    application.add_handler(CallbackQueryHandler(handle_logs_callbacks, pattern=r"^logs:"))
    application.add_handler(CallbackQueryHandler(handle_settings_callbacks, pattern=r"^settings:"))

    application.add_handler(InlineQueryHandler(inline_query_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, auto_response))

    application.add_error_handler(error_handler)
    return application


async def run_bot() -> None:
    ensure_data_files()
    app = build_application()
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    logging.info("Bot started successfully.")
    await app.updater.idle()
    await app.stop()
    await app.shutdown()


if __name__ == "__main__":
    ensure_data_files()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
    )

    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logging.info("Bot stopped by user.")
