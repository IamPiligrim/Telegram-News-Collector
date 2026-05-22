import asyncio
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from openrouter import OpenRouter

api_id = 0
api_hash = ""
OPENROUTER_KEY = ""

telegram = TelegramClient("telegram", api_id, api_hash)
client = OpenRouter(api_key=OPENROUTER_KEY)

semaphore = asyncio.Semaphore(5)
lock = asyncio.Lock()

total_price = 0.0
total_messages = 0

FILTER_PROMPT = """Ты — фильтр новостей Minecraft Telegram-каналов.
Определи, является ли сообщение интересной новостью.
Ответ — ТОЛЬКО одно слово: ДА или НЕТ. Любой другой текст запрещён.

Отвечай НЕТ: анонс стрима/видео, личная жизнь, поздравления, реклама, оффтоп, не Minecraft.
Отвечай ДА: важные события, драмы, конфликты, достижения, новости сообщества, серверы, турниры.
При сомнениях — НЕТ.

Сообщение:"""


def calc_price(usage) -> float:
    input_cost = usage.prompt_tokens / 1_000_000 * 0.02
    output_cost = usage.completion_tokens / 1_000_000 * 0.05
    return input_cost + output_cost


async def classify_message(text: str) -> tuple[str, float]:
    """Возвращает (решение, стоимость)."""
    response = await asyncio.to_thread(
        client.chat.send,
        model="meta-llama/llama-3.1-8b-instruct",
        messages=[{"role": "user", "content": FILTER_PROMPT + text}],
    )
    return response.choices[0].message.content.strip().lower(), calc_price(response.usage)


async def process_dialog(dialog, out_file):
    global total_price, total_messages

    async with semaphore:
        try:
            entity = await telegram.get_entity(dialog)
            username = getattr(entity, "username", entity.id)

            # Получаем только непрочитанные сообщения
            unread_messages = await telegram.get_messages(
                dialog,
                min_id=dialog.dialog.read_inbox_max_id,
                limit=None,
            )

            if not unread_messages:
                return

            dialog_price = 0.0
            dialog_count = 0

            for msg in unread_messages:
                if not msg.text or len(msg.text.strip()) == 0:
                    continue

                decision, msg_price = await classify_message(msg.text)
                dialog_price += msg_price
                dialog_count += 1

                link = f"https://t.me/{username}/{msg.id}"

                if decision == "да":
                    line = f"{link}\n{msg.text}\n-------\n"
                    await asyncio.to_thread(out_file.write, line)
                    print(f"[+] {link}")

                print(f"    {link} → {decision} (${msg_price:.8f})")

            async with lock:
                total_price += dialog_price
                total_messages += dialog_count

        except FloodWaitError as e:
            print(f"[flood] Ждём {e.seconds}s")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            print(f"[error] {dialog.name}: {e}")


async def main():
    with open("output.txt", "a", encoding="utf-8") as out_file:
        tasks = [
            asyncio.create_task(process_dialog(dialog, out_file))
            async for dialog in telegram.iter_dialogs()
            if dialog.is_channel
            and dialog.archived
            and dialog.unread_count != 0
        ]
        await asyncio.gather(*tasks)

    print(f"\nИтого: ${total_price:.6f}, обработано сообщений: {total_messages}")


with telegram:
    telegram.loop.run_until_complete(main())