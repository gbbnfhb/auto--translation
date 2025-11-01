import os
import asyncio
import random
import re

# --- 設定 ---
INPUT_DIR = 'input_md'      # 翻訳したいMarkdownプロジェクトのルートフォルダ
OUTPUT_DIR = 'output_md'    # 翻訳後のファイルを保存するルートフォルダ
TARGET_LANG = 'ja'           # 翻訳先の言語コード
CONCURRENT_LIMIT = 5         # 同時実行数の上限
MIN_DELAY = 0.5              # 最低0.5秒の待機時間
MAX_DELAY = 1.5              # 最大1.5秒の待機時間
FILE_EXTENSIONS = ['.md', '.markdown'] # 対象とするファイルの拡張子
# --- 設定ここまで ---

# googletransは別途インストールが必要です: pip install googletrans==4.0.0-rc1
try:
    from googletrans import Translator
except ImportError:
    print("googletransがインストールされていません。")
    print("コマンドプロンプトで 'pip install googletrans==4.0.0-rc1' を実行してください。")
    exit()

CODE_BLOCK_MARKER = "`" * 3

# セマフォを使って翻訳を実行するラッパー関数
async def translate_line(line, translator, semaphore):
    """テキスト行を翻訳する。インラインコードは保護する。"""
    
    if not re.search(r'[a-zA-Z0-9]', line):
        return line

    inline_code_snippets = {}
    def replace_inline_code(match):
        placeholder = f"__INLINECODE{len(inline_code_snippets)}__"
        inline_code_snippets[placeholder] = match.group(0)
        return placeholder

    line_with_placeholders = re.sub(r'`[^`]*?`', replace_inline_code, line)

    if not re.search(r'[a-zA-Z0-9]', line_with_placeholders):
        return line

    async with semaphore:
        try:
            wait_time = random.uniform(MIN_DELAY, MAX_DELAY)
            await asyncio.sleep(wait_time)
            
            translated = await translator.translate(line_with_placeholders, dest=TARGET_LANG)
            translated_line = translated.text

            for placeholder, original_code in inline_code_snippets.items():
                translated_line = re.sub(r'\s*' + placeholder + r'\s*', original_code, translated_line)
            
            return translated_line
        except Exception as e:
            print(f"  - 翻訳中にエラーが発生しました: '{line[:30]}...' -> {e}")
            return line

# ファイルを処理するメイン関数
async def process_file(input_path, output_path, translator, semaphore):
    print(f"処理中: {input_path} ...")
    try:
        with open(input_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"  - エラー: ファイル読み込みに失敗しました: {e}")
        return

    tasks = []
    lines_to_translate_info = [] 
    in_code_block = False
    
    for i, line in enumerate(lines):
        if line.strip().startswith(CODE_BLOCK_MARKER):
            in_code_block = not in_code_block
            continue
        
        if in_code_block:
            continue
            
        original_line_content = line.rstrip('\n\r')
        if not original_line_content:
            continue

        lines_to_translate_info.append({'index': i, 'original_line': line})
        tasks.append(translate_line(original_line_content, translator, semaphore))

    if tasks:
        print(f"  - {len(tasks)}行のテキストを翻訳します...")
        translated_results = await asyncio.gather(*tasks)
        
        for i, translated_content in enumerate(translated_results):
            info = lines_to_translate_info[i]
            original_ending = info['original_line'][len(info['original_line'].rstrip('\n\r')):]
            lines[info['index']] = translated_content + original_ending
    else:
        print("  - 翻訳対象のテキストが見つかりませんでした。")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    print(f"保存先: {output_path}\n")

async def main():
    translator = Translator()
    semaphore = asyncio.Semaphore(CONCURRENT_LIMIT)
    tasks = []
    
    for root, dirs, files in os.walk(INPUT_DIR):
        # ★★★ このループが抜けていました！★★★
        for file in files:
            if any(file.endswith(ext) for ext in FILE_EXTENSIONS):
                input_path = os.path.join(root, file)
                relative_path = os.path.relpath(input_path, INPUT_DIR)
                output_path = os.path.join(OUTPUT_DIR, relative_path)
                tasks.append(process_file(input_path, output_path, translator, semaphore))

    if not tasks:
        print(f"'{INPUT_DIR}' 内に拡張子が {FILE_EXTENSIONS} のファイルが見つかりませんでした。")
        return
        
    print(f"{len(tasks)}個のファイルが見つかりました。処理を開始します...")
    await asyncio.gather(*tasks)
    print("すべてのファイルの処理が完了しました。")

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
