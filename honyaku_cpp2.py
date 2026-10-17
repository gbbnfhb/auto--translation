import os
import asyncio
import random
import re

# --- 設定 ---
INPUT_DIR = 'input_cpp'      # 翻訳したいC++プロジェクトのルートフォルダ
OUTPUT_DIR = 'output_cpp'    # 翻訳後のファイルを保存するルートフォルダ
FROM_LANG = 'en'             # 翻訳元の言語コード
TARGET_LANG = 'ja'           # 翻訳先の言語コード
CONCURRENT_LIMIT = 5         # 同時実行数の上限
MIN_DELAY = 0.5              # 最低0.5秒の待機時間
MAX_DELAY = 1.5              # 最大1.5秒の待機時間
FILE_EXTENSIONS = ['.cpp', '.h', '.c', '.hpp'] # 対象とするファイルの拡張子
# --- 設定ここまで ---

# argostranslateは別途インストールが必要です: pip install argostranslate
try:
    import argostranslate.translate
    import argostranslate.package
except ImportError:
    print("argostranslateがインストールされていません。")
    print("コマンドプロンプトで 'pip install argostranslate' を実行してください。")
    exit()

def ensure_installed_language_package(from_code, to_code):
    """指定した言語ペアのパッケージがインストールされているか確認し、なければインストールする"""
    print(f"言語パッケージの確認中 ({from_code} -> {to_code})...")
    argostranslate.package.update_package_index()
    available_packages = argostranslate.package.get_available_packages()
    
    # 既にインストールされているパッケージをチェック
    installed_packages = argostranslate.package.get_installed_packages()
    is_installed = any(
        p.from_code == from_code and p.to_code == to_code 
        for p in installed_packages
    )
    
    if not is_installed:
        print(f"パッケージ {from_code} -> {to_code} をダウンロードしてインストールします...")
        package_to_install = next(
            filter(
                lambda x: x.from_code == from_code and x.to_code == to_code,
                available_packages
            ),
            None
        )
        if package_to_install:
            argostranslate.package.install_from_path(package_to_install.download())
            print("言語パッケージのインストールが完了しました。")
        else:
            raise RuntimeError(f"言語ペア {from_code} -> {to_code} のパッケージが見つかりませんでした。")

# セマフォを使って翻訳を実行するラッパー関数
async def translate_with_semaphore(text, semaphore):
    # 空白や特殊文字のみのコメントは翻訳しない
    if not re.search(r'[a-zA-Z0-9]', text):
        return text
        
    async with semaphore:
        try:
            wait_time = random.uniform(MIN_DELAY, MAX_DELAY)
            await asyncio.sleep(wait_time)
            
            # 翻訳APIに渡す前に、コメント記号などを取り除く
            clean_text = text.strip().lstrip('//').lstrip('/*').rstrip('*/').strip()
            if not clean_text:
                return text

            # argostranslateの翻訳処理は同期処理のため、to_threadで非同期化
            translated_text = await asyncio.to_thread(
                argostranslate.translate.translate, 
                clean_text, 
                FROM_LANG, 
                TARGET_LANG
            )
            
            # 元のインデントやコメント形式を維持して整形する
            indent = text[:len(text) - len(text.lstrip())]
            if text.lstrip().startswith('//'):
                return f"{indent}// {translated_text}"
            elif text.lstrip().startswith('/*'):
                # ブロックコメントは元の形式をできるだけ維持
                return f"{indent}/* {translated_text} */"
            else: # これは基本起こらないはず
                return translated_text

        except Exception as e:
            print(f"  - ERROR during translation for '{text[:30]}...': {e}")
            return text # エラー時は元のテキストを返す

# ファイルを処理するメイン関数
async def process_file(input_path, output_path, semaphore):
    print(f"Processing: {input_path} ...")
    try:
        with open(input_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        print(f"  - ERROR reading file: {e}")
        return

    # C++のコメントを正規表現で全て見つけ出す
    comment_pattern = re.compile(r'(//.*)|(/\*[\s\S]*?\*/)')
    
    comments = [match.group(0) for match in comment_pattern.finditer(content)]
    
    if not comments:
        print("  - No comments found. Copying file directly.")
    else:
        print(f"  - Found {len(comments)} comments. Translating...")
        
        # 見つけたコメントをまとめて翻訳
        tasks = [translate_with_semaphore(comment, semaphore) for comment in comments]
        translated_comments = await asyncio.gather(*tasks)
        
        # 元のコンテンツのコメント部分を、翻訳後のコメントで置換していく
        translation_map = dict(zip(comments, translated_comments))
        
        def replace_comment(match):
            original_comment = match.group(0)
            return translation_map.get(original_comment, original_comment)

        content = comment_pattern.sub(replace_comment, content)

    # 出力先のディレクトリを作成
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # 変更を新しいファイルに保存
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"Saved to: {output_path}\n")

async def main():
    # 初回実行時に必要な言語モデル（英語 -> 日本語）がなければ自動インストール
    try:
        ensure_installed_language_package(FROM_LANG, TARGET_LANG)
    except Exception as e:
        print(f"言語パッケージのセットアップに失敗しました: {e}")
        return

    semaphore = asyncio.Semaphore(CONCURRENT_LIMIT)
    tasks = []

    # os.walkを使ってサブディレクトリを再帰的に探索
    for root, dirs, files in os.walk(INPUT_DIR):
        for file in files:
            # 指定された拡張子のファイルのみを対象とする
            if any(file.endswith(ext) for ext in FILE_EXTENSIONS):
                input_path = os.path.join(root, file)
                
                # 出力パスを計算 (入力ディレクトリ構造を維持)
                relative_path = os.path.relpath(input_path, INPUT_DIR)
                output_path = os.path.join(OUTPUT_DIR, relative_path)
                
                tasks.append(process_file(input_path, output_path, semaphore))

    if not tasks:
        print(f"No files with extensions {FILE_EXTENSIONS} found in '{INPUT_DIR}'.")
        return
        
    print(f"Found {len(tasks)} files to process. Starting...")
    await asyncio.gather(*tasks)
    print("All files processed.")

if __name__ == "__main__":
    # Windowsでasyncioを動かすためのおまじない
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())