# caption-batch

画像フォルダを一括キャプションする Windows 向けツールです（Gemini / OpenRouter）。

**Gradio UI は廃止**し、ほかの huagya ツールと同じ構成に揃えました。

- **core** … キャプション処理本体（discover / runner / providers / prompts）
- **FastAPI** … ローカル API（ジョブ開始・停止・状態・モデル一覧・キー保存・UI設定）
- **静的 WebUI** … `web/`
- **Typer CLI** … `caption-batch` / `python -m caption_batch.cli`
- **install.bat / start.bat / update.bat** … ダブルクリック運用
- **port.json** … 既定ポート **8771**（8751=prepend, 8761=pair-filter）

## Windows での使い方（最短）

1. クローン
   ```bat
   git clone https://github.com/huagya/caption-batch.git
   cd caption-batch
   ```
2. `install.bat` をダブルクリック（`.venv` 作成 + 依存関係インストール）
3. `.env.example` を `.env` にコピーし、キーを入れる
   ```
   GEMINI_API_KEY=...
   OPENROUTER_API_KEY=...
   ```
4. `start.bat` をダブルクリック → ブラウザが `http://127.0.0.1:8771/` を開く
5. WebUI でプロバイダ・モデル・フォルダを指定して **Start**

キーをチャットに貼ってしまった場合は **必ずローテーション**してください。`.env` は gitignore 済みです。

モデル例（時期により変わります）: `gemini-3.5-flash-lite` / OpenRouter の vision 対応モデル。

更新後は `update.bat` → サーバ再起動（`start.bat`）を行ってください。

## 画像準備（Image prep）契約

| モード | 挙動 |
|--------|------|
| **OFF** (`image_prep_enabled=false`) | 元ファイルのバイトをそのまま送信。再エンコードなし。MIME は拡張子から判定。 |
| **ON**（既定） | **拡大しない**。最長辺が `max_image_side` を超えるときだけ縮小。サイズ内でも **必ず** 指定フォーマット／品質へ再エンコード。 |

- 既定: `max_image_side=768`, `image_format=webp`, `image_quality=95`, Lanczos のみ
- webp の quality=100 → 可逆（lossless）
- png の quality≥100 → compress_level=0（ほぼ無圧縮）
- jpeg は RGBA→RGB（白背景合成）

## LLM パラメータ

空欄 / `null` のときは **API に送らず**、各プロバイダの既定に任せます。

| フィールド | UI 既定 | Gemini | OpenRouter | 備考 |
|------------|---------|--------|------------|------|
| temperature | 空 | ○（省略可） | ○ | Gemini 3.x は空欄推奨（公式） |
| top_p | 空 | ○ | ○ | 同上 |
| max_output_tokens | 1024 | ○ (`max_output_tokens`) | ○ (`max_tokens`) | キャプション長の安全弁。**thinking 利用時は思考トークンもここから消費**するため、medium/high では 2048 以上を推奨 |
| seed | 空 | ○ | ○ | 再現用 |
| thinking_level | 空 | ○ (`ThinkingConfig`) | ○ (`reasoning.effort`) | 下記テーブル参照 |
| media_resolution | 空 | ○ | ×（送信しない） | vision トークンコスト調整 |

presence_penalty / frequency_penalty / top_k は未対応です。

### thinking / Reasoning（統一コントロール）

| UI 値 | Gemini | OpenRouter `reasoning.effort` |
|-------|--------|-------------------------------|
| （空） | 送信しない（API 既定） | 送信しない |
| `none` | **`minimal` にマップ**（3.x は完全オフ不可。2.5 でも統一のため budget=0 は使わない） | `"none"` |
| `minimal` | `thinking_level=MINIMAL` | `"minimal"` |
| `low` | `LOW` | `"low"` |
| `medium` | `MEDIUM` | `"medium"` |
| `high` | `HIGH` | `"high"` |

- バッチでは **`include_thoughts` は付けません**（キャプション本文のみ保存）。
- 思考トークンは課金され、かつ `max_output_tokens` を消費します。切れやすいときはトークン上限を上げてください。
- OpenRouter で reasoning 非対応モデルの場合は通常無視されます。

### media_resolution（Gemini のみ）

`low` / `medium` / `high`（または `MEDIA_RESOLUTION_*`）。空欄＝API 既定。大量バッチでコストを抑えたいときは低めを検討。OpenRouter には送りません（UI でも無効化）。

### キャプション向け推奨

- **大量 / flash-lite バッチ**: thinking は空欄または `minimal`/`low`。`max_output_tokens=1024` で十分なことが多い。media_resolution は `low`〜`medium` でコスト削減可。
- **品質重視（難しいカット）**: thinking `medium`/`high` + `max_output_tokens` を **2048 以上**。media_resolution は空欄または `high`。
- **Gemini 3.x**: temperature / top_p は空欄のまま。thinking の `none` は minimal 相当。
- **旧モデル**: UI の「推奨（旧モデル向け）」で temperature=0.2 / top_p=0.95（参考値）
- **画像**: prep ON + webp q95 + max_side 768（帯域と品質のバランス）

