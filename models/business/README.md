此目录保存 business 模型工件及其版本/摘要清单。Compose 将此目录只读挂载到
`/app/models/business`；不得放入 evaluation 模型用于业务推荐。

内容推荐模型通过项目根目录的 `python scripts/build_content_model.py` 生成到
`content-genre-v1/`。它只使用批准的电影类型特征，并由清单绑定业务历史评分和
特征文件摘要。
