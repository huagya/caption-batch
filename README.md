# caption-batch

100万枚規模を見据えた画像キャプション一括ツール（Gemini / OpenRouter）。

- **再開**: 既存の非空 `.txt` はスキップ
- **並列**: `--workers`
- **失敗ログ**: `<input>/.caption_state/errors.jsonl`
- **キー**: 環境変数 / ローカル `.env` のみ（**Git に入れない**）
- **UI**: Gradio（`app.py`）＋ Windows ダブルクリック用 bat
- **画像前処理**: 長辺を `max_image_side`（既定 1536）に縮小 → JPEG quality≈85 で API へ

⚠️ **チャットや Issue に API キーを貼った場合は必ずローテート**してください。

## Windows 最初の手順（おすすめ）

1. このリポジトリを clone / 展開したフォルダを開く  
2. **`setup.bat`** をダブルクリック（初回だけ。venv 作成＋ `pip install`）  
3. 作られた **`.env`** をメモ帳で開き、キーを入れる  

```
GEMINI_API_KEY=...
OPENROUTER_API_KEY=...
```

4. **`run_ui.bat`** をダブルクリック → ブラウザで UI が開く  
5. Provider / Model / 画像フォルダを指定して実行（まずは Dry-run や Limit=5 推奨）

止めるときは UI の黒いコンソール窓で `Ctrl+C`、または窓を閉じる。  
依存を入れ直したいときも `setup.bat` をもう一度。

## Gradio でできること

- Provider / モデル ID / 画像フォルダ
- workers・limit・上書き・dry-run
- temperature / max output tokens / max image side
- モデル一覧（**OpenRouter は料金付き**。**Gemini の list API には単価なし**）
- API キーをこの PC の `.env` に保存（任意）

## CLI

```bat
cd caption-batch
.venv\Scripts\activate

python -m caption_batch list-models --provider openrouter --contains gemini
python -m caption_batch list-models --provider gemini --contains flash

REM 小規模
python -m caption_batch run --provider gemini --model gemini-3.5-flash-lite --input-dir D:\dataset\images --workers 4 --limit 20

REM 百万枚向け: 先にインデックス作成（1行1パス）
python -m caption_batch build-index --input-dir D:\dataset\images
python -m caption_batch run --provider gemini --model gemini-3.5-flash-lite --input-dir D:\dataset\images --from-index --workers 4

python -m caption_batch retry-failed --provider gemini --model gemini-3.5-flash-lite --input-dir D:\dataset\images --errors D:\dataset\images\.caption_state\errors.jsonl
```

生成パラメータ例:

```bat
python -m caption_batch run ... --temperature 0.2 --max-output-tokens 1024 --max-image-side 1536
REM プロバイダに送らない場合:
python -m caption_batch run ... --no-temperature --no-max-output-tokens
```

手動セットアップ（Linux/macOS）:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## モデルメモ

| Provider | 例 | 料金表示 |
|----------|-----|----------|
| Gemini 直接 | `gemini-3.5-flash-lite`（推奨デフォルト） | list API に単価なし → [Google AI 料金](https://ai.google.dev/pricing) を参照 |
| OpenRouter | `google/gemini-2.5-flash-lite` | `list-models` に $/token が出る |

新しい Gemini キーでは古い `gemini-2.5-flash-lite` が 404 になることがあります → **`gemini-3.5-flash-lite`**。

## 100万枚メモ

1. `build-index` で `image_index.txt` を作る（再スキャン不要）  
2. `run --from-index`（インデックスが無い巨大フォルダは自動で index 作成を試行）  
3. まず `--limit 20` で品質・料金感を確認  
4. workers を一気に上げない（429）  
5. 失敗は `retry-failed`  
6. 長辺リサイズで転送量を抑える（既定 1536）

残ギャップ（今後）: 完全ストリーミングキュー（メモリに全 Path を載せない）、ワーカー横断のレートリミッタ、課金ダッシュボード、Grok 本格対応。

## ライセンス / カタログ

ローカル利用向け。キーは自分のアカウントで管理。