### 二パス自己レビューについて（未実装・意図的に見送り）

キャプション生成後にもう一度モデルへ「見直し・書き換え」させる **二パス自己レビュー** は検討しましたが、**本バージョンでは入れません**。

- コストがおおよそ **×2**
- 自己書き換えによるバイアス・冗長化
- キャプション本文へのメタ文言混入（pollution）リスク

将来必要なら、バッチ本体とは別の **任意コマンド** として検討する想定です（現状の API/UI にはありません）。

## UI 設定の保存

WebUI の「設定を保存」「設定を読込」はプロジェクト直下の `ui-settings.json` に永続化します（API キーは含めません。キーは `.env`）。

```json
{ "schema": 4, "updated_at": "…", "settings": { … } }
```

`ui-settings.json` は `.gitignore` 済みです。スキーマが未知／新しい場合も既知キーだけマージし、欠けたキーは `/api/defaults` の値で補います（schema 3 で `thinking_level` / `media_resolution`、schema 4 で `user_prompt` を追加）。


## 0.6.1 — プロンプト分割と画像/テキスト順序

- **システム指示**（従来の長い `prompt` / DEFAULT_PROMPT）と **ユーザー指示**（短い `user_prompt`、既定 `Caption this image.`）を分離。
- **Gemini**: `system_instruction` にルール。ユーザー contents は **画像 → テキスト**（お手本も同様）。長いルールはユーザー parts に入れない。
- **OpenRouter**: `role=system` にルール。ユーザーは **テキスト → 画像**。few-shot は multi-turn（user/assistant）を優先。
- WebUI: 「システム指示」「ユーザー指示」の2欄。CLI: `--user-prompt`。

## 0.6.0 の新機能

### プレビュー（数枚だけ試す）
WebUI の **「プレビュー (N枚)」** で、本番と同じ設定で 1〜5 枚だけキャプションします。結果は画面のプレビュー欄に出ます（既定では `.txt` も書きます）。

### 進捗表示
ジョブ実行中に、進捗バー・ETA・速度・いま処理中のファイル・直近の失敗一覧を表示します。

### レート制限
**レート制限 RPM** で「1分あたり何回まで API を呼ぶか」を制限できます。空欄または 0 でオフ（従来どおり）。429 が多いときは 20〜60 を試してください。429 時はログに `rate_limited retry attempt=N sleep=S` と出ます。

### 前回の設定 / 続きから
フォルダ内の `.caption_state/job_snapshot.json` に、最後のジョブ設定が保存されます。
1. フォルダパスを入れる  
2. **「前回の設定を読込」**  
3. 上書き（overwrite）は OFF のまま **Start**  
→ 既にある `.txt` はスキップして続きから進みます。

### Few-shot お手本
お手本の画像パス＋キャプションを最大 3 組入れられます。モデルに「こんな書き方で」と示します。空欄なら従来どおりです。

### まだないもの（次の予定）
- 複数 PC での分割処理（sharding）
- 二パス AI 自己レビュー（コスト・汚染リスクのため見送り継続）

## CLI

```bat
.venv\Scripts\activate
caption-batch run --provider gemini --model gemini-3.5-flash-lite --input-dir D:\dataset --workers 4
caption-batch run --provider gemini --model gemini-3.5-flash-lite --input-dir D:\dataset --no-image-prep
caption-batch run --provider gemini --model gemini-3.5-flash-lite --input-dir D:\dataset --image-format webp --image-quality 95 --max-image-side 768
caption-batch list-models --provider openrouter
caption-batch build-index --input-dir D:\dataset
caption-batch retry-failed --provider gemini --model gemini-3.5-flash-lite --input-dir D:\dataset --errors D:\dataset\.caption_state\errors.jsonl
caption-batch run --provider gemini --model gemini-2.0-flash --input-dir D:\dataset --rate-limit-rpm 30
caption-batch run --provider gemini --model gemini-2.0-flash --input-dir D:\dataset --few-shot examples.json --preview-count 3
caption-batch selfcheck
caption-batch serve
```

`--temperature` / `--top-p` / `--seed` は省略すると API 既定（送信しない）。`--no-temperature` で明示的に省略も可。 `--thinking-level`（none|minimal|low|medium|high）、`--media-resolution`（Gemini のみ: low|medium|high）も同様に省略可。

## 自己診断

- `selfcheck.bat` … import + dry-run + API/static の薄いチェック
- `smoke.bat` … `_smoke` に対する dry-run
- `collect-diagnostics.bat` … `diagnostics/diagnostics-*.zip`（秘密値なし）

## 開発メモ

```bat
pip install -e ".[dev]"
pytest
python scripts/selfcheck.py
```

## 旧 Gradio 版について

以前の `app.py` / `setup.bat` / `run_ui.bat` / `requirements.txt` 中心の Gradio 構成は本リポジトリから取り除きました。コアのキャプションロジック（プロバイダ・runner・resume・workers・temperature 等）は維持しています。
