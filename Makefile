PROJECT_ID := $(shell cd terraform && terraform output -raw project_id 2>/dev/null)
IMAGE_URI  := asia-northeast1-docker.pkg.dev/$(PROJECT_ID)/slack-interface-server/app:latest

.PHONY: up build push

up:  ## Socket Mode でローカル起動
	uv run python local_dev.py

build:  ## linux/amd64 向けに Docker イメージをビルド（M1 Mac 対応）
	docker buildx build --platform linux/amd64 -t $(IMAGE_URI) .

push: build  ## ビルド後 Artifact Registry へ push
	gcloud auth configure-docker asia-northeast1-docker.pkg.dev
	docker push $(IMAGE_URI)
