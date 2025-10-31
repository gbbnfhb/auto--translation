import os
import asyncio
import random
import re

# --- 設定 ---
INPUT_DIR = 'input_tex'      # 翻訳したいTeXプロジェクトのルートフォルダ
OUTPUT_DIR = 'output_tex'    # 翻訳後のファイルを保存するルートフォルダ
TARGET_LANG = 'ja'           # 翻訳先の言語コード
CONCURRENT_LIMIT = 5         # 同時実行数の上限
MIN_DELAY = 0.5              # 最低0.5秒の待機時間
MAX_DELAY = 1.5              # 最大1.5秒の待機時間
FILE_EXTENSIONS = ['.tex']   # 対象とするファイルの拡張子
# --- 設定ここまで ---

# googletransは別途インストールが必要です: pip install googletrans==4.0.0-rc1
try:
    from googletrans import Translator
except ImportError:
    print("googletransがインストールされていません。")
    print("コマンドプロンプトで 'pip install googletrans==4.0.0-rc1' を実行してください。")
    exit()

# セマフォを使って翻訳を実行するラッパー関数
async def translate_with_semaphore(text, translator, semaphore):
    if not re.search(r'[a-zA-Z0-9]', text):
        return text
        
    async with semaphore:
        try:
            wait_time = random.uniform(MIN_DELAY, MAX_DELAY)
            await asyncio.sleep(wait_time)
            
            clean_text = text.strip()
            if not clean_text:
                return text

            translated = await translator.translate(clean_text, dest=TARGET_LANG)
            
            indent = text[:len(text) - len(text.lstrip())]
            return f"{indent}{translated.text}\n"

        except Exception as e:
            print(f"  - ERROR during translation for '{text[:30]}...': {e}")
            return text

# ファイルを処理するメイン関数
async def process_file(input_path, output_path, translator, semaphore):
    print(f"Processing: {input_path} ...")
    try:
        with open(input_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"  - ERROR reading file: {e}")
        return

    lines_to_translate = []
    line_indices_to_translate = []
    
    item_pattern = re.compile(r'^\s*\\item\s*')
    begin_pattern = re.compile(r'\\{')
    end_pattern = re.compile(r'\\}')
    
    in_code_block = False

    for i, line in enumerate(lines):
        # ★★★★★ ロジック修正箇所 ★★★★★
        # ルール1: \item の行を絶対最優先で判定
        if item_pattern.match(line):
            text_part = item_pattern.sub('', line)
            if text_part.strip():
                lines_to_translate.append(text_part)
                line_indices_to_translate.append(i)
            # \item の行は翻訳対象リストに追加したら、他のルールを評価せず次の行へ
            continue
        # ★★★★★ ここまで ★★★★★

        # ルール2: コードブロックの開始/終了を判定
        if begin_pattern.search(line):
            in_code_block = True
            continue
        if end_pattern.search(line):
            in_code_block = False
            continue
        
        # ルール3: コードブロック内、または'\'を含む行は翻訳しない
        if in_code_block or '\\' in line:
            continue

        # ルール4: 空行や空白のみの行は翻訳しない
        if not line.strip():
            continue

        # --- 上記のルールに当てはまらないものが翻訳対象 ---
        lines_to_translate.append(line)
        line_indices_to_translate.append(i)

    # --- 翻訳処理の実行 ---
    if not lines_to_translate:
        print("  - No translatable text found. Copying file directly.")
        translated_content = "".join(lines)
    else:
        print(f"  - Found {len(lines_to_translate)} lines/parts to translate. Translating...")
        
        tasks = [translate_with_semaphore(text, translator, semaphore) for text in lines_to_translate]
        translated_texts = await asyncio.gather(*tasks)
        
        translated_lines = list(lines)
        for i, original_line_index in enumerate(line_indices_to_translate):
            original_line = lines[original_line_index]
            translated_text = translated_texts[i]
            
            if item_pattern.match(original_line):
                item_command_part = item_pattern.match(original_line).group(0)
                translated_lines[original_line_index] = f"{item_command_part}{translated_text.lstrip()}"
            else:
                translated_lines[original_line_index] = translated_text
        
        translated_content = "".join(translated_lines)

    # --- ファイルへの書き込み ---
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(translated_content)
    
    print(f"Saved to: {output_path}\n")

async def main():
    translator = Translator()
    semaphore = asyncio.Semaphore(CONCURRENT_LIMIT)
    tasks = []

    for root, dirs, files in os.walk(INPUT_DIR):
        for file in files:
            if any(file.endswith(ext) for ext in FILE_EXTENSIONS):
                input_path = os.path.join(root, file)
                relative_path = os.path.relpath(input_path, INPUT_DIR)
                output_path = os.path.join(OUTPUT_DIR, relative_path)
                tasks.append(process_file(input_path, output_path, translator, semaphore))

    if not tasks:
        print(f"No files with extensions {FILE_EXTENSIONS} found in '{INPUT_DIR}'.")
        return
        
    print(f"Found {len(tasks)} files to process. Starting...")
    await asyncio.gather(*tasks)
    print("All files processed.")

if __name__ == "__main__":
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
