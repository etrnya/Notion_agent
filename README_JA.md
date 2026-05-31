# Notion AI スマートノート & バッチ知識抽出ツール 🤖📝

🌐 **言語切替 (Languages)**: [繁體中文](README.md) | [简体中文](README_ZH.md) | [English](README_EN.md) | **日本語** | [한국어](README_KO.md)

このプロジェクトは、**自然言語対話 (Interactive Agent)** と **大規模バッチ増分処理 (Batch Processor)** を統合した Notion 向けの高度な知識管理ソリューションを提供します。

> 💡 **出典の明記**：
> 本プロジェクトの対話型 Agent モジュールと一部のワークフロー設計は、Shubhamsaboo 氏のオープンソースプロジェクト [awesome-llm-apps/notion_mcp_agent](https://github.com/Shubhamsaboo/awesome-llm-apps/tree/main/notion_mcp_agent) に触発され、作成されました。本プロジェクトでは、この基盤の上で大幅なカスタマイズを加え、大規模バッチ処理およびハイブリッド RAG 知識集約エンジンを追加拡張しました。

---

## 🌟 主な機能

### 1. 大量ノートの自動要約と AI タグ付け (Batch Processor)
数千件のウェブ記事、電子書籍、動画ノートが格納された Notion のソースデータベースに対し、増分バッチ処理を行います：
* **重複防止増分処理**：未処理のページ（`AI已處理` が未チェックのもの）のみを自動的に抽出し、処理完了後にチェックを入れることで、Token の浪費やデータの重複書き込みを防止します。
* **プロパティの構造化分割書き込み**：
  * **「一言要約」**：Notion の **`AI摘要`** プロパティへ自動書き込み。
  * **「3つの主要ナレッジポイント」**：Notion の **`AI知識點`** プロパティへ自動書き込み。
* **空白 URL ページの自動スクレイピング**：URL しかなく本文が空のカード（例：Facebook のシェアなど）を自動検出し、コンテンツを抽出してタイトルを再構築し、AI による要約とタグ付けを実行します。

### 2. 本格的な知識ベース集約と要約記事生成 (Knowledge Synthesizer)
すでに要約とタグ付けが完了した Notion データベースから、複数の記事にまたがるテーマを自動的に分類・統合します：
* **タグのクレンジングと重複排除**：大文字小文字、スペース、重複したタグをクレンジングして意味を整合し、広すぎるカテゴリ（例：`"AI工具"`, `"AI應用"`, `"自動化"` など）をフィルタリングしてテーマを高度に絞り込みます。
* **「深くインスパイアされた」精選記事優先**：`深受啟發`（深くインスパイアされた）プロパティを持つ精選記事を自動検出。**この精選記事を含むテーマを優先的に選択**し、要約時には**その全文を RAG のコアコンテキストとして読み込み**ます。
* **優れた Markdown レイアウトの最適化**：
  * **複数階層ヘッダーの解析**：H1〜H6 の見出しを動的に処理。ハッシュ記号（`#`）を自動的に取り除き、レベル H4〜H6 の見出しを Notion がサポートする H3 (`heading_3`) に安全にマッピングし、適切なフォントサイズで表示します。
  * **装飾テキストスタイルの変換**：Markdown の**太字 (`**`)**、*斜体 (`*`)*、および ``インラインコード`` を正確に Notion のテキストアノテーションに変換し、余分な markdown 記号を表示せずにテキストを美しく強調します。
  * **自動ハイパーリンク変換**：標準的な Markdown 形式のリンク `[Text](URL)` と、文中に現れる**生の URL (HTTP/HTTPS)** を両方キャプチャし、クリック可能な青いハイパーリンクとして Notion に反映します。
  * **引用検証 (Guardrail)**：LLM が生成した参考文献リストを検証し、架空の文献を排除して文中で実際に引用されているソースのみを残し、URL を正確に整合させます。

---

## 📖 設定ガイド (Step-by-Step)

Notion データベースおよび API キーの設定手順は以下の通りです：

### 1. Notion インテグレーション・トークンの取得
1. [Notion Developers インテグレーション管理画面](https://www.notion.so/profile/integrations) を開きます。
2. 右上の **「+ 新しいインテグレーション」** をクリックします。
3. ワークスペースを選択し、名前を `Notion AI Curation Assistant` に設定して **「送信」** をクリックします。
4. 生成された **Secrets** の下にある **Internal Integration Token** をコピーします。これが `NOTION_API_KEY` です。
5. **「インテグレーション機能 (Capabilities)」** で以下の権限がオンになっていることを確認します：
   * `コンテンツを読み取る`
   * `コンテンツを更新する`
   * `コンテンツを挿入する`

### 2. Notion データベース ID の取得
1. 対象の Notion データベースをブラウザで開きます。
2. 右上の **「リンクをコピー」** をクリックします。
3. ワークスペース名を表すスラッシュ `/` の後、クエスチョンマーク `?` の前にある 32 文字の英数字がデータベース ID です。例：`981c349065cd4f92bb0ba358b9e0a56d`。

### 3. Notion でのコネクション追加
1. ブラウザで対象の Notion データベースを開きます。
2. 右上の **`...`** (3つの点) アイコンをクリックします。
3. 下部にある **「コネクションの追加」** を選択します。
4. 作成したインテグレーション（例：`Notion AI Curation Assistant`）を検索して選択し、**「確認」** をクリックします。

### 4. Google Gemini API キーの取得
* 前提として [Google AI Studio](https://aistudio.google.com/) にアクセスし、ログインして **"Get API key"** -> **"Create API key in a new project"** をクリックして作成します。

### 5. Agent Platform (旧 Vertex AI) サービスアカウント JSON 認証情報の設定
GCP サービスアカウントによる本格的な高速呼び出しを行う場合：
1. [Google Cloud Console](https://console.cloud.google.com/) にログインします。
2. **「IAM と管理」** -> **「サービス アカウント」** に移動し、新規作成します。
3. IAM ロールで、**`Vertex AI User`** ロールを検索して割り当てます。
4. サービスアカウントのオプションメニューで **「鍵を管理」** -> **「鍵を追加」** -> **「新しい鍵を作成」** を選択し、**JSON** 形式でダウンロードします。
5. ダウンロードしたファイルを **`gcp-key.json`** として `Notion_agent/` ルートディレクトリに保存します（すでに `.gitignore` に登録されています）。
6. API 切り替え：`.env` で `USE_VERTEX_AI=false` に設定すると、標準の API キーによる実行にフォールバックできます。

---

## 📥 インストールと環境構築

### 1. パッケージのインストール
```powershell
pip install -r requirements.txt
```

### 2. 環境変数の設定
`.env.example` を `.env` にコピーして書き換えます：
```ini
NOTION_API_KEY=ntn_your_notion_token_here
GEMINI_API_KEY=your_gemini_api_key_here
NOTION_DATABASE_ID=your_database_id_here
```

---

## 🎯 クイックコマンド一覧表

| シナリオ (キーワード) | 実行 CLI コマンド | 詳細 & ベストプラクティス |
| :--- | :--- | :--- |
| **データベースへの自動要約・タグ付け** | `python batch_processor.py --limit <件数> --yes` | **増分 AI 抽出**：未処理のページを自動収集し、`AI摘要` と `AI知識點` プロパティを更新。 |
| **集約記事の自動生成** | `python synthesize_knowledge.py --count <件数>` | **本番グレードの RAG 集約**：タグをクレンジングし、精選記事を優先的に読み込んでテーマごとの統合記事を生成。 |
| **空の Facebook/Web ページの修復と抽出** | `python fix_empty_title_and_body_pages.py` | **空ページ修復**：URL はあるが本文が空のカードをスクレイピングし、タイトルと内容を再構築して書き込み。 |
| **GCP JSON 鍵の無効化/有効化** | `.env` で `USE_VERTEX_AI` を修正 | `USE_VERTEX_AI=true` (GCP を優先使用)、`USE_VERTEX_AI=false` (Gemini API キーにフォールバック)。 |
| **確認ドライラン (Notion への書き込みなし)** | `python batch_processor.py --limit 5 --dry-run` | **プレビューモード**：Notion に書き込まずに取得・要約プレビューを表示。 |
| **自然言語による対話型クエリ・管理** | `python notion_mcp_agent.py` | **対話型 Agent**：自然言語を用いて対話形式でデータベースを検索・操作。 |
