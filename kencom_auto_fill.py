#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import csv
import re
import time
import argparse
from datetime import datetime
from playwright.sync_api import sync_playwright


def parse_args():
    parser = argparse.ArgumentParser(description="kencomの歩数自動入力スクリプト")
    parser.add_argument(
        "--csv",
        default="steps_may_2026.csv",
        help="歩数データが記録されたCSVファイルのパス (デフォルト: steps_may_2026.csv)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9222,
        help="Chromeのデバッグポート番号 (デフォルト: 9222)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="実際に入力・保存せず、要素の特定や日付の遷移テストのみを行う"
    )
    parser.add_argument(
        "--debug-dom",
        action="store_true",
        help="現在開いているページのボタンやインプットなどの要素を一覧出力して終了する"
    )
    parser.add_argument(
        "--wait",
        type=float,
        default=1.5,
        help="各操作の間の待機秒数 (デフォルト: 1.5)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="実行する最大日数（0を指定すると無制限。1を指定すると1日分だけで終了します）"
    )
    return parser.parse_args()


def load_steps_csv(csv_path):
    """CSVファイルから歩数データを読み込む"""
    if not os.path.exists(csv_path):
        print(f"[-] エラー: CSVファイルが見つかりません: {csv_path}", file=sys.stderr)
        sys.exit(1)

    steps_data = {}
    try:
        with open(csv_path, mode='r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader, None)  # ヘッダーをスキップ

            if header and len(header) >= 2:
                print(f"[+] CSVヘッダーを確認: {header}")

            for row in reader:
                if not row or len(row) < 2:
                    continue
                date_str = row[0].strip()
                count_str = row[1].strip()

                date_norm = date_str.replace('/', '-')

                try:
                    steps_data[date_norm] = int(count_str)
                except ValueError:
                    print(
                        f"[!] 警告: 歩数が数値ではありません。スキップします: 日付={date_str}, 歩数={count_str}")

        print(f"[+] CSVから {len(steps_data)} 件の歩数データを読み込みました。")
        return steps_data
    except Exception as e:
        print(f"[-] エラー: CSVファイルの読み込みに失敗しました: {e}", file=sys.stderr)
        sys.exit(1)


def get_current_date_from_page(page):
    """ページ内のテキストから現在表示されている日付(YYYY-MM-DD)を抽出する"""
    print("[TRACE] 日付の取得を開始します...")
    targets = [
        "h2",
        "h3",
        "[class*='date']",
        "[class*='calendar']",
        "[class*='header']",
        "body"
    ]

    for selector in targets:
        try:
            locator = page.locator(selector)
            count = locator.count()
            for i in range(count):
                el = locator.nth(i)
                if not el.is_visible():
                    continue
                text = el.inner_text().strip()
                if not text:
                    continue

                # 1. YYYY年MM月DD日
                match = re.search(r'(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日', text)
                if match:
                    year, month, day = match.groups()
                    dt_str = f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
                    print(
                        f"[TRACE] 要素 '{selector}' (インデックス {i}) から日付を検出: '{text}' -> パース結果: '{dt_str}'")
                    return dt_str

                # 2. YYYY/MM/DD
                match = re.search(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', text)
                if match:
                    year, month, day = match.groups()
                    dt_str = f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
                    print(
                        f"[TRACE] 要素 '{selector}' (インデックス {i}) から日付を検出: '{text}' -> パース結果: '{dt_str}'")
                    return dt_str

                # 3. MM月DD日(曜)
                match = re.search(r'(\d{1,2})月\s*(\d{1,2})日', text)
                if match:
                    month, day = match.groups()
                    dt_str = f"2026-{int(month):02d}-{int(day):02d}"
                    print(
                        f"[TRACE] 要素 '{selector}' (インデックス {i}) から年なし日付を検出 (2026年と仮定): '{text}' -> パース結果: '{dt_str}'")
                    return dt_str
        except Exception as e:
            print(f"[TRACE] 要素 '{selector}' の解析中にエラー: {e}")
            continue

    print("[TRACE] ページから日付を検出できませんでした。")
    return None


def debug_print_dom(page):
    """デバッグ用に現在のページの主要な要素一覧を出力する"""
    print("\n" + "=" * 50)
    print("【デバッグ情報】現在のページの主要なインタラクティブ要素一覧")
    print("=" * 50)

    print("\n--- ボタン (<button>) ---")
    buttons = page.locator("button").all()
    for i, btn in enumerate(buttons):
        try:
            text = btn.inner_text().strip().replace('\n', ' ')
            html = btn.evaluate("el => el.outerHTML")
            has_svg = "<svg" in html
            svg_info = " (SVGあり)" if has_svg else ""
            print(f"[{i:02d}] テキスト: '{text}'{svg_info}")
            if i < 20:
                html_short = html[:200] + "..." if len(html) > 200 else html
                print(f"     HTML: {html_short}")
        except Exception as e:
            print(f"[{i:02d}] 取得エラー: {e}")

    print("\n--- リンク (<a>) ---")
    links = page.locator("a").all()
    for i, lnk in enumerate(links):
        try:
            text = lnk.inner_text().strip().replace('\n', ' ')
            href = lnk.get_attribute("href") or ""
            print(f"[{i:02d}] テキスト: '{text}' | href: '{href}'")
        except Exception as e:
            print(f"[{i:02d}] 取得エラー: {e}")

    print("\n--- 入力フィールド (<input>) ---")
    inputs = page.locator("input").all()
    for i, inp in enumerate(inputs):
        try:
            inp_type = inp.get_attribute("type") or "text"
            placeholder = inp.get_attribute("placeholder") or ""
            inp_val = inp.evaluate("el => el.value") or ""
            inp_id = inp.get_attribute("id") or ""
            print(
                f"[{i:02d}] ID: '{inp_id}' | Type: '{inp_type}' | Placeholder: '{placeholder}' | Value: '{inp_val}'")
        except Exception as e:
            print(f"[{i:02d}] 取得エラー: {e}")

    print("=" * 50 + "\n")


def get_element_html_safe(locator_element):
    """ロケーターから安全にHTMLを取得する"""
    try:
        if locator_element and locator_element.count() > 0:
            return locator_element.evaluate("el => el.outerHTML")
    except Exception:
        pass
    return "[HTML取得失敗 または 要素なし]"


def find_step_button(page):
    """歩数入力画面を開くためのボタン（未入力アイコン）を特定する"""
    print("[TRACE] 歩数入力ボタンの探索を開始します...")

    # 1. ユーザー指定のSVGパス (未入力を示す丸いXマーク)
    path_locator = page.locator(
        'path[d^="M12 2.5C6.75 2.5 2.5 6.75 2.5 12C2.5 17.25 6.75 21.5 12 21.5C17.25 21.5"]')
    if path_locator.count() > 0:
        html = get_element_html_safe(path_locator.first)
        print(f"[TRACE] 1. ユーザー指定の完全なSVGパスを検出しました: {html[:150]}...")
        parent_btn = path_locator.first.locator(
            "xpath=./ancestor::button | ./ancestor::a | ./ancestor::div[@role='button']")
        if parent_btn.count() > 0:
            print(
                f"[TRACE] -> クリック可能な親要素を検出: {get_element_html_safe(parent_btn.first)[:150]}...")
            return parent_btn.first
        return path_locator.first

    # 2. その他のSVGパス部分一致
    path_locator_short = page.locator('path[d^="M12 2.5C6.75 2.5"]')
    if path_locator_short.count() > 0:
        html = get_element_html_safe(path_locator_short.first)
        print(f"[TRACE] 2. 部分一致のSVGパスを検出しました: {html[:150]}...")
        parent_btn = path_locator_short.first.locator(
            "xpath=./ancestor::button | ./ancestor::a | ./ancestor::div[@role='button']")
        if parent_btn.count() > 0:
            print(
                f"[TRACE] -> クリック可能な親要素を検出: {get_element_html_safe(parent_btn.first)[:150]}...")
            return parent_btn.first
        return path_locator_short.first

    # 3. テキストや属性からの推測
    step_btn = page.locator(
        'button:has-text("歩数"), [aria-label*="歩数"], [class*="step"]')
    if step_btn.count() > 0:
        print(
            f"[TRACE] 3. テキスト/属性から歩数ボタンを推測しました: {get_element_html_safe(step_btn.first)[:150]}...")
        return step_btn.first

    print("[TRACE] 歩数入力ボタンを特定できませんでした。")
    return None


def select_date_in_calendar(page, target_date_str, wait_sec):
    """歩数入力ダイアログ内でカレンダーを開き、指定された日付(YYYY-MM-DD)を選択する"""
    print(f"[TRACE] カレンダーで日付 '{target_date_str}' の選択を開始します...")

    # 1. 日付文字列から年、月、日を抽出
    try:
        dt = datetime.strptime(target_date_str, "%Y-%m-%d")
        target_year = dt.year
        target_month = dt.month
        target_day = dt.day
    except Exception as e:
        print(f"[-] エラー: 日付のパースに失敗しました ({target_date_str}): {e}")
        return False

    # 2. カレンダーアイコンボタンをクリックしてカレンダーを表示
    # ユーザー提供HTML: <button class="... DatePicker_calendarButton__I_k8E ..." ...>
    calendar_btn = page.locator('button[class*="calendarButton"]')
    if calendar_btn.count() == 0:
        print("[-] エラー: カレンダーボタンが見つかりません。")
        return False

    print(
        f"[TRACE] -> カレンダーボタンをクリックします: {get_element_html_safe(calendar_btn.first)[:150]}...")
    calendar_btn.first.click()
    time.sleep(wait_sec * 0.5)

    # 3. カレンダーの表示月を合わせる
    # ユーザー提供HTML: <div class="MuiPickersCalendarHeader-label ...">2026年 5月</div>
    # 「前月を表示」ボタン: title="前月を表示" aria-label="前月を表示"
    # 「次月を表示」ボタン: title="次月を表示" aria-label="次月を表示"

    month_label = page.locator('.MuiPickersCalendarHeader-label')
    if month_label.count() == 0:
        print("[-] エラー: カレンダーの月表示ラベルが見つかりません。")
        return False

    max_adjust_attempts = 12
    for attempt in range(max_adjust_attempts):
        current_month_text = month_label.first.inner_text().strip()
        print(
            f"[TRACE]    - 現在のカレンダー表示月 (試行 {attempt}): '{current_month_text}'")

        # 柔軟に対応するため正規表現で年と月を抽出
        match = re.search(r'(\d{4})年\s*(\d{1,2})月', current_month_text)
        if not match:
            match = re.search(r'([A-Za-z]+)\s*(\d{4})', current_month_text)

        if match:
            try:
                curr_year = int(match.group(1))
                curr_month = int(match.group(2))
            except ValueError:
                curr_year = target_year
                curr_month = target_month
        else:
            print("[TRACE]    - 月表示のパースに失敗しました。デフォルトの移動を行います。")
            curr_year = target_year
            curr_month = target_month

        # 年月が一致したらループを抜ける
        if curr_year == target_year and curr_month == target_month:
            print(
                f"[TRACE]    -> カレンダーの月が目標に一致しました: {target_year}年{target_month}月")
            break

        # 移動方向の決定
        go_prev = False
        if curr_year > target_year:
            go_prev = True
        elif curr_year < target_year:
            go_prev = False
        else:
            go_prev = curr_month > target_month

        if go_prev:
            prev_btn = page.locator(
                'button[title="前月を表示"], button[aria-label="前月を表示"]')
            if prev_btn.count() > 0 and prev_btn.first.is_visible():
                print("[TRACE]    -> 『前月を表示』をクリックします...")
                prev_btn.first.click()
            else:
                print("[-] エラー: 『前月を表示』ボタンが見つかりません。")
                return False
        else:
            next_btn = page.locator(
                'button[title="次月を表示"], button[aria-label="次月を表示"]')
            if next_btn.count() > 0 and next_btn.first.is_visible():
                print("[TRACE]    -> 『次月を表示』をクリックします...")
                next_btn.first.click()
            else:
                print("[-] エラー: 『次月を表示』ボタンが見つかりません。")
                return False

        time.sleep(wait_sec * 0.5)

    # 4. カレンダーから対象の日付ボタンをクリック
    # ユーザー提供HTML: <button class="... MuiPickersDay-root ...">28</button>
    # 完全一致テキストで、かつ disabled ではないものを優先してクリック
    day_btn_selector = f'button.MuiPickersDay-root:not(.Mui-disabled):text("{target_day}")'
    day_btn = page.locator(day_btn_selector)

    if day_btn.count() == 0:
        day_btn_selector = f'button.MuiPickersDay-root:text("{target_day}")'
        day_btn = page.locator(day_btn_selector)

    if day_btn.count() == 0:
        day_btn_selector = f'button[role="gridcell"]:text("{target_day}")'
        day_btn = page.locator(day_btn_selector)

    if day_btn.count() > 0:
        target_day_btn = None
        for i in range(day_btn.count()):
            btn = day_btn.nth(i)
            if btn.is_visible():
                target_day_btn = btn
                break

        if target_day_btn:
            print(
                f"[TRACE] -> 対象日ボタンをクリックします: {get_element_html_safe(target_day_btn)[:150]}...")
            target_day_btn.click()
            time.sleep(wait_sec * 0.5)
            return True

    print(f"[-] エラー: カレンダー内で日付 '{target_day}' のボタンを見つけられませんでした。")
    return False


def auto_fill_kencom():
    args = parse_args()

    # 1. CSVデータの読み込み
    print(f"[*] CSVファイルを読み込んでいます: {args.csv}")
    steps_data = load_steps_csv(args.csv)

    # 2. Playwrightで起動中のChromeに接続
    print(f"[*] Chromeデバッグポート (localhost:{args.port}) に接続中...")
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(
                f"http://localhost:{args.port}")
        except Exception as e:
            print(f"[-] エラー: Chromeへの接続に失敗しました。Chromeがデバッグモードで起動しているか確認してください。")
            print(f"    詳細: {e}", file=sys.stderr)
            sys.exit(1)

        print("[+] Chromeに正常に接続しました。")

        # すでに開いているコンテキストとタブを取得
        context = browser.contexts[0]
        page = None

        for p_tab in context.pages:
            try:
                title = p_tab.title()
                url = p_tab.url
                if "kencom.jp/vitals" in url or "カラダの記録" in title:
                    page = p_tab
                    print(f"[+] kencomのタブを特定しました: タイトル='{title}', URL='{url}'")
                    break
            except Exception:
                continue

        if not page:
            print("[!] 警告: kencomの『カラダの記録』ページが開かれているタブが見つかりませんでした。")
            print("[*] 新しいタブで `https://kencom.jp/vitals` を開きます。")
            page = context.new_page()
            page.goto("https://kencom.jp/vitals")
            page.wait_for_load_state("networkidle")

        if args.debug_dom:
            debug_print_dom(page)
            return

        # 3. 自動入力ループ (モーダル内カレンダー切り替え方式)
        pending_dates = sorted(list(steps_data.keys()), reverse=True)
        if not pending_dates:
            print("[-] CSVデータが空のため、処理を終了します。")
            return

        print("\n" + "=" * 50)
        print(
            f"[*] 自動入力を開始します。動作モード: {'[テストモード]' if args.dry_run else '[本番保存モード]'}")
        print(
            f"[*] 処理対象件数: {len(pending_dates)} 件 ({pending_dates[-1]} 〜 {pending_dates[0]})")
        if args.limit > 0:
            print(f"[!] 制限実行モードが有効です。最大 {args.limit} 日分の入力試行後に終了します。")
        print("=" * 50 + "\n")

        success_count = 0
        skip_count = 0
        processed_days = 0

        for target_date in pending_dates:
            if args.limit > 0 and processed_days >= args.limit:
                print(f"[+] 指定された制限日数 ({args.limit}日) に達したため、処理を終了します。")
                break

            processed_days += 1
            target_steps = steps_data[target_date]
            print(
                f"\n--- 処理開始: {target_date} ({target_steps} 歩) (処理累計: {processed_days}/{args.limit if args.limit > 0 else '無制限'}日) ---")

            # 1. 歩数入力ボタン（未入力アイコンまたは登録済み数値ボタン）をクリックしてモーダルを開く
            # 画面全体の日付変更処理は一切不要で、現在表示中の日付の入力エリアをただクリックします。
            step_btn = find_step_button(page)

            if not step_btn or not step_btn.is_visible():
                print("[-] エラー: 画面上に歩数入力ボタンが見つかりません。モーダルを開けませんでした。スキップします。")
                skip_count += 1
                continue

            try:
                print(
                    f"[TRACE] -> 歩数入力エリアをクリックしてモーダルを開きます。対象要素: {get_element_html_safe(step_btn)[:150]}...")
                step_btn.click()
                time.sleep(args.wait)

                # 2. ダイアログ内のカレンダーを操作して日付を対象日に切り替える
                if not select_date_in_calendar(page, target_date, args.wait):
                    print("[-] エラー: カレンダーでの日付切り替えに失敗しました。この日をスキップします。")
                    page.keyboard.press("Escape")  # モーダルを閉じる
                    time.sleep(args.wait)
                    skip_count += 1
                    continue

                # 3. 歩数入力フィールドの特定と入力
                input_field = page.locator(
                    'input[type="number"], input[placeholder*="歩数"], input[placeholder*="入力"]')
                print(f"[TRACE] -> 発見された入力フィールドの数: {input_field.count()}")

                target_input = None
                for i in range(input_field.count()):
                    inp = input_field.nth(i)
                    print(
                        f"[TRACE]    - 入力フィールド[{i}]: {get_element_html_safe(inp)[:150]}")
                    if inp.is_visible():
                        target_input = inp
                        break

                if target_input:
                    print(
                        f"[TRACE] -> ターゲット入力欄を決定: {get_element_html_safe(target_input)[:150]}")

                    if not args.dry_run:
                        # 既存の値をクリアして入力
                        target_input.click()
                        page.keyboard.press("Control+A")
                        page.keyboard.press("Backspace")
                        target_input.fill(str(target_steps))
                        time.sleep(args.wait * 0.5)

                        # 入力後の値を確認
                        curr_val = target_input.evaluate("el => el.value")
                        print(f"[TRACE] -> 入力完了後のフィールドの値: '{curr_val}'")

                        # 4. 保存・登録ボタンのテキスト直接特定とクリック
                        save_btn = page.locator('button:has-text("登録する")')
                        print(
                            f"[TRACE] -> 発見された '登録する' ボタン数: {save_btn.count()}")

                        if save_btn.count() == 0:
                            save_btn = page.locator(
                                'button:has-text("登録"), button:has-text("保存"), button:has-text("記録")')
                            print(
                                f"[TRACE] -> 発見された '登録/保存/記録' ボタン数: {save_btn.count()}")

                        if save_btn.count() == 0:
                            save_btn = page.locator(
                                '[class*="submitButton"], [class*="StepForm_submitButton"]')
                            print(
                                f"[TRACE] -> クラス名による保存ボタン候補数: {save_btn.count()}")

                        target_save = None
                        for i in range(save_btn.count()):
                            btn = save_btn.nth(i)
                            print(
                                f"[TRACE]    - 保存ボタン[{i}]: Text='{btn.inner_text().strip()}', {get_element_html_safe(btn)[:150]}")
                            if btn.is_visible():
                                target_save = btn
                                break

                        if target_save and target_save.is_visible():
                            try:
                                print(
                                    f"[TRACE] -> 保存ボタンをクリックします。対象: {get_element_html_safe(target_save)[:150]}")
                                target_save.click()
                                time.sleep(args.wait * 0.5)
                            except Exception as e:
                                print(f"[TRACE] -> 保存ボタンクリックで例外: {e}")

                        # 5. 上書き確認ダイアログの自動検知と処理
                        time.sleep(args.wait * 0.5)
                        overwrite_dialog = page.locator(
                            'form:has-text("同じ日付 of データ"), form:has-text("既に存在しています"), h2:has-text("既に存在しています")')
                        print(
                            f"[TRACE] -> 上書き確認ダイアログの検出数: {overwrite_dialog.count()}")

                        is_dialog_visible = False
                        for i in range(overwrite_dialog.count()):
                            dialog = overwrite_dialog.nth(i)
                            print(
                                f"[TRACE]    - ダイアログ[{i}]: {get_element_html_safe(dialog)[:150]}")
                            if dialog.is_visible():
                                is_dialog_visible = True
                                break

                        if is_dialog_visible:
                            print("[+] 上書き確認ポップアップを検知しました。")
                            overwrite_btn = page.locator(
                                'button:has-text("上書きする")')
                            print(
                                f"[TRACE] -> 発見された '上書きする' ボタン数: {overwrite_btn.count()}")

                            if overwrite_btn.count() == 0:
                                overwrite_btn = page.locator(
                                    'button[type="submit"]:has-text("上書き")')
                                print(
                                    f"[TRACE] -> 発見された上書きボタン(フォールバック)候補数: {overwrite_btn.count()}")

                            target_overwrite = None
                            for i in range(overwrite_btn.count()):
                                btn = overwrite_btn.nth(i)
                                print(
                                    f"[TRACE]    - 上書きボタン[{i}]: Text='{btn.inner_text().strip()}', {get_element_html_safe(btn)[:150]}")
                                if btn.is_visible():
                                    target_overwrite = btn
                                    break

                            if target_overwrite:
                                print(
                                    f"[TRACE] -> 『上書きする』ボタンをクリックします: {get_element_html_safe(target_overwrite)[:150]}")
                                target_overwrite.click()
                                time.sleep(args.wait * 1.5)
                                print(
                                    f"[✔] {target_date}: {target_steps} 歩 を上書き記録しました。")
                                success_count += 1
                            else:
                                print("[-] エラー: 『上書きする』ボタンを特定できませんでした。")
                                page.keyboard.press("Escape")
                                time.sleep(args.wait)
                                skip_count += 1
                        else:
                            time.sleep(args.wait)
                            print(
                                f"[✔] {target_date}: {target_steps} 歩 を新規記録しました。")
                            success_count += 1
                    else:
                        print(
                            f"    [Dry-run] テストモードのため保存はスキップします（値={target_steps}）。")
                        page.keyboard.press("Escape")
                        time.sleep(args.wait)
                        success_count += 1
                else:
                    print("[-] エラー: 歩数入力用のインプットフィールドが見つかりませんでした。")
                    page.keyboard.press("Escape")
                    time.sleep(args.wait)
                    skip_count += 1

            except Exception as e:
                print(f"[-] 入力処理中に例外が発生しました: {e}")
                page.keyboard.press("Escape")
                time.sleep(args.wait)
                skip_count += 1

        print("\n" + "=" * 50)
        print("【実行完了レポート】")
        print(f"  - 処理モード: {'テストモード' if args.dry_run else '本番保存モード'}")
        print(f"  - 処理試行日数: {processed_days} 日")
        print(f"  - 記録成功（新規/上書き）: {success_count} 件")
        print(f"  - スキップ（入力失敗など）: {skip_count} 件")
        print("=" * 50 + "\n")


if __name__ == "__main__":
    auto_fill_kencom()
