"""Every handler: parse args -> one ApiClient call -> format text. No
business logic here — that's the whole point of calling the REST API
instead of claudeshorts.services directly."""

from __future__ import annotations

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from .client import ApiClient


def is_authorized(chat_id: int, allowed_chat_id: int) -> bool:
    return chat_id == allowed_chat_id


def format_queue(posts: list[dict]) -> str:
    if not posts:
        return "No posts awaiting review."
    return "\n".join(f"#{p['id']}: {p['title']}" for p in posts)


def format_job(job: dict) -> str:
    text = f"Job #{job['id']} ({job['job_type']}): {job['status']}, attempts={job['attempts']}"
    if job.get("error"):
        text += f"\nerror: {job['error']}"
    return text


def build_application(token: str, chat_id: int, client: ApiClient) -> Application:
    app = Application.builder().token(token).build()

    async def guard(update: Update) -> bool:
        if not is_authorized(update.effective_chat.id, chat_id):
            await update.message.reply_text("Not authorized.")
            return False
        return True

    async def queue_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update):
            return
        posts = client.list_posts(status="rendered")
        await update.message.reply_text(format_queue(posts))

    async def generate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update):
            return
        count = int(context.args[0]) if context.args else 1
        result = client.generate(count)
        await update.message.reply_text(f"Enqueued job #{result['job_id']}")

    async def approve_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update):
            return
        post_id = int(context.args[0])
        result = client.approve(post_id)
        await update.message.reply_text(f"Approved post #{post_id}: {result}")

    async def reject_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update):
            return
        post_id = int(context.args[0])
        note = " ".join(context.args[1:]) if len(context.args) > 1 else None
        client.reject(post_id, note=note)
        await update.message.reply_text(f"Rejected post #{post_id}")

    async def retry_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update):
            return
        job_id = int(context.args[0])
        result = client.retry_job(job_id)
        await update.message.reply_text(f"Retried as job #{result['job_id']}")

    async def profiles_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update):
            return
        profiles = client.list_profiles()
        if not profiles:
            await update.message.reply_text("No profiles configured yet.")
            return
        text = "\n".join(f"{p['slug']} ({p['platform']}): {p['login_health']}" for p in profiles)
        await update.message.reply_text(text)

    async def workers_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update):
            return
        jobs = client.list_jobs(status="running")
        text = "\n".join(format_job(j) for j in jobs) or "No running jobs."
        await update.message.reply_text(text)

    async def logs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await guard(update):
            return
        job = client.get_job(int(context.args[0]))
        await update.message.reply_text(f"{format_job(job)}\n\n{job.get('log', '')}"[:4000])

    app.add_handler(CommandHandler("queue", queue_cmd))
    app.add_handler(CommandHandler("generate", generate_cmd))
    app.add_handler(CommandHandler("approve", approve_cmd))
    app.add_handler(CommandHandler("reject", reject_cmd))
    app.add_handler(CommandHandler("retry", retry_cmd))
    app.add_handler(CommandHandler("profiles", profiles_cmd))
    app.add_handler(CommandHandler("workers", workers_cmd))
    app.add_handler(CommandHandler("logs", logs_cmd))
    return app
