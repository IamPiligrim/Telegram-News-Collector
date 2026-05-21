import asyncio
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from openrouter import OpenRouter
from telethon import utils

api_id = 
api_hash = ""

telegram = TelegramClient("telegram", api_id, api_hash)

OPENROUTER_KEY = ""

output = []
price = 0
global price_input
global price_output
count = 0
lock = asyncio.Lock()

# limit concurrent tasks
semaphore = asyncio.Semaphore(5)

client = OpenRouter(api_key=OPENROUTER_KEY)

async def process_dialog(dialog):
    global price, count
    global mcount
    mcount = 0
    async with semaphore:
        try:
            message_zero = await telegram.get_messages(
                dialog,
                min_id=dialog.dialog.read_inbox_max_id,
                reverse=True,
            )
            for i in range(len(message_zero)):
                if not message_zero:
                    return

                text = """Ты — фильтр новостей Minecraft Telegram-каналов.

    Твоя задача: определить, является ли сообщение интересной новостью.

    Ответ должен содержать ТОЛЬКО одно слово:
    ДА
    или
    НЕТ

    Любой другой текст запрещён.

    Отвечай НЕТ, если сообщение:
    - является анонсом стрима, видео или трансляции;
    - связано с личной жизнью;
    - поздравляет с днём рождения;
    - является рекламой, оффтопом или обычным общением;
    - не связано напрямую с Minecraft.

    Отвечай ДА, если сообщение:
    - содержит важные события;
    - рассказывает о драмах, конфликтах или расследованиях;
    - сообщает о достижениях игроков;
    - содержит значимые новости сообщества;
    - связано с крупными Minecraft-проектами, серверами, турнирами или игроками.

    Если есть сомнения — отвечай НЕТ.

    Сообщение:""" + message_zero[i].text

                if len(message_zero[i].text) <= 30:
                    continue

                # run blocking OpenRouter call in thread
                response = await asyncio.to_thread(
                    lambda: client.chat.send(
                        model="meta-llama/llama-3.1-8b-instruct",
                        messages=[
                            {
                                "role": "user",
                                "content": text
                            }
                        ],
                    )
                )
                
                price_input = (
                    float(response.usage.completion_tokens)
                    / 1_000_000
                    * 0.05
                )

                price_output = (
                    float(response.usage.prompt_tokens)
                    / 1_000_000
                    * 0.02
                )
                
                if response.choices[0].message.content.lower() == "да":
                    entity = await telegram.get_entity(dialog)
                    olink = f"https://t.me/{entity.username}/{message_zero[i].id}"
                    output.append(olink + "\n" + message_zero[i].text + "\n" + "-------" + "\n")
                    with open('output.txt', 'w', encoding='utf-8') as file:
                        file.writelines(output)
                mcount += 1;

            async with lock:
                price += price_input + price_output
                count += 1

                print(
                    f'Output: "{response.choices[0].message.content}"\n'
                    f'Price: ${price:.8f}\n'
                )

        except FloodWaitError as e:
            print(f"Flood wait: sleeping {e.seconds}s")
            await asyncio.sleep(e.seconds)

        except Exception as e:
            print(f"Error: {e}")

async def main():
    tasks = []

    async for dialog in telegram.iter_dialogs():
        if (
            dialog.is_channel
            and dialog.archived
            and dialog.unread_count != 0
        ):
            tasks.append(asyncio.create_task(process_dialog(dialog)))

    await asyncio.gather(*tasks)
    
    print('$' + str(price) + '\n' + str(mcount))


with telegram:
    telegram.loop.run_until_complete(main())