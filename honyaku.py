import os
import asyncio
from bs4 import BeautifulSoup, NavigableString
from googletrans import Translator

# --- 設定 ---
INPUT_DIR = 'input_html' #入力するhtmlのあるディレクトリ
OUTPUT_DIR = 'output_html' #出力するディレクトリ
TARGET_LANG = 'ja'
# ★★★ 同時実行数の上限を設定 ★★★
CONCURRENT_LIMIT = 10  # 一度に実行する翻訳タスクの数を10に制限

EXCLUDE_TAGS = ['a', 'code', 'script', 'style', 'head', 'title', 'meta', '[document]']
#タグの中に'// 'を見つけると除外の除外(つまり翻訳する)になります

SPECIAL_HANDLING_TAGS = ['pre']
# --- 設定ここまで ---

# ★★★ セマフォを引数として受け取るように変更 ★★★
async def translate_text_list(texts, translator, semaphore):
    """テキストのリストをまとめて翻訳するヘルパー関数"""
    tasks = []
    for text in texts:
        if text.strip():
            # 各タスクにセマフォの制御を追加
            task = asyncio.create_task(translate_with_semaphore(text, translator, semaphore))
            tasks.append(task)
    
    translated_results = await asyncio.gather(*tasks)
    return [result for result in translated_results if result is not None]

# ★★★ セマフォを使って翻訳を実行するラッパー関数 ★★★
async def translate_with_semaphore(text, translator, semaphore):
    async with semaphore: # セマフォの「許可」が得られるまで待つ
        try:
            # 許可が得られたら翻訳を実行
            translated = await translator.translate(text, dest=TARGET_LANG)
            return translated.text
        except Exception as e:
            print(f"  - ERROR during translation: {e}")
            return None # エラー時はNoneを返す

async def process_file(filename, translator, semaphore): # semaphoreを引数に追加
    input_path = os.path.join(INPUT_DIR, filename)
    output_path = os.path.join(OUTPUT_DIR, filename)

    print(f"Processing: {filename} ...")

    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'html.parser')
    except Exception as e:
        print(f"  - ERROR reading file: {e}")
        return

    # 1. 特別扱いするタグ（<pre>など）を先に処理する
    for tag in soup.find_all(SPECIAL_HANDLING_TAGS):
        lines = tag.get_text().split('\n')
        lines_to_translate = []
        translation_map = {}

        for i, line in enumerate(lines):
            stripped_line = line.strip()
            if stripped_line.startswith('//'):
                comment_text = stripped_line.lstrip('//').strip()
                if comment_text:
                    lines_to_translate.append(comment_text)
                    translation_map[comment_text] = i

        if lines_to_translate:
            print(f"  - Found {len(lines_to_translate)} comments in <{tag.name}> to translate...")
            # semaphoreを渡す
            translated_comments = await translate_text_list(lines_to_translate, translator, semaphore)
            
            # 翻訳前と翻訳後のペアを作成（エラーでNoneが返った場合を考慮）
            original_texts_for_mapping = [text for text in lines_to_translate if text.strip()]
            for original, translated in zip(original_texts_for_mapping, translated_comments):
                if translated is None: continue # 翻訳に失敗したものはスキップ
                line_index = translation_map[original]
                indent = lines[line_index][:lines[line_index].find('//')]
                lines[line_index] = f"{indent}// {translated}"

        new_content = '\n'.join(lines)
        tag.string = new_content
        print(f"  - Processed special tag <{tag.name}>.")

    # 2. 通常の翻訳処理（再帰関数）
    async def translate_element(element):
        if hasattr(element, 'name') and element.name is not None:
            if element.name in EXCLUDE_TAGS or element.name in SPECIAL_HANDLING_TAGS:
                return
            for child in list(element.children):
                await translate_element(child)
        
        elif isinstance(element, NavigableString) and element.strip():
            if element.parent.name not in EXCLUDE_TAGS and element.parent.name not in SPECIAL_HANDLING_TAGS:
                # ここでもセマフォを使って翻訳
                translated_text = await translate_with_semaphore(str(element), translator, semaphore)
                if translated_text:
                    element.replace_with(translated_text)

    if soup.body:
        await translate_element(soup.body)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(str(soup))
    
    print(f"Saved to: {output_path}\n")

async def main():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    translator = Translator()
    # ★★★ セマフォをここで作成 ★★★
    semaphore = asyncio.Semaphore(CONCURRENT_LIMIT)
    tasks = []

    for filename in os.listdir(INPUT_DIR):
        if filename.endswith('.html'):
            # process_fileにセマフォを渡す
            tasks.append(process_file(filename, translator, semaphore))
    
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
