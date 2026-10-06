#前準備
# pip install argostranslate
#argospm update
#argospm install translate-en_ja

import os
import re
import argostranslate.package
import argostranslate.translate

# --- 設定 ---
INPUT_DIR = 'input_js'      # 翻訳したいJSプロジェクトのルートフォルダ
OUTPUT_DIR = 'output_js'    # 翻訳後のファイルを保存するルートフォルダ
FROM_LANG = 'en'            # 翻訳元の言語コード
TO_LANG = 'ja'              # 翻訳先の言語コード
FILE_EXTENSIONS = ['.js']   # 対象とするファイルの拡張子
# --- 設定ここまで ---

def translate_comment(text):
    # 空白や特殊文字のみのコメントは翻訳しない
    if not re.search(r'[a-zA-Z0-9]', text):
        return text
        
    try:
        # コメント記号を取り除く
        clean_text = text.strip().lstrip('//').lstrip('/*').rstrip('*/').strip()
        if not clean_text:
            return text

        # argostranslateによるローカルオフライン翻訳
        translated_text = argostranslate.translate.translate(clean_text, FROM_LANG, TO_LANG)
        if not translated_text:
            return text
        
        # 元のインデントやコメント形式を維持
        indent = text[:len(text) - len(text.lstrip())]
        if text.lstrip().startswith('//'):
            return f"{indent}// {translated_text}"
        elif text.lstrip().startswith('/*'):
            return f"{indent}/* {translated_text} */"
        else:
            return translated_text

    except Exception as e:
        print(f"  - 翻訳エラー (スキップ): {e}")
        return text

def process_file(input_path, output_path):
    print(f"Processing: {input_path} ...")
    try:
        with open(input_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception as e:
        print(f"  - ERROR reading file: {e}")
        return

    # コメントを抽出
    comment_pattern = re.compile(r'(//.*)|(/\*[\s\S]*?\*/)')
    comments = [match.group(0) for match in comment_pattern.finditer(content)]
    
    if not comments:
        print("  - No comments found. Copying file directly.")
    else:
        print(f"  - Found {len(comments)} comments. Translating offline...")
        
        # 1つずつローカルで高速に翻訳（辞書化して重複をまとめる）
        translation_map = {}
        for comment in comments:
            if comment not in translation_map:
                translation_map[comment] = translate_comment(comment)
        
        def replace_comment(match):
            original_comment = match.group(0)
            return translation_map.get(original_comment, original_comment)

        content = comment_pattern.sub(replace_comment, content)

    # 出力先のディレクトリを作成して保存
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"Saved to: {output_path}\n")

def main():
    # 念のためパッケージリストの更新を確認（オフラインでも動作）
    try:
        argostranslate.package.update_package_index()
    except Exception:
        pass
    
    files_to_process = []
    for root, dirs, files in os.walk(INPUT_DIR):
        for file in files:
            if any(file.endswith(ext) for ext in FILE_EXTENSIONS):
                input_path = os.path.join(root, file)
                relative_path = os.path.relpath(input_path, INPUT_DIR)
                output_path = os.path.join(OUTPUT_DIR, relative_path)
                files_to_process.append((input_path, output_path))

    if not files_to_process:
        print(f"No files with extensions {FILE_EXTENSIONS} found in '{INPUT_DIR}'.")
        return
        
    print(f"Found {len(files_to_process)} files to process. Starting offline translation...")
    
    for input_path, output_path in files_to_process:
        process_file(input_path, output_path)
        
    print("All files processed successfully!")

if __name__ == "__main__":
    main()